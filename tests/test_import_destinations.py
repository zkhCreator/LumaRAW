"""Selected destination-folder summaries for reviewed Copy imports.

Inputs: captured source clocks/layouts, selection and duplicate choices, and
revision-bound cursor requests. Outputs: bounded primary-folder counts plus an
independent second-copy total. Tests cover catalog-only reads and schema 31
upgrade behavior; they do not claim desktop interaction or Adobe menu parity.
"""
import json
import shutil
import sqlite3
from pathlib import Path

import jsonschema
import pytest

from lumaraw import catalog as catalog_module
from lumaraw import filename_templates as names
from lumaraw.catalog import Catalog
from lumaraw.service import Service
from test_import_review import library, picture, prepare, scan
from test_xmp_read import packet
from legacy_catalog import migrate_to


def copy_ready(service, sources, destination, **options):
    destination.mkdir(parents=True, exist_ok=True)
    return scan(service, prepare(service, sources, mode='copy',
                                 destination=str(destination), **options))


def destinations(service, plan, after=None):
    request = {'plan_id': plan['id'], 'expected_revision': plan['revision']}
    if after is not None:
        request['after'] = after
    return service.dispatch('get_import_destinations', request)


@pytest.mark.parametrize(('organization', 'date_format', 'relative'), [
    ('flat', 'year_date', 'Collection'),
    ('source', 'year_date', 'Collection/相册/子目录'),
    ('date', 'year_date', 'Collection/2026/2026-09-28'),
    ('date', 'year_month_day', 'Collection/2026/09/28'),
    ('date', 'date', 'Collection/2026-09-28'),
])
def test_groups_follow_captured_primary_layout_without_filename(library, organization, date_format, relative):
    service, root = library
    source_root = root/'相册'
    photo = picture(source_root/'子目录'/'原片.jpg')
    destination = root/'主目录'
    plan = copy_ready(service, [source_root], destination,
                      organization=organization, date_format=date_format,
                      subfolder='Collection')

    result = destinations(service, plan)
    assert result == {
        'plan_id': plan['id'], 'revision': plan['revision'],
        'destination': str(destination), 'selected_count': 1,
        'items': [{'relative_path': relative,
                   'path': str(destination/relative), 'photo_count': 1}],
        'next_after': None, 'page_size': 60, 'backup': None,
    }
    assert not list(destination.rglob('*'))
    assert photo.is_file()


def test_unknown_date_and_unicode_subfolder_are_preserved(library):
    service, root = library
    source_root = root/'摄影'/'输入'
    picture(source_root/'夏天.jpg', clock=False)
    destination = root/'输出'
    plan = copy_ready(service, [source_root], destination,
                      organization='date', date_format='date', subfolder='旅行')

    result = destinations(service, plan)
    assert result['items'] == [{'relative_path': '旅行/Unknown Date',
                                'path': str(destination/'旅行'/'Unknown Date'),
                                'photo_count': 1}]
    assert result['selected_count'] == 1


def test_folder_counts_track_checkbox_and_duplicate_policy(library):
    service, root = library
    cataloged = picture(root/'cataloged'/'same.jpg')
    service.dispatch('import_photos', {'paths': [str(cataloged)]})
    incoming = root/'incoming'
    duplicate = incoming/'same.jpg'
    duplicate.parent.mkdir()
    shutil.copy2(cataloged, duplicate)
    new_photo = picture(incoming/'new.jpg', clock=False)
    destination = root/'destination'
    plan = copy_ready(service, [incoming], destination, organization='flat')

    initial = destinations(service, plan)
    assert initial['selected_count'] == 1
    assert initial['items'] == [{'relative_path': '',
                                'path': str(destination), 'photo_count': 1}]
    assert plan['selected_bytes'] == new_photo.stat().st_size
    review = service.dispatch('get_import', {'plan_id': plan['id'], 'kind': 'all'})
    duplicate_item = next(item for item in review['items'] if item['state'] == 'duplicate')
    with pytest.raises(ValueError, match='selectable'):
        service.dispatch('select_import_items', {
            'plan_id': plan['id'], 'expected_revision': plan['revision'],
            'item_ids': [duplicate_item['id']], 'selected': False,
        })
    unchanged = service.dispatch('get_import')['plan']
    assert (unchanged['selected_count'], unchanged['selected_bytes']) == (
        1, new_photo.stat().st_size)

    plan = service.dispatch('set_import_options', {
        'plan_id': plan['id'], 'expected_revision': plan['revision'],
        'skip_duplicates': False,
    })['plan']
    included = destinations(service, plan)
    assert included['selected_count'] == 2
    assert included['items'][0]['photo_count'] == 2
    assert plan['selected_bytes'] == duplicate.stat().st_size + new_photo.stat().st_size

    review = service.dispatch('get_import', {'plan_id': plan['id'], 'kind': 'all'})
    new_item = next(item for item in review['items'] if item['state'] == 'new')
    plan = service.dispatch('select_import_items', {
        'plan_id': plan['id'], 'expected_revision': plan['revision'],
        'item_ids': [new_item['id']], 'selected': False,
    })['plan']
    unchecked = destinations(service, plan)
    assert unchecked['selected_count'] == 1
    assert unchecked['items'][0]['photo_count'] == 1
    assert plan['selected_bytes'] == duplicate.stat().st_size

    plan = service.dispatch('set_import_options', {
        'plan_id': plan['id'], 'expected_revision': plan['revision'],
        'skip_duplicates': True,
    })['plan']
    excluded = destinations(service, plan)
    assert excluded['selected_count'] == 0
    assert excluded['items'] == []
    assert plan['selected_bytes'] == 0
    assert duplicate.is_file() and new_photo.is_file()


