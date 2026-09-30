"""Snapshot-status filtering over shared families and live collection sources.

Generated originals and disposable catalogs verify first/last transitions,
transaction rollback, bounded recipe-free queries, bulk removal, old migration
and backup persistence. No desktop or photographic-processing claim is made.
"""
from contextlib import closing
import json
import sqlite3

import jsonschema
from PIL import Image
import pytest

from lumaraw.catalog import Catalog
from lumaraw.model import Recipe
from lumaraw.service import Service
from lumaraw.snapshot_status import migrate, revision
from legacy_catalog import migrate_to, seed_photo


@pytest.fixture
def library(tmp_path):
    paths = [tmp_path / 'Photos' / name for name in ('a.png', 'b.png', 'Child/c.png')]
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', (32, 24), 'navy').save(path)
    s = Service(tmp_path / 'catalog', presets_root=tmp_path / 'presets')
    s.dispatch('queue_control', {'action': 'pause'})
    s.dispatch('import_photos', {'paths': list(map(str, paths))})
    yield s, paths
    s.close()


def save(s, id_=1, name='Snapshot'):
    return s.dispatch('save_version', {'photo_id': id_, 'name': name})['version']


def delete(s, row, id_=1):
    return s.dispatch('delete_version', {'photo_id': id_, 'version_id': row['id'], 'expected_version_revision': row['revision']})


def ids(s, **extra):
    return [p['id'] for p in s.dispatch('list_photos', {'stacked': False, 'descending': False, **extra})['photos']]


def token(s):
    return s.dispatch('library_state')['snapshot_filter_revision']


def test_presence_is_shared_and_only_first_last_transitions_invalidate(library):
    s, paths = library; originals = [p.read_bytes() for p in paths]
    p = s.dispatch('get_photo', {'photo_id': 1})
    copy_id = s.dispatch('create_virtual_copies', {'targets': [{'photo_id': 1,
        'expected_revision': p['revision'], 'expected_metadata_revision': p['metadata_revision']}]})['photos'][0]['id']
    assert ids(s, filters={'has_snapshots': True}) == []
    assert ids(s, filters={'has_snapshots': False}) == [1, 2, 3, copy_id]
    s.dispatch('edit_photo', {'photo_id': 1, 'expected_revision': 0, 'patch': {'exposure': 1}})
    s.dispatch('before_after', {'photo_id': 1, 'expected_revision': 1, 'action': 'after_to_before'})
    assert token(s) == 0 and ids(s, filters={'has_snapshots': True}) == []
    first = save(s, copy_id)
    assert token(s) == 1 and ids(s, filters={'has_snapshots': True}) == [1, copy_id]
    assert ids(s, filters={'has_snapshots': True, 'is_virtual': True}) == [copy_id]
    other = save(s, name='Another')
    assert token(s) == 1
    renamed = s.dispatch('rename_version', {'photo_id': 1, 'version_id': first['id'],
        'expected_version_revision': first['revision'], 'name': 'Renamed'})['version']
    updated = s.dispatch('update_version', {'photo_id': 1, 'version_id': renamed['id'],
        'expected_version_revision': renamed['revision'], 'expected_revision': 2})['version']
    assert token(s) == 1
    delete(s, other);assert token(s) == 1
    delete(s, updated, copy_id)
    assert token(s) == 2 and ids(s, filters={'has_snapshots': True}) == []
    assert [p.read_bytes() for p in paths] == originals


