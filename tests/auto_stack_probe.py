"""Measure source-wide auto-stack planning and replacement on synthetic rows.

Inputs: a new work directory, row count and sample count. Outputs: warm SQLite
service timings and peak RSS. No real files, EXIF reads, image workers, IPC or
desktop latency are measured. Fixture clocks form ten-photo bursts; a separate
case joins the entire source to expose oversized-group replacement costs.
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
    folder = root / 'synthetic'
    try:
        service.dispatch('queue_control', {'action': 'pause'})
        album = service.dispatch('save_collection', {'name': 'All synthetic', 'kind': 'regular'})
        with service.catalog() as catalog:
            recipe = json.dumps(Recipe().dict())
            with catalog.db:
                catalog.db.executemany(
                    'INSERT INTO photos(path,name,bytes,mtime,recipe,created,taken_us,capture_clock) '
                    "VALUES(?,?,0,0,?,0,?,'camera')",
                    ((str(folder / f'{i}.png'), f'{i:08}.png', recipe,
                      (i // 10) * 2000000 + (i % 10) * 100000) for i in range(args.rows)))
                catalog.db.execute('INSERT INTO collection_photos SELECT ?,id FROM photos', (album['id'],))
        report = {
            'platform': platform.platform(), 'machine': platform.machine(),
            'memory_gb': round(psutil.virtual_memory().total / 1024**3, 1),
            'photos': args.rows, 'cache': 'Warm SQLite; no images or image cache',
            'scope': 'In-process service/SQL only; excludes EXIF reads, IPC, pixels and native UI',
        }

        def preview(params):
            result = service.dispatch('preview_auto_stack', params)
            assert result['photos'] == args.rows and len(result['examples']) <= 20
            return result

        def replace(params):
            plan = preview(params)
            result = service.dispatch('apply_auto_stack', {**params, 'token': plan['token']})
            assert result['applied'] and result['stacks'] == plan['stacks']

        for label, source in (('folder', {'folder': str(folder)}), ('collection', {'collection_id': album['id']})):
            params = {**source, 'seconds': 1}
            first = preview(params)
            report[label + '_preview'] = {'stacks': first['stacks'], **measure(lambda: preview(params), args.samples)}
            replace(params)
            report[label + '_replace_including_preview'] = measure(lambda: replace(params), 3)
        large = {'folder': str(folder), 'seconds': 3600}
        replace(large)
        assert preview(large)['stacks'] == 1
        report['one_large_stack_replace_including_preview'] = measure(lambda: replace(large), 3)
        page = service.dispatch('list_photos')
        assert page['total'] == 1 and len(page['photos']) == 1
        report['peak_rss_mb'] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss /
                                      (1024**2 if platform.system() == 'Darwin' else 1024), 2)
        report['worker_peak_mb'] = service.peak
        (root / 'report.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
    finally:
        service.close()


if __name__ == '__main__':
    main()
