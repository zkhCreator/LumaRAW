"""Disposable adversarial stdio peer for native transport regression only.

Reads framed test requests, writes split/out-of-order/malformed replies or exits
after recording a fake mutation. Its explicit catalog path contains test markers;
it never connects to the real broker or edits photographs.
"""
from concurrent.futures import ThreadPoolExecutor
import argparse
import json
import os
from pathlib import Path
import sys
import threading
import time

p=argparse.ArgumentParser();p.add_argument('--catalog',type=Path,required=True);p.add_argument('--native-client',action='store_true')
args=p.parse_args();args.catalog.mkdir(parents=True,exist_ok=True)
lock=threading.Lock()


def respond(row):
    method=row['method'];params=row['params']
    if method=='slow':time.sleep(.3)
    if method=='lost_mutation':
        with (args.catalog/'mutation-count').open('a') as f:f.write('committed\n')
        os._exit(43)
    result={'id':row['id'],'ok':True,'result':{'pid':os.getpid(),'value':params.get('value','')}}
    if method=='failure':result={'id':row['id'],'ok':False,'error':'Engine busy','can_activate':True}
    payload=json.dumps(result,ensure_ascii=False).encode()+b'\n'
    if method=='malformed':payload=b'not-json\n'
    if method=='unknown':payload=b'{"id":9999999,"ok":true,"result":{}}\n'
    if method=='oversize':payload=b'x'*(1024*1024+1)+b'\n'
    with lock:
        if method=='split':
            for byte in payload:
                sys.stdout.buffer.write(bytes([byte]));sys.stdout.buffer.flush()
        else:sys.stdout.buffer.write(payload);sys.stdout.buffer.flush()


with ThreadPoolExecutor(max_workers=8) as pool:
    for line in sys.stdin.buffer:pool.submit(respond,json.loads(line))