def test_live_all_any_nested_sets_and_folder_previous_import_scope(library):
    s, _ = library; first = save(s)
    s.dispatch('rate_photo', {'photo_id': 2, 'rating': 5})
    root = s.dispatch('save_collection', {'name': 'Root', 'kind': 'set'})
    child = s.dispatch('save_collection', {'name': 'Child', 'kind': 'set', 'parent_id': root['id']})
    all_ = s.dispatch('save_collection', {'name': 'Both', 'kind': 'smart', 'parent_id': child['id'],
        'rules': {'has_snapshots': True, 'rating_min': 5}, 'match': 'all'})
    any_ = s.dispatch('save_collection', {'name': 'Either', 'kind': 'smart', 'parent_id': child['id'],
        'rules': {'has_snapshots': True, 'rating_min': 5}, 'match': 'any'})
    assert ids(s, collection_id=all_['id']) == []
    assert ids(s, collection_id=any_['id']) == [1, 2]
    assert ids(s, collection_id=root['id']) == [1, 2]
    save(s, 2)
    assert ids(s, collection_id=all_['id']) == [2]
    assert ids(s, collection_id=root['id'], filters={'has_snapshots': False}) == []
    delete(s, first)
    assert ids(s, collection_id=root['id']) == [2]
    assert ids(s, mode='previous_import', filters={'has_snapshots': True}) == [2]
    folder = s.dispatch('get_folder', {'photo_id': 1})['id']
    save(s, 3)
    assert ids(s, folder_id=folder, include_subfolders=False, filters={'has_snapshots': True}) == [2]
    assert ids(s, folder_id=folder, include_subfolders=True, filters={'has_snapshots': True}) == [2, 3]
    assert ids(s, search='c.png', filters={'has_snapshots': True}, sort='name') == [3]


def test_pages_are_bounded_and_do_not_read_recipe_payloads(library, monkeypatch):
    s, _ = library
    with s.catalog() as c, c.db:
        c.db.executemany('INSERT INTO photos(path,name,bytes,mtime,recipe,created) VALUES(?,?,0,0,?,0)',
            ((f'/synthetic/filter-{i}.png', f'filter-{i:03d}.png', json.dumps(Recipe().dict())) for i in range(143)))
        c.db.execute("INSERT INTO versions(photo_id,source_id,name,name_key,recipe,created,updated) "
            "SELECT id,source_id,'Seed','seed',recipe,0,0 FROM photos WHERE id%2=0")
    first = s.dispatch('list_photos', {'filters': {'has_snapshots': True}, 'stacked': False})
    assert first['total'] == 73 and len(first['photos']) == 60
    last = s.dispatch('list_photos', {'filters': {'has_snapshots': True}, 'offset': 99999, 'stacked': False})
    assert last['offset'] == 60 and len(last['photos']) == 13
    assert len({p['id'] for p in first['photos']+last['photos']}) == 73
    monkeypatch.setattr(Catalog, 'photo', lambda *a, **k: pytest.fail('Full-photo read during filtering'))
    assert len(ids(s, filters={'has_snapshots': False})) == 60
    with s.catalog() as c:
        c.db.set_authorizer(lambda action, table, column, db, trigger: sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_READ and column in ('recipe', 'metadata') else sqlite3.SQLITE_OK)
        for present in (True, False):
            assert c.filtered_count(filters={'has_snapshots': present}, stacked=False) == 73
            assert len(c.filtered_page(filters={'has_snapshots': present}, stacked=False)) == 60
            where, params = c.filter_sql(filters={'has_snapshots': present})
            plan = c.db.execute('EXPLAIN QUERY PLAN SELECT id FROM photos'+where, params).fetchall()
            assert any('source_snapshot_count' in row[3] for row in plan)
            assert any('photo_source' in row[3] for row in plan)


def test_receipts_strict_boolean_and_transaction_failure(library):
    s, _ = library
    for bad in (1, 'true', None):
        with pytest.raises(jsonschema.ValidationError): ids(s, filters={'has_snapshots': bad})
    with s.catalog() as c:
        c.db.execute('CREATE TRIGGER reject_family BEFORE UPDATE OF snapshots_revision ON photo_sources '
                     "BEGIN SELECT RAISE(ABORT,'injected family failure'); END")
    with pytest.raises(sqlite3.DatabaseError, match='injected'): save(s)
    assert token(s) == 0 and ids(s, filters={'has_snapshots': True}) == []
    with s.catalog() as c:
        assert c.db.execute('SELECT snapshot_count FROM photo_sources WHERE id=1').fetchone()[0] == 0
        assert c.db.execute('SELECT next_id FROM snapshot_identity').fetchone()[0] == 1
        c.db.execute('DROP TRIGGER reject_family')
    row = save(s)
    for method, params in [('library_state', {}), ('photo_summaries', {'photo_ids': [1, 2]}), ('list_photos', {})]:
        assert s.dispatch(method, params)['snapshot_filter_revision'] == 1
    with s.catalog() as c:
        c.db.execute('CREATE TRIGGER reject_family BEFORE UPDATE OF snapshots_revision ON photo_sources '
                     "BEGIN SELECT RAISE(ABORT,'injected family failure'); END")
    with pytest.raises(sqlite3.DatabaseError, match='injected'): delete(s, row)
    assert token(s) == 1 and ids(s, filters={'has_snapshots': True}) == [1]