def test_xmp_and_second_copy_do_not_add_destination_photo_counts(library):
    service, root = library
    source_root = root/'原片'
    photo = picture(source_root/'照片.jpg')
    sidecar = photo.with_suffix('.xmp')
    sidecar.write_bytes(packet('<dc:title>Sidecar</dc:title>'))
    primary = root/'primary'
    backup = root/'secondary'
    primary.mkdir()
    backup.mkdir()
    plan = copy_ready(service, [source_root], primary, organization='flat',
                      subfolder='Album')
    plan = service.dispatch('set_import_backup', {
        'plan_id': plan['id'], 'expected_revision': plan['revision'],
        'destination': str(backup),
    })['plan']

    result = destinations(service, plan)
    assert result['selected_count'] == 1
    assert result['items'] == [{'relative_path': 'Album',
                                'path': str(primary/'Album'), 'photo_count': 1}]
    assert result['backup']['destination'] == str(backup)
    assert result['backup']['subfolder'].startswith('Imported on ')
    assert result['backup']['photo_count'] == 1
    assert not list(primary.rglob('*')) and not list(backup.rglob('*'))
    assert photo.is_file() and sidecar.is_file()


def test_filename_renaming_does_not_change_folder_groups(library):
    service, root = library
    source_root = root/'source'/'nested'
    picture(source_root/'original.jpg')
    destination = root/'destination'
    plan = copy_ready(service, [source_root.parent], destination,
                      organization='source', subfolder='Album')
    before = destinations(service, plan)
    settings = {**names.defaults(), 'enabled': True,
                'template': names.builtins()[2]['template'], 'custom_text': '旅行'}
    service.dispatch('set_import_naming', {
        'plan_id': plan['id'], 'expected_revision': plan['revision'],
        'settings': settings,
    })
    changed_plan = service.dispatch('get_import')['plan']
    after = destinations(service, changed_plan)

    assert after['items'] == before['items']
    assert after['selected_count'] == before['selected_count']
    preview = service.dispatch('get_import', {'plan_id': plan['id'], 'kind': 'all'})
    assert Path(preview['items'][0]['destination']).name != 'original.jpg'


@pytest.mark.parametrize('folder_count', [60, 61])
def test_binary_keyset_pages_have_exact_boundary_and_accept_empty_cursor(library, folder_count):
    service, root = library
    source_root = root/'source'
    for index in range(folder_count):
        picture(source_root/f'folder-{index:03}'/'photo.jpg', clock=False)
    destination = root/'destination'
    plan = copy_ready(service, [source_root], destination, organization='source')
    expected = [f'source/folder-{index:03}' for index in range(folder_count)]

    first = destinations(service, plan)
    assert [item['relative_path'] for item in first['items']] == expected[:60]
    assert len(first['items']) == min(folder_count, 60)
    assert first['next_after'] == (expected[59] if folder_count > 60 else None)

    # Empty is a legal cursor value; all these source-relative keys sort after it.
    empty_cursor = destinations(service, plan, after='')
    assert [item['relative_path'] for item in empty_cursor['items']] == expected[:60]

    if folder_count > 60:
        last = destinations(service, plan, after=first['next_after'])
        assert [item['relative_path'] for item in last['items']] == expected[60:]
        assert last['next_after'] is None


