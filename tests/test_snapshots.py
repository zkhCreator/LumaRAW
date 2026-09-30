"""Shared snapshots across revision conflicts, paging, migration and restoration.

Generated originals and disposable catalogs prove frozen settings, independent
history/Before/export state, stable identities and bounded summary reads. These
tests do not establish Adobe processing, sidecar exchange or native UI behavior.
"""
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from PIL import Image
import pytest

from lumaraw.api import TOOLS
from lumaraw.before_after import BeforeAfter
from lumaraw.catalog import Catalog
from lumaraw.model import Recipe
from lumaraw.service import Service
from lumaraw.snapshots import Snapshots, migrate
from legacy_catalog import migrate_to, seed_photo


@pytest.fixture
def library(tmp_path):
    paths = [tmp_path / f'original-{i}.png' for i in range(2)]
    for path, color in zip(paths, ['navy', 'orange']):
        Image.new('RGB', (96, 64), color).save(path)
    service = Service(tmp_path / 'catalog', presets_root=tmp_path / 'presets')
    service.dispatch('queue_control', {'action': 'pause'})
    service.dispatch('import_photos', {'paths': list(map(str, paths))})
    yield service, paths
    service.close()


def photo(s, id_=1):
    return s.dispatch('get_photo', {'photo_id': id_})


def create(s, name='Snapshot', id_=1, **extra):
    return s.dispatch('save_version', {'photo_id': id_, 'name': name,
        'expected_revision': photo(s, id_)['revision'], **extra})['version']


def edit(s, id_=1, **patch):
    return s.dispatch('edit_photo', {'photo_id': id_, 'expected_revision': photo(s, id_)['revision'], 'patch': patch})


def target(row, id_=1):
    return {'photo_id': id_, 'version_id': row['id'], 'expected_version_revision': row['revision']}


def test_current_and_history_creation_preserve_cursor_redo_and_before(library):
    s, paths = library
    original = paths[0].read_bytes()
    edit(s, exposure=1, crop='1:1', monochrome=True, blue_bw=-20)
    first = s.dispatch('list_history', {'photo_id': 1, 'expected_revision': 1})['cursor']
    saved = create(s, 'Current')
    edit(s, exposure=2)
    current = photo(s)
    history = s.dispatch('list_history', {'photo_id': 1, 'expected_revision': current['revision']})
    earlier = create(s, 'Earlier', step_id=first)
    assert photo(s) == current
    assert s.dispatch('list_history', {'photo_id': 1, 'expected_revision': current['revision']}) == history
    with s.catalog() as c:
        assert Snapshots(c.db).value(1, earlier['id'])[0].dict() == Snapshots(c.db).value(1, saved['id'])[0].dict()
        assert BeforeAfter(c.db).read(1)[0].exposure == 0
    s.dispatch('undo_photo', {'photo_id': 1, 'expected_revision': current['revision']})
    create(s, 'During redo')
    s.dispatch('redo_photo', {'photo_id': 1, 'expected_revision': photo(s)['revision']})
    assert photo(s)['recipe']['exposure'] == 2 and paths[0].read_bytes() == original


def test_shared_update_rename_restore_and_frozen_before_exports(library, tmp_path):
    s, paths = library
    originals = [p.read_bytes() for p in paths]
    source = photo(s)
    copy_id = s.dispatch('create_virtual_copies', {'targets': [{'photo_id': 1,
        'expected_revision': source['revision'], 'expected_metadata_revision': source['metadata_revision']}]})['photos'][0]['id']
    edit(s, id_=copy_id, exposure=1, crop_box=[.1, .2, .8, .9])
    row = create(s, 'Shared', id_=copy_id)
    assert s.dispatch('list_versions', {'photo_id': 1})['versions'][0] == row
    s.dispatch('before_after', {**target(row), 'expected_revision': photo(s)['revision'], 'action': 'snapshot_to_before'})
    job = s.dispatch('enqueue_exports', {'photo_ids': [copy_id], 'destination': str(tmp_path / 'exports'),
        'format': 'jpeg', 'request_key': 'snapshot-frozen'})['job_ids'][0]
    edit(s, exposure=2)
    current = photo(s)
    updated = s.dispatch('update_version', {**target(row), 'expected_revision': current['revision']})['version']
    assert updated['revision'] == row['revision']+1 and updated['created'] == row['created']
    assert photo(s) == current
    with s.catalog() as c:
        assert BeforeAfter(c.db).read(1)[0].exposure == 1
    assert s.dispatch('get_job', {'job_id': job})['recipe']['exposure'] == 1
    renamed = s.dispatch('rename_version', {**target(updated), 'name': 'Bright'})['version']
    assert renamed['revision'] == 2
    s.dispatch('restore_version', {**target(renamed, copy_id), 'expected_revision': photo(s, copy_id)['revision']})
    assert photo(s, copy_id)['recipe']['exposure'] == 2
    s.dispatch('undo_photo', {'photo_id': copy_id, 'expected_revision': photo(s, copy_id)['revision']})
    assert photo(s, copy_id)['recipe']['exposure'] == 1
    assert [p.read_bytes() for p in paths] == originals


