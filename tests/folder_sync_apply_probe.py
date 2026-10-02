"""Measure Folder Sync's metadata apply path over synthetic SQLite originals.

Inputs: a new work directory and catalog row counts. Outputs: one first and five
warm direct-domain apply timings for unchanged rows and ten changed existing
stat rows, plus catalog correctness and RSS observations. SQLite photo/source
and staged-plan rows are real, but all original paths are deliberately absent.
This isolates FolderSync.apply's metadata transaction: it bypasses filesystem
discovery/stat, the scan runner, IPC, image decoding/pixels, and desktop UI. It
is not an end-to-end or photographic-performance benchmark.
"""
import argparse
import json
import os
import platform
import resource
import statistics
import time
from pathlib import Path

from lumaraw.catalog import Catalog
from lumaraw.folder_sync import FolderSync
from lumaraw.folders import Folders
from lumaraw.model import Recipe
from lumaraw.runtime import engine_identity


BASE_BYTES = 4096
BASE_MTIME = 1_790_000_000
CHANGED_ROWS = 10
WARM_SAMPLES = 5


def open_catalog(path):
    return Catalog(path)


def seed_catalog(catalog_path, work, rows):
    """Bulk-seed actual catalog/source rows without creating original files."""
    photo_dir = work / 'synthetic-originals-not-created' / f'rows-{rows}' / 'Photos'
    assert not photo_dir.exists()
    catalog = open_catalog(catalog_path)
    started = time.perf_counter()
    db = catalog.db
    recipe = json.dumps(Recipe().dict(), separators=(',', ':'))
    with db:
        # Keep seeding out of FolderSync.apply measurements. The normal photo
        # trigger still creates each source and folder_photos membership; only
        # hierarchy/count maintenance is recomputed once after the bulk insert.
        db.execute('UPDATE folder_maintenance SET enabled=0 WHERE id=1')
        db.executemany(
            'INSERT INTO photos(path,name,bytes,mtime,recipe,created) VALUES(?,?,?,?,?,0)',
            ((str(photo_dir / f'photo-{index:08}.jpg'), f'photo-{index:08}.jpg',
              BASE_BYTES, BASE_MTIME, recipe) for index in range(rows)),
        )
        db.execute(
            'INSERT OR IGNORE INTO catalog_folders(path,name,parent_path) '
            'WITH RECURSIVE paths(path) AS '
            '(SELECT ? UNION SELECT folder_parent(path) FROM paths WHERE folder_parent(path) IS NOT NULL) '
            'SELECT path,folder_name(path),folder_parent(path) FROM paths',
            (str(photo_dir),),
        )
        db.execute('UPDATE catalog_folders SET direct_count=0,total_count=0,is_root=0')
        db.execute('UPDATE catalog_folders SET direct_count=?,is_root=1 WHERE path=?',
                   (rows, str(photo_dir)))
        ancestor = str(photo_dir)
        while True:
            db.execute('UPDATE catalog_folders SET total_count=? WHERE path=?', (rows, ancestor))
            parent = os.path.dirname(ancestor)
            if parent == ancestor:
                break
            ancestor = parent
        db.execute('UPDATE folder_maintenance SET enabled=1 WHERE id=1')
    folder = db.execute('SELECT id FROM catalog_folders WHERE path=?', (str(photo_dir),)).fetchone()
    assert folder is not None
    assert db.execute('SELECT count(*) FROM photos').fetchone()[0] == rows
    assert db.execute('SELECT count(*) FROM photo_sources').fetchone()[0] == rows
    assert db.execute('SELECT count(*) FROM folder_photos').fetchone()[0] == rows
    assert db.execute('SELECT count(*) FROM folder_sync_files').fetchone()[0] == 0
    assert not photo_dir.exists()
    elapsed_ms = (time.perf_counter() - started) * 1000
    catalog.close()
    return str(catalog_path), str(photo_dir), int(folder['id']), elapsed_ms


