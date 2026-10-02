"""Reproducible domain-only performance probe for Folder Sync apply.

Inputs: an unused ``--work`` directory and bounded existing/new row counts.
Outputs: first and warm direct-domain apply timings, SQL-category costs, and
correctness receipts in ``report.json``. Catalog rows are synthetic and source
paths are absent. The probe measures SQLite/domain mutation only; it excludes
directory scanning, filesystem identity validation, IPC, workers, pixels, and
desktop responsiveness. It is intentionally not registered with pytest. Run
only with a fresh output directory, for example:
``python tests/folder_sync_mutation_probe.py --work <new-directory> --rows 10000 --new-rows 1000 --warm-samples 5``.
The reported process RSS includes fixture seeding and prior samples, and later
samples may benefit from the operating-system page cache.
"""
import argparse
from collections import Counter, defaultdict
import json
import os
from pathlib import Path
import platform
import resource
import sqlite3
import statistics
import time

from lumaraw.catalog import Catalog
from lumaraw.folders import Folders
from lumaraw.folder_sync import FolderSync
from lumaraw.import_sequence import state as import_sequence_state
from lumaraw.model import Recipe
from lumaraw.previous_import import state as previous_import_state
from lumaraw.runtime import engine_identity


BASE_BYTES = 4096
BASE_MTIME = 1_790_000_000
WARM_SAMPLES = 3


def _normalized(sql):
    return " ".join(str(sql).lower().split())


def _sql_category(sql):
    text = _normalized(sql)
    if 'from folder_sync_photos s left join photos p' in text:
        return 'guard_source_snapshot'
    if 'from folder_sync_photos s join photos p on p.id=s.photo_id join folder_sync_files f' in text:
        return 'guard_photo_edits'
    if "select 1 from jobs where state='running'" in text:
        return 'guard_running_jobs'
    if "f.state='new' and f.selected=1" in text and 'taken_us is not null' in text:
        return 'guard_late_duplicate'
    if text.startswith('select count(*) from photos where source_id in'):
        return 'count_removed_photos'
    if text.startswith('select count(*) from folder_sync_files where'):
        return 'count_import_rows'
    if text.startswith('insert into sync_deltas') and 'from photos where source_id in' in text:
        return 'delta_removed_photos'
    if text.startswith('insert into sync_deltas') and 'from folder_sync_files where' in text:
        return 'delta_new_photos'
    if text.startswith('update collections set revision=revision+1'):
        return 'revise_affected_collections'
    if text.startswith('delete from collection_photos'):
        return 'delete_collection_memberships'
    if text.startswith('delete from history'):
        return 'delete_history'
    if text.startswith('delete from versions'):
        return 'delete_versions'
    if text.startswith('delete from photos'):
        return 'delete_photos'
    if text.startswith('insert into photos('):
        return 'insert_new_photos'
    if text.startswith('select f.id,f.state,f.selected,') and 'from folder_sync_files f join photos p' in text:
        return 'read_apply_page'
    if text.startswith('select f.id,f.bytes as staged_bytes,f.mtime as staged_mtime,'):
        return 'read_sparse_missing_page'
    if text.startswith('update catalog_folders set direct_count='):
        return 'update_folder_direct_counts'
    if text.startswith('with recursive changes(path,delta)'):
        return 'update_folder_total_counts'
    if text.startswith('insert into previous_import_sources'):
        return 'replace_previous_import_membership'
    if text.startswith('update previous_import_state'):
        return 'update_previous_import_state'
    if text.startswith('update folder_state set revision='):
        return 'update_folder_revision'
    if text.startswith('update folder_sync_plans set state='):
        return 'finish_plan'
    if text.startswith('delete from folder_sync_'):
        return 'discard_staging'
    return 'other_sql'


