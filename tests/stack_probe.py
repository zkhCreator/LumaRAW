"""Measure stack-aware bounded SQL pages in a generated catalog.

Inputs: a new work directory and bounded row/sample counts. Outputs: JSON latency
and peak process RSS. Synthetic rows have no files; no image workers, RAW timing
or desktop latency are included. SQLite is warmed before repeated measurements.
"""
import argparse
import json
from pathlib import Path
import platform
import resource

import psutil

from library_probe import measure
from lumaraw.model import Recipe
from lumaraw.service import Service
from lumaraw.stacks import Stacks


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--rows',type=int,default=10000)
    parser.add_argument('--samples',type=int,default=30)
    args=parser.parse_args()
    if not 120<=args.rows<=1000000 or not 1<=args.samples<=1000:
        raise SystemExit('Counts outside probe bounds')
    root=args.work.resolve()
    if root.exists():raise SystemExit('Choose a new work directory')
    root.mkdir(parents=True)
    s=Service(root/'catalog')
    try:
        s.dispatch('queue_control',{'action':'pause'})
        with s.catalog() as c:
            payload=json.dumps(Recipe().dict())
            with c.db:
                c.db.executemany('INSERT INTO photos(path,name,bytes,mtime,recipe,created,rating) VALUES(?,?,0,0,?,0,?)',
                    ((str(root/'synthetic'/f'{i}.png'),f'{i:08}.png',payload,i%6) for i in range(args.rows)))
                stacks=Stacks(c)
                for start in range(1,args.rows-8,10):
                    stacks.create('folder',str(root/'synthetic'),list(range(start,start+10)))
        report={'platform':platform.platform(),'machine':platform.machine(),
                'memory_gb':round(psutil.virtual_memory().total/1024**3,1),'photos':args.rows,
                'cache':'Warm SQLite; no images or image cache',
                'scope':'In-process service/SQL only; excludes IPC, image work and native UI'}
        def sample(name,params):
            result=s.dispatch('list_photos',params)
            report[name]={'visible_total':result['total'],**measure(lambda:s.dispatch('list_photos',params),args.samples)}
        sample('collapsed',{})
        sample('collapsed_name',{'sort':'name','descending':False})
        sample('collapsed_rating',{'filters':{'rating_min':3}})
        sample('flat_baseline',{'stacked':False})
        with s.catalog() as c:
            with c.db:c.db.execute('UPDATE photo_stacks SET collapsed=0')
        sample('expanded',{})
        sample('expanded_last_page',{'offset':args.rows-60})
        report['peak_rss_mb']=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024**2 if platform.system()=='Darwin' else 1024),2)
        report['worker_peak_mb']=s.peak
        (root/'report.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))
    finally:s.close()


if __name__=='__main__':main()