def prepare_and_stage(catalog_path, folder_id, rows, changed):
    catalog = open_catalog(catalog_path)
    sync = FolderSync(catalog)
    plan = sync.prepare(folder_id, Folders(catalog).revision(), False, [0, 0, 0])['plan']
    plan_id = plan['id']
    changed = min(changed, rows)
    counts = {'unchanged': rows - changed}
    if changed:
        counts['updated'] = changed
    with catalog.db:
        # These rows represent already-reviewed scan observations. JSON is
        # generated in SQLite so setup stays bounded and outside apply timing.
        catalog.db.execute(
            "UPDATE folder_sync_files SET state='unchanged',selected=1,bytes=?,mtime=?,"
            'fingerprints=json_object(path,json_array(0,0,?,?)),patch=\'{}\',clock=\'{}\',notes=\'[]\',error=\'\' '
            'WHERE plan_id=?',
            (BASE_BYTES, BASE_MTIME, BASE_BYTES, BASE_MTIME, plan_id),
        )
        if changed:
            catalog.db.execute(
                "UPDATE folder_sync_files SET state='updated',bytes=?,mtime=?,"
                'fingerprints=json_object(path,json_array(0,0,?,?)) '
                'WHERE plan_id=? AND path IN (SELECT path FROM photos WHERE id<=?)',
                (BASE_BYTES + 1, BASE_MTIME + 1, BASE_BYTES + 1, BASE_MTIME + 1,
                 plan_id, changed),
            )
        catalog.db.execute('UPDATE folder_sync_directories SET done=1 WHERE plan_id=?', (plan_id,))
        catalog.db.execute(
            "UPDATE folder_sync_plans SET state='ready',phase='files',scanned=?,checked=0,"
            'directories_done=directory_count,counts=?,selected_counts=?,revision=revision+1 WHERE id=?',
            (rows, json.dumps(counts, sort_keys=True), json.dumps(counts, sort_keys=True), plan_id),
        )
    plan = sync.row(plan_id)
    plan['counts'] = json.loads(plan['counts'])
    plan['selected_counts'] = json.loads(plan['selected_counts'])
    assert plan['state'] == 'ready' and plan['file_count'] == rows
    assert plan['counts'] == counts and plan['selected_counts'] == counts
    catalog.close()
    return plan_id, plan['revision'], plan['folder_revision'], counts


def run_apply_trial(catalog_path, folder_id, rows, changed, expected_source_revision):
    plan_id, ready_revision, folder_revision_before, expected_counts = prepare_and_stage(
        catalog_path, folder_id, rows, changed)

    # Service normally opens a fresh connection for each command. Keep the
    # direct domain probe's connection lifetime equivalent, and avoid retaining
    # temporary transaction tables between apply calls.
    catalog = open_catalog(catalog_path)
    verifying = FolderSync(catalog).start_apply(
        plan_id, ready_revision, read_metadata=False, import_new=False)
    catalog.close()

    catalog = open_catalog(catalog_path)
    started = time.perf_counter()
    result = FolderSync(catalog).apply(
        plan_id, verifying['revision'], import_new=False, remove_missing=False,
        read_metadata=False)['plan']
    elapsed_ms = (time.perf_counter() - started) * 1000
    db = catalog.db

    assert result['state'] == 'applied', result
    assert result['file_count'] == rows
    assert result['counts'] == expected_counts
    assert (result['imported'], result['removed'], result['modified']) == (0, 0, 0)
    assert db.execute('SELECT count(*) FROM photos').fetchone()[0] == rows
    assert db.execute('SELECT count(*) FROM folder_sync_files').fetchone()[0] == 0
    assert db.execute('SELECT count(*) FROM photo_sources').fetchone()[0] == rows
    assert db.execute('SELECT sum(revision) FROM photo_sources').fetchone()[0] == expected_source_revision + changed
    expected_changed = changed
    assert db.execute(
        'SELECT count(*) FROM photos WHERE bytes=? AND mtime=?',
        (BASE_BYTES + 1, BASE_MTIME + 1),
    ).fetchone()[0] == expected_changed
    assert db.execute(
        'SELECT count(*) FROM photos WHERE bytes=? AND mtime=?',
        (BASE_BYTES, BASE_MTIME),
    ).fetchone()[0] == rows - expected_changed
    folder = db.execute('SELECT direct_count,total_count FROM catalog_folders WHERE id=?',
                        (folder_id,)).fetchone()
    assert tuple(folder) == (rows, rows)
    folder_revision = db.execute('SELECT revision FROM folder_state WHERE id=1').fetchone()[0]
    assert folder_revision == folder_revision_before + 1
    sample_paths = [row[0] for row in db.execute(
        'SELECT path FROM photos WHERE id IN (1,?,?) ORDER BY id', (max(1, changed), rows))]
    catalog.close()
    assert all(not Path(path).exists() for path in sample_paths)

    return {
        'apply_ms': round(elapsed_ms, 3),
        'final_photo_count': rows,
        'final_changed_stat_count': expected_changed,
        'source_revision_sum': expected_source_revision + changed,
        'folder_revision': folder_revision,
        'original_paths_exist': False,
    }


