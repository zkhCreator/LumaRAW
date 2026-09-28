"""Local JSON transport adapter and CLI for the portable service.

macOS/Linux use a Unix socket in a user-only directory. Windows selects AF_PIPE;
that adapter is implemented but requires Windows integration validation. Wire data
uses send_bytes/recv_bytes JSON, never pickle. Startup and lifetime owner locks
prevent competing brokers. Identity negotiation precedes every domain command;
only a sealed idle handoff preserves pending exports across engine changes.
"""
import argparse
from contextlib import contextmanager, nullcontext
import hashlib
import json
from multiprocessing.connection import Listener, Client
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

from .runtime import engine_identity, valid_identity
from .broker_lifecycle import (BrokerLifecycle, ServiceConnectionError, allow_start,
                               owner_lock, write_state)

MAX_MESSAGE=1024*1024

def default_catalog():
    if sys.platform=='darwin':return Path.home()/'Library/Application Support/LumaRAW Native'
    if os.name=='nt':return Path(os.environ.get('LOCALAPPDATA',Path.home()))/'LumaRAW'
    return Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))/'lumaraw'

def endpoint(root):
    digest=hashlib.sha256(str(Path(root).resolve()).encode()).hexdigest()[:24]
    if os.name=='nt':return rf'\\.\pipe\lumaraw-{digest}','AF_PIPE'
    directory=Path(tempfile.gettempdir())/f'lumaraw-{os.getuid()}'
    if directory.is_symlink():raise RuntimeError('Unsafe IPC directory')
    directory.mkdir(mode=0o700,exist_ok=True)
    st=directory.stat()
    if st.st_uid!=os.getuid() or st.st_mode&0o077:raise RuntimeError('IPC directory must be private to this user')
    return str(directory/(digest+'.sock')),'AF_UNIX'

@contextmanager
def startup_lock(root):
    path=Path(root)/'.broker.lock';path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as stream:
        if os.name=='nt':
            import msvcrt
            stream.seek(0);stream.write(b'0');stream.flush();stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_LOCK,1)
        else:
            import fcntl
            fcntl.flock(stream,fcntl.LOCK_EX)
        try:yield
        finally:
            if os.name=='nt':stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(stream,fcntl.LOCK_UN)

