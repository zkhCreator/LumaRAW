"""Measure bounded vocabulary pages with a large synthetic keyword dictionary.

Inputs: a new work directory, ordinary tag count and warm sample count. Outputs:
service/SQL timings, response sizes and peak RSS. Sixty-one deep tags have maximal
Unicode paths and thirty synonyms each. No photographs, pixels, IPC or UI timing.
"""
import argparse
import json
from pathlib import Path
import platform
import resource

import psutil

from library_probe import measure
from lumaraw.service import Service


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--tags',type=int,default=10000)
    parser.add_argument('--samples',type=int,default=30)
    args=parser.parse_args()
    if not 1000<=args.tags<=1000000 or not 1<=args.samples<=1000:
        raise SystemExit('Counts outside probe bounds')
    root=args.work.resolve()
    if root.exists():raise SystemExit('Choose a new work directory')
    root.mkdir(parents=True)
    s=Service(root/'catalog')
    try:
        with s.catalog() as c,c.db:
            c.db.executemany('INSERT INTO keywords(name,normalized) VALUES(?,?)',
                ((f'Tag {i:06}',f'tag {i:06}') for i in range(args.tags)))
            parent=None
            for i in range(31):
                name=f'{i:02}'+('🌊'*118)
                parent=c.db.execute('INSERT INTO keywords(name,normalized,parent_id) VALUES(?,?,?)',(name,name,parent)).lastrowid
            ids=[]
            for i in range(61):
                name=f'{i:02}'+('🌴'*118)
                id_=c.db.execute('INSERT INTO keywords(name,normalized,parent_id) VALUES(?,?,?)',(name,name,parent)).lastrowid
                ids.append(id_)
                c.db.executemany('INSERT INTO keyword_synonyms VALUES(?,?,?)',
                    ((id_,f'{j:02}'+('🐳'*118),f'{j:02}'+('🐳'*118)) for j in range(30)))
            c.db.execute('UPDATE keyword_state SET revision=revision+1')
        report={'platform':platform.platform(),'machine':platform.machine(),
            'memory_gb':round(psutil.virtual_memory().total/1024**3,1),'ordinary_tags':args.tags,
            'total_tags':args.tags+92,'deep_leaves':61,'depth':32,'synonyms_per_leaf':30,
            'cache':'Warm SQLite; no photographs','scope':'In-process service/SQL; no pixels, IPC or UI'}
        for name,method,params in (
            ('roots','list_keywords',{}),
            ('deep_children','list_keywords',{'parent_id':parent}),
            ('deep_last_page','list_keywords',{'parent_id':parent,'offset':60}),
            ('synonym_search','list_keywords',{'search':'🐳'}),
            ('complete_detail','get_keyword',{'keyword_id':ids[0],'expected_revision':1})):
            result=s.dispatch(method,params)
            report[name]=measure(lambda method=method,params=params:s.dispatch(method,params),args.samples)
            report[name]['response_bytes']=len(json.dumps({'ok':True,'result':result},ensure_ascii=False).encode())
            assert report[name]['response_bytes']<512*1024
        report['peak_rss_mb']=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024**2 if platform.system()=='Darwin' else 1024),2)
        report['worker_peak_mb']=s.peak
        assert s.peak==0
        (root/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    finally:s.close()


if __name__=='__main__':main()