class SQLProfile:
    """Count and time catalog API calls without retaining SQL or parameters."""

    def __init__(self):
        self.enabled = False
        self.values = defaultdict(lambda: {
            'execute_calls': 0, 'execute_ms': 0.0,
            'fetch_calls': 0, 'fetch_ms': 0.0,
        })
        self.transaction_finalize_calls = 0
        self.transaction_finalize_ms = 0.0
        self.statement_markers = Counter()

    def record(self, category, operation, elapsed):
        if not self.enabled:
            return
        row = self.values[category]
        row[f'{operation}_calls'] += 1
        row[f'{operation}_ms'] += elapsed * 1000

    def observe_statement(self, sql):
        """Record safe structural markers without retaining SQL or parameters."""
        if not self.enabled:
            return
        text = _normalized(sql)
        marker = "select source_id from folder_sync_files where plan_id=? and state='missing' and selected=1"
        if marker in text:
            self.statement_markers['missing_source_subquery_uses'] += 1

    def report(self):
        return {
            'categories': {
                key: {
                    'execute_calls': value['execute_calls'],
                    'execute_ms': round(value['execute_ms'], 3),
                    'fetch_calls': value['fetch_calls'],
                    'fetch_ms': round(value['fetch_ms'], 3),
                }
                for key, value in sorted(self.values.items())
            },
            'transaction_finalize_calls': self.transaction_finalize_calls,
            'transaction_finalize_ms': round(self.transaction_finalize_ms, 3),
            'safe_statement_markers': dict(sorted(self.statement_markers.items())),
        }


class CursorFacade:
    """Forward cursor behavior and time only explicit result consumption."""

    def __init__(self, cursor, profile, category):
        self._cursor = cursor
        self._profile = profile
        self._category = category

    def _timed(self, function, *args):
        started = time.perf_counter()
        try:
            return function(*args)
        finally:
            self._profile.record(self._category, 'fetch', time.perf_counter() - started)

    def fetchone(self):
        return self._timed(self._cursor.fetchone)

    def fetchmany(self, size=None):
        if size is None:
            return self._timed(self._cursor.fetchmany)
        return self._timed(self._cursor.fetchmany, size)

    def fetchall(self):
        return self._timed(self._cursor.fetchall)

    def __iter__(self):
        return self

    def __next__(self):
        return self._timed(self._cursor.__next__)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class DatabaseFacade:
    """Forward the sqlite connection contract used by FolderSync."""

    def __init__(self, connection, profile):
        object.__setattr__(self, '_connection', connection)
        object.__setattr__(self, '_profile', profile)

    def execute(self, sql, parameters=()):
        category = _sql_category(sql)
        self._profile.observe_statement(sql)
        started = time.perf_counter()
        try:
            cursor = self._connection.execute(sql, parameters)
        finally:
            self._profile.record(category, 'execute', time.perf_counter() - started)
        return CursorFacade(cursor, self._profile, category)

    def executemany(self, sql, parameters):
        category = _sql_category(sql)
        self._profile.observe_statement(sql)
        started = time.perf_counter()
        try:
            cursor = self._connection.executemany(sql, parameters)
        finally:
            self._profile.record(category, 'execute', time.perf_counter() - started)
        return CursorFacade(cursor, self._profile, category)

    def executescript(self, sql_script):
        category = _sql_category(sql_script)
        self._profile.observe_statement(sql_script)
        started = time.perf_counter()
        try:
            cursor = self._connection.executescript(sql_script)
        finally:
            self._profile.record(category, 'execute', time.perf_counter() - started)
        return CursorFacade(cursor, self._profile, category)

    def cursor(self, *args, **kwargs):
        return CursorFacade(self._connection.cursor(*args, **kwargs), self._profile, 'other_sql')

    def __enter__(self):
        self._connection.__enter__()
        return self

    def __exit__(self, *exc_info):
        started = time.perf_counter()
        try:
            return self._connection.__exit__(*exc_info)
        finally:
            if self._profile.enabled:
                self._profile.transaction_finalize_calls += 1
                self._profile.transaction_finalize_ms += (time.perf_counter() - started) * 1000

    def __getattr__(self, name):
        return getattr(self._connection, name)

    def __setattr__(self, name, value):
        if name.startswith('_'):
            object.__setattr__(self, name, value)
        else:
            setattr(self._connection, name, value)


