"""Measure hierarchical collection operations on a generated large catalog.

Inputs: new work directory, synthetic row count and sample count. Outputs: JSON
latency/memory receipts; no real originals or pixel work. Setup inserts fixture
memberships directly; timed operations use the public service commands. Copies
remain in the disposable catalog. No UI/IPC latency or hard timing assertions.
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
    parser.add_argument('--rows',type=int,default=10000)
    parser.add_argument('--samples',type=int,default=30)
    args=parser.parse_args()
    if not 1<=args.rows<=1000000 or not 1<=args.samples<=1000: raise SystemExit('Counts outside probe bounds')
    root=args.work.resolve()
    if root.exists(): raise SystemExit('Choose a new work directory')
    root.mkdir(parents=True)
    service=Service(root/'catalog')
    try:
        service.dispatch('queue_control',{'action':'pause'})
        group=service.dispatch('save_collection',{'name':'Portfolio','kind':'set'})
        albums=[service.dispatch('save_collection',{'name':f'Album {i:02}','kind':'regular','parent_id':group['id']}) for i in range(12)]
        quick=service.dispatch('collection_state')['quick']
        with service.catalog() as c:
            recipe=json.dumps(Recipe().dict())
            c.db.executemany('INSERT INTO photos(path,name,bytes,mtime,recipe,created,rating) VALUES(?,?,?,?,?,?,?)',
                ((str(root/'synthetic'/f'{i}.png'),f'{i:08}.png',0,0,recipe,0,i%6) for i in range(args.rows)))
            c.db.executemany('INSERT INTO collection_photos VALUES(?,?)',
                ((albums[(i-1)%12]['id'],i) for i in range(1,args.rows+1)))
            c.db.execute('INSERT INTO collection_photos SELECT ?,id FROM photos',(quick['id'],));c.db.commit()
        report={'platform':platform.platform(),'machine':platform.machine(),
                'memory_gb':round(psutil.virtual_memory().total/1024**3,1),
                'photos':args.rows,'subtree_nodes':13,'scope':'Synthetic SQLite/service; excludes images, IPC and native UI'}
        report['set_page']=measure(lambda:service.dispatch('list_photos',{'collection_id':group['id']}),args.samples)
        report['children']=measure(lambda:service.dispatch('list_collections',{'parent_id':group['id']}),args.samples)
        report['target_page_state']=measure(lambda:service.dispatch('collection_state',{'photo_ids':list(range(1,min(args.rows,60)+1))}),args.samples)
        report['save_quick']=measure(lambda:service.dispatch('quick_collection',{'action':'save',
            'expected_revision':quick['revision'],'name':'Saved sample'}),3)
        revision=service.dispatch('get_collection',{'collection_id':group['id']})['revision']
        report['duplicate_subtree']=measure(lambda:service.dispatch('duplicate_collection',{
            'collection_id':group['id'],'expected_revision':revision,'name':'Copied sample'}),3)
        report['broker_rss_mb']=round(psutil.Process().memory_info().rss/1024**2,2)
        report['workers_started']=service.peak>0
        (root/'report.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))
    finally:
        service.close()


if __name__=='__main__':
    main()