def connect(root,activate=False):
    address,family=endpoint(root)
    try:return Client(address,family=family)
    except (OSError,ConnectionError):pass
    with startup_lock(root):
        try:return Client(address,family=family)
        except (OSError,ConnectionError):pass
        identity=engine_identity()
        allow_start(root,identity,activate)
        if activate:
            write_state(root,{'engine':identity,'phase':'activation'})
        from .service import executable_args
        kwargs={'start_new_session':True} if os.name!='nt' else {'creationflags':subprocess.CREATE_NO_WINDOW}
        subprocess.Popen(executable_args()+['--broker','--catalog',str(root)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**kwargs)
        for _ in range(100):
            time.sleep(.05)
            try:return Client(address,family=family)
            except (OSError,ConnectionError):pass
    raise RuntimeError('Unable to start the local catalog service')

def exchange(conn,request,timeout=620):
    data=json.dumps(request,allow_nan=False).encode()
    if len(data)>MAX_MESSAGE:raise ValueError('Request too large')
    conn.send_bytes(data)
    if not conn.poll(timeout):raise TimeoutError('Service request timed out; its outcome is unknown. Read operation status before retrying.')
    return json.loads(conn.recv_bytes(MAX_MESSAGE))


def call(root,method,params=None):
    params={} if params is None else params
    connection_command=method=='service_connection'
    if connection_command and (not isinstance(params,dict) or set(params)!={'action'} or params['action'] not in ('status','activate')):
        raise ValueError('service_connection requires action: status or activate')
    activate=connection_command and params['action']=='activate'
    identity=engine_identity()
    # Preflight never dispatches the requested mutation to an unknown/old engine.
    # Reconnect only before admission, never after an uncertain command response.
    deadline=time.monotonic()+8
    switching=False
    while True:
        try:
            with connect(root,activate) as conn:
                hello=exchange(conn,{'method':'__broker_info__'},timeout=10)
        except (EOFError,OSError,ConnectionError):
            if not switching or time.monotonic()>deadline:raise
            time.sleep(.05)
            continue
        info=hello.get('result',{}) if hello.get('ok') else {}
        current=info.get('engine')
        if not valid_identity(current):
            raise ServiceConnectionError('An older background service is still using this catalog. Finish its exports, close older LumaRAW windows and agent clients, then reconnect after three minutes. The requested action was not applied.')
        if connection_command and not activate:
            return {'ok':True,'result':{**info,'client_engine':identity,'compatible':current==identity}}
        if info.get('retiring'):
            if time.monotonic()>deadline:
                raise ServiceConnectionError('The background service is switching versions. Reconnect shortly.',True)
            time.sleep(.05)
            continue
        if current != identity:
            if current['generation']>identity['generation'] or current['catalog_version']>identity['catalog_version']:
                raise ServiceConnectionError('A newer LumaRAW engine is using this catalog. Open the newer application; no action was applied.')
            if current['generation']==identity['generation'] and not activate:
                raise ServiceConnectionError('Another build of LumaRAW is using this catalog. Choose Connect with This Version in Settings to switch when it is idle.',True)
            with connect(root) as conn:
                reply=exchange(conn,{'method':'__broker_handoff__','expected':current,
                                     'target':identity,'explicit':activate},timeout=10)
            if not reply.get('ok'):
                return reply
            switching=True
            if time.monotonic()>deadline:
                raise ServiceConnectionError('The background service is switching versions. Reconnect shortly.',True)
            time.sleep(.05)
            continue
        if activate:
            return {'ok':True,'result':{**info,'compatible':True}}
        with connect(root) as conn:
            return exchange(conn,{'method':method,'params':params,'engine':identity})

def serve(root):
    # Acquire before migration or unlinking. Manually starting a second broker
    # cannot steal the endpoint from a live owner.
    with owner_lock(root):
        allow_start(root,engine_identity())
        serve_owned(root)


def serve_owned(root):
    from .service import Service
    address,family=endpoint(root)
    if family=='AF_UNIX':Path(address).unlink(missing_ok=True)
    service=Service(root,identity=engine_identity());listener=Listener(address,family=family)
    lifecycle=BrokerLifecycle(service)
    semaphore=threading.BoundedSemaphore(12)
    def handle(conn):
        request={}
        try:
            with conn:
                if not conn.poll(10):return
                request=json.loads(conn.recv_bytes(MAX_MESSAGE))
                try:
                    control=request.get('method') in ('__broker_info__','__broker_handoff__')
                    gate=nullcontext() if control else lifecycle.admit(request.get('engine'))
                    with gate:
                        try:
                            if request.get('method')=='__broker_info__':
                                result=lifecycle.info()
                            elif request.get('method')=='__broker_handoff__':
                                result=lifecycle.handoff(request.get('expected'),request.get('target'),request.get('explicit') is True)
                            else:
                                result=service.dispatch(request['method'],request.get('params'))
                            response={'ok':True,'result':result}
                        except Exception as e:
                            response={'ok':False,'error':str(e)[:2000],'type':type(e).__name__,
                                      'can_activate':getattr(e,'can_activate',False)}
                        conn.send_bytes(json.dumps(response,ensure_ascii=False,allow_nan=False).encode())
                except Exception as e:
                    conn.send_bytes(json.dumps({'ok':False,'error':str(e)[:2000],'type':type(e).__name__,
                        'can_activate':getattr(e,'can_activate',False)}).encode())
        except (EOFError,OSError,ValueError):pass
        finally:
            # A disconnected requester must not leave an already-sealed broker
            # stuck forever. Its exact target can consume the durable receipt.
            if isinstance(request,dict) and request.get('method')=='__broker_handoff__' and lifecycle.retiring:
                lifecycle.finished.set()
            semaphore.release()
    # A user-owned service exits when idle. Pending work keeps it alive.
    def idle():
        while not service.stopping.is_set():
            if lifecycle.finished.wait(10) or lifecycle.retire_if_idle():
                # Handoff/admission proved no image job or domain command active.
                # The clean receipt is consumed only by its exact target engine.
                service.close();listener.close();os._exit(0)
    threading.Thread(target=idle,daemon=True).start()
    try:
        while True:
            conn=listener.accept();semaphore.acquire();threading.Thread(target=handle,args=(conn,),daemon=True).start()
    finally:listener.close();service.close()

def main():
    parser=argparse.ArgumentParser(description='LumaRAW local service / CLI / MCP')
    parser.add_argument('--catalog',type=Path,default=default_catalog())
    parser.add_argument('--worker',action='store_true');parser.add_argument('--broker',action='store_true');parser.add_argument('--mcp',action='store_true')
    parser.add_argument('method',nargs='?',default='status');parser.add_argument('--params',help='JSON object; omitted: read stdin for commands other than status and recipe_schema')
    args=parser.parse_args()
    if args.worker:
        from .worker import main as worker_main
        worker_main();return
    if args.broker:serve(args.catalog);return
    if args.mcp:
        from .mcp import run
        run(args.catalog);return
    try:
        params=json.loads(args.params) if args.params else (json.loads(sys.stdin.buffer.readline(MAX_MESSAGE+1)) if args.method not in ('status','recipe_schema') else {})
        result=call(args.catalog,args.method,params)
    except Exception as e:result={'ok':False,'error':str(e),'type':type(e).__name__,
                                'can_activate':getattr(e,'can_activate',False)}
    print(json.dumps(result,ensure_ascii=False,allow_nan=False),flush=True)
    if not result['ok']:sys.exit(1)

if __name__=='__main__':main()
