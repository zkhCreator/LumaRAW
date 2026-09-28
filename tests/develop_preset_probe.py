"""Measure bounded Develop preset reads and sixty-photo partial application.

Inputs: a new isolated work directory and synthetic photo/preset counts. Outputs:
warm in-process service/SQL latency, response bytes and RSS. Targets have heavy
keyword metadata; original images stay undecoded. Setup, IPC, pixels, previews and
desktop interaction are excluded. No hardware timing thresholds or personal state.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import resource

from PIL import Image
import psutil

from library_probe import measure
from lumaraw.model import Recipe
from lumaraw.service import Service


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--photos',type=int,default=10000)
    parser.add_argument('--presets',type=int,default=1000)
    parser.add_argument('--samples',type=int,default=30)
    args=parser.parse_args()
    if not 60<=args.photos<=1000000 or not 30<=args.presets<=100000 or not 1<=args.samples<=1000:
        raise SystemExit('Counts outside probe bounds')
    root=args.work.resolve()
    root.mkdir()
    paths=[]
    for i in range(60):
        path=root/f'{i:02}.png'
        Image.new('RGB',(8,8),'navy').save(path)
        paths.append(path)
    fingerprints=[hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
    s=Service(root/'catalog',presets_root=root/'presets')
    try:
        s.dispatch('queue_control',{'action':'pause'})
        s.dispatch('import_photos',{'paths':list(map(str,paths))})
        with s.catalog() as c,c.db:
            recipe=json.dumps(Recipe(temperature=12,crop='4:5').dict())
            c.db.execute('UPDATE photos SET recipe=?',(recipe,))
            c.db.executemany('INSERT INTO photos(path,name,bytes,mtime,recipe,created) VALUES(?,?,0,0,?,0)',
                ((str(root/'synthetic'/f'{i}.png'),f'{i:08}.png',recipe) for i in range(args.photos-60)))
            parent=None
            for i in range(31):
                name=f'{i:02}'+('海'*118)
                parent=c.db.execute('INSERT INTO keywords(parent_id,name,normalized) VALUES(?,?,?)',(parent,name,name)).lastrowid
            keywords=[]
            for i in range(100):
                name=f'Leaf{i:03}'+('景'*113)
                keywords.append(c.db.execute('INSERT INTO keywords(parent_id,name,normalized) VALUES(?,?,?)',(parent,name,name)).lastrowid)
            c.db.executemany('INSERT INTO keyword_photos VALUES(?,?)',((p,k) for p in range(1,61) for k in keywords))
            c.db.execute('UPDATE photos SET title=?,caption=? WHERE id<=60',('Title '*80,'Caption '*600))
        with s.develop_presets.transaction() as (_,_,db,_):
            db.executemany('INSERT INTO develop_presets VALUES(?,?,?,?,?,?,0,0)',
                ((f'probe-{i}',f'Preset {i:06}',f'preset {i:06}','user',json.dumps({'exposure':1 if i%2 else 0}),1)
                 for i in range(args.presets)))
            s.develop_presets.bump(db)
        report={'platform':platform.platform(),'machine':platform.machine(),
            'memory_gb':round(psutil.virtual_memory().total/1024**3,1),'photos':args.photos,'presets':args.presets+5,
            'targets':60,'keywords_per_target':100,'keyword_depth':32,'image_dimensions':[8,8],
            'cache':'Warm SQLite; no image decoding or LUT assets',
            'scope':'In-process service/SQL; apply includes preset-token reads and captured visual revisions, excluding IPC/preview/UI/setup'}
        for name,params in [('first_page',{}),('last_page',{'offset':args.presets}),('search',{'search':f'Preset {args.presets-1:06}'})]:
            result=s.dispatch('list_develop_presets',params)
            report[name]=measure(lambda params=params:s.dispatch('list_develop_presets',params),args.samples)
            report[name]['response_bytes']=len(json.dumps(result,ensure_ascii=False).encode())
            assert len(result['presets'])<=30 and all('patch' not in row for row in result['presets'])
        def apply(id_):
            state=s.dispatch('list_develop_presets')
            # This bounded revision read models already displayed native targets;
            # full metadata and keyword paths are intentionally not materialized.
            with s.catalog() as c:
                targets=[{'photo_id':r['id'],'expected_revision':r['revision']} for r in
                         c.db.execute('SELECT id,revision FROM photos WHERE id BETWEEN 1 AND 60')]
            return s.dispatch('apply_develop_preset',{'preset_id':id_,'expected_revision':state['revision'],'targets':targets})
        report['first_apply']=measure(lambda:apply('probe-1'),1)
        report['equal_reapply']=measure(lambda:apply('probe-1'),args.samples)
        def cycle():
            apply('probe-0')
            return apply('probe-1')
        report['two_changed_applications']=measure(cycle,args.samples)
        with s.catalog() as c:
            rows=c.db.execute('SELECT recipe,revision,metadata_revision,orientation FROM photos WHERE id<=60').fetchall()
            expected=Recipe(temperature=12,crop='4:5',exposure=1).dict()
            assert all(json.loads(r['recipe'])==expected and r['revision']==1+args.samples*2
                       and r['metadata_revision']==0 and r['orientation']==0 for r in rows)
            assert c.db.execute('SELECT COUNT(*) FROM history').fetchone()[0]==60*min(50,1+args.samples*2)
            assert c.db.execute('SELECT COUNT(*) FROM keyword_photos').fetchone()[0]==6000
        assert [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]==fingerprints
        report['peak_rss_mb']=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024**2 if platform.system()=='Darwin' else 1024),2)
        report['worker_peak_mb']=s.peak
        assert s.peak==0
        (root/'report.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))
    finally:
        s.close()


if __name__=='__main__':
    main()
