"""Measure bounded export-preset pages at synthetic shared-store sizes.

Inputs: a new work directory and one or more row counts. Outputs: first-call,
five warm-call, reply-size, separate SQLite VM/query-plan and sampled-RSS data.
Timing includes in-process Service dispatch, token reads and SQLite connection /
transaction setup; it excludes process IPC, UI, seed work and cold-disk behavior.
No photos or export workers are created.
"""
import argparse
import json
import platform
import sqlite3
import statistics
import threading
import time
from pathlib import Path

import psutil

from lumaraw.service import Service


def measure(operation, process):
    baseline = process.memory_info().rss
    peak = [baseline]
    stopped = threading.Event()

    def sample_rss():
        while not stopped.wait(0.005):
            peak[0] = max(peak[0], process.memory_info().rss)

    sampler = threading.Thread(target=sample_rss, daemon=True)
    sampler.start()
    started = time.perf_counter()
    first = operation()
    first_ms = (time.perf_counter() - started) * 1000
    warm_ms = []
    for _ in range(5):
        started = time.perf_counter()
        result = operation()
        warm_ms.append((time.perf_counter() - started) * 1000)
    stopped.set()
    sampler.join()
    peak[0] = max(peak[0], process.memory_info().rss)
    return first, {
        'first_ms': round(first_ms, 3),
        'warm_ms': [round(value, 3) for value in warm_ms],
        'warm_median_ms': round(statistics.median(warm_ms), 3),
        'baseline_rss_mb': round(baseline / 1024**2, 2),
        'sampled_peak_rss_mb': round(peak[0] / 1024**2, 2),
        'sampled_rss_delta_mb': round(max(0, peak[0] - baseline) / 1024**2, 2),
    }


def vm_steps(db, sql, params=()):
    count = [0]

    def progress():
        count[0] += 100
        return 0

    db.set_progress_handler(progress, 100)
    try:
        db.execute(sql, params).fetchall()
    finally:
        db.set_progress_handler(None, 0)
    return count[0]


def measure_size(work, row_count):
    case = work / f'rows-{row_count}'
    case.mkdir()
    preset_root = case / 'presets'
    service = Service(case / 'catalog', presets_root=preset_root)
    service.dispatch('queue_control', {'action': 'pause'})
    try:
        service.dispatch('list_export_presets')
        settings = json.dumps({
            'format': 'jpeg',
            'options': {
                'space': 'srgb', 'max_edge': 0, 'quality': 96,
                'output_sharpen': 0, 'name': '{stem}-Luma-{seq}',
                'priority': 0, 'metadata': 'catalog', 'keyword_hierarchy': False,
            },
            'destination': None,
        }, separators=(',', ':'))
        store_path = preset_root / 'export' / 'presets.sqlite'
        with service.export_presets.transaction() as (_, _, db, local):
            if local:
                raise AssertionError('fresh probe store unexpectedly defaults to catalog-local')
            db.executemany(
                'INSERT INTO export_presets(id,name,normalized,settings) VALUES(?,?,?,?)',
                ((f'probe-{index:06d}', f'Preset {index:06d}', f'preset {index:06d}', settings)
                 for index in range(row_count)),
            )
            service.export_presets.bump(db)

        last_page_offset = max(0, ((row_count - 1) // 30) * 30)
        sparse_search = f'Preset {row_count - 1:06d}'
        queries = {
            'first_page_and_total': {'offset': 0},
            'deep_page_and_total': {'offset': row_count + 30},
            'sparse_search_and_total': {'search': sparse_search, 'offset': 0},
        }
        process = psutil.Process()
        report = {'rows': row_count, 'page_size': 30, 'queries': {},
                  'cache_state': 'SQLite/OS warm after seeding; cold disk not measured'}
        for name, params in queries.items():
            result, timing = measure(
                lambda params=params: service.dispatch('list_export_presets', params), process)
            assert len(result['presets']) <= 30
            assert all(set(row) == {'id', 'name'} for row in result['presets'])
            timing.update(total=result['total'], offset=result['offset'],
                          returned=len(result['presets']),
                          reply_bytes=len(json.dumps(result, separators=(',', ':')).encode('utf-8')))
            report['queries'][name] = timing
        assert report['queries']['deep_page_and_total']['offset'] == last_page_offset
        assert report['queries']['sparse_search_and_total']['total'] == 1

        with sqlite3.connect(store_path) as db:
            sql = {
                'count': ('SELECT COUNT(*) FROM export_presets', ()),
                'sparse_search_count': ('SELECT COUNT(*) FROM export_presets WHERE instr(normalized,?)>0',
                                        (sparse_search.casefold(),)),
                'first_page': ('SELECT id,name FROM export_presets ORDER BY normalized,id LIMIT 30 OFFSET 0', ()),
                'deep_page': ('SELECT id,name FROM export_presets ORDER BY normalized,id LIMIT 30 OFFSET ?',
                              (last_page_offset,)),
                'sparse_search': ('SELECT id,name FROM export_presets WHERE instr(normalized,?)>0 '
                                  'ORDER BY normalized,id LIMIT 30 OFFSET 0', (sparse_search.casefold(),)),
            }
            report['sqlite_vm_steps'] = {
                name: vm_steps(db, sql_text, params) for name, (sql_text, params) in sql.items()
            }
            report['query_plans'] = {
                name: [row[3] for row in db.execute('EXPLAIN QUERY PLAN ' + sql_text, params)]
                for name, (sql_text, params) in sql.items()
            }
        return report
    finally:
        service.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--rows', type=int, nargs='+', default=[10000, 100000])
    args = parser.parse_args()
    if args.work.exists():
        raise SystemExit('Choose a new work directory')
    if not args.rows or any(not 1 <= count <= 100000 for count in args.rows):
        raise SystemExit('Each row count must be between 1 and 100000')
    work = args.work.resolve()
    work.mkdir(parents=True)
    report = {
        'platform': platform.platform(), 'machine': platform.machine(),
        'scope': 'In-process Service + SQLite; includes token/catalog/shared connection setup, excludes IPC/UI/seed work',
        'rss_note': 'RSS is sampled every 5 ms per query; baseline may include memory retained from an earlier size in this process',
        'sizes': [measure_size(work, count) for count in args.rows],
        'vm_step_granularity': 100,
        'vm_step_note': 'SQLite VM work is counted in 100-op progress-handler intervals; zero means fewer than 100 ops',
    }
    (work / 'report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
