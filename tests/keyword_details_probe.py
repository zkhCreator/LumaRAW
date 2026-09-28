"""Measure bounded full-photo keywords and identity editing in synthetic catalogs.

Inputs: a new work directory, photo count and warm sample count. Outputs: service
median/p95, serialized response bytes and RSS. One photo has 100 maximal Unicode
paths; other rows start with two ordinary tags. No pixels, IPC or desktop timing.
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
        with service.catalog() as c,c.db:
            recipe=json.dumps(Recipe().dict())
            c.db.executemany('INSERT INTO photos(path,name,bytes,mtime,recipe,created) VALUES(?,?,0,0,?,0)',
                ((str(root/'synthetic'/f'{i:08}.png'),f'{i:08}.png',recipe) for i in range(args.rows)))
            c.db.executemany('INSERT INTO keywords(id,name,normalized) VALUES(?,?,?)',
                ((i+1,f'Root-{i:02}',f'root-{i:02}') for i in range(10)))
            c.db.executemany('INSERT INTO keywords(id,parent_id,name,normalized) VALUES(?,?,?,?)',
                ((i+11,i%10+1,f'Leaf-{i:04}',f'leaf-{i:04}') for i in range(1000)))
            c.db.executemany('INSERT INTO keyword_photos VALUES(?,?)',
                ((i+1,(i+j)%1000+11) for i in range(args.rows) for j in (0,500)))
            parent=None
            for i in range(31):
                name=str(i)+'🌊'*118
                parent=c.db.execute('INSERT INTO keywords(parent_id,name,normalized) VALUES(?,?,?)',(parent,name,name)).lastrowid
            ids=[]
            for i in range(100):
                name=str(i)+'🌊'*118
                ids.append(c.db.execute('INSERT INTO keywords(parent_id,name,normalized) VALUES(?,?,?)',(parent,name,name)).lastrowid)
            c.db.execute('DELETE FROM keyword_photos WHERE photo_id=1')
            c.db.executemany('INSERT INTO keyword_photos VALUES(1,?)',((id_,) for id_ in ids))
        report={'platform':platform.platform(),'machine':platform.machine(),
            'memory_gb':round(psutil.virtual_memory().total/1024**3,1),'photos':args.rows,
            'tags':1141,'initial_assignments':args.rows*2+98,'deep_photo_paths':100,'depth':32,
            'cache':'Warm SQLite; no photographs','scope':'In-process service/SQL; no pixels, IPC or UI'}
        for name,method,params in (
            ('ordinary_photo','get_photo',{'photo_id':2}),
            ('deep_photo','get_photo',{'photo_id':1}),
            ('deep_first_page','get_photo_keywords',{'photo_id':1,'expected_metadata_revision':0}),
            ('deep_last_page','get_photo_keywords',{'photo_id':1,'expected_metadata_revision':0,'offset':80}),
            ('selected_choices','keyword_choices',{'keyword_ids':ids}),
            ('search_choices','keyword_choices',{'search':'Leaf-'})):
            result=service.dispatch(method,params)
            report[name]=measure(lambda method=method,params=params:service.dispatch(method,params),args.samples)
            report[name]['response_bytes']=len(json.dumps({'ok':True,'result':result},ensure_ascii=False).encode())
        iteration=0
        def replace_batch():
            nonlocal iteration
            iteration+=1
            with service.catalog() as c:
                targets=[{'photo_id':row[0],'expected_metadata_revision':row[1]} for row in
                    c.db.execute('SELECT id,metadata_revision FROM photos WHERE id<=60 ORDER BY id')]
            return service.dispatch('edit_metadata',{'targets':targets,'patch':{'keyword_ids':ids,'title':str(iteration)}})
        report['replace_60_with_revision_read']=measure(replace_batch,min(args.samples,5))
        report['peak_rss_mb']=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024**2 if platform.system()=='Darwin' else 1024),2)
        report['worker_peak_mb']=service.peak
        assert report['deep_photo']['response_bytes']<32768 and service.peak==0
        (root/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    finally:service.close()


if __name__=='__main__':main()
