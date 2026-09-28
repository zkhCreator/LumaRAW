"""Measure bounded metadata preset pages and sixty-photo catalog-only application.

Inputs: new work directory and synthetic catalog/preset counts. Outputs: warm
service/SQL latency, wire bytes and RSS with heavy IPTC/keyword targets. Setup,
IPC, image decoding and desktop latency are excluded; originals remain read-only.
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
    root=args.work.resolve();root.mkdir()
    paths=[]
    for i in range(60):
        path=root/f'{i:02}.png';Image.new('RGB',(8,8),'navy').save(path);paths.append(path)
    fingerprints=[hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
    s=Service(root/'catalog',presets_root=root/'presets')
    try:
        s.dispatch('queue_control',{'action':'pause'})
        s.dispatch('import_photos',{'paths':list(map(str,paths))})
        iptc={'instructions':'海'*5000,'alt_text':'景'*5000,'extended_description':'山'*5000,'rights_usage_terms':'水'*5000}
        with s.catalog() as c,c.db:
            recipe=json.dumps(Recipe(exposure=1.25).dict())
            c.db.execute('UPDATE photos SET recipe=?,iptc=?,orientation=3',(recipe,json.dumps(iptc,ensure_ascii=False)))
            c.db.executemany('INSERT INTO photos(path,name,bytes,mtime,recipe,created) VALUES(?,?,0,0,?,0)',
                ((str(root/'synthetic'/f'{i}.png'),f'{i:08}.png',recipe) for i in range(args.photos-60)))
            parent=None
            for i in range(31):
                name=f'{i:02}'+('海'*118)
                parent=c.db.execute('INSERT INTO keywords(parent_id,name,normalized) VALUES(?,?,?)',(parent,name,name)).lastrowid
            keywords=[]
            for i in range(99):
                name=f'Leaf{i:03}'+('景'*113)
                keywords.append(c.db.execute('INSERT INTO keywords(parent_id,name,normalized) VALUES(?,?,?)',(parent,name,name)).lastrowid)
            c.db.executemany('INSERT INTO keyword_photos VALUES(?,?)',((p,k) for p in range(1,61) for k in keywords))
        with s.metadata_presets.transaction() as (_,_,db,_):
            db.executemany('INSERT INTO metadata_presets VALUES(?,?,?,?,3)',
                ((f'probe-{i}',f'Preset {i:06}',f'preset {i:06}',json.dumps({'title':str(i%2),
                 'iptc':{'city':'City '+str(i%2)},'keywords':['Probe addition']})) for i in range(args.presets)))
            s.metadata_presets.bump(db)
        report={'platform':platform.platform(),'machine':platform.machine(),
            'memory_gb':round(psutil.virtual_memory().total/1024**3,1),'photos':args.photos,'presets':args.presets,
            'targets':60,'keywords_per_target_before':99,'keywords_per_target_after':100,'keyword_depth':32,
            'iptc_utf8_bytes_before':len(json.dumps(iptc,ensure_ascii=False).encode()),'image_dimensions':[8,8],
            'cache':'Warm SQLite; no image decoding',
            'scope':'In-process service/SQL, including token and target revision reads; excludes setup, IPC, pixels and UI'}
        for name,params in [('first_page',{}),('last_page',{'offset':args.presets}),('search',{'search':f'Preset {args.presets-1:06}'})]:
            result=s.dispatch('list_metadata_presets',params)
            report[name]=measure(lambda params=params:s.dispatch('list_metadata_presets',params),args.samples)
            report[name]['response_bytes']=len(json.dumps(result).encode())
            assert len(result['presets'])<=30 and all('patch' not in row for row in result['presets'])
        def apply(id_):
            state=s.dispatch('list_metadata_presets')
            with s.catalog() as c:
                targets=[{'photo_id':r['id'],'expected_metadata_revision':r['metadata_revision'],'expected_rating':r['rating']}
                         for r in c.db.execute('SELECT id,metadata_revision,rating FROM photos WHERE id BETWEEN 1 AND 60')]
            return s.dispatch('apply_metadata_preset',{'preset_id':id_,'expected_revision':state['revision'],'targets':targets})
        report['first_apply']=measure(lambda:apply('probe-1'),1)
        report['equal_reapply']=measure(lambda:apply('probe-1'),args.samples)
        def cycle():
            apply('probe-0');return apply('probe-1')
        report['two_changed_applications']=measure(cycle,args.samples)
        with s.catalog() as c:
            rows=c.db.execute('SELECT recipe,revision,metadata_revision,orientation,iptc,title FROM photos WHERE id<=60').fetchall()
            assert all(r['recipe']==recipe and r['revision']==0 and r['metadata_revision']==1+args.samples*2 and
                       r['orientation']==3 and json.loads(r['iptc'])=={**iptc,'city':'City 1'} and r['title']=='1' for r in rows)
            assert c.db.execute('SELECT COUNT(*) FROM history').fetchone()[0]==0
            assert c.db.execute('SELECT COUNT(*) FROM keyword_photos').fetchone()[0]==6000
        assert [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]==fingerprints
        report['peak_rss_mb']=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024**2 if platform.system()=='Darwin' else 1024),2)
        report['worker_peak_mb']=s.peak;assert s.peak==0
        (root/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    finally:s.close()


if __name__=='__main__':main()
