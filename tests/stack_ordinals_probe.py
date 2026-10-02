"""Measure true stack ordinals on generated SQL catalogs with no photograph I/O.

Inputs: a new disposable work directory and explicit member counts. Outputs: full
60-row page and isolated ordinal-annotation timing/VM work, reply bytes and sampled
RSS for first/middle/last pages and sparse filters. Positions are intentionally
sparse and negative. Deep pages may count a large prefix once; this is not an
O(1) rank claim. No image processing, IPC or desktop rendering is measured.
"""
import argparse
import json
from pathlib import Path
import platform
import statistics
import threading
import time

import psutil

from lumaraw.catalog import Catalog
from lumaraw.model import Recipe
from lumaraw.stacks import Stacks


def seed(catalog, count):
    recipe = json.dumps(Recipe().dict())
    with catalog.db:
        catalog.db.executemany(
            'INSERT INTO photos(path,name,bytes,mtime,recipe,created,rating) '
            'VALUES(?,?,0,0,?,0,?)',
            ((f'/probe/stack/{i:08}.jpg', f'{i:08}.jpg', recipe,
              5 if i % 100 == 0 else 0) for i in range(1, count + 1)))
        stack_id = catalog.db.execute(
            "INSERT INTO photo_stacks(scope,folder,collapsed,top_id,size) "
            "VALUES('folder','/probe/stack',0,1,?)", (count,)).lastrowid
        catalog.db.executemany(
            "INSERT INTO stack_members(scope,photo_id,stack_id,position) VALUES('folder',?,?,?)",
            ((i, stack_id, i * 3 - count * 2) for i in range(1, count + 1)))


def timed(catalog, function):
    steps = [0]

    def progress():
        steps[0] += 100
        return 0

    catalog.db.set_progress_handler(progress, 100)
    started = time.perf_counter()
    try:
        result = function()
    finally:
        elapsed = (time.perf_counter() - started) * 1000
        catalog.db.set_progress_handler(None, 0)
    return result, elapsed, steps[0]


def summarize(samples):
    return {'first_ms': round(samples[0][0], 3),
            'warm_median_ms': round(statistics.median(s[0] for s in samples[1:]), 3),
            'warm_max_ms': round(max(s[0] for s in samples[1:]), 3),
            'vm_steps': [s[1] for s in samples]}


def measure(catalog, count, label, offset, filters=None):
    expected = list(range(100, count + 1, 100)) if filters else range(1, count + 1)
    expected = list(expected[offset:offset + 60])
    full, ordinal = [], []
    rows = None
    for _ in range(6):
        rows, elapsed, steps = timed(catalog, lambda: catalog.filtered_page(
            offset, filters=filters, sort='imported', descending=False))
        assert [row['id'] for row in rows] == expected
        assert [row['stack_ordinal'] for row in rows] == expected
        full.append((elapsed, steps))
        captured = [dict(row) for row in rows]
        _, elapsed, steps = timed(catalog, lambda: Stacks(catalog).annotate_ordinals(captured, 'folder'))
        assert [row['stack_ordinal'] for row in captured] == expected
        # A generous linear bound rejects 60 repeated full-prefix scans, without
        # making a wall-clock performance promise on other machines.
        assert steps <= count * 20 + 50_000, 'Ordinal work repeated large prefixes'
        ordinal.append((elapsed, steps))
    return {'label': label, 'offset': offset, 'filters': filters,
            'returned': len(rows), 'reply_bytes': len(json.dumps(rows).encode()),
            'page': summarize(full), 'ordinal_only': summarize(ordinal)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--rows', type=int, nargs='+', default=[10000, 100000])
    args = parser.parse_args()
    if any(count < 10000 or count > 1000000 for count in args.rows):
        parser.error('Use 10000 to 1000000 members per generated stack')
    root = args.work.resolve()
    root.mkdir(parents=True, exist_ok=False)
    results = []
    process = psutil.Process()
    for count in args.rows:
        path = root / f'catalog-{count}'
        catalog = Catalog(path)
        seed(catalog, count)
        catalog.close()
        catalog = Catalog(path)
        peak = [process.memory_info().rss / 1024**2]
        stop = threading.Event()

        def sample():
            while not stop.wait(.005):
                peak[0] = max(peak[0], process.memory_info().rss / 1024**2)

        sampler = threading.Thread(target=sample, daemon=True)
        sampler.start()
        try:
            cases = [measure(catalog, count, label, offset) for label, offset in
                     [('first', 0), ('middle', count // 2), ('last', count - 60)]]
            for label, offset in [('sparse-first', 0), ('sparse-last', count // 100 - 60)]:
                cases.append(measure(catalog, count, label, offset, {'rating_min': 5}))
            with catalog.db:
                catalog.db.execute('UPDATE photo_stacks SET collapsed=1')
            cover, elapsed, steps = timed(catalog, lambda: catalog.filtered_page(
                sort='imported', descending=False))
            assert len(cover) == 1 and cover[0]['stack_ordinal'] == 1
            _, ordinal_ms, ordinal_steps = timed(catalog, lambda: Stacks(catalog).annotate_ordinals(cover, 'folder'))
            results.append({'members': count, 'cases': cases,
                            'collapsed': {'page_ms': round(elapsed, 3), 'page_vm_steps': steps,
                                          'ordinal_ms': round(ordinal_ms, 3), 'ordinal_vm_steps': ordinal_steps},
                            'peak_mib': round(peak[0], 3)})
        finally:
            stop.set()
            sampler.join()
            catalog.close()
    report = {'system': platform.platform(), 'memory_gib': round(psutil.virtual_memory().total / 1024**3, 1),
              'cache': 'Fresh SQL connection after seeding; OS caches warm; first request plus five repeats.',
              'scope': 'Synthetic in-process SQL and Python; page excludes total-count/IPC/UI. Ordinal-only excludes page retrieval. RSS samples every 5 ms, excluding seeding.',
              'results': results}
    (root / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
