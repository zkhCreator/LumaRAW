"""Measure hierarchical keyword lookup and rename on synthetic catalog rows.

Inputs: new work directory, photo count and warm sample count. Outputs: service /
SQLite timings and peak RSS. No images, pixels, IPC, file import or desktop timing.
Assignments use production tables/triggers; each photo has two distinct leaf tags.
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
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--rows', type=int, default=10000)
    parser.add_argument('--samples', type=int, default=30)
    args = parser.parse_args()
    if not 120 <= args.rows <= 1000000 or not 1 <= args.samples <= 1000:
        raise SystemExit('Counts outside probe bounds')
    root = args.work.resolve()
    if root.exists():
        raise SystemExit('Choose a new work directory')
    root.mkdir(parents=True)
    service = Service(root / 'catalog')
    try:
        service.dispatch('queue_control', {'action':'pause'})
        started = time.perf_counter()
        with service.catalog() as c:
            recipe = json.dumps(Recipe().dict())
            with c.db:
                c.db.executemany('INSERT INTO photos(path,name,bytes,mtime,recipe,created,rating) VALUES(?,?,0,0,?,0,?)',
                    ((str(root/'synthetic'/f'{i:08}.png'), f'{i:08}.png', recipe, i%6) for i in range(args.rows)))
                c.db.executemany('INSERT INTO keywords(id,name,normalized) VALUES(?,?,?)',
                                ((i+1, f'Root-{i:02}', f'root-{i:02}') for i in range(10)))
                c.db.executemany('INSERT INTO keywords(id,parent_id,name,normalized) VALUES(?,?,?,?)',
                                ((i+11, i%10+1, f'Leaf-{i:04}', f'leaf-{i:04}') for i in range(1000)))
                c.db.executemany('INSERT INTO keyword_photos VALUES(?,?)',
                                ((i+1, (i+j)%1000+11) for i in range(args.rows) for j in (0,500)))
        report = {'platform':platform.platform(), 'machine':platform.machine(),
            'memory_gb':round(psutil.virtual_memory().total/1024**3, 1), 'photos':args.rows,
            'tags':1010, 'assignments':args.rows*2, 'cache':'Warm SQLite; no photographs',
            'scope':'In-process service/SQL; excludes file import, EXIF, IPC, pixels and native UI',
            'synthetic_insert_ms':round((time.perf_counter()-started)*1000, 3)}
        for name, method, params in (
            ('roots', 'list_keywords', {}),
            ('children_selection', 'list_keywords', {'parent_id':1, 'photo_ids':list(range(1,61))}),
            ('search', 'list_keywords', {'search':'leaf-'}),
            ('tagged_photos', 'list_photos', {'filters':{'keyword_id':1}}),
            ('deep_tagged_page', 'list_photos', {'filters':{'keyword_id':1}, 'offset':args.rows//10-60}),
            ('keyword_text', 'list_photos', {'filters':{'keyword':'root-00'}}),
            ('tagged_photo_details', 'get_photo', {'photo_id':1}),
        ):
            service.dispatch(method, params)
            report[name] = measure(lambda method=method, params=params:service.dispatch(method, params), args.samples)
        rename_count = 0
        def rename():
            nonlocal rename_count
            rename_count += 1
            revision = service.dispatch('library_state')['keyword_revision']
            return service.dispatch('save_keyword', {'keyword_id':1, 'name':f'Renamed-{rename_count}', 'expected_revision':revision})
        report['rename_parent'] = measure(rename, min(args.samples, 5))
        report['peak_rss_mb'] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss /
                                    (1024**2 if platform.system() == 'Darwin' else 1024), 2)
        report['worker_peak_mb'] = service.peak
        (root/'report.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
    finally:
        service.close()


if __name__ == '__main__':
    main()