def test_snapshot_only_asset_backup_restores_revisions_names_and_counter(library, tmp_path):
    s, paths = library
    original = paths[0].read_bytes()
    cube = tmp_path / 'identity.cube'
    cube.write_text('LUT_3D_SIZE 2\n0 0 0\n1 0 0\n0 1 0\n1 1 0\n0 0 1\n1 0 1\n0 1 1\n1 1 1\n')
    asset = s.dispatch('import_asset', {'path': str(cube), 'kind': 'lut'})['asset']
    edit(s, lut=asset)
    row = create(s, 'LUT only in snapshot')
    row = s.dispatch('rename_version', {**target(row), 'name': 'Retained LUT'})['version']
    deleted = create(s, 'Deleted identity')
    s.dispatch('delete_version', target(deleted))
    edit(s, lut={})
    s.dispatch('clear_history', {'photo_id': 1, 'expected_revision': photo(s)['revision']})
    before = s.dispatch('list_versions', {'photo_id': 1})
    backup = tmp_path / 'backup.sqlite'; dest = tmp_path / 'restored'
    s.dispatch('backup_catalog', {'path': str(backup)})
    s.dispatch('restore_catalog', {'path': str(backup), 'destination': str(dest)})
    with closing(Catalog(dest)) as c:
        assert Snapshots(c.db).page(1) == before
        recipe, name = Snapshots(c.db).value(1, row['id'], row['revision'])
        assert name == 'Retained LUT' and Path(recipe.lut['path']).parent == dest / 'assets'
        assert Path(recipe.lut['path']).read_bytes() == cube.read_bytes()
        assert c.save_version(1, 'After restore')['version']['id'] > deleted['id']
    assert paths[0].read_bytes() == original


@pytest.mark.parametrize('method', ['rename_version', 'update_version', 'delete_version', 'restore_version', 'before_after'])
def test_stale_snapshot_and_cross_family_actions_fail_without_effects(library, method):
    s, _ = library
    row = create(s)
    renamed = s.dispatch('rename_version', {**target(row), 'name': 'Renamed'})['version']
    args = target(row)
    if method == 'rename_version': args['name'] = 'Stale'
    if method in ('update_version', 'restore_version', 'before_after'): args['expected_revision'] = photo(s)['revision']
    if method == 'before_after': args['action'] = 'snapshot_to_before'
    before = photo(s)
    with pytest.raises(ValueError, match='Snapshot conflict'):
        s.dispatch(method, args)
    args.update(target(renamed, 2))
    with pytest.raises(ValueError, match='does not exist'):
        s.dispatch(method, args)
    assert photo(s) == before and s.dispatch('list_versions', {'photo_id': 1})['versions'] == [renamed]


