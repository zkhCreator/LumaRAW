"""Regression evidence for Folder Sync's reviewed duplicate and identity boundary.

Inputs: generated originals, captured folder plans and controlled catalog races.
Outputs: exact duplicate identities, explicit selection behavior, atomic apply,
numbering/Previous Import provenance, path-derived original names and additive
schema compatibility. These fixtures prove catalog semantics only; they do not
claim Lightroom equivalence.
"""
import hashlib
import json
import os
import shutil
import sqlite3

from PIL import Image
import pytest

from lumaraw.catalog import Catalog
from lumaraw.folder_sync import FolderSync, migrate_suspected_duplicates
from lumaraw.import_sequence import state as sequence_state
from lumaraw.previous_import import state as previous_state
from lumaraw.service import Service
from test_folder_sync import scan
from test_xmp_read import packet


def camera_jpeg(path, fraction='123456789'):
    path.parent.mkdir(parents=True, exist_ok=True)
    exif = Image.Exif()
    exif[272] = 'Fixture Camera'
    exif[34665] = {
        36867: '2026:09:26 12:00:01',
        37521: fraction,
        36881: '+08:00',
    }
    Image.new('RGB', (12, 8), 'navy').save(path, format='JPEG', quality=91, exif=exif)
    return path


def plain_jpeg(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new('RGB', (12, 8), 'navy').save(path, format='JPEG', quality=91)
    return path


def library(tmp_path, originals=()):
    root = tmp_path / 'Photos'
    root.mkdir()
    anchor = root / 'anchor.png'
    Image.new('RGB', (12, 8), 'gray').save(anchor)
    service = Service(tmp_path / 'catalog')
    service.dispatch('queue_control', {'action': 'pause'})
    service.dispatch('import_photos', {'paths': [str(path) for path in (*originals, anchor)]})
    return service, root, anchor


def prepare(service, root, scan_metadata=True):
    with service.catalog() as catalog:
        folder_id = catalog.db.execute('SELECT id FROM catalog_folders WHERE path=?',
                                       (str(root),)).fetchone()[0]
        revision = catalog.db.execute('SELECT revision FROM folder_state WHERE id=1').fetchone()[0]
    return service.dispatch('prepare_folder_sync', {
        'folder_id': folder_id,
        'expected_revision': revision,
        'scan_metadata': scan_metadata,
    })['plan']


def items(service, plan, kind='all'):
    return service.dispatch('get_folder_sync', {
        'plan_id': plan['id'], 'kind': kind,
    })['items']


def select(service, plan, kind, item_ids, selected):
    return service.dispatch('select_folder_sync_items', {
        'plan_id': plan['id'], 'expected_revision': plan['revision'],
        'kind': kind, 'item_ids': item_ids, 'selected': selected,
    })['plan']


def apply(service, plan, **options):
    params = {
        'plan_id': plan['id'], 'expected_revision': plan['revision'],
        'import_new': True, 'remove_missing': False, 'read_metadata': True,
    }
    params.update(options)
    return service.dispatch('apply_folder_sync', params)['plan']


def test_catalog_identity_uses_original_name_and_full_capture_fraction_with_explicit_selection_backup(tmp_path):
    source = camera_jpeg(tmp_path / 'External' / 'catalog-copy-name.jpg')
    service, root, _ = library(tmp_path, [source])
    restored = None
    try:
        with service.catalog() as catalog, catalog.db:
            catalog.db.execute('UPDATE photos SET original_name=? WHERE path=?',
                               ('camera-original.jpg', str(source)))

        first = root / 'one' / 'camera-original.jpg'
        second = root / 'two' / 'camera-original.jpg'
        wrong_name = root / 'three' / 'catalog-copy-name.jpg'
        wrong_fraction = root / 'four' / 'camera-original.jpg'
        for path in (first, second, wrong_name):
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, path)
        camera_jpeg(wrong_fraction, '123456788')
        assert wrong_fraction.stat().st_size == source.stat().st_size

        plan = scan(service, prepare(service, root, scan_metadata=False))
        rows = {row['path']: row for row in items(service, plan)}
        assert plan['duplicate_detection'] == 1
        assert rows[str(first)]['state'] == rows[str(second)]['state'] == 'duplicate'
        for path in (first, second):
            assert rows[str(path)]['duplicate_match'] == 'catalog'
            assert rows[str(path)]['duplicate_of_path'] == str(source)
        assert rows[str(wrong_name)]['state'] == 'new'
        assert rows[str(wrong_fraction)]['state'] == 'new'
        assert plan['counts']['duplicate'] == 2

        # A normal apply skips duplicate rows unless the user opts in. Keep the
        # two deliberately non-matching originals out of this first application.
        plan = select(service, plan, 'new',
                      [rows[str(wrong_name)]['id'], rows[str(wrong_fraction)]['id']], False)
        skipped = apply(service, plan, read_metadata=False)
        assert skipped['state'] == 'applied' and skipped['imported'] == 0
        with service.catalog() as catalog:
            assert not catalog.db.execute('SELECT 1 FROM photos WHERE path IN (?,?)',
                                          (str(first), str(second))).fetchone()

        # A fresh review captures the chosen duplicate and its deselection.
        # The product backup/restore path must preserve that review exactly.
        plan = scan(service, prepare(service, root, scan_metadata=False))
        current = {row['path']: row for row in items(service, plan)}
        assert current[str(first)]['state'] == current[str(second)]['state'] == 'duplicate'
        plan = select(service, plan, 'duplicate', [current[str(second)]['id']], False)
        current = {row['path']: row for row in items(service, plan)}
        plan = select(service, plan, 'new',
                      [current[str(wrong_name)]['id'], current[str(wrong_fraction)]['id']], False)
        assert plan['selected_counts']['duplicate'] == 1
        assert plan['selected_counts'].get('new', 0) == 0
        backup = tmp_path / 'folder-sync-review.sqlite'
        service.dispatch('backup_catalog', {'path': str(backup)})
        restored = Service(service.dispatch('restore_catalog', {
            'path': str(backup), 'destination': str(tmp_path / 'restored'),
        })['catalog'])
        loaded = restored.dispatch('get_folder_sync', {'plan_id': plan['id'], 'kind': 'all'})
        assert loaded['plan']['duplicate_detection'] == 1
        assert loaded['plan']['selected_counts']['duplicate'] == 1
        restored_rows = {row['path']: row for row in loaded['items']}
        assert restored_rows[str(first)]['selected'] == 1
        assert restored_rows[str(second)]['selected'] == 0
        assert restored_rows[str(second)]['duplicate_match'] == 'catalog'
        assert restored_rows[str(second)]['duplicate_of_path'] == str(source)

        done = apply(restored, loaded['plan'], include_duplicates=True, read_metadata=False)
        assert done['state'] == 'applied' and done['imported'] == 1
        with restored.catalog() as catalog:
            assert catalog.db.execute('SELECT count(*) FROM photos WHERE path=?',
                                      (str(first),)).fetchone()[0] == 1
            assert catalog.db.execute('SELECT count(*) FROM photos WHERE path=?',
                                      (str(second),)).fetchone()[0] == 0
            assert catalog.db.execute('SELECT count(*) FROM photos WHERE path=?',
                                      (str(wrong_name),)).fetchone()[0] == 0
            assert catalog.db.execute('SELECT count(*) FROM photos WHERE path=?',
                                      (str(wrong_fraction),)).fetchone()[0] == 0
    finally:
        if restored is not None:
            restored.close()
        service.close()