def reset_changed_stats(catalog_path):
    catalog = open_catalog(catalog_path)
    with catalog.db:
        catalog.db.execute('UPDATE photos SET bytes=?,mtime=?,sha256=\'\' WHERE id<=?',
                           (BASE_BYTES, BASE_MTIME, CHANGED_ROWS))
    catalog.close()


def source_revision_sum(catalog_path):
    catalog = open_catalog(catalog_path)
    value = catalog.db.execute('SELECT coalesce(sum(revision),0) FROM photo_sources').fetchone()[0]
    catalog.close()
    return value


def run_case(catalog_path, folder_id, photo_dir, rows, changed):
    samples = []
    for index in range(WARM_SAMPLES + 1):
        if index and changed:
            reset_changed_stats(catalog_path)
        before_revision = source_revision_sum(catalog_path)
        sample = run_apply_trial(catalog_path, folder_id, rows, changed, before_revision)
        samples.append(sample)
        assert sample['source_revision_sum'] == before_revision + changed
        assert not Path(photo_dir).exists()
    timings = [sample['apply_ms'] for sample in samples]
    return {
        'changed_existing_stat_rows_per_apply': changed,
        'unchanged_rows_per_apply': rows - changed,
        'plan_count': len(samples),
        'first_apply_ms': timings[0],
        'warm_apply_ms': timings[1:],
        'warm_median_ms': round(statistics.median(timings[1:]), 3),
        'samples': samples,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--rows', type=int, nargs='+', default=[10000, 100000])
    args = parser.parse_args()
    if not args.rows or any(not 1000 <= rows <= 100000 for rows in args.rows):
        raise SystemExit('Each row count must be between 1000 and 100000')
    if len(set(args.rows)) != len(args.rows):
        raise SystemExit('Row counts must be unique')
    root = args.work.expanduser().resolve()
    if root.exists():
        raise SystemExit('Choose a new work directory; existing data will not be overwritten')
    root.mkdir(parents=True)

    report = {
        'platform': platform.platform(),
        'machine': platform.machine(),
        'engine': engine_identity(),
        'backend': 'Direct FolderSync domain calls over local SQLite; CPU only',
        'cache': 'Fresh plan each sample; first apply reported separately, then five warm applies; no cache flush',
        'scope': ('Metadata transaction only. Uses real SQLite photos, photo_sources, folder_photos, '
                  'folder_sync_files, and FolderSync prepare/start_apply/apply. Original paths are absent; '
                  'bypasses filesystem scan/stat, scan runner, IPC, image decoding/pixels, and desktop UI. '
                  'Not an end-to-end or image-performance claim.'),
        'rows_requested': args.rows,
        'seeded_image_files': 0,
        'catalogs': [],
        'rss_measurement': ('ru_maxrss is a process-wide high-water mark, including catalog seeding and prior '
                            'trials; it is not an apply-only peak or per-sample RSS.'),
    }

    process_peak_samples = []
    for rows in args.rows:
        catalog_path, photo_dir, folder_id, seed_ms = seed_catalog(
            root / f'catalog-{rows}', root, rows)
        catalog_report = {
            'rows': rows,
            'catalog_originals': rows,
            'filesystem_originals': 0,
            'synthetic_catalog_seed_ms': round(seed_ms, 3),
            'cases': [],
        }
        for changed in (0, CHANGED_ROWS):
            catalog_report['cases'].append(
                run_case(catalog_path, folder_id, photo_dir, rows, changed))
        catalog = open_catalog(catalog_path)
        db = catalog.db
        assert db.execute('SELECT count(*) FROM photos').fetchone()[0] == rows
        assert db.execute('SELECT count(*) FROM folder_photos').fetchone()[0] == rows
        assert db.execute('SELECT count(*) FROM folder_sync_files').fetchone()[0] == 0
        assert not Path(photo_dir).exists()
        catalog.close()
        report['catalogs'].append(catalog_report)
        process_peak_samples.append(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)

    peak_raw = max(process_peak_samples, default=0)
    report['process_peak_rss_mb'] = round(
        peak_raw / (1024 * 1024 if platform.system() == 'Darwin' else 1024), 2)
    (root / 'report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