def test_adaptive_page_shapes_preserve_order_and_sparse_stack_paths(library):
    s, _ = library
    with s.catalog() as c, c.db:
        c.db.executemany("INSERT INTO photos(path,name,bytes,mtime,recipe,created,rating) VALUES(?,?,0,0,'{}',0,?)",
            ((f'/synthetic/shape-{i}.png', f'shape-{i:04d}.png', i%6) for i in range(1500)))
        c.db.execute("INSERT INTO versions(photo_id,source_id,name,name_key,recipe,created,updated) "
                     "SELECT id,source_id,'Seed','seed',recipe,0,0 FROM photos WHERE id%5=0")
    smart=s.dispatch('save_collection',{'name':'Shapes','kind':'smart','rules':{'has_snapshots':True,'rating_min':4},'match':'any'})
    with s.catalog() as c:
        for filters,collection in [({'has_snapshots':True},None),({'has_snapshots':False},None),({},smart['id'])]:
            total=c.filtered_count(filters=filters,collection_id=collection,stacked=False)
            for offset in (0,120):
                for descending in (True,False):
                    regular=c.filtered_page(offset,filters=filters,collection_id=collection,descending=descending,stacked=False)
                    dense=c.filtered_page(offset,filters=filters,collection_id=collection,descending=descending,stacked=False,match_count=total)
                    assert dense==regular
        statements=[];c.db.set_trace_callback(statements.append)
        c.filtered_page(filters={'has_snapshots':True},stacked=False,match_count=300)
        assert any('EXISTS(SELECT 1 FROM photo_sources snapshot_source' in q for q in statements)
        where,args=c.filter_sql(filters={'has_snapshots':True},ordered_page=True)
        plan=c.db.execute('EXPLAIN QUERY PLAN SELECT id FROM photos'+where+' ORDER BY id DESC LIMIT 60',args).fetchall()
        assert not any('TEMP B-TREE' in row[3] for row in plan)
        statements.clear()
        c.filtered_page(filters={'has_snapshots':True},sort='name',stacked=False,match_count=300)
        assert not any('snapshot_source' in q for q in statements)
        # An actual folder stack retains the original full-projection query.
        from lumaraw.stacks import Stacks
        with c.db: Stacks(c).create('folder','/synthetic',[5,10],collapsed=True)
        statements.clear()
        page=c.filtered_page(filters={'has_snapshots':True},stacked=True,match_count=299)
        assert not any('snapshot_source' in q for q in statements)
        assert page==c.filtered_page(filters={'has_snapshots':True},stacked=True)
        with c.db: c.db.execute('DELETE FROM versions WHERE photo_id>300')
        sparse_count=c.filtered_count(filters={'has_snapshots':True},stacked=False)
        assert sparse_count==60
        statements.clear()
        sparse=c.filtered_page(filters={'has_snapshots':True},stacked=False,match_count=sparse_count)
        assert not any('snapshot_source' in q for q in statements)
        assert sparse==c.filtered_page(filters={'has_snapshots':True},stacked=False)