def test_destination_read_requires_current_ready_copy_revision(library):
    service, root = library
    source = picture(root/'source'/'a.jpg')
    destination = root/'destination'
    plan = copy_ready(service, [source], destination)
    stale = plan
    plan = service.dispatch('set_import_options', {
        'plan_id': plan['id'], 'expected_revision': plan['revision'],
        'skip_duplicates': False,
    })['plan']
    with pytest.raises(ValueError, match='changed'):
        destinations(service, stale)

    service.dispatch('cancel_import', {'plan_id': plan['id']})
    add_plan = scan(service, prepare(service, [source]))
    with pytest.raises(ValueError, match='Copy'):
        service.dispatch('get_import_destinations', {
            'plan_id': add_plan['id'], 'expected_revision': add_plan['revision'],
        })
    service.dispatch('cancel_import', {'plan_id': add_plan['id']})

    pending = prepare(service, [source], mode='copy', destination=str(destination))
    with pytest.raises(ValueError, match='changed'):
        service.dispatch('get_import_destinations', {
            'plan_id': pending['id'], 'expected_revision': pending['revision'],
        })


@pytest.mark.parametrize('after', [1, 'x'*4097])
def test_destination_cursor_schema_rejects_invalid_values(library, after):
    service, root = library
    source = picture(root/'source.jpg')
    plan = copy_ready(service, [source], root/'destination')
    with pytest.raises(jsonschema.ValidationError):
        service.dispatch('get_import_destinations', {
            'plan_id': plan['id'], 'expected_revision': plan['revision'],
            'after': after,
        })
    assert destinations(service, plan, after='x'*4096)['items'] == []


def _schema31_catalog(root, monkeypatch):
    with monkeypatch.context() as context:
        context.setattr(catalog_module, 'migrate', lambda db: migrate_to(db, 31))
        return Catalog(root)


def _seed_frozen_schema31_copy(catalog):
    db = catalog.db
    plan_id = db.execute(
        "INSERT INTO import_plans(state,phase,revision,include_subfolders,file_count,selected_count,created) "
        "VALUES('interrupted','copying',7,1,3,2,1)"
    ).lastrowid
    source = '/missing-source/source'
    db.execute(
        'INSERT INTO import_copy_plans(plan_id,destination,destination_identity,organization,subfolder,roots,owner,date_format) '
        'VALUES(?,?,?,?,?,?,?,?)',
        (plan_id, '/missing-destination', '[]', 'date', 'Album', json.dumps([source]),
         str(catalog.root), 'date'),
    )
    clocks = (
        {'capture_civil': {'year': '2026', 'month': '9', 'day': '28'}},
        {'capture_civil': {'year': '2026', 'month': '10', 'day': '2'}},
        {},
    )
    rows = (
        (f'{source}/one.jpg', 'one.jpg', 'new', 1, clocks[0]),
        (f'{source}/two.jpg', 'two.jpg', 'duplicate', 1, clocks[1]),
        (f'{source}/three.jpg', 'three.jpg', 'new', 0, clocks[2]),
    )
    db.executemany(
        'INSERT INTO import_files(plan_id,path,name,extension,state,selected,clock) '
        'VALUES(?,?,?,\'jpg\',?,?,?)',
        ((plan_id, path, name, state, selected, json.dumps(clock))
         for path, name, state, selected, clock in rows),
    )
    old_target = '/missing-destination/Album/2026/2026-09-28/one.jpg'
    db.execute(
        'INSERT INTO import_transfers(plan_id,source,target,target_key,source_identity,temporary,state) '
        'VALUES(?,?,?,?,?,?,?)',
        (plan_id, rows[0][0], old_target, old_target.lower(), '[]', '.owned.part', 'published'),
    )
    db.commit()
    return plan_id, old_target


