"""Measure broker identity negotiation and full CLI startup on an empty catalog.

Inputs: an explicit engine, new work directory and sample count. Outputs: timing
and broker RSS receipts. The raw RPC baseline omits only identity negotiation;
both paths use the same server and status command. No image or desktop timing.
"""
import argparse
import json
from multiprocessing.connection import Client
from pathlib import Path
import platform
import subprocess

import psutil

from library_probe import measure
from lumaraw.bridge import endpoint, exchange


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--engine',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=30)
    args=parser.parse_args()
    if not 1<=args.samples<=1000:raise SystemExit('Samples outside probe bounds')
    root=args.work.resolve()
    if root.exists():raise SystemExit('Choose a new work directory')
    root.mkdir(parents=True);catalog=root/'catalog'
    def cli(method,params=None):
        result=subprocess.run([str(args.engine.resolve()),'--catalog',str(catalog),method],
            input=json.dumps(params or {})+'\n',capture_output=True,text=True,check=True)
        value=json.loads(result.stdout);assert value['ok'];return value['result']
    info=cli('service_connection',{'action':'status'})
    address,family=endpoint(catalog)
    def single():
        with Client(address,family=family) as conn:
            result=exchange(conn,{'method':'status','engine':info['engine']})
            assert result['ok']
    def negotiated():
        with Client(address,family=family) as conn:
            hello=exchange(conn,{'method':'__broker_info__'})
            assert hello['result']['engine']==info['engine']
        single()
    try:
        report={'platform':platform.platform(),'machine':platform.machine(),
            'memory_gb':round(psutil.virtual_memory().total/1024**3,1),
            'catalog_rows':0,'cache':'Warm broker, no image caches/workers',
            'scope':'Same-engine status IPC and CLI launch; excludes images and native UI'}
        report['single_rpc']=measure(single,args.samples)
        report['negotiated_rpc']=measure(negotiated,args.samples)
        report['full_cli']=measure(lambda:cli('status'),args.samples)
        report['broker_rss_mb']=round(psutil.Process(info['pid']).memory_info().rss/1024**2,2)
        report['worker_peak_mb']=cli('status')['peak_mb']
        (root/'report.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))
    finally:
        process=psutil.Process(info['pid'])
        if str(catalog) in process.cmdline():process.terminate();process.wait(timeout=5)


if __name__=='__main__':main()