def seed_catalog(catalog_root, originals_root, rows):
    """Seed one synthetic folder with real catalog triggers, no image files."""
    photo_dir = originals_root / f'rows-{rows}' / 'Photos'
    if photo_dir.exists():
        raise ValueError('Synthetic original path unexpectedly exists')
    catalog = Catalog(catalog_root)
    started = time.perf_counter()
    db = catalog.db
    recipe = json.dumps(Recipe().dict(), separators=(',', ':'))
    with db:
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
    return str(catalog_root), photo_dir, int(folder['id']), elapsed_ms


def seed_empty_catalog(catalog_root, photo_dir):
    """Create only a catalog folder identity for the new-only case."""
    if photo_dir.exists():
        raise ValueError('Synthetic original path unexpectedly exists')
    catalog = Catalog(catalog_root)
    with catalog.db:
        catalog.db.execute(
            'INSERT INTO catalog_folders(path,name,parent_path,direct_count,total_count,is_root) '
            'VALUES(?,?,?,0,0,1)',
            (str(photo_dir), photo_dir.name, str(photo_dir.parent)),
        )
    row = catalog.db.execute('SELECT id FROM catalog_folders WHERE path=?', (str(photo_dir),)).fetchone()
    assert row is not None
    assert catalog.db.execute('SELECT count(*) FROM photos').fetchone()[0] == 0
    folder_id = int(row['id'])
    catalog.close()
    return folder_id


def backup_catalog(template_root, sample_root):
    """Make a fresh catalog file for every irreversible apply sample."""
    sample_root.mkdir(parents=True, exist_ok=False)
    source = sqlite3.connect(template_root / 'catalog.sqlite')
    target = sqlite3.connect(sample_root / 'catalog.sqlite')
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()


def stage_plan(catalog, folder_id, photo_dir, existing_rows, unchanged_rows, missing_rows, new_rows):
    if unchanged_rows + missing_rows != existing_rows:
        raise ValueError('Existing rows must be fully classified as unchanged or missing')
    sync = FolderSync(catalog)
    prepared = sync.prepare(folder_id, Folders(catalog).revision(), False, [0, 0, 0])
    plan_id = prepared['plan']['id']
    assert prepared['plan']['file_count'] == existing_rows

    state_counts = Counter()
    if unchanged_rows:
        state_counts['unchanged'] += unchanged_rows
    if missing_rows:
        state_counts['missing'] += missing_rows
    if new_rows:
        state_counts['new'] += new_rows

    with catalog.db:
        if unchanged_rows:
            updated = catalog.db.execute(
                "UPDATE folder_sync_files SET state='unchanged',selected=1,bytes=?,mtime=?,"
                "fingerprints='{}',patch='{}',clock='{}',notes='[]',error='' "
                'WHERE plan_id=? AND source_id>0 AND id IN '
                '(SELECT id FROM folder_sync_files WHERE plan_id=? AND source_id>0 ORDER BY id LIMIT ?)',
                (BASE_BYTES, BASE_MTIME, plan_id, plan_id, unchanged_rows),
            ).rowcount
            assert updated == unchanged_rows
        if missing_rows:
            # In this fixture, observed missing originals report zero stat data.
            updated = catalog.db.execute(
                "UPDATE folder_sync_files SET state='missing',selected=1,bytes=0,mtime=0,"
                "fingerprints='{}',patch='{}',clock='{}',notes='[]',error='' "
                'WHERE plan_id=? AND source_id>0 AND state!=\'unchanged\'',
                (plan_id,),
            ).rowcount
            assert updated == missing_rows
            # If a mixed case has one intentional unchanged row, only the first
            # missing_rows remain pending and the WHERE above covers them all.
        if new_rows:
            inserted = catalog.db.executemany(
                'INSERT INTO folder_sync_files(plan_id,path,name,state,selected,bytes,mtime,patch,clock,notes,error) '
                "VALUES(?,?,?,'new',1,?,?,'{}','{}','[]','')",
                ((plan_id, str(photo_dir / f'new-{index:08}.jpg'), f'new-{index:08}.jpg',
                  BASE_BYTES, BASE_MTIME) for index in range(new_rows)),
            ).rowcount
            assert inserted == new_rows
        catalog.db.execute('UPDATE folder_sync_directories SET done=1 WHERE plan_id=?', (plan_id,))
        catalog.db.execute(
            "UPDATE folder_sync_plans SET state='ready',phase='files',scanned=?,checked=0,"
            'file_count=?,directories_done=directory_count,counts=?,selected_counts=?,revision=revision+1 WHERE id=?',
            (existing_rows + new_rows, existing_rows + new_rows,
             json.dumps(dict(state_counts), sort_keys=True), json.dumps(dict(state_counts), sort_keys=True), plan_id),
        )

    response = sync.get(plan_id, kind='all')
    plan = response['plan']
    assert plan['state'] == 'ready'
    assert plan['file_count'] == existing_rows + new_rows
    assert plan['counts'] == dict(state_counts)
    assert plan['selected_counts'] == dict(state_counts)
    return plan