def test_schema31_backfill_is_atomic_idempotent_and_keeps_frozen_journals(tmp_path, monkeypatch):
    catalog = _schema31_catalog(tmp_path/'schema31', monkeypatch)
    try:
        plan_id, old_target = _seed_frozen_schema31_copy(catalog)
        before_plan = tuple(catalog.db.execute(
            'SELECT state,phase,revision FROM import_plans WHERE id=?', (plan_id,)
        ).fetchone())
        before_transfer = tuple(catalog.db.execute(
            'SELECT source,target,target_key,state,temporary FROM import_transfers WHERE plan_id=?',
            (plan_id,),
        ).fetchone())

        from lumaraw import import_destinations
        catalog.db.set_authorizer(
            lambda action, arg1, arg2, db_name, trigger:
                sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_CREATE_TABLE and
                arg1 == 'import_destination_groups' else sqlite3.SQLITE_OK
        )
        with pytest.raises(sqlite3.DatabaseError):
            import_destinations.migrate(catalog.db)
        catalog.db.set_authorizer(None)
        assert catalog.db.execute('PRAGMA user_version').fetchone()[0] == 31
        assert 'destination_directory' not in {
            row[1] for row in catalog.db.execute('PRAGMA table_info(import_files)')
        }
        assert catalog.db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='import_destination_groups'"
        ).fetchone() is None
        assert tuple(catalog.db.execute(
            'SELECT state,phase,revision FROM import_plans WHERE id=?', (plan_id,)
        ).fetchone()) == before_plan
        assert tuple(catalog.db.execute(
            'SELECT source,target,target_key,state,temporary FROM import_transfers WHERE plan_id=?',
            (plan_id,),
        ).fetchone()) == before_transfer

        def reject_filesystem(*args, **kwargs):
            raise AssertionError('Schema backfill must not access the filesystem')

        with monkeypatch.context() as fs_guard:
            fs_guard.setattr(Path, 'stat', reject_filesystem)
            fs_guard.setattr(Path, 'mkdir', reject_filesystem)
            fs_guard.setattr(Path, 'open', reject_filesystem)
            import_destinations.migrate(catalog.db)
            import_destinations.migrate(catalog.db)
        assert catalog.db.execute('PRAGMA user_version').fetchone()[0] == 32
        assert [tuple(row) for row in catalog.db.execute(
            'SELECT directory,new_count,duplicate_count FROM import_destination_groups '
            'WHERE plan_id=? ORDER BY directory COLLATE BINARY', (plan_id,)
        ).fetchall()] == [
            ('Album/2026-09-28', 1, 0),
            ('Album/2026-10-02', 0, 1),
        ]
        assert [tuple(row) for row in catalog.db.execute(
            'SELECT destination_directory FROM import_files WHERE plan_id=? ORDER BY id',
            (plan_id,),
        ).fetchall()] == [
            ('Album/2026-09-28',),
            ('Album/2026-10-02',),
            ('Album/Unknown Date',),
        ]
        assert tuple(catalog.db.execute(
            'SELECT state,phase,revision FROM import_plans WHERE id=?', (plan_id,)
        ).fetchone()) == before_plan
        assert tuple(catalog.db.execute(
            'SELECT source,target,target_key,state,temporary FROM import_transfers WHERE plan_id=?',
            (plan_id,),
        ).fetchone()) == before_transfer
        assert before_transfer[1] == old_target
    finally:
        catalog.close()