def test_unknown_capture_time_does_not_fall_back_to_matching_mtime(tmp_path):
    source = plain_jpeg(tmp_path / 'External' / 'unknown.jpg')
    service, root, _ = library(tmp_path, [source])
    try:
        candidate = root / 'nested' / 'unknown.jpg'
        candidate.parent.mkdir(parents=True)
        shutil.copyfile(source, candidate)
        stat = source.stat()
        os.utime(candidate, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        plan = scan(service, prepare(service, root))
        row = next(item for item in items(service, plan) if item['path'] == str(candidate))
        assert row['state'] == 'new'
        assert plan['counts'].get('duplicate', 0) == 0
        with service.catalog() as catalog:
            captured = catalog.db.execute('SELECT taken_us,capture_clock FROM folder_sync_files WHERE id=?',
                                          (row['id'],)).fetchone()
            assert tuple(captured) == (None, 'unknown')
    finally:
        service.close()


def test_plan_duplicate_can_be_imported_after_predecessor_is_deselected_with_metadata_and_numbers(tmp_path):
    sample = camera_jpeg(tmp_path / 'untracked-source.jpg')
    service, root, _ = library(tmp_path)
    try:
        first = root / 'first' / 'series.jpg'
        second = root / 'second' / 'series.jpg'
        for path in (first, second):
            path.parent.mkdir(parents=True)
            shutil.copyfile(sample, path)
            path.with_suffix('.xmp').write_bytes(packet('<dc:title>Synced duplicate</dc:title>'))

        with service.catalog() as catalog:
            sequence_before = sequence_state(catalog.db)
            previous_before = previous_state(catalog.db)
        plan = scan(service, prepare(service, root, scan_metadata=True))
        rows = items(service, plan)
        new_row = next(row for row in rows if row['path'] in (str(first), str(second)) and row['state'] == 'new')
        duplicate_row = next(row for row in rows if row['path'] in (str(first), str(second)) and row['state'] == 'duplicate')
        assert duplicate_row['duplicate_match'] == 'plan'
        assert duplicate_row['duplicate_of_path'] == new_row['path']

        with pytest.raises(ValueError, match='requires importing new photos'):
            service.dispatch('apply_folder_sync', {
                'plan_id': plan['id'], 'expected_revision': plan['revision'],
                'import_new': False, 'include_duplicates': True,
                'remove_missing': False, 'read_metadata': True,
            })
        still_ready = service.dispatch('get_folder_sync', {'plan_id': plan['id']})['plan']
        assert still_ready['state'] == 'ready' and still_ready['revision'] == plan['revision']

        plan = select(service, plan, 'new', [new_row['id']], False)
        still_duplicate = {row['path']: row for row in items(service, plan)}[duplicate_row['path']]
        assert still_duplicate['state'] == 'duplicate'
        assert still_duplicate['duplicate_of_path'] == new_row['path']
        assert plan['selected_counts'].get('new', 0) == 0
        assert plan['selected_counts']['duplicate'] == 1

        done = apply(service, plan, include_duplicates=True)
        assert done['state'] == 'applied' and done['imported'] == 1
        with service.catalog() as catalog:
            imported = catalog.db.execute('SELECT id,source_id,original_name,taken_us,taken_submicro,import_number,image_number,title '
                                          'FROM photos WHERE path=? AND is_virtual=0',
                                          (duplicate_row['path'],)).fetchone()
            assert imported is not None
            assert imported['original_name'] == 'series.jpg'
            assert imported['taken_us'] is not None and imported['taken_submicro'] == '789'
            assert imported['title'] == 'Synced duplicate'
            assert imported['import_number'] == sequence_before['next_import']
            assert imported['image_number'] == sequence_before['next_image']
            sequence_after = sequence_state(catalog.db)
            assert sequence_after['next_import'] == sequence_before['next_import'] + 1
            assert sequence_after['next_image'] == sequence_before['next_image'] + 1
            assert sequence_after['revision'] == sequence_before['revision'] + 1
            previous_after = previous_state(catalog.db)
            assert previous_after['kind'] == 'folder_sync'
            assert previous_after['imported'] == 1
            assert previous_after['revision'] == previous_before['revision'] + 1
            assert catalog.db.execute('SELECT 1 FROM previous_import_sources WHERE source_id=?',
                                      (imported['source_id'],)).fetchone()
            assert catalog.db.execute('SELECT 1 FROM photos WHERE path=? AND is_virtual=0',
                                      (new_row['path'],)).fetchone() is None
    finally:
        service.close()


def test_final_recheck_rejects_new_to_duplicate_race_before_removal_or_allocation(tmp_path):
    service, root, _ = library(tmp_path)
    try:
        missing = root / 'missing.jpg'
        camera_jpeg(missing)
        # Import the soon-to-be-missing row, then remove its file before the plan
        # captures the root identity. The plan can now request removal atomically.
        service.dispatch('import_photos', {'paths': [str(missing)]})
        missing.unlink()
        target = camera_jpeg(root / 'race.jpg')
        late_catalog = tmp_path / 'External' / 'race.jpg'
        late_catalog.parent.mkdir(parents=True)
        shutil.copyfile(target, late_catalog)
        plan = scan(service, prepare(service, root))
        assert plan['counts'].get('missing') == 1 and plan['counts'].get('new') == 1

        with service.catalog() as catalog, catalog.db:
            folder_revision = catalog.db.execute('SELECT revision FROM folder_state WHERE id=1').fetchone()[0]
            catalog.db.execute('UPDATE folder_maintenance SET enabled=0 WHERE id=1')
            assert catalog.import_paths([str(late_catalog)]) == (1, 0)
            catalog.db.execute('UPDATE folder_maintenance SET enabled=1 WHERE id=1')
            assert catalog.db.execute('SELECT revision FROM folder_state WHERE id=1').fetchone()[0] == folder_revision
            sequence_after_late_import = sequence_state(catalog.db)
            previous_after_late_import = previous_state(catalog.db)
            late_id = catalog.db.execute('SELECT id FROM photos WHERE path=?',
                                         (str(late_catalog),)).fetchone()[0]

        failed = apply(service, plan, remove_missing=True)
        assert failed['state'] == 'failed'
        assert failed['error'] == 'A suspected duplicate appeared after review; create a fresh synchronization plan'
        with service.catalog() as catalog:
            assert catalog.db.execute('SELECT id FROM photos WHERE path=?',
                                      (str(late_catalog),)).fetchone()[0] == late_id
            assert catalog.db.execute('SELECT id,missing FROM photos WHERE path=?',
                                      (str(missing),)).fetchone()[:] == (2, 0)
            assert catalog.db.execute('SELECT 1 FROM photos WHERE path=?', (str(target),)).fetchone() is None
            assert sequence_state(catalog.db) == sequence_after_late_import
            assert previous_state(catalog.db) == previous_after_late_import
            assert catalog.db.execute('SELECT enabled FROM folder_maintenance WHERE id=1').fetchone()[0] == 1
    finally:
        service.close()


def test_genuine_schema_36_duplicate_migration_is_additive_atomic_and_grandfathers_saved_plan(tmp_path, monkeypatch):
    import lumaraw.catalog as catalog_module
    from legacy_catalog import migrate_to, seed_photo

    photo_path = plain_jpeg(tmp_path / 'Legacy' / 'old.jpg')
    with monkeypatch.context() as patch:
        patch.setattr(catalog_module, 'migrate', lambda db: migrate_to(db, 36))
        catalog = Catalog(tmp_path / 'legacy-catalog')
    photo_id = seed_photo(catalog.db, photo_path)
    folder_id = catalog.db.execute('SELECT id FROM catalog_folders WHERE path=?',
                                   (str(photo_path.parent),)).fetchone()[0]
    folder_revision = catalog.db.execute('SELECT revision FROM folder_state WHERE id=1').fetchone()[0]
    with catalog.db:
        plan_id = catalog.db.execute(
            "INSERT INTO folder_sync_plans(folder_id,path,fingerprint,folder_revision,scan_metadata,state,revision,"
            "file_count,counts,selected_counts,created) VALUES(?,?,?,?,1,'ready',7,1,?,?,1)",
            (folder_id, str(photo_path.parent), '[]', folder_revision,
             json.dumps({'new': 1}), json.dumps({'new': 1})),
        ).lastrowid
        item_id = catalog.db.execute(
            "INSERT INTO folder_sync_files(plan_id,path,source_id,state,selected,bytes,mtime,fingerprints,patch,clock,notes,error) "
            "VALUES(?,?,0,'new',1,0,0,'{}','{}','{}','[]','')",
            (plan_id, str(photo_path.parent / 'not-yet-scanned.jpg')),
        ).lastrowid
    old_plan = tuple(catalog.db.execute(
        'SELECT id,folder_id,path,fingerprint,folder_revision,scan_metadata,state,revision,file_count,counts,selected_counts '
        'FROM folder_sync_plans WHERE id=?', (plan_id,),
    ).fetchone())
    old_file = tuple(catalog.db.execute(
        'SELECT id,plan_id,path,source_id,state,selected,bytes,mtime,fingerprints,patch,clock,notes,error '
        'FROM folder_sync_files WHERE id=?', (item_id,),
    ).fetchone())
    assert catalog.db.execute('PRAGMA user_version').fetchone()[0] == 36
    assert 'duplicate_detection' not in {row[1] for row in catalog.db.execute('PRAGMA table_info(folder_sync_plans)')}

    denied = []

    def reject_version_bump(action, name, detail, database, trigger):
        if action == sqlite3.SQLITE_PRAGMA and name == 'user_version' and detail == '37':
            denied.append(f'{name}={detail}')
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    catalog.db.set_authorizer(reject_version_bump)
    with pytest.raises(sqlite3.DatabaseError):
        migrate_suspected_duplicates(catalog.db)
    catalog.db.set_authorizer(None)
    assert denied == ['user_version=37']
    assert catalog.db.execute('PRAGMA user_version').fetchone()[0] == 36
    assert 'duplicate_detection' not in {row[1] for row in catalog.db.execute('PRAGMA table_info(folder_sync_plans)')}
    assert 'duplicate_match' not in {row[1] for row in catalog.db.execute('PRAGMA table_info(folder_sync_files)')}
    assert not catalog.db.execute("SELECT 1 FROM sqlite_master WHERE name='folder_sync_file_duplicate'").fetchone()
    assert tuple(catalog.db.execute(
        'SELECT id,folder_id,path,fingerprint,folder_revision,scan_metadata,state,revision,file_count,counts,selected_counts '
        'FROM folder_sync_plans WHERE id=?', (plan_id,),
    ).fetchone()) == old_plan
    assert tuple(catalog.db.execute(
        'SELECT id,plan_id,path,source_id,state,selected,bytes,mtime,fingerprints,patch,clock,notes,error '
        'FROM folder_sync_files WHERE id=?', (item_id,),
    ).fetchone()) == old_file

    migrate_suspected_duplicates(catalog.db)
    migrate_suspected_duplicates(catalog.db)
    assert catalog.db.execute('PRAGMA user_version').fetchone()[0] == 37
    assert tuple(catalog.db.execute(
        'SELECT duplicate_detection FROM folder_sync_plans WHERE id=?', (plan_id,),
    ).fetchone()) == (0,)
    added = catalog.db.execute(
        'SELECT name,taken_us,taken_submicro,capture_clock,duplicate_match,duplicate_of_path '
        'FROM folder_sync_files WHERE id=?', (item_id,),
    ).fetchone()
    assert tuple(added) == ('', None, '', 'unknown', '', '')
    assert tuple(catalog.db.execute(
        'SELECT id,folder_id,path,fingerprint,folder_revision,scan_metadata,state,revision,file_count,counts,selected_counts '
        'FROM folder_sync_plans WHERE id=?', (plan_id,),
    ).fetchone()) == old_plan
    with pytest.raises(ValueError, match='predates suspected-duplicate review'):
        FolderSync(catalog).start_apply(plan_id, 7, True, include_duplicates=True)
    assert catalog.db.execute('SELECT state,revision FROM folder_sync_plans WHERE id=?',
                              (plan_id,)).fetchone()[:] == ('ready', 7)
    indexes = {row[0]: row[1] for row in catalog.db.execute(
        "SELECT name,sql FROM sqlite_master WHERE type='index' AND name IN "
        "('folder_sync_changes','folder_sync_file_duplicate','photo_import_duplicate')")}
    assert 'duplicate' in indexes['folder_sync_changes']
    assert 'state IN (\'new\',\'duplicate\')' in indexes['folder_sync_file_duplicate']
    assert 'photo_import_duplicate' in indexes
    catalog.close()


def test_genuine_v36_ready_plan_derives_original_name_from_unicode_path(tmp_path, monkeypatch):
    import lumaraw.catalog as catalog_module
    from legacy_catalog import migrate_to, seed_photo
    from lumaraw.folder_sync_io import directory_identity, inspect_file

    root = tmp_path / 'Library' / '旅行'
    anchor = plain_jpeg(root / 'anchor.jpg')
    candidate = plain_jpeg(root / 'Cafe\u0301.jpg')
    original_hash = hashlib.sha256(candidate.read_bytes()).digest()
    catalog_root = tmp_path / 'schema-36-unicode-original-name'

    with monkeypatch.context() as patch:
        patch.setattr(catalog_module, 'migrate', lambda db: migrate_to(db, 36))
        legacy = Catalog(catalog_root)
    seed_photo(legacy.db, anchor)
    folder_id = legacy.db.execute(
        'SELECT id FROM catalog_folders WHERE path=?', (str(root),),
    ).fetchone()[0]
    folder_revision = legacy.db.execute(
        'SELECT revision FROM folder_state WHERE id=1',
    ).fetchone()[0]
    candidate_stat = candidate.stat()
    observation = inspect_file({'path': str(candidate), 'source_id': 0}, False, lambda: False)
    assert not observation.get('error')
    with legacy.db:
        plan_id = legacy.db.execute(
            "INSERT INTO folder_sync_plans(folder_id,path,fingerprint,folder_revision,scan_metadata,state,phase,revision,"
            "file_count,directory_count,directories_done,scanned,checked,counts,selected_counts,created) "
            "VALUES(?,?,?,?,0,'ready','files',4,1,1,1,1,1,?,?,1)",
            (folder_id, str(root), json.dumps(directory_identity(root)), folder_revision,
             json.dumps({'new': 1}), json.dumps({'new': 1})),
        ).lastrowid
        legacy.db.execute(
            'INSERT INTO folder_sync_directories(plan_id,path,fingerprint,done) VALUES(?,?,?,1)',
            (plan_id, str(root), json.dumps(directory_identity(root))),
        )
        legacy.db.execute(
            "INSERT INTO folder_sync_files(plan_id,path,source_id,state,selected,bytes,mtime,fingerprints,patch,clock,notes,error) "
            "VALUES(?,?,0,'new',1,?,?,?,?,?,'[]','')",
            (plan_id, str(candidate), candidate_stat.st_size, candidate_stat.st_mtime_ns,
             json.dumps(observation['fingerprints']), json.dumps(observation['patch']),
             json.dumps(observation['clock'])),
        )
    assert legacy.db.execute('PRAGMA user_version').fetchone()[0] == 36
    legacy.close()

    service = Service(catalog_root)
    try:
        expected_name = candidate.name
        with service.catalog() as upgraded:
            assert upgraded.db.execute('PRAGMA user_version').fetchone()[0] == 37
            assert upgraded.db.execute(
                'SELECT duplicate_detection FROM folder_sync_plans WHERE id=?', (plan_id,),
            ).fetchone()[0] == 0
            staged = upgraded.db.execute(
                'SELECT name FROM folder_sync_files WHERE plan_id=?', (plan_id,),
            ).fetchone()
            assert staged['name'] == ''

        # Old ready plans can contain incomplete or untrusted staged names. The
        # eventual catalog identity must come from the checked source path.
        forged_stage_name = 'untrusted-staging-name.jpg'
        with service.catalog() as upgraded, upgraded.db:
            upgraded.db.execute('UPDATE folder_sync_files SET name=? WHERE plan_id=?',
                                (forged_stage_name, plan_id))
            assert upgraded.db.execute(
                'SELECT name FROM folder_sync_files WHERE plan_id=?', (plan_id,),
            ).fetchone()[0] == forged_stage_name

        applied = service.dispatch('apply_folder_sync', {
            'plan_id': plan_id,
            'expected_revision': 4,
            'import_new': True,
            'remove_missing': False,
            'read_metadata': False,
        })['plan']
        assert applied['state'] == 'applied'
        assert applied['imported'] == 1
        with service.catalog() as upgraded:
            physical = upgraded.db.execute(
                'SELECT id,name,original_name,is_virtual FROM photos WHERE path=?',
                (str(candidate),),
            ).fetchone()
            assert tuple(physical[key] for key in ('name', 'original_name', 'is_virtual')) == (
                expected_name, expected_name, 0,
            )
            physical_id = physical['id']

        master = service.dispatch('get_photo', {'photo_id': physical_id})
        copied = service.dispatch('create_virtual_copies', {'targets': [{
            'photo_id': physical_id,
            'expected_revision': master['revision'],
            'expected_metadata_revision': master['metadata_revision'],
        }]})['photos'][0]
        with service.catalog() as upgraded:
            virtual = upgraded.db.execute(
                'SELECT name,original_name,is_virtual FROM photos WHERE id=?', (copied['id'],),
            ).fetchone()
            assert tuple(virtual) == (expected_name, expected_name, 1)
        assert hashlib.sha256(candidate.read_bytes()).digest() == original_hash
    finally:
        service.close()


def test_genuine_v36_pending_plan_resumes_with_legacy_new_file_semantics(tmp_path, monkeypatch):
    import lumaraw.catalog as catalog_module
    from legacy_catalog import migrate_to, seed_photo
    from lumaraw.capture_time import read_capture_time
    from lumaraw.folder_sync_io import directory_identity

    original = camera_jpeg(tmp_path / 'External' / 'legacy-match.jpg')
    root = tmp_path / 'Photos'
    root.mkdir()
    candidate = root / 'legacy-match.jpg'
    shutil.copyfile(original, candidate)
    anchor = root / 'anchor.png'
    Image.new('RGB', (12, 8), 'gray').save(anchor)
    original_hash = hashlib.sha256(original.read_bytes()).digest()
    candidate_hash = hashlib.sha256(candidate.read_bytes()).digest()

    with monkeypatch.context() as patch:
        patch.setattr(catalog_module, 'migrate', lambda db: migrate_to(db, 36))
        catalog = Catalog(tmp_path / 'schema-36-resume')
    original_id = seed_photo(catalog.db, original)
    seed_photo(catalog.db, anchor)
    clock = read_capture_time(original)
    with catalog.db:
        catalog.db.execute('UPDATE photos SET taken=?,taken_us=?,taken_submicro=?,capture_clock=?,camera=? WHERE id=?',
                           (clock['taken'], clock['taken_us'], clock['taken_submicro'],
                            clock['capture_clock'], clock['camera'], original_id))
    with catalog.db:
        folder_id = catalog.db.execute('SELECT id FROM catalog_folders WHERE path=?',
                                        (str(root),)).fetchone()[0]
        folder_revision = catalog.db.execute('SELECT revision FROM folder_state WHERE id=1').fetchone()[0]
        plan_id = catalog.db.execute(
            "INSERT INTO folder_sync_plans(folder_id,path,fingerprint,folder_revision,scan_metadata,state,phase,revision,"
            "file_count,directory_count,directories_done,scanned,checked,counts,selected_counts,created) "
            "VALUES(?,?,?,?,1,'planning','files',4,1,1,1,0,0,'{}','{}',1)",
            (folder_id, str(root), json.dumps(directory_identity(root)), folder_revision),
        ).lastrowid
        catalog.db.execute(
            "INSERT INTO folder_sync_files(plan_id,path,source_id,state,selected,bytes,mtime,fingerprints,patch,clock,notes,error) "
            "VALUES(?,?,0,'pending',1,0,0,'{}','{}','{}','[]','')",
            (plan_id, str(candidate)),
        )
        identity_before = tuple(catalog.db.execute(
            'SELECT original_name,bytes,capture_clock,taken_us,taken_submicro FROM photos WHERE path=?',
            (str(original),),
        ).fetchone())
    assert catalog.db.execute('PRAGMA user_version').fetchone()[0] == 36
    catalog.close()

    service = Service(tmp_path / 'schema-36-resume')
    try:
        loaded = service.dispatch('get_folder_sync', {'plan_id': plan_id})['plan']
        assert loaded['duplicate_detection'] == 0 and loaded['state'] == 'planning'
        loaded = scan(service, loaded)
        row = next(item for item in items(service, loaded) if item['path'] == str(candidate))
        assert row['state'] == 'new'
        assert row['duplicate_match'] == '' and row['duplicate_of_path'] == ''
        with service.catalog() as upgraded:
            staged_identity = tuple(upgraded.db.execute(
                'SELECT name,bytes,capture_clock,taken_us,taken_submicro FROM folder_sync_files WHERE id=?',
                (row['id'],),
            ).fetchone())
            assert staged_identity == identity_before

        done = apply(service, loaded)
        assert done['state'] == 'applied' and done['imported'] == 1
        with service.catalog() as upgraded:
            assert upgraded.db.execute('SELECT count(*) FROM photos WHERE path IN (?,?)',
                                       (str(original), str(candidate))).fetchone()[0] == 2
            assert tuple(upgraded.db.execute(
                'SELECT original_name,bytes,capture_clock,taken_us,taken_submicro FROM photos WHERE path=?',
                (str(original),),
            ).fetchone()) == identity_before
        assert hashlib.sha256(original.read_bytes()).digest() == original_hash
        assert hashlib.sha256(candidate.read_bytes()).digest() == candidate_hash
    finally:
        service.close()


def test_folder_sync_duplicate_and_changes_queries_use_bounded_indexes(tmp_path):
    source = camera_jpeg(tmp_path / 'External' / 'same.jpg')
    service, root, _ = library(tmp_path, [source])
    try:
        candidate = root / 'nested' / 'same.jpg'
        candidate.parent.mkdir()
        shutil.copyfile(source, candidate)
        plan = scan(service, prepare(service, root))
        with service.catalog() as catalog:
            db = catalog.db
            staged = db.execute('SELECT id,taken_us FROM folder_sync_files WHERE path=?',
                                (str(candidate),)).fetchone()
            original = db.execute('SELECT taken_us FROM photos WHERE path=?',
                                 (str(source),)).fetchone()
            def plan_for(sql, params):
                return ' '.join(row['detail'] for row in db.execute('EXPLAIN QUERY PLAN ' + sql, params))

            changed = plan_for(
                "SELECT id,path,source_id,state,selected,duplicate_match,duplicate_of_path,patch,clock,notes,error "
                "FROM folder_sync_files AS f WHERE plan_id=? "
                "AND state IN ('new','duplicate','missing','updated','error') ORDER BY id LIMIT 60 OFFSET 0",
                (plan['id'],),
            )
            duplicate_page = plan_for(
                "SELECT id,path FROM folder_sync_files WHERE plan_id=? AND state='duplicate' ORDER BY id LIMIT 60",
                (plan['id'],),
            )
            plan_match = plan_for(
                "SELECT path FROM folder_sync_files WHERE plan_id=? AND name=? AND bytes=? AND capture_clock=? "
                "AND taken_us=? AND taken_submicro=? AND id<? AND state IN ('new','duplicate') ORDER BY id LIMIT 1",
                (plan['id'], 'same.jpg', candidate.stat().st_size, 'utc',
                 staged['taken_us'], '789', staged['id']),
            )
            catalog_match = plan_for(
                "SELECT path FROM photos WHERE is_virtual=0 AND original_name=? AND bytes=? AND capture_clock=? "
                "AND taken_us=? AND taken_submicro=? ORDER BY id LIMIT 1",
                ('same.jpg', source.stat().st_size, 'utc', original['taken_us'], '789'),
            )
        assert 'folder_sync_changes' in changed and 'SCAN folder_sync_files' not in changed
        assert 'folder_sync_file_state' in duplicate_page and 'folder_sync_file_page' not in duplicate_page
        assert 'folder_sync_file_duplicate' in plan_match and 'SCAN folder_sync_files' not in plan_match
        assert 'photo_import_duplicate' in catalog_match and 'SCAN photos' not in catalog_match
    finally:
        service.close()