def test_photo_conflict_names_noops_and_legacy_commands(library):
    s, _ = library
    row = create(s, '  Cafe\u0301  ')
    assert row['name'] == 'Café'
    with pytest.raises(ValueError, match='already exists'): create(s, 'CAFÉ')
    with pytest.raises(ValueError, match='1 to 120'): create(s, ' \t ')
    with pytest.raises(ValueError, match='control'): create(s, 'Bad\nName')
    before = s.dispatch('list_versions', {'photo_id': 1})
    assert not s.dispatch('rename_version', {**target(row), 'name': 'Café'})['changed']
    assert not s.dispatch('update_version', {**target(row), 'expected_revision': 0})['changed']
    assert s.dispatch('list_versions', {'photo_id': 1}) == before
    edit(s, exposure=1)
    with pytest.raises(ValueError, match='Edit conflict'):
        s.dispatch('update_version', {**target(row), 'expected_revision': 0})
    with pytest.raises(ValueError, match='Edit conflict'):
        s.dispatch('save_version', {'photo_id': 1, 'name': 'Stale', 'expected_revision': 0})
    with pytest.raises(ValueError, match='captured photo revision'):
        s.dispatch('save_version', {'photo_id': 1, 'name': 'Step', 'step_id': 0})
    assert s.dispatch('save_version', {'photo_id': 1, 'name': 'Legacy append'})['saved']
    s.dispatch('restore_version', {'photo_id': 1, 'version_id': row['id'], 'expected_revision': photo(s)['revision']})
    assert photo(s)['recipe']['exposure'] == 0


def test_alphabetical_keyset_pages_compact_refresh_and_invalidation(library, monkeypatch):
    s, _ = library
    for n in reversed(range(143)): create(s, f'Version {n:03d}')
    def forbidden(*args, **kwargs): raise AssertionError('Listing must not read full photos')
    monkeypatch.setattr(Catalog, 'photo', forbidden)
    first = s.dispatch('list_versions', {'photo_id': 1})
    assert len(first['versions']) == 60 and first['versions'][0]['name'] == 'Version 000'
    unchanged = s.dispatch('list_versions', {'photo_id': 1, 'known_revision': first['snapshots_revision']})
    assert unchanged['unchanged'] and 'versions' not in unchanged and len(json.dumps(unchanged)) < 200
    rows = list(first['versions']); page = first
    while page['next_after'] is not None:
        page = s.dispatch('list_versions', {'photo_id': 1, 'after_id': page['next_after'],
            'expected_snapshots_revision': first['snapshots_revision']})
        rows += page['versions']
    assert [r['name'] for r in rows] == [f'Version {n:03d}' for n in range(143)]
    assert all('recipe' not in row for row in rows)
    s.dispatch('rename_version', {**target(rows[-1]), 'name': 'A first'})
    with pytest.raises(ValueError, match='list changed'):
        s.dispatch('list_versions', {'photo_id': 1, 'after_id': first['next_after'],
            'expected_snapshots_revision': first['snapshots_revision']})
    assert s.dispatch('list_versions', {'photo_id': 1, 'known_revision': first['snapshots_revision']})['versions'][0]['name'] == 'A first'
    with pytest.raises(ValueError, match='paging requires'):
        s.dispatch('list_versions', {'photo_id': 1, 'after_id': first['next_after']})
    with s.catalog() as c:
        c.db.set_authorizer(lambda action, table, column, db, trigger:
            sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_READ and column == 'recipe' else sqlite3.SQLITE_OK)
        assert len(Snapshots(c.db).page(1)['versions']) == 60
        plan = c.db.execute('EXPLAIN QUERY PLAN SELECT id,name FROM versions WHERE source_id=? '
            'AND (name_key,id)>(?,?) ORDER BY name_key,id LIMIT 61', (1, 'version 090', 50)).fetchall()
        assert any('versions_alphabetical' in row[3] for row in plan)
        assert all('TEMP B-TREE' not in row[3] for row in plan)


