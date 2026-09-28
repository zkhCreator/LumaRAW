"""Folder sources, bounded hierarchy and catalog-only metadata contracts.

Generated files and legacy catalogs cover maintained counts, root visibility,
source/filter independence and persistence. No desktop or physical move/rename
acceptance is implied. Original hashes are checked across folder metadata edits.
"""
import hashlib
import json
import sqlite3

from PIL import Image
import pytest

from lumaraw.catalog import Catalog
from lumaraw.folders import Folders
from lumaraw.model import Recipe
from lumaraw.service import Service


@pytest.fixture
def library(tmp_path):
    root = tmp_path / 'photos'
    paths = [root / 'a.jpg', root / 'child' / 'b.jpg', root / 'child' / 'deeper' / 'c.jpg',
             tmp_path / 'photos-sibling' / 'd.jpg']
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', (16, 12), 'orange').save(path)
    service = Service(tmp_path / 'catalog')
    service.dispatch('import_photos', {'paths': [str(path) for path in paths]})
    yield service, paths
    service.close()


def folder(service, photo_id):
    return service.dispatch('get_folder', {'photo_id': photo_id})


def test_hierarchy_counts_sources_and_metadata_filters_are_independent(library):
    service, paths = library
    roots = service.dispatch('list_folders')
    assert [row['name'] for row in roots['folders']] == ['photos', 'photos-sibling']
    root = roots['folders'][0]
    assert root['direct_count'] == 1 and root['total_count'] == 3 and root['has_children']
    children = service.dispatch('list_folders', {'parent_id': root['id']})['folders']
    assert len(children) == 1 and children[0]['name'] == 'child' and children[0]['total_count'] == 2
    assert service.dispatch('list_photos', {'folder_id': root['id']})['total'] == 3
    assert service.dispatch('list_photos', {'folder_id': root['id'], 'include_subfolders': False})['total'] == 1
    service.dispatch('rate_photo', {'photo_id': 2, 'rating': 5})
    assert service.dispatch('list_photos', {'folder_id': root['id'], 'filters': {'rating_min': 5}})['photos'][0]['id'] == 2
    assert service.dispatch('list_photos', {'folder_id': root['id'], 'include_subfolders': False,
                                          'filters': {'rating_min': 5}})['total'] == 0
    album = service.dispatch('save_collection', {'name': 'A', 'kind': 'regular'})
    with pytest.raises(ValueError, match='either a folder or collection'):
        service.dispatch('list_photos', {'folder_id': root['id'], 'collection_id': album['id']})


def test_importing_parent_after_children_coalesces_roots_and_visibility_is_persistent(tmp_path):
    service = Service(tmp_path / 'catalog')
    paths = [tmp_path / 'images' / name / 'p.png' for name in ('b', 'a')]
    for path in paths:
        path.parent.mkdir(parents=True)
        Image.new('RGB', (8, 8)).save(path)
    try:
        service.dispatch('import_photos', {'paths': [str(path) for path in paths]})
        roots = service.dispatch('list_folders')
        assert [row['name'] for row in roots['folders']] == ['a', 'b']
        service.dispatch('set_folder_visibility', {'folder_id': roots['folders'][0]['id'],
            'expected_revision': roots['folder_revision'], 'action': 'show_parent'})
        root = service.dispatch('list_folders')['folders'][0]
        assert root['name'] == 'images' and root['total_count'] == 2 and root['direct_count'] == 0
        with pytest.raises(ValueError, match='tree changed'):
            service.dispatch('set_folder_visibility', {'folder_id': root['id'],
                'expected_revision': roots['folder_revision'], 'action': 'hide_parent'})
        service.dispatch('set_folder_visibility', {'folder_id': root['id'],
            'expected_revision': service.dispatch('library_state')['folder_revision'], 'action': 'hide_parent'})
        assert len(service.dispatch('list_folders')['folders']) == 2
        direct = tmp_path / 'images' / 'direct.png'
        Image.new('RGB', (8, 8)).save(direct)
        service.dispatch('import_photos', {'paths': [str(direct)]})
        roots = service.dispatch('list_folders')
        assert len(roots['folders']) == 1 and roots['folders'][0]['direct_count'] == 1
        with pytest.raises(ValueError, match='containing photos'):
            service.dispatch('set_folder_visibility', {'folder_id': root['id'],
                'expected_revision': roots['folder_revision'], 'action': 'hide_parent'})
        with service.catalog() as catalog:
            assert Folders(catalog).list() == roots
    finally:
        service.close()


