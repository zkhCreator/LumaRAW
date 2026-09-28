"""Measure catalog folder maintenance and bounded navigation on synthetic rows.

Input: a new work directory and row count. Output: warm service/SQLite timings,
metadata-only insertion cost and peak RSS. Paths do not exist; no originals, EXIF,
pixel workers, IPC or native UI are measured. Hierarchy and counts use real
production triggers instead of a separate benchmark-only folder index.
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
        service.dispatch('queue_control', {'action': 'pause'})
        started = time.perf_counter()
        with service.catalog() as catalog:
            recipe = json.dumps(Recipe().dict())
            def rows():
                for index in range(args.rows):
                    folder = root / 'synthetic'
                    if index:
                        folder = folder / f'year-{index % 10:02}' / f'shoot-{index % 1000:04}'
                    yield str(folder / f'{index:08}.png'), f'{index:08}.png', recipe, index % 6
            with catalog.db:
                catalog.db.executemany('INSERT INTO photos(path,name,bytes,mtime,recipe,created,rating) '
                                       'VALUES(?,?,0,0,?,0,?)', rows())
        insertion_ms = (time.perf_counter() - started) * 1000
        folder = service.dispatch('get_folder', {'photo_id': 1})
        leaf = service.dispatch('get_folder', {'photo_id': 2})
        assert folder['total_count'] == args.rows
        report = {
            'platform': platform.platform(), 'machine': platform.machine(),
            'memory_gb': round(psutil.virtual_memory().total / 1024**3, 1),
            'photos': args.rows, 'leaf_folders': min(1000,args.rows-1), 'cache': 'Warm SQLite; no photographs',
            'scope': 'In-process service/SQL; excludes file import, EXIF, IPC, pixels and native UI',
            'synthetic_insert_ms': round(insertion_ms, 3),
        }
        for name, method, params in (
            ('roots', 'list_folders', {}),
            ('children', 'list_folders', {'parent_id': folder['id']}),
            ('folder_search', 'list_folders', {'search': 'shoot-'}),
            ('all_descendant_photos', 'list_photos', {'folder_id': folder['id']}),
            ('descendant_rating_filter', 'list_photos', {'folder_id': folder['id'], 'filters': {'rating_min': 3}}),
            ('direct_leaf_photos', 'list_photos', {'folder_id': leaf['id'], 'include_subfolders': False}),
            ('deep_photo_page', 'list_photos', {'folder_id': folder['id'], 'offset': args.rows - 60}),
            ('photo_location', 'get_folder', {'photo_id': 2}),
        ):
            service.dispatch(method, params)
            report[name] = measure(lambda method=method, params=params: service.dispatch(method, params), args.samples)
        report['peak_rss_mb'] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss /
            (1024**2 if platform.system() == 'Darwin' else 1024), 2)
        report['worker_peak_mb'] = service.peak
        (root / 'report.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
    finally:
        service.close()


if __name__ == '__main__':
    main()