def test_delete_recreate_restart_and_copy_removal_preserve_identity(library):
    s, paths = library
    original = paths[0].read_bytes()
    row = create(s)
    old_photo = photo(s)
    s.dispatch('delete_version', target(row))
    new = create(s, 'Replacement')
    assert new['id'] > row['id'] and photo(s) == old_photo
    with pytest.raises(ValueError, match='does not exist'): s.dispatch('delete_version', target(row))
    with closing(Catalog(s.root)) as c:
        third = c.save_version(1, 'Restarted')['version']
        assert third['id'] > new['id']
    p = photo(s)
    copy_id = s.dispatch('create_virtual_copies', {'targets': [{'photo_id': 1,
        'expected_revision': p['revision'], 'expected_metadata_revision': p['metadata_revision']}]})['photos'][0]['id']
    shared = create(s, 'From copy', id_=copy_id)
    p = photo(s, copy_id)
    s.dispatch('remove_virtual_copies', {'targets': [{'photo_id': copy_id, 'expected_revision': p['revision'],
        'expected_metadata_revision': p['metadata_revision'], 'expected_source_revision': p['source_revision']}]})
    assert shared['id'] in [r['id'] for r in s.dispatch('list_versions', {'photo_id': 1})['versions']]
    s.dispatch('delete_version', target(shared))
    assert paths[0].read_bytes() == original


def test_write_failure_rolls_back_snapshot_counter_and_family_revision(library):
    s, _ = library
    with s.catalog() as c:
        c.db.execute("CREATE TRIGGER reject_snapshot BEFORE INSERT ON versions BEGIN SELECT RAISE(ABORT,'injected insert'); END")
        counter = c.db.execute('SELECT next_id FROM snapshot_identity').fetchone()[0]
    with pytest.raises(sqlite3.DatabaseError, match='injected insert'): create(s)
    with s.catalog() as c:
        assert c.db.execute('SELECT next_id FROM snapshot_identity').fetchone()[0] == counter
        assert c.db.execute('SELECT snapshots_revision FROM photo_sources WHERE id=1').fetchone()[0] == 0
        c.db.execute('DROP TRIGGER reject_snapshot')
    row = create(s)
    with s.catalog() as c:
        c.db.execute("CREATE TRIGGER reject_snapshot_touch BEFORE UPDATE OF snapshots_revision ON photo_sources "
                     "BEGIN SELECT RAISE(ABORT,'injected touch'); END")
    with pytest.raises(sqlite3.DatabaseError, match='injected touch'):
        s.dispatch('rename_version', {**target(row), 'name': 'Lost'})
    assert s.dispatch('list_versions', {'photo_id': 1})['versions'] == [row]


def test_genuine_schema23_migration_preserves_legacy_duplicates_and_rolls_back(tmp_path, monkeypatch):
    from lumaraw import catalog as module
    path = tmp_path / 'old.png';Image.new('RGB', (8, 8)).save(path)
    root = tmp_path / 'old';payload = json.dumps({'exposure': .7})
    with monkeypatch.context() as context:
        context.setattr(module, 'migrate', lambda db: migrate_to(db, 23))
        c = Catalog(root);seed_photo(c.db, path)
        with c.db:
            c.db.executemany('INSERT INTO versions(id,photo_id,name,recipe,created,source_id) VALUES(?,1,?,?,?,1)',
                [(90, 'Cafe\u0301', payload, 123.0), (91, 'CAFÉ', payload, 124.0)])
        original = [tuple(r) for r in c.db.execute('SELECT * FROM versions')]
        c.db.set_authorizer(lambda action, name, b, db, trigger:
            sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_CREATE_INDEX and name == 'versions_alphabetical' else sqlite3.SQLITE_OK)
        with pytest.raises(sqlite3.DatabaseError): migrate(c.db)
        c.db.set_authorizer(None)
        assert c.db.execute('PRAGMA user_version').fetchone()[0] == 23
        assert [tuple(r) for r in c.db.execute('SELECT * FROM versions')] == original
        c.close()
    with closing(Catalog(root)) as c:
        migrate(c.db)
        assert c.db.execute('PRAGMA user_version').fetchone()[0] == 24
        assert [tuple(r) for r in c.db.execute('SELECT id,photo_id,name,recipe,created,source_id FROM versions')] == original
        assert len(Snapshots(c.db).page(1)['versions']) == 2
        assert c.save_version(1, 'New')['version']['id'] == 92


def test_snapshot_effect_annotations():
    assert TOOLS['delete_version']['annotations']['destructiveHint']
    assert TOOLS['update_version']['annotations']['destructiveHint']
    assert TOOLS['list_versions']['annotations']['readOnlyHint']