def test_labels_favorites_search_conflicts_and_original_safety(library):
    service, paths = library
    hashes = [hashlib.sha256(path.read_bytes()).digest() for path in paths]
    target = folder(service, 2)
    edited = service.dispatch('edit_folder', {'folder_id': target['id'], 'expected_revision': target['revision'],
        'patch': {'favorite': True, 'color_label': 'red'}})
    assert edited['revision'] == target['revision'] + 1
    for params in ({'favorites': True}, {'color_label': 'red'}, {'search': 'CHILD'}):
        result = service.dispatch('list_folders', params)
        assert result['filtered'] and [row['id'] for row in result['folders']] == [target['id']]
    with pytest.raises(ValueError, match='Folder conflict'):
        service.dispatch('edit_folder', {'folder_id': target['id'], 'expected_revision': target['revision'],
                                        'patch': {'favorite': False}})
    assert service.dispatch('list_folders', {'search': '%'})['total'] == 0
    assert hashes == [hashlib.sha256(path.read_bytes()).digest() for path in paths]
    assert service.dispatch('get_photo', {'photo_id': 2})['revision'] == 0


def test_virtual_copy_removal_relink_and_rollback_keep_counts_consistent(library):
    service, paths = library
    original = folder(service, 2)
    copy = service.dispatch('create_virtual_copies', {'targets': [
        {'photo_id': 2, 'expected_revision': 0, 'expected_metadata_revision': 0}]})['photos'][0]
    assert folder(service, 2)['direct_count'] == 2
    service.dispatch('remove_virtual_copies', {'targets': [{'photo_id': copy['id'], 'expected_revision': 0,
        'expected_metadata_revision': 0, 'expected_source_revision': copy['source_revision']}]})
    assert folder(service, 2)['direct_count'] == 1
    replacement = paths[3].parent / 'moved.jpg'
    paths[1].rename(replacement)
    service.dispatch('relink_photo', {'photo_id': 2, 'path': str(replacement)})
    assert folder(service, 2)['id'] == folder(service, 4)['id']
    assert service.dispatch('get_folder', {'folder_id': original['id']})['direct_count'] == 0
    before = service.dispatch('library_state')
    with service.catalog() as catalog:
        with pytest.raises(RuntimeError), catalog.db:
            catalog.db.execute('DELETE FROM photos WHERE id=3')
            raise RuntimeError('Abort fixture transaction')
        assert Folders(catalog).revision() == before['folder_revision']
        assert catalog.db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'


def test_large_folder_pages_and_photo_location_are_bounded(tmp_path):
    catalog = Catalog(tmp_path / 'catalog')
    payload = json.dumps(Recipe().dict())
    with catalog.db:
        catalog.db.executemany('INSERT INTO photos(path,name,bytes,mtime,recipe,created) VALUES(?,?,0,0,?,0)',
            ((str(tmp_path / f'folder-{i:03}' / 'p.png'), 'p.png', payload) for i in range(130)))
        catalog.db.executemany('INSERT INTO photos(path,name,bytes,mtime,recipe,created) VALUES(?,?,0,0,?,0)',
            ((str(tmp_path / 'folder-000' / f'{i}.png'), f'{i}.png', payload) for i in range(130)))
    store = Folders(catalog)
    first = store.list()
    assert first['total'] == 130 and len(first['folders']) == 60
    assert len(store.list(offset=120)['folders']) == 10
    last = store.details(photo_id=130)
    assert last['page_offset'] == 120
    oldest = store.details(photo_id=1)
    assert oldest['photo_offset'] == 120
    assert any(row['id'] == 1 for row in catalog.filtered_page(offset=120,folder_id=oldest['id'],
                                                            include_subfolders=False,stacked=False))
    catalog.close()


