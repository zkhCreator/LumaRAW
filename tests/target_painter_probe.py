"""Measure target-collection strokes without photo-detail materialization.

Inputs: a new isolated work directory, synthetic catalog size and sample count.
Outputs: warm service/SQLite latency and RSS, with sixty generated 8x8 originals.
Targets carry one hundred deep Unicode keyword paths and descriptive metadata.
No pixels, personal presets, IPC or desktop latency; setup is excluded. Run the
same probe before/after a change rather than asserting hardware timing thresholds.
"""
import argparse
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
    parser.add_argument('--rows',type=int,default=10000)
    parser.add_argument('--samples',type=int,default=30)
    args=parser.parse_args()
    if not 1000<=args.rows<=1000000 or not 1<=args.samples<=1000:
        raise SystemExit('Counts outside probe bounds')
    root=args.work.resolve()
    root.mkdir()
    paths=[]
    for i in range(60):
        path=root/f'{i:02}.png'
        Image.new('RGB',(8,8),'navy').save(path)
        paths.append(str(path))
    s=Service(root/'catalog',presets_root=root/'presets')
    try:
        s.dispatch('import_photos',{'paths':paths})
        with s.catalog() as c,c.db:
            recipe=json.dumps(Recipe().dict())
            c.db.executemany('INSERT INTO photos(path,name,bytes,mtime,recipe,created) VALUES(?,?,?,?,?,?)',
                ((str(root/'synthetic'/f'{i}.png'),f'{i:08}.png',0,0,recipe,0) for i in range(args.rows-60)))
            parent=None
            for i in range(31):
                name=f'{i:02}'+('海'*118)
                parent=c.db.execute('INSERT INTO keywords(parent_id,name,normalized) VALUES(?,?,?)',(parent,name,name)).lastrowid
            keyword_ids=[]
            for i in range(100):
                name=f'Leaf{i:03}'+('景'*113)
                keyword_ids.append(c.db.execute('INSERT INTO keywords(parent_id,name,normalized) VALUES(?,?,?)',(parent,name,name)).lastrowid)
            c.db.executemany('INSERT INTO keyword_photos VALUES(?,?)',((p,k) for p in range(1,61) for k in keyword_ids))
            c.db.execute('UPDATE photos SET title=?,caption=? WHERE id<=60',('Title '*80,'Caption '*600))
        photo_ids=list(range(1,61))
        def stroke(action):
            state=s.dispatch('collection_state',{'photo_ids':photo_ids})
            return s.dispatch('target_membership',{'collection_id':state['target']['id'],
                'expected_state_revision':state['revision'],'expected_revision':state['target']['revision'],
                'photo_ids':photo_ids,'action':action})
        report={'platform':platform.platform(),'machine':platform.machine(),
            'memory_gb':round(psutil.virtual_memory().total/1024**3,1),'photos':args.rows,
            'targets':60,'keywords_per_target':100,'keyword_depth':32,'image_dimensions':[8,8],
            'scope':'Warm in-process service/SQL including target state reads; no setup, IPC, pixels or desktop UI'}
        report['first_add']=measure(lambda:stroke('add'),1)
        report['repeat_add']=measure(lambda:stroke('add'),args.samples)
        def cycle():
            stroke('remove')
            return stroke('add')
        report['remove_and_add']=measure(cycle,args.samples)
        state=s.dispatch('collection_state',{'photo_ids':photo_ids})
        assert set(state['members'])==set(photo_ids)
        report['state_bytes']=len(json.dumps(state).encode())
        with s.catalog() as c:
            assert c.db.execute('SELECT SUM(revision),SUM(metadata_revision) FROM photos').fetchone()[:]==(0,0)
            assert c.db.execute('SELECT COUNT(*) FROM keyword_photos').fetchone()[0]==6000
        report['peak_rss_mb']=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024**2 if platform.system()=='Darwin' else 1024),2)
        report['worker_peak_mb']=s.peak
        assert s.peak==0
        (root/'report.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))
    finally:
        s.close()


if __name__=='__main__':
    main()