def test_large_schema31_backfill_rolls_back_after_first_page_and_reads_legacy_clock(tmp_path, monkeypatch):
    catalog = _schema31_catalog(tmp_path/'large-schema31', monkeypatch)
    try:
        db = catalog.db
        plan_id = db.execute(
            "INSERT INTO import_plans(state,phase,revision,include_subfolders,file_count,selected_count,created) "
            "VALUES('interrupted','copying',9,1,125,125,1)"
        ).lastrowid
        source = '/missing-large-source/source'
        db.execute(
            'INSERT INTO import_copy_plans(plan_id,destination,destination_identity,organization,subfolder,roots,owner,date_format) '
            'VALUES(?,?,?,?,?,?,?,?)',
            (plan_id, '/missing-large-destination', '[]', 'date', 'Album',
             json.dumps([source]), str(catalog.root), 'date'),
        )
        db.execute('UPDATE import_sequence_state SET revision=8,next_import=700,next_image=900')
        db.execute('INSERT INTO import_sequence_plans VALUES(?,?,?,?,?,1)',
                   (plan_id, 8, 699, 775, 125))
        files = []
        for index in range(125):
            if index == 0:
                clock = {'capture_date': '2026/2026-09-28'}
            else:
                clock = {'capture_civil': {
                    'year': '2026', 'month': '10', 'day': f'{(index % 28) + 1:02}',
                }}
            path = f'{source}/folder-{index:03}/photo.jpg'
            files.append((plan_id, path, f'photo-{index:03}.jpg', 'new', 1,
                          json.dumps(clock)))
        db.executemany(
            'INSERT INTO import_files(plan_id,path,name,extension,state,selected,clock) '
            'VALUES(?,?,?,\'jpg\',?,?,?)', files,
        )
        old_target = '/missing-large-destination/Album/2026/2026-09-28/photo.jpg'
        db.execute(
            'INSERT INTO import_transfers(plan_id,source,target,target_key,source_identity,temporary,state) '
            'VALUES(?,?,?,?,?,?,?)',
            (plan_id, files[0][1], old_target, old_target.lower(), '[]', '.frozen.part', 'published'),
        )
        db.commit()

        from lumaraw import import_copy, import_destinations
        original_directory = import_copy.relative_directory
        calls, processed = [0], []

        def interrupt_at_second_page(copy, row):
            calls[0] += 1
            if calls[0] == 61:
                processed.append(db.execute(
                    'SELECT count(*) FROM import_files WHERE plan_id=? AND destination_directory IS NOT NULL',
                    (plan_id,),
                ).fetchone()[0])
                raise RuntimeError('injected backfill interruption')
            return original_directory(copy, row)

        monkeypatch.setattr(import_copy, 'relative_directory', interrupt_at_second_page)

        def reject_filesystem(*args, **kwargs):
            raise AssertionError('Schema backfill must not access the filesystem')

        before_sequence = tuple(db.execute(
            'SELECT revision,next_import,next_image FROM import_sequence_state WHERE id=1'
        ).fetchone())
        before_reservation = tuple(db.execute(
            'SELECT revision,import_number,image_number,image_count,frozen '
            'FROM import_sequence_plans WHERE plan_id=?', (plan_id,)
        ).fetchone())
        before_transfer = tuple(db.execute(
            'SELECT source,target,target_key,state,temporary FROM import_transfers WHERE plan_id=?',
            (plan_id,),
        ).fetchone())

        with monkeypatch.context() as fs_guard:
            fs_guard.setattr(Path, 'stat', reject_filesystem)
            fs_guard.setattr(Path, 'mkdir', reject_filesystem)
            fs_guard.setattr(Path, 'open', reject_filesystem)
            with pytest.raises(RuntimeError, match='injected'):
                import_destinations.migrate(db)
        assert calls[0] == 61 and processed == [60]
        assert db.execute('PRAGMA user_version').fetchone()[0] == 31
        assert 'destination_directory' not in {
            row[1] for row in db.execute('PRAGMA table_info(import_files)')
        }
        assert db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='import_destination_groups'"
        ).fetchone() is None
        assert tuple(db.execute(
            'SELECT revision,next_import,next_image FROM import_sequence_state WHERE id=1'
        ).fetchone()) == before_sequence
        assert tuple(db.execute(
            'SELECT revision,import_number,image_number,image_count,frozen '
            'FROM import_sequence_plans WHERE plan_id=?', (plan_id,)
        ).fetchone()) == before_reservation
        assert tuple(db.execute(
            'SELECT source,target,target_key,state,temporary FROM import_transfers WHERE plan_id=?',
            (plan_id,),
        ).fetchone()) == before_transfer

        monkeypatch.setattr(import_copy, 'relative_directory', original_directory)
        with monkeypatch.context() as fs_guard:
            fs_guard.setattr(Path, 'stat', reject_filesystem)
            fs_guard.setattr(Path, 'mkdir', reject_filesystem)
            fs_guard.setattr(Path, 'open', reject_filesystem)
            import_destinations.migrate(db)
            import_destinations.migrate(db)
        assert db.execute('PRAGMA user_version').fetchone()[0] == 32
        assert db.execute(
            'SELECT destination_directory FROM import_files WHERE plan_id=? ORDER BY id LIMIT 1',
            (plan_id,),
        ).fetchone()[0] == 'Album/2026-09-28'
        assert db.execute(
            'SELECT sum(new_count) FROM import_destination_groups WHERE plan_id=?', (plan_id,)
        ).fetchone()[0] == 125
        assert tuple(db.execute(
            'SELECT revision,next_import,next_image FROM import_sequence_state WHERE id=1'
        ).fetchone()) == before_sequence
        assert tuple(db.execute(
            'SELECT revision,import_number,image_number,image_count,frozen '
            'FROM import_sequence_plans WHERE plan_id=?', (plan_id,)
        ).fetchone()) == before_reservation
        assert tuple(db.execute(
            'SELECT source,target,target_key,state,temporary FROM import_transfers WHERE plan_id=?',
            (plan_id,),
        ).fetchone()) == before_transfer
    finally:
        catalog.close()