def test_bulk_delete_move_and_rollback_keep_counts_exact(library):
    s, _ = library
    row = save(s);save(s, name='Second');save(s, 2)
    assert token(s) == 2
    with s.catalog() as c, c.db:
        c.db.execute('UPDATE versions SET source_id=3 WHERE id=?', (row['id'],))
    assert token(s) == 3 and ids(s, filters={'has_snapshots': True}) == [1, 2, 3]
    with s.catalog() as c:
        c.db.execute("CREATE TRIGGER reject_bulk BEFORE DELETE ON versions WHEN OLD.source_id=2 "
                     "BEGIN SELECT RAISE(ABORT,'injected bulk'); END")
        with pytest.raises(sqlite3.DatabaseError, match='injected bulk'), c.db:
            c.db.execute('DELETE FROM versions')
        assert revision(c.db) == 3
        assert [r[0] for r in c.db.execute('SELECT snapshot_count FROM photo_sources ORDER BY id')] == [1, 1, 1]
        c.db.execute('DROP TRIGGER reject_bulk')
        with c.db: c.db.execute('DELETE FROM versions WHERE source_id IN (1,2)')
        assert revision(c.db) == 5
    assert ids(s, filters={'has_snapshots': True}) == [3]


def test_real_schema24_migration_is_atomic_and_preserves_payloads(tmp_path, monkeypatch):
    from lumaraw import catalog as module
    path = tmp_path / 'old.png';Image.new('RGB', (8, 8)).save(path)
    root = tmp_path / 'legacy'
    with monkeypatch.context() as patch:
        patch.setattr(module, 'migrate', lambda db: migrate_to(db, 24))
        c = Catalog(root);seed_photo(c.db, path)
        # Build the published v24 row shape, independent of future writers.
        with c.db:
            c.db.executemany('INSERT INTO versions(id,photo_id,source_id,name,name_key,recipe,created,updated) '
                'VALUES(?,1,1,?,?,?,10,10)', [(1, 'Existing', 'existing', '{}'), (2, 'Another', 'another', '{}')])
            c.db.execute('UPDATE snapshot_identity SET next_id=3 WHERE id=1')
            c.db.execute('UPDATE photo_sources SET snapshots_revision=2 WHERE id=1')
        versions = [tuple(r) for r in c.db.execute('SELECT * FROM versions')]
        sources = [tuple(r) for r in c.db.execute('SELECT * FROM photo_sources')]
        c.db.set_authorizer(lambda action, name, *rest: sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_CREATE_INDEX and name == 'source_snapshot_count' else sqlite3.SQLITE_OK)
        with pytest.raises(sqlite3.DatabaseError): migrate(c.db)
        c.db.set_authorizer(None)
        assert c.db.execute('PRAGMA user_version').fetchone()[0] == 24
        assert [tuple(r) for r in c.db.execute('SELECT * FROM photo_sources')] == sources
        assert [tuple(r) for r in c.db.execute('SELECT * FROM versions')] == versions
        c.close()
    with closing(Catalog(root)) as c:
        migrate(c.db)
        assert c.db.execute('PRAGMA user_version').fetchone()[0] == 25
        assert [tuple(r) for r in c.db.execute('SELECT * FROM versions')] == versions
        assert c.db.execute('SELECT snapshot_count FROM photo_sources').fetchone()[0] == 2
        assert revision(c.db) == 0
        assert c.filtered_count(filters={'has_snapshots': True}) == 1


def test_backup_preserves_status_counts_and_live_triggers(library, tmp_path):
    s, _ = library;save(s);save(s, name='Second');save(s, 2)
    saved = token(s);backup = tmp_path / 'backup.sqlite';dest = tmp_path / 'restored'
    s.dispatch('backup_catalog', {'path': str(backup)})
    s.dispatch('restore_catalog', {'path': str(backup), 'destination': str(dest)})
    with closing(Catalog(dest)) as c:
        assert revision(c.db) == saved
        assert c.filtered_count(filters={'has_snapshots': True}, stacked=False) == 2
        with c.db: c.db.execute('DELETE FROM versions WHERE source_id=1')
        assert revision(c.db) == saved+1
        assert c.filtered_count(filters={'has_snapshots': True}, stacked=False) == 1
