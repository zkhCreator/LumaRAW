"""Measure bounded virtual-copy workflows in a generated large catalog.

Input: new work directory and explicit counts. Output: JSON service latency/RSS.
Fixture rows stand in for files; no pixel decoding, worker or desktop latency.
Warm SQLite samples retain created copies and use real public command validation.
"""
import argparse
import json
from pathlib import Path
import platform

import psutil

from library_probe import measure
from lumaraw.model import Recipe
from lumaraw.service import Service


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--sources',type=int,default=10000)
    parser.add_argument('--samples',type=int,default=30)
    args=parser.parse_args()
    if not 60<=args.sources<=1000000 or not 1<=args.samples<=1000:
        raise SystemExit('Counts outside probe bounds')
    root=args.work.resolve()
    if root.exists(): raise SystemExit('Choose a new work directory')
    root.mkdir(parents=True)
    s=Service(root/'catalog')
    try:
        s.dispatch('queue_control',{'action':'pause'})
        with s.catalog() as c:
            recipe=json.dumps(Recipe().dict())
            c.db.executemany('INSERT INTO photos(path,name,bytes,mtime,recipe,created) VALUES(?,?,?,?,?,?)',
                ((str(root/'synthetic'/f'{i}.png'),f'{i:08}.png',0,0,recipe,0) for i in range(args.sources)))
            c.db.execute('INSERT INTO photos(path,name,bytes,mtime,recipe,created,source_id,is_virtual,copy_name) '
                "SELECT path,name,bytes,mtime,recipe,created,source_id,1,'Copy 1' FROM photos WHERE is_virtual=0")
            c.db.execute('UPDATE photo_sources SET next_copy=2,revision=1');c.db.commit()
        report={'platform':platform.platform(),'machine':platform.machine(),
                'memory_gb':round(psutil.virtual_memory().total/1024**3,1),
                'source_count':args.sources,'initial_photo_count':args.sources*2,
                'cache':'Warm SQLite; no image cache or worker',
                'scope':'Synthetic service/SQLite only; excludes IPC, images and desktop UI'}
        ids=list(range(1,61))
        report['page_60']=measure(lambda:s.dispatch('list_photos'),args.samples)
        report['virtual_filter']=measure(lambda:s.dispatch('list_photos',{'filters':{'is_virtual':True}}),args.samples)
        report['source_family']=measure(lambda:s.dispatch('list_photos',{'filters':{'source_id':1}}),args.samples)
        report['capture_60']=measure(lambda:s.dispatch('photo_summaries',{'photo_ids':ids}),args.samples)
        targets=[{'photo_id':id_,'expected_revision':0,'expected_metadata_revision':0} for id_ in ids]
        report['create_60']=measure(lambda:s.dispatch('create_virtual_copies',{'targets':targets}),args.samples)
        report['final_photo_count']=s.dispatch('status')['photos']
        report['broker_rss_mb']=round(psutil.Process().memory_info().rss/1024**2,2)
        report['worker_peak_mb']=s.peak
        (root/'report.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))
    finally:
        s.close()


if __name__=='__main__': main()
