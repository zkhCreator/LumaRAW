"""Compare one-shot CLI and persistent native relay on the same packaged engine.

Inputs: an explicit engine, new work directory and bounded sample count. Outputs:
first/warm command latency and relay RSS with generated read-only photographs.
No desktop timing, pixel-processing benchmark or personal catalog is implied.
Every command retains normal broker identity negotiation.
"""
import argparse
import json
from pathlib import Path
import platform
import select
import subprocess
import time

from PIL import Image
import psutil


def summary(values):
    ordered=sorted(values)
    return {'samples':len(values),'median_ms':round(ordered[len(ordered)//2],3),
            'p95_ms':round(ordered[int((len(ordered)-1)*.95)],3)}


def main():
    p=argparse.ArgumentParser();p.add_argument('--engine',type=Path,required=True)
    p.add_argument('--work',type=Path,required=True);p.add_argument('--samples',type=int,default=30)
    args=p.parse_args();assert 5<=args.samples<=1000
    root=args.work.resolve();root.mkdir(parents=True,exist_ok=False)
    engine=str(args.engine.resolve());catalog=root/'catalog'
    launches=[]
    def cli(method,params=None):
        start=time.perf_counter()
        process=subprocess.Popen([engine,'--catalog',str(catalog),method],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        out,err=process.communicate(json.dumps(params or {})+'\n',timeout=30)
        result=json.loads(out);assert process.returncode==0 and result['ok'],(result,err)
        launches.append(process.pid)
        return result['result'],(time.perf_counter()-start)*1000
    _,cold=cli('queue_control',{'action':'pause'})
    photo=root/'fixture.png';Image.new('RGB',(160,100),'navy').save(photo)
    original=photo.read_bytes()
    cli('import_photos',{'paths':[str(photo)]})
    start=time.perf_counter()
    relay=subprocess.Popen([engine,'--catalog',str(catalog),'--native-client'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    number=0
    def persistent(method,params=None):
        nonlocal number
        number+=1;begin=time.perf_counter()
        relay.stdin.write(json.dumps({'id':number,'method':method,'params':params or {}}).encode()+b'\n');relay.stdin.flush()
        assert select.select([relay.stdout],[],[],30)[0],'Relay timed out'
        result=json.loads(relay.stdout.readline());assert result['id']==number and result['ok'],result
        return result['result'],(time.perf_counter()-begin)*1000
    try:
        persistent('status');relay_first=(time.perf_counter()-start)*1000
        results={}
        for method,params in [('status',{}),('get_photo',{'photo_id':1})]:
            once=[];warm=[]
            for _ in range(args.samples):
                left,a=cli(method,params);right,b=persistent(method,params)
                if method=='get_photo':assert left==right
                else:assert left['photos']==right['photos']==1
                once.append(a);warm.append(b)
            results[method]={'one_shot':summary(once),'persistent':summary(warm)}
        assert photo.read_bytes()==original
        report={'platform':platform.platform(),'memory_gib':round(psutil.virtual_memory().total/1024**3,1),
            'scope':'Sequential warm negotiated commands, same engine/catalog; excludes pixels and desktop rendering',
            'cold_cli_and_broker_ms':round(cold,3),'relay_first_on_warm_broker_ms':round(relay_first,3),
            'relay_processes':1,'one_shot_launches':len(launches),'relay_rss_mib':round(psutil.Process(relay.pid).memory_info().rss/1024**2,2),
            'results':results,'original_unchanged':True}
        (root/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
    finally:
        relay.stdin.close();relay.wait(timeout=30);relay.stdout.close()


if __name__=='__main__':main()