def test_stack_visibility_respects_direct_folder_scope(library):
    service, paths = library
    for photo_id in (1,2):
        service.dispatch('create_virtual_copies', {'targets': [
            {'photo_id': photo_id, 'expected_revision': 0, 'expected_metadata_revision': 0}]})
    root = folder(service,1)
    revision = service.dispatch('stack_state')['revision']
    result = service.dispatch('set_stack_visibility', {'folder': str(paths[0].parent),
        'include_subfolders': False, 'collapsed': True, 'expected_revision': revision})
    assert result['changed'] == 1
    rows = service.dispatch('list_photos', {'folder_id': root['id']})
    assert rows['total'] == 4
    child = next(row for row in rows['photos'] if row['id']==2)
    assert child['stack_collapsed'] == 0 and child['stack_count'] == 2
    assert service.dispatch('list_photos', {'folder_id': root['id'], 'include_subfolders': False})['total'] == 1
    assert service.dispatch('list_photos', {'folder_id': root['id'], 'stacked': False})['total'] == 5


def test_missing_directory_keeps_catalog_counts_and_hidden_ancestors_do_not_leak_into_search(library):
    service, paths = library
    paths[2].parent.rename(paths[2].parent.with_name('offline'))
    missing = folder(service,3)
    assert missing['missing'] and missing['direct_count'] == 1
    assert service.dispatch('list_photos', {'folder_id': missing['id']})['total'] == 1
    assert service.dispatch('list_folders', {'search': paths[0].parent.parent.name})['total'] == 0


def test_v6_migration_preserves_existing_photos_and_backup(tmp_path, monkeypatch):
    from lumaraw import catalog as module
    from lumaraw.capture_time import migrate as migrate_clock
    from lumaraw.collections import migrate as migrate_collections, migrate_identities
    from lumaraw.organization import migrate_metadata
    from lumaraw.stacks import migrate as migrate_stacks
    from lumaraw.virtual_copies import migrate as migrate_copies
    from lumaraw.library import backup_catalog, restore_catalog

    def legacy(db):
        for operation in (migrate_metadata,migrate_collections,migrate_copies,migrate_stacks,migrate_identities,migrate_clock):
            operation(db)
    root = tmp_path / 'catalog'
    with monkeypatch.context() as patch:
        patch.setattr(module, 'migrate', legacy)
        catalog = Catalog(root)
        with catalog.db:
            catalog.db.execute('INSERT INTO photos(path,name,bytes,mtime,recipe,created) VALUES(?,?,0,0,?,0)',
                (str(tmp_path / 'source' / 'p.png'), 'p.png', json.dumps(Recipe().dict())))
        before = tuple(catalog.db.execute('SELECT * FROM photos').fetchone())
        from lumaraw.folders import migrate
        catalog.db.set_authorizer(lambda action,a,b,d,t: sqlite3.SQLITE_DENY
            if action==sqlite3.SQLITE_INSERT and a=='folder_photos' else sqlite3.SQLITE_OK)
        with pytest.raises(sqlite3.DatabaseError):
            migrate(catalog.db)
        catalog.db.set_authorizer(None)
        assert catalog.db.execute('PRAGMA user_version').fetchone()[0] == 6
        assert catalog.db.execute("SELECT count(*) FROM sqlite_master WHERE name='catalog_folders'").fetchone()[0] == 0
        assert tuple(catalog.db.execute('SELECT * FROM photos').fetchone()) == before
        catalog.close()
    catalog = Catalog(root)
    assert tuple(catalog.db.execute('SELECT * FROM photos').fetchone()) == before
    folders = Folders(catalog)
    row = folders.list()['folders'][0]
    folders.edit(row['id'],0,{'favorite':True})
    expected = folders.list()
    backup_catalog(catalog,tmp_path / 'backup')
    catalog.close()
    restored = Catalog(restore_catalog(tmp_path / 'backup',tmp_path / 'restored'))
    assert Folders(restored).list() == expected
    restored.close()
