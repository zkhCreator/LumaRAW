"""Local JSON transport adapter and CLI for the portable service.

macOS/Linux use a Unix socket in a user-only directory. Windows selects AF_PIPE;
that adapter is implemented but requires Windows integration validation. Wire data
uses send_bytes/recv_bytes JSON, never pickle. Startup is serialized with an OS
file lock. A broker owns each catalog; all clients share its worker and queue.
"""
import argparse
from contextlib import contextmanager
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

def connect(root):
    address,family=endpoint(root)
    try:return Client(address,family=family)
    except (OSError,ConnectionError):pass
    with startup_lock(root):
        try:return Client(address,family=family)
        except (OSError,ConnectionError):pass
        from .service import executable_args
        kwargs={'start_new_session':True} if os.name!='nt' else {'creationflags':subprocess.CREATE_NO_WINDOW}
        subprocess.Popen(executable_args()+['--broker','--catalog',str(root)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**kwargs)
        for _ in range(100):
            time.sleep(.05)
            try:return Client(address,family=family)
            except (OSError,ConnectionError):pass
    raise RuntimeError('Unable to start the local catalog service')

def call(root,method,params=None):
    data=json.dumps({'method':method,'params':params or {}},allow_nan=False).encode()
    if len(data)>MAX_MESSAGE:raise ValueError('Request too large')
    with connect(root) as conn:
        conn.send_bytes(data)
        if not conn.poll(620):raise TimeoutError('Service request timed out; check export status with list_jobs')
        return json.loads(conn.recv_bytes(MAX_MESSAGE))

def serve(root):
    from .service import Service
    address,family=endpoint(root)
    if family=='AF_UNIX':Path(address).unlink(missing_ok=True)
    service=Service(root);listener=Listener(address,family=family)
    semaphore=threading.BoundedSemaphore(12)
    def handle(conn):
        try:
            with conn:
                if not conn.poll(10):return
                request=json.loads(conn.recv_bytes(MAX_MESSAGE))
                try:
                    result=service.dispatch(request['method'],request.get('params'))
                    response={'ok':True,'result':result}
                except Exception as e:response={'ok':False,'error':str(e)[:2000],'type':type(e).__name__}
                conn.send_bytes(json.dumps(response,ensure_ascii=False,allow_nan=False).encode())
        except (EOFError,OSError,ValueError):pass
        finally:semaphore.release()
    # A user-owned service exits when idle. Pending work keeps it alive.
    def idle():
        while not service.stopping.wait(10):
            if time.monotonic()-service.last_activity>180 and not service.active:
                with service.catalog() as c:pending=c.job_counts().get('pending',0)
                if not pending:
                    listener.close();service.close();os._exit(0)
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
    except Exception as e:result={'ok':False,'error':str(e),'type':type(e).__name__}
    print(json.dumps(result,ensure_ascii=False,allow_nan=False),flush=True)
    if not result['ok']:sys.exit(1)

if __name__=='__main__':main()
