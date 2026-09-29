"""Measure last-import membership and bounded pages in a synthetic catalog.

Inputs: a new work directory and explicit catalog/batch sizes. Outputs: warm SQL
and in-process service timing samples, RSS and response sizes with assertions.
No photo decoding, filesystem import, IPC, desktop timing or user catalog access.
Setup is excluded; replacement measures one atomic membership transaction only.
"""
import argparse
import json
from pathlib import Path
import platform
import resource

import psutil

from library_probe import measure
from lumaraw.model import Recipe
from lumaraw.previous_import import replace
from lumaraw.service import Service


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--work',type=Path,required=True)
    p.add_argument('--photos',type=int,default=100000)
    p.add_argument('--batch',type=int,default=10000)
    p.add_argument('--samples',type=int,default=30)
    args=p.parse_args()
    if not 60<=args.batch<args.photos<=1000000 or not 1<=args.samples<=1000:
        raise SystemExit('Counts outside probe bounds')
    root=args.work.resolve();root.mkdir()
    s=Service(root/'catalog',presets_root=root/'presets')
    try:
        s.dispatch('queue_control',{'action':'pause'})
        with s.catalog() as c,c.db:
            recipe=json.dumps(Recipe().dict())
            c.db.executemany('INSERT INTO photos(path,name,bytes,mtime,recipe,created,rating,taken) VALUES(?,?,1,0,?,0,?,?)',
                ((str(root/'synthetic'/f'{i:08}.png'),f'{i:08}.png',recipe,i%6,i*1000) for i in range(args.photos)))
            replace(c.db,'SELECT source_id FROM photos',(),'fixture',args.photos)
        def capture():
            with s.catalog() as c,c.db:
                c.db.execute('BEGIN IMMEDIATE')
                replace(c.db,'SELECT source_id FROM photos WHERE id>?',(args.photos-args.batch,),'fixture',args.batch)
        report={'platform':platform.platform(),'machine':platform.machine(),'memory_gb':round(psutil.virtual_memory().total/1024**3,1),
                'catalog_photos':args.photos,'previous_import_sources':args.batch,'cache':'Warm SQLite',
                'scope':'Synthetic in-process SQL/service; excludes setup, file verification, decoding, IPC and UI'}
        report['replace_membership']=measure(capture,1)
        for name,options in [('first_page',{}),('last_page',{'offset':args.batch}),('name_sort',{'sort':'name'}),
                             ('capture_sort',{'sort':'captured'}),('rating_filter',{'filters':{'rating_min':5}})]:
            params={'mode':'previous_import',**options}
            result=s.dispatch('list_photos',params)
            assert len(result['photos'])<=60 and all(row['id']>args.photos-args.batch for row in result['photos'])
            assert all('recipe' not in row and 'metadata' not in row for row in result['photos'])
            if name in ('first_page','last_page'):assert result['total']==args.batch
            report[name]=measure(lambda:s.dispatch('list_photos',params),args.samples)
            report[name]['response_bytes']=len(json.dumps(result).encode())
        report['source_poll']=measure(lambda:s.dispatch('library_state'),args.samples)
        with s.catalog() as c:
            assert c.db.execute('SELECT count(*) FROM previous_import_sources').fetchone()[0]==args.batch
            report['membership_query_plan']=[tuple(row) for row in c.db.execute('EXPLAIN QUERY PLAN SELECT id FROM photos WHERE source_id IN (SELECT source_id FROM previous_import_sources)')]
        report['peak_process_rss_mb']=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024**2,2)
        report['image_worker_peak_mb']=s.peak
        (root/'report.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))
    finally:s.close()


if __name__=='__main__':main()
