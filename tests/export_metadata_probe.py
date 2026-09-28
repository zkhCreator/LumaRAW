"""Measure metadata projection and frozen enqueue cost in large synthetic catalogs.

Inputs: new work directory, photo count and repeat count. Outputs: warm median/p95
service timings and RSS. Every photo has two leaf tags with three synonyms each.
No pixels, files, IPC or native UI are measured; queued jobs stay paused.
"""
import argparse
import json
from pathlib import Path
import platform
import resource
import time

import psutil

from library_probe import measure
from lumaraw.model import Recipe
from lumaraw.service import Service


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--rows',type=int,default=10000)
    parser.add_argument('--samples',type=int,default=30)
    args=parser.parse_args()
    if not 1000<=args.rows<=1000000 or not 1<=args.samples<=1000:
        raise SystemExit('Counts outside probe bounds')
    root=args.work.resolve()
    if root.exists():raise SystemExit('Choose a new work directory')
    root.mkdir(parents=True)
    service=Service(root/'catalog')
    try:
        service.dispatch('queue_control',{'action':'pause'})
        with service.catalog() as c,c.db:
            recipe=json.dumps(Recipe().dict())
            c.db.executemany('INSERT INTO photos(path,name,bytes,mtime,recipe,created,title) VALUES(?,?,0,0,?,0,?)',
                ((str(root/'synthetic'/f'{i:08}.png'),f'{i:08}.png',recipe,f'Photo {i}') for i in range(args.rows)))
            c.db.executemany('INSERT INTO keywords(id,name,normalized) VALUES(?,?,?)',
                ((i+1,f'Root-{i:02}',f'root-{i:02}') for i in range(10)))
            c.db.executemany('INSERT INTO keywords(id,parent_id,name,normalized) VALUES(?,?,?,?)',
                ((i+11,i%10+1,f'Leaf-{i:04}',f'leaf-{i:04}') for i in range(1000)))
            c.db.executemany('INSERT INTO keyword_synonyms VALUES(?,?,?)',
                ((i+11,f'alias-{i}-{j}',f'Alias-{i}-{j}') for i in range(1000) for j in range(3)))
            c.db.executemany('INSERT INTO keyword_photos VALUES(?,?)',
                ((i+1,(i+j)%1000+11) for i in range(args.rows) for j in (0,500)))
        report={'platform':platform.platform(),'machine':platform.machine(),
                'memory_gb':round(psutil.virtual_memory().total/1024**3,1),
                'photos':args.rows,'tags':1010,'assignments':args.rows*2,
                'cache':'Warm SQLite; no photographs',
                'scope':'In-process metadata/SQL only; queued jobs paused; no pixels, IPC or UI'}
        for kind in ('keywords','hierarchy'):
            query={'photo_id':1,'kind':kind,'keyword_hierarchy':True}
            service.dispatch('preview_export_metadata',query)
            report[kind]=measure(lambda query=query:service.dispatch('preview_export_metadata',query),args.samples)
        request=0
        def enqueue(count):
            nonlocal request
            request+=1
            return service.dispatch('enqueue_exports',{'photo_ids':list(range(1,count+1)),
                'destination':str(root/'exports'),'format':'jpeg','request_key':f'batch-{request}',
                'options':{'metadata':'catalog','keyword_hierarchy':True}})
        report['enqueue_60']=measure(lambda:enqueue(60),min(args.samples,5))
        report['enqueue_1000']=measure(lambda:enqueue(1000),min(args.samples,5))
        report['queue_page']=measure(lambda:service.dispatch('list_jobs'),args.samples)
        page=service.dispatch('list_jobs')
        assert len(page['jobs'])==60 and all('metadata_snapshot' not in row for row in page['jobs'])
        assert all(row['export_metadata']['keyword_count']==9 for row in page['jobs'])
        report['public_queue_bytes']=len(json.dumps(page,ensure_ascii=False).encode())
        with service.catalog() as c:
            report['frozen_snapshot_bytes']=c.db.execute('SELECT sum(length(CAST(metadata_snapshot AS BLOB))) FROM jobs').fetchone()[0]
        report['peak_rss_mb']=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024**2 if platform.system()=='Darwin' else 1024),2)
        report['worker_peak_mb']=service.peak
        (root/'report.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))
    finally:
        service.close()


if __name__=='__main__':main()

