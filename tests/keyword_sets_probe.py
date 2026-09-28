"""Measure bounded preset reads and sixty-photo keyword application.

Inputs: explicit new work directory and synthetic vocabulary/preset counts.
Outputs: warm service/SQLite timings, response sizes and peak RSS. Sixty tiny
generated images are metadata targets only; no processing, IPC or desktop timing.
Preset storage is isolated from the user's preferences. Setup is not timed.
"""
import argparse
import json
from pathlib import Path
import platform
import resource

from PIL import Image
import psutil

from library_probe import measure
from lumaraw.service import Service


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--tags',type=int,default=10000)
    parser.add_argument('--sets',type=int,default=1000)
    parser.add_argument('--samples',type=int,default=30)
    args=parser.parse_args()
    if not 1000<=args.tags<=1000000 or not 30<=args.sets<=100000 or not 1<=args.samples<=1000:
        raise SystemExit('Counts outside probe bounds')
    root=args.work.resolve()
    if root.exists():raise SystemExit('Choose a new work directory')
    root.mkdir(parents=True)
    paths=[]
    for i in range(60):
        path=root/f'photo-{i:02}.png';Image.new('RGB',(8,8),'navy').save(path);paths.append(str(path))
    s=Service(root/'catalog',presets_root=root/'presets')
    try:
        s.dispatch('import_photos',{'paths':paths})
        with s.catalog() as c,c.db:
            c.db.executemany('INSERT INTO keywords(name,normalized) VALUES(?,?)',
                ((f'Tag {i:06}',f'tag {i:06}') for i in range(args.tags)))
            c.db.execute('UPDATE keyword_state SET revision=revision+1')
        with s.keyword_sets.shared() as db:
            db.executemany('INSERT INTO keyword_sets VALUES(?,?,?,?)',
                ((str(i),f'Set {i:06}',f'set {i:06}',json.dumps([f'Tag {args.tags-1:06}']+['']*8)) for i in range(args.sets)))
            db.execute("UPDATE keyword_set_state SET revision=revision+1,selected='0'")
        report={'platform':platform.platform(),'machine':platform.machine(),
            'memory_gb':round(psutil.virtual_memory().total/1024**3,1),'ordinary_tags':args.tags,
            'keyword_sets':args.sets,'photos':60,'image_dimensions':[8,8],
            'cache':'Warm SQLite; generated images remain undecoded',
            'scope':'In-process service/SQL, including captured state/revision reads; no IPC, pixels or UI'}
        for name,params in (('preset_first_page',{}),('preset_last_page',{'offset':args.sets-1})):
            result=s.dispatch('list_keyword_sets',params)
            report[name]=measure(lambda params=params:s.dispatch('list_keyword_sets',params),args.samples)
            report[name]['response_bytes']=len(json.dumps(result,ensure_ascii=False).encode())
        def apply():
            state=s.dispatch('list_keyword_sets')
            with s.catalog() as c:
                targets=[{'photo_id':r[0],'expected_metadata_revision':r[1]} for r in c.db.execute('SELECT id,metadata_revision FROM photos ORDER BY id')]
            return s.dispatch('apply_keyword_set',{'slot':1,'targets':targets,'expected_revision':state['revision']})
        first=apply()
        assert len(first['updated'])==60
        report['repeat_apply_60']=measure(apply,args.samples)
        current=s.dispatch('list_keyword_sets')
        s.dispatch('keyword_set_action',{'action':'select','set_id':'recent','expected_revision':current['revision']})
        report['recent_page']=measure(lambda:s.dispatch('list_keyword_sets'),args.samples)
        with s.catalog() as c:
            assert c.db.execute('SELECT COUNT(*) FROM keyword_photos').fetchone()[0]==60
            assert c.db.execute('SELECT COUNT(*) FROM keyword_recent').fetchone()[0]==1
        report['peak_rss_mb']=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024**2 if platform.system()=='Darwin' else 1024),2)
        report['worker_peak_mb']=s.peak
        assert s.peak==0
        (root/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    finally:s.close()


if __name__=='__main__':main()
