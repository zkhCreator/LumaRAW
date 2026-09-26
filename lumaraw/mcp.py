"""MCP 2025-11-25 stdio adapter over the same catalog broker as the desktop app.

Inputs: newline-delimited JSON-RPC 2.0. Outputs: protocol replies only on stdout.
No arbitrary shell, file-read or network tool. Tool errors are isError results;
invalid RPC envelopes are JSON-RPC errors. Supported handshake versions are
explicit; no HTTP/auth implementation is claimed. Calls are synchronous and
exports return durable job IDs immediately for polling and cancellation.
"""
import argparse
import json
import sys
from .api import TOOLS
from .bridge import call, default_catalog, MAX_MESSAGE

VERSIONS=('2025-11-25','2025-06-18','2025-03-26','2024-11-05')

def run(root,source=None,sink=None):
    source=source or sys.stdin;sink=sink or sys.stdout;initialized=False;ready=False
    def emit(value):sink.write(json.dumps(value,ensure_ascii=False,allow_nan=False)+'\n');sink.flush()
    while True:
        line=source.readline(MAX_MESSAGE+1)
        if not line:break
        id_=None
        try:
            if len(line.encode())>MAX_MESSAGE:raise ValueError('Request too large')
            request=json.loads(line)
            if not isinstance(request,dict) or request.get('jsonrpc')!='2.0' or not isinstance(request.get('method'),str):
                emit({'jsonrpc':'2.0','id':None,'error':{'code':-32600,'message':'Invalid request'}});continue
            id_=request.get('id');method=request['method'];params=request.get('params',{})
            if 'id' not in request:
                if method=='notifications/initialized' and initialized:ready=True
                continue
            if type(id_) not in (int,str):
                emit({'jsonrpc':'2.0','id':None,'error':{'code':-32600,'message':'Invalid id'}});continue
            if not isinstance(params,dict):
                emit({'jsonrpc':'2.0','id':id_,'error':{'code':-32602,'message':'Invalid params'}});continue
            result=None;error=None
            if method=='initialize':
                if initialized:error=(-32600,'Already initialized')
                elif not isinstance(params.get('clientInfo'),dict) or not isinstance(params.get('capabilities'),dict) or not isinstance(params.get('protocolVersion'),str):error=(-32602,'Invalid initialize params')
                else:
                    initialized=True
                    result={'protocolVersion':params['protocolVersion'] if params['protocolVersion'] in VERSIONS else VERSIONS[0],
                        'capabilities':{'tools':{'listChanged':False}},'serverInfo':{'name':'lumaraw','version':'0.4.1'},
                        'instructions':'Local non-destructive RAW editor. Read get_photo before editing; pass expected_revision. Exports return job IDs. Check list_jobs for final output. Original files are read-only.'}
            elif method=='ping':result={}
            elif not ready:error=(-32002,'Initialize and send notifications/initialized first')
            elif method=='tools/list':result={'tools':[{**t,'name':'lumaraw_'+name} for name,t in TOOLS.items()]}
            elif method=='tools/call':
                name=params.get('name','');name=name.removeprefix('lumaraw_') if isinstance(name,str) else ''
                if name not in TOOLS:error=(-32602,'Unknown tool')
                else:
                    try:response=call(root,name,params.get('arguments',{}))
                    except Exception as e:response={'ok':False,'error':str(e),'type':type(e).__name__}
                    payload=response.get('result',response)
                    result={'content':[{'type':'text','text':json.dumps(payload,ensure_ascii=False)}],'isError':not response.get('ok',False)}
                    if response.get('ok'):result['structuredContent']=payload
            else:error=(-32601,'Method not found')
            emit({'jsonrpc':'2.0','id':id_,**({'error':{'code':error[0],'message':error[1]}} if error else {'result':result})})
        except (ValueError,TypeError) as e:emit({'jsonrpc':'2.0','id':id_,'error':{'code':-32700,'message':'Parse error: '+str(e)[:200]}})

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--catalog',default=default_catalog());args=parser.parse_args();run(args.catalog)
if __name__=='__main__':main()
