"""Measure bounded Painter strokes against synthetic large photo catalogs.

Inputs: new work directory, photo/tag counts and warm sample count. Outputs:
service/SQLite timings and RSS for sixty targets with two or one hundred keywords.
Generated 8x8 originals are never developed; remaining catalog rows are synthetic.
Includes shortcut/target revision reads, excludes setup, IPC and desktop latency.
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
    if not 1000<=args.rows<=1000000 or not 1<=args.samples<=1000:raise SystemExit('Counts outside probe bounds')
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
            recipe=json.dumps(Recipe().dict())
            c.db.executemany('INSERT INTO photos(path,name,bytes,mtime,recipe,created) VALUES(?,?,?,?,?,?)',
                ((str(root/'synthetic'/f'{i}.png'),f'{i:08}.png',0,0,recipe,0) for i in range(args.rows-60)))
            c.db.executemany('INSERT INTO keywords(name,normalized) VALUES(?,?)',
                ((f'Tag {i:06}',f'tag {i:06}') for i in range(args.rows)))
            c.db.execute('UPDATE keyword_state SET revision=revision+1')
        report={'platform':platform.platform(),'machine':platform.machine(),
            'memory_gb':round(psutil.virtual_memory().total/1024**3,1),'photos':args.rows,'tags':args.rows,
            'stroke_targets':60,'generated_image_dimensions':[8,8],'cache':'Warm SQLite',
            'scope':'In-process service/SQL including captured shortcut and metadata revision reads; no IPC, pixels or UI'}
        def configure(count):
            state=s.dispatch('get_keyword_shortcut')
            return s.dispatch('set_keyword_shortcut',{'keyword_ids':list(range(1,count+1)),'expected_revision':state['revision']})
        def stroke(kind='keywords',erase=False):
            params={'kind':kind}
            if kind=='keywords':params.update(erase=erase,expected_shortcut_revision=s.dispatch('get_keyword_shortcut')['revision'])
            else:params['value']=4
            with s.catalog() as c:
                params['targets']=[{'photo_id':r[0],'expected_metadata_revision':r[1]} for r in c.db.execute('SELECT id,metadata_revision FROM photos WHERE id<=60 ORDER BY id')]
            return s.dispatch('paint_library',params)
        for count in (2,100):
            state=configure(count)
            report[f'shortcut_{count}']=measure(lambda:s.dispatch('get_keyword_shortcut'),args.samples)
            report[f'shortcut_{count}']['response_bytes']=len(json.dumps(state,ensure_ascii=False).encode())
            report[f'first_add_{count}']=measure(stroke,1)
            report[f'repeat_add_{count}']=measure(stroke,args.samples)
            def cycle():stroke(erase=True);stroke()
            report[f'erase_and_add_{count}']=measure(cycle,args.samples)
            with s.catalog() as c:
                assert c.db.execute('SELECT COUNT(*) FROM keyword_photos').fetchone()[0]==60*count
            stroke(erase=True)
        report['rating_60']=measure(lambda:stroke('rating'),args.samples)
        with s.catalog() as c:
            assert c.db.execute('SELECT COUNT(*) FROM photos WHERE rating=4').fetchone()[0]==60
            assert c.db.execute('SELECT COUNT(*) FROM keyword_photos').fetchone()[0]==0
        report['peak_rss_mb']=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024**2 if platform.system()=='Darwin' else 1024),2)
        report['worker_peak_mb']=s.peak
        assert s.peak==0
        (root/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    finally:s.close()


if __name__=='__main__':main()