def _count(db, sql, parameters=()):
    return db.execute(sql, parameters).fetchone()[0]


def _folder_counts(db, folder_id):
    row = db.execute('SELECT direct_count,total_count FROM catalog_folders WHERE id=?', (folder_id,)).fetchone()
    assert row is not None
    return int(row['direct_count']), int(row['total_count'])


def _profile_snapshot(profile):
    return profile.report()


def run_trial(template_root, sample_root, folder_id, photo_dir, existing_rows,
              unchanged_rows, missing_rows, new_rows, remove_missing):
    backup_catalog(template_root, sample_root)
    catalog = Catalog(sample_root)
    plan = stage_plan(catalog, folder_id, photo_dir, existing_rows,
                      unchanged_rows, missing_rows, new_rows)
    plan_id = plan['id']
    verifier = FolderSync(catalog).start_apply(
        plan_id, plan['revision'], read_metadata=False, import_new=True, include_duplicates=False)

    profile = SQLProfile()
    raw_db = catalog.db
    catalog.db = DatabaseFacade(raw_db, profile)
    sync = FolderSync(catalog)

    initial_photo_count = _count(raw_db, 'SELECT count(*) FROM photos')
    initial_source_count = _count(raw_db, 'SELECT count(*) FROM photo_sources')
    initial_folder_revision = Folders(catalog).revision()
    initial_folder_counts = _folder_counts(raw_db, folder_id)
    initial_previous = previous_import_state(raw_db)
    initial_sequence = import_sequence_state(raw_db)
    assert initial_photo_count == existing_rows
    assert initial_source_count == existing_rows
    assert initial_folder_counts == (existing_rows, existing_rows)
    new_prefix = str(photo_dir / 'new-')

    started = time.perf_counter()
    profile.enabled = True
    try:
        # FolderSync.apply returns the usual get-plan envelope; retain its plan.
        envelope = sync.apply(plan_id, verifier['revision'], import_new=True,
                              remove_missing=remove_missing, read_metadata=False,
                              include_duplicates=False)
    finally:
        profile.enabled = False
    elapsed_ms = (time.perf_counter() - started) * 1000
    applied = envelope['plan']

    final_photo_count = _count(raw_db, 'SELECT count(*) FROM photos')
    final_source_count = _count(raw_db, 'SELECT count(*) FROM photo_sources')
    final_folder_counts = _folder_counts(raw_db, folder_id)
    final_folder_revision = Folders(catalog).revision()
    final_previous = previous_import_state(raw_db)
    final_sequence = import_sequence_state(raw_db)
    actual_new_count = 0
    for index, row in enumerate(raw_db.execute(
            'SELECT name,original_name,import_number,image_number,is_virtual FROM photos '
            'WHERE substr(path,1,?)=? ORDER BY image_number', (len(new_prefix), new_prefix))):
        assert row['original_name'] == row['name']
        assert row['import_number'] == initial_sequence['next_import']
        assert row['image_number'] == initial_sequence['next_image'] + index
        assert row['is_virtual'] == 0
        actual_new_count += 1

    expected_imported = new_rows
    expected_removed = missing_rows
    expected_remaining_photos = unchanged_rows + new_rows
    assert applied['state'] == 'applied', applied
    assert applied['imported'] == expected_imported, applied
    assert applied['removed'] == expected_removed, applied
    assert applied['modified'] == 0, applied
    assert final_photo_count == expected_remaining_photos
    assert final_source_count == initial_source_count + new_rows
    assert final_folder_counts == (expected_remaining_photos, expected_remaining_photos)
    assert final_folder_revision == initial_folder_revision + 1
    assert actual_new_count == new_rows
    expected_sequence_advance = 1 if new_rows else 0
    assert final_sequence['revision'] == initial_sequence['revision'] + expected_sequence_advance
    assert final_sequence['next_import'] == initial_sequence['next_import'] + expected_sequence_advance
    assert final_sequence['next_image'] == initial_sequence['next_image'] + new_rows
    if new_rows:
        assert final_previous['imported'] == new_rows
        assert final_previous['kind'] == 'folder_sync'
        assert final_previous['revision'] == initial_previous['revision'] + 1
    else:
        assert final_previous == initial_previous
    assert _count(raw_db, 'SELECT count(*) FROM folder_sync_files WHERE plan_id=?', (plan_id,)) == 0
    assert _count(raw_db, 'SELECT count(*) FROM folder_sync_directories WHERE plan_id=?', (plan_id,)) == 0
    assert _count(raw_db, 'SELECT count(*) FROM folder_sync_photos WHERE plan_id=?', (plan_id,)) == 0
    assert not photo_dir.exists()

    result = {
        'apply_wall_ms': round(elapsed_ms, 3),
        'existing_rows': existing_rows,
        'unchanged_rows': unchanged_rows,
        'missing_rows': missing_rows,
        'new_rows': new_rows,
        'imported': applied['imported'],
        'removed': applied['removed'],
        'modified': applied['modified'],
        'initial_photo_count': initial_photo_count,
        'final_photo_count': final_photo_count,
        'initial_source_count': initial_source_count,
        'final_source_count': final_source_count,
        'folder_counts': {'direct': final_folder_counts[0], 'total': final_folder_counts[1]},
        'folder_revision_delta': final_folder_revision - initial_folder_revision,
        'import_sequence': {
            'revision_delta': final_sequence['revision'] - initial_sequence['revision'],
            'next_import_delta': final_sequence['next_import'] - initial_sequence['next_import'],
            'next_image_delta': final_sequence['next_image'] - initial_sequence['next_image'],
        },
        'previous_import': {
            'imported': final_previous['imported'],
            'revision_delta': final_previous['revision'] - initial_previous['revision'],
            'kind': final_previous['kind'],
        },
        'new_original_names_match': True,
        'staging_cleanup': True,
        'sql_profile': _profile_snapshot(profile),
    }
    catalog.close()
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--rows', type=int, default=100000,
                        help='Existing master originals for remove/mixed/control cases (1000..100000)')
    parser.add_argument('--new-rows', type=int, default=10000,
                        help='New reviewed items in new/control/mixed cases (1..100000)')
    parser.add_argument('--warm-samples', type=int, default=WARM_SAMPLES,
                        help='Warm samples after one separately reported first sample (0..10)')
    args = parser.parse_args()
    if not 1000 <= args.rows <= 100000:
        raise SystemExit('Existing rows must be between 1000 and 100000')
    if not 1 <= args.new_rows <= 100000:
        raise SystemExit('New rows must be between 1 and 100000')
    if not 0 <= args.warm_samples <= 10:
        raise SystemExit('Warm sample count must be between 0 and 10')
    root = args.work.expanduser().resolve()
    if root.exists():
        raise SystemExit('Choose a new work directory; existing data will not be overwritten')
    root.mkdir(parents=True)

    rows = args.rows
    new_rows = args.new_rows
    remove_rows = max(0, rows - 1)
    template_root = root / 'templates'
    template_root.mkdir()
    empty_template = template_root / 'empty-catalog'
    empty_photo_dir = root / 'synthetic-originals-not-created' / 'new-only' / 'Photos'
    empty_folder_id = seed_empty_catalog(empty_template, empty_photo_dir)
    _, populated_photo_dir, populated_folder_id, seed_ms = seed_catalog(
        template_root / f'existing-{rows}', root / 'synthetic-originals-not-created', rows)

    cases = [
        {'name': 'new_only', 'template': empty_template, 'folder_id': empty_folder_id,
         'photo_dir': empty_photo_dir, 'existing': 0, 'unchanged': 0, 'missing': 0,
         'new': new_rows, 'remove_missing': False},
        {'name': 'unchanged_plus_new', 'template': template_root / f'existing-{rows}',
         'folder_id': populated_folder_id, 'photo_dir': populated_photo_dir,
         'existing': rows, 'unchanged': rows, 'missing': 0,
         'new': new_rows, 'remove_missing': False},
        {'name': 'remove_only', 'template': template_root / f'existing-{rows}',
         'folder_id': populated_folder_id, 'photo_dir': populated_photo_dir,
         'existing': rows, 'unchanged': 0, 'missing': rows,
         'new': 0, 'remove_missing': True},
        {'name': 'mixed_99_percent_remove_plus_new', 'template': template_root / f'existing-{rows}',
         'folder_id': populated_folder_id, 'photo_dir': populated_photo_dir,
         'existing': rows, 'unchanged': rows - remove_rows, 'missing': remove_rows,
         'new': new_rows, 'remove_missing': True},
    ]

    report = {
        'platform': platform.platform(),
        'machine': platform.machine(),
        'python': platform.python_version(),
        'sqlite': sqlite3.sqlite_version,
        'engine': engine_identity(),
        'catalog_existing_masters': rows,
        'new_rows': new_rows,
        'warm_samples': args.warm_samples,
        'scope': ('Direct FolderSync domain/SQLite transaction with synthetic catalog rows and absent originals. '
                  'Filesystem scan/validation, IPC, worker, pixels and UI are intentionally excluded.'),
        'cache_policy': ('Each sample is a fresh SQLite backup and connection; first sample is separated from warm '
                         'samples. No OS page-cache flush is attempted, so later backups may benefit from warm OS cache.'),
        'rss_policy': ('ru_maxrss is process-wide and includes template seeding, database copies and earlier cases; '
                       'it is not per-apply peak memory.'),
        'synthetic_template_seed_ms': round(seed_ms, 3),
        'cases': [],
    }

    sample_index = 0
    for case in cases:
        case_report = {
            'name': case['name'],
            'counts': {
                'existing': case['existing'], 'unchanged': case['unchanged'],
                'missing': case['missing'], 'new': case['new'],
            },
            'samples': [],
        }
        for sample_number in range(args.warm_samples + 1):
            sample_root = root / 'trials' / case['name'] / f'sample-{sample_number:02d}' / 'catalog'
            sample = run_trial(case['template'], sample_root, case['folder_id'], case['photo_dir'],
                               case['existing'], case['unchanged'], case['missing'], case['new'],
                               case['remove_missing'])
            sample['sample_kind'] = 'first' if sample_number == 0 else 'warm'
            case_report['samples'].append(sample)
            sample_index += 1
        timings = [sample['apply_wall_ms'] for sample in case_report['samples']]
        case_report['first_apply_ms'] = timings[0]
        case_report['warm_apply_ms'] = timings[1:]
        case_report['warm_median_ms'] = round(statistics.median(timings[1:]), 3) if len(timings) > 1 else None
        report['cases'].append(case_report)

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    report['process_peak_rss_mb'] = round(
        peak / (1024 * 1024 if platform.system() == 'Darwin' else 1024), 2)
    report['sample_count'] = sample_index
    (root / 'report.json').write_text(json.dumps(report, indent=2, sort_keys=True))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
