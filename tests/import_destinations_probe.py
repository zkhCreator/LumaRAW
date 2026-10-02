"""Measure indexed Copy destination pages over generated staged SQL originals.

Inputs: a new disposable work directory and explicit row counts. Outputs: first
and warm page latency, SQLite VM steps, response bytes and sampled process RSS.
One original occupies each folder to stress directory cardinality. A sparse-new
phase retains many duplicate-only groups to check eligible-page index bounds.
No real sources, pixels, filesystem scan, broker IPC or desktop input are measured.
"""
import argparse
import json
from pathlib import Path
import statistics
import threading
import time

import psutil

from lumaraw.catalog import Catalog
from lumaraw.import_destinations import ImportDestinations
from lumaraw.import_review import ImportReview


def seed(catalog, count):
    with catalog.db:
        catalog.db.execute(
            "INSERT INTO import_plans(state,phase,include_subfolders,file_count,selected_count,created) "
            "VALUES('ready','files',1,?,?,1)", (count, count))
        catalog.db.execute(
            "INSERT INTO import_copy_plans(plan_id,destination,destination_identity,organization,subfolder,roots,owner) "
            "VALUES(1,'/probe/destination','{}','source','','[]','probe')")
        catalog.db.executemany(
            "INSERT INTO import_files(plan_id,path,name,extension,state,selected,destination_directory) "
            "VALUES(1,?,?,'jpg','new',1,?)",
            ((f'/probe/source/f{i:08}/photo.jpg', 'photo.jpg', f'f{i:08}')
             for i in range(count)))


def measure(catalog, after, expected):
    domain = ImportDestinations(catalog)
    revision = catalog.db.execute('SELECT revision FROM import_plans WHERE id=1').fetchone()[0]
    runs, vm = [], []
    for _ in range(6):
        steps = [0]
        def progress():
            steps[0] += 100
            return 0
        catalog.db.set_progress_handler(progress, 100)
        started = time.perf_counter()
        try:
            result = domain.get(1, revision, after)
        finally:
            elapsed = (time.perf_counter() - started) * 1000
            catalog.db.set_progress_handler(None, 0)
        assert [row['relative_path'] for row in result['items']] == expected
        assert all(row['photo_count'] == 1 for row in result['items'])
        assert all(row['path'] == '/probe/destination/' + row['relative_path']
                   for row in result['items'])
        assert max(steps) < 20_000, 'Directory paging performed catalog-scale VM work'
        runs.append(elapsed)
        vm.append(steps[0])
    return {'after': after, 'first_ms': runs[0],
            'warm_median_ms': statistics.median(runs[1:]), 'warm_max_ms': max(runs[1:]),
            'vm_steps': vm, 'reply_bytes': len(json.dumps(result).encode()),
            'returned': len(result['items']), 'next_after': result['next_after']}


def selection_probe(catalog, count):
    """Measure ordinary one-row uncheck/recheck without scanning every selection."""
    review = ImportReview(catalog)
    samples = []
    for selected in (False, True, False, True, False, True):
        revision = review.row(1)['revision']
        steps = [0]
        def progress():
            steps[0] += 100
            return 0
        catalog.db.set_progress_handler(progress, 100)
        started = time.perf_counter()
        try:
            result = review.select(1, revision, selected, item_ids=[count // 2])
        finally:
            elapsed = (time.perf_counter() - started) * 1000
            catalog.db.set_progress_handler(None, 0)
        assert result['plan']['selected_count'] == count - (not selected)
        assert steps[0] < 20_000, 'Single-item selection scanned the full review'
        samples.append({'selected': selected, 'ms': elapsed, 'vm_steps': steps[0]})
    return samples


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--rows', type=int, nargs='+', default=[10000, 100000])
    args = parser.parse_args()
    if any(count < 120 for count in args.rows):
        parser.error('Use at least 120 originals per catalog')
    args.work.mkdir(parents=True, exist_ok=False)
    reports = []
    for count in args.rows:
        root = args.work / str(count)
        catalog = Catalog(root)
        seed(catalog, count)
        catalog.close()
        catalog = Catalog(root)
        process = psutil.Process()
        peak = [process.memory_info().rss]
        stop = threading.Event()
        def sample():
            while not stop.wait(.005):
                peak[0] = max(peak[0], process.memory_info().rss)
        sampler = threading.Thread(target=sample, daemon=True)
        sampler.start()
        pages = []
        try:
            for offset in (0, count // 2, count - 60):
                after = f'f{offset - 1:08}' if offset else None
                pages.append(measure(catalog, after,
                                     [f'f{i:08}' for i in range(offset, offset + 60)]))
            selections = selection_probe(catalog, count)
            # Keep ninety-nine percent of folders in the aggregate table but
            # outside the skip-duplicates eligible index. Selection counts are
            # updated here because the probe deliberately bypasses service writes.
            with catalog.db:
                catalog.db.execute("UPDATE import_files SET state='duplicate' WHERE (id-1)%100!=0")
                catalog.db.execute(
                    "UPDATE import_plans SET selected_count=(SELECT count(*) FROM import_files "
                    "WHERE plan_id=1 AND state='new') WHERE id=1")
            sparse = measure(catalog, None, [f'f{i:08}' for i in range(0, count, 100)][:60])
            with catalog.db:
                catalog.db.execute('UPDATE import_plans SET skip_duplicates=0,selected_count=? WHERE id=1', (count,))
            duplicate_page = measure(catalog, f'f{count - 61:08}',
                                     [f'f{i:08}' for i in range(count - 60, count)])
        finally:
            peak[0] = max(peak[0], process.memory_info().rss)
            stop.set()
            sampler.join()
            catalog.close()
        reports.append({'originals': count, 'distinct_folders': count, 'pages': pages,
                        'single_item_selection': selections,
                        'sparse_new_page': sparse, 'duplicates_included_last_page': duplicate_page,
                        'sampled_peak_mb': peak[0] / 1024**2, 'sample_interval_ms': 5})
    report = {'results': reports, 'fixtures': 'generated SQLite rows only',
              'cache': 'new SQLite connection; OS cache warm from seeding',
              'pixel_workers': 0, 'desktop_ui': 'NOT_VERIFIED'}
    (args.work / 'report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
