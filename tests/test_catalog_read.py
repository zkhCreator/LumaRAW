"""Verify read-only catalog snapshots for Library photo pages.

Inputs: disposable catalogs and bounded list_photos queries. Outputs: comparisons
between existing catalog queries and snapshot-backed queries, plus concurrency,
read-only and migration assertions. No production data, pixels or UI interaction.
"""
from concurrent.futures import ThreadPoolExecutor
import sqlite3
import threading

from PIL import Image
import pytest

import lumaraw.catalog as catalog_module
from lumaraw.catalog import Catalog
from lumaraw.catalog_read import CatalogReadSnapshot
from lumaraw.collections import Collections
from lumaraw.folders import Folders
from lumaraw.keywords import Keywords
from lumaraw.library_queries import LibraryQueries
from lumaraw.previous_import import state as previous_import_state
from lumaraw.runtime import CATALOG_VERSION
from lumaraw.service import Service
from lumaraw.snapshot_status import revision as snapshot_filter_revision
from lumaraw.stacks import Stacks


def _photo_list(queries, catalog_like, params):
    mode = params.get('mode', 'all')
    search = params.get('search', '')
    filters = params.get('filters')
    collection = params.get('collection_id')
    stacked = params.get('stacked', True)
    folder = params.get('folder_id')
    subfolders = params.get('include_subfolders', True)
    total = queries.filtered_count(mode, search, filters, collection, stacked, folder, subfolders)
    offset = min(params.get('offset', 0), max(0, ((total - 1) // 60) * 60))
    photos = queries.filtered_page(
        offset, mode, search, filters, collection,
        params.get('sort', 'imported'), params.get('descending', True),
        stacked, folder, subfolders, match_count=total,
    )
    db = catalog_like.db
    return {
        'photos': photos,
        'total': total,
        'offset': offset,
        'page_size': 60,
        'stack_revision': Stacks(catalog_like).revision(),
        'folder_revision': Folders(catalog_like).revision(),
        'keyword_revision': Keywords(catalog_like).revision(),
        'previous_import': previous_import_state(db),
        'snapshot_filter_revision': snapshot_filter_revision(db),
    }


@pytest.fixture
def photo_library(tmp_path):
    root = tmp_path / 'catalog % ? # 旅行'
    service = Service(root, presets_root=tmp_path / 'presets')
    try:
        service.dispatch('queue_control', {'action': 'pause'})
        paths = []
        for index in range(72):
            folder = tmp_path / '旅行' / ('夏' if index < 48 else '冬')
            folder.mkdir(parents=True, exist_ok=True)
            name = f'海边-{index:03}.png' if index % 3 == 0 else f'風景-{index:03}.png'
            path = folder / name
            Image.new('RGB', (8, 8), (index % 255, 80, 120)).save(path)
            paths.append(path)
        service.dispatch('import_photos', {'paths': [str(path) for path in paths]})
        yield service, root, paths
    finally:
        if not service.stopping.is_set():
            service.close()


def _build_sources(service, root, paths):
    with service.catalog() as catalog:
        ids_by_path = {
            row['path']: row['id']
            for row in catalog.db.execute('SELECT id,path FROM photos')
        }
        folder_id = catalog.db.execute(
            'SELECT id FROM catalog_folders WHERE path=?', (str(paths[0].parent.parent),)
        ).fetchone()['id']
    ids = [ids_by_path[str(path)] for path in paths]
    regular = service.dispatch('save_collection', {'name': '旅行 Picks', 'kind': 'regular'})
    first = service.dispatch('collection_membership', {
        'collection_id': regular['id'], 'expected_revision': regular['revision'],
        'photo_ids': ids[:60], 'action': 'add',
    })
    service.dispatch('collection_membership', {
        'collection_id': regular['id'], 'expected_revision': first['revision'],
        'photo_ids': ids[60:], 'action': 'add',
    })
    root_set = service.dispatch('save_collection', {'name': '旅行', 'kind': 'set'})
    nested_set = service.dispatch('save_collection', {
        'name': 'Selected', 'kind': 'set', 'parent_id': root_set['id'],
    })
    smart = service.dispatch('save_collection', {
        'name': 'Rated', 'kind': 'smart', 'parent_id': root_set['id'],
        'rules': {'rating_min': 4},
    })
    for photo_id in ids[:18:2]:
        service.dispatch('rate_photo', {'photo_id': photo_id, 'rating': 5})
    # The set view includes the nested regular collection; smart membership is
    # live and exercises query compilation without assigning direct set members.
    nested_regular = service.dispatch('save_collection', {
        'name': 'Nested choices', 'kind': 'regular', 'parent_id': nested_set['id'],
    })
    service.dispatch('collection_membership', {
        'collection_id': nested_regular['id'], 'expected_revision': nested_regular['revision'],
        'photo_ids': ids[:12], 'action': 'add',
    })
    with service.catalog() as catalog:
        stack_revision = Stacks(catalog).revision()
    service.dispatch('stack_photos', {
        'action': 'group', 'photo_ids': ids[:3], 'expected_revision': stack_revision,
    })
    with service.catalog() as catalog:
        stack_revision = Stacks(catalog).revision()
    service.dispatch('stack_photos', {
        'action': 'group', 'photo_ids': ids[4:7], 'expected_revision': stack_revision,
        'collection_id': regular['id'],
    })
    return {
        'folder_id': folder_id,
        'ids': ids,
        'regular_id': regular['id'],
        'root_set_id': root_set['id'],
        'nested_set_id': nested_set['id'],
        'smart_id': smart['id'],
    }


def test_snapshot_pages_match_catalog_queries_for_sources_filters_stacks_and_unicode(photo_library):
    service, root, paths = photo_library
    source = _build_sources(service, root, paths)
    cases = [
        {'stacked': True},
        {'folder_id': source['folder_id'], 'include_subfolders': False},
        {'mode': 'previous_import', 'stacked': False},
        {'search': '海边', 'sort': 'name', 'descending': False, 'stacked': False},
        {'folder_id': source['folder_id'], 'include_subfolders': True,
         'sort': 'imported', 'descending': False, 'stacked': False, 'offset': 60},
        {'collection_id': source['regular_id'], 'sort': 'imported',
         'descending': False, 'stacked': True, 'offset': 60},
        {'collection_id': source['smart_id'], 'filters': {'rating_min': 4},
         'sort': 'name', 'descending': False, 'stacked': False},
        {'collection_id': source['root_set_id'], 'sort': 'rating',
         'descending': True, 'stacked': True},
    ]

    for params in cases:
        with service.catalog() as catalog:
            expected = _photo_list(catalog, catalog, params)
        with CatalogReadSnapshot(root) as snapshot:
            actual = _photo_list(LibraryQueries(snapshot), snapshot, params)
        assert actual == expected

    offset_page = service.dispatch('list_photos', {
        'collection_id': source['regular_id'], 'sort': 'imported',
        'descending': False, 'stacked': False, 'offset': 71,
    })
    assert offset_page['offset'] == 60 and len(offset_page['photos']) == 12
    assert offset_page['photos'][0]['id'] == source['ids'][60]


def test_open_snapshot_keeps_count_page_and_collection_revisions_consistent(photo_library):
    service, root, paths = photo_library
    source = _build_sources(service, root, paths)
    collection_id = service.dispatch('save_collection', {'name': 'Snapshot target', 'kind': 'regular'})['id']
    ids = source['ids'][:2]
    first = service.dispatch('collection_membership', {
        'collection_id': collection_id, 'expected_revision': 0,
        'photo_ids': ids, 'action': 'add',
    })
    with CatalogReadSnapshot(root) as snapshot:
        queries = LibraryQueries(snapshot)
        before_total = queries.filtered_count(
            'all', '', None, collection_id, False, None, True,
        )
        before_collection = Collections(snapshot).get(collection_id)
        before_tree_revision = Collections(snapshot).tree_revision()
        assert before_total == 2

        service.dispatch('collection_membership', {
            'collection_id': collection_id, 'expected_revision': first['revision'],
            'photo_ids': [source['ids'][2]], 'action': 'add',
        })

        page = queries.filtered_page(0, 'all', '', None, collection_id,
                                     'imported', True, False, None, True,
                                     match_count=before_total)
        assert [row['id'] for row in page] == list(reversed(ids))
        assert queries.filtered_count('all', '', None, collection_id, False, None, True) == before_total
        assert Collections(snapshot).get(collection_id)['revision'] == before_collection['revision']
        assert Collections(snapshot).tree_revision() == before_tree_revision

    with CatalogReadSnapshot(root) as snapshot:
        queries = LibraryQueries(snapshot)
        assert queries.filtered_count('all', '', None, collection_id, False, None, True) == 3
        assert Collections(snapshot).get(collection_id)['revision'] > before_collection['revision']
        assert Collections(snapshot).tree_revision() > before_tree_revision


def test_service_list_photos_keeps_count_page_and_revisions_on_one_snapshot(photo_library, monkeypatch):
    service, _, paths = photo_library
    params = {'stacked': False, 'sort': 'imported', 'descending': True}
    before = service.dispatch('list_photos', params)
    assert before['total'] == 72 and len(before['photos']) == 60
    new_path = paths[0].parent / 'new-during-list.png'
    Image.new('RGB', (8, 8), (180, 40, 80)).save(new_path)

    original_count = LibraryQueries.filtered_count
    committed = False

    def count_then_import(queries, *args, **kwargs):
        nonlocal committed
        count = original_count(queries, *args, **kwargs)
        if not committed:
            committed = True
            service.dispatch('import_photos', {'paths': [str(new_path)]})
        return count

    monkeypatch.setattr(LibraryQueries, 'filtered_count', count_then_import)
    during = service.dispatch('list_photos', params)
    assert committed
    assert during == before

    after = service.dispatch('list_photos', params)
    assert after['total'] == 73
    assert after['photos'][0]['path'] == str(new_path)
    assert [row['id'] for row in after['photos'][1:]] == [row['id'] for row in before['photos'][:-1]]
    assert after['folder_revision'] > before['folder_revision']
    assert after['previous_import']['revision'] > before['previous_import']['revision']


def test_list_photos_snapshot_bypasses_service_lock_and_sees_new_state_after_writer_commit(photo_library):
    service, _, _ = photo_library
    photo_id = service.dispatch('list_photos', {'stacked': False})['photos'][0]['id']
    params = {'filters': {'rating_min': 5}, 'stacked': False}
    assert service.dispatch('list_photos', params)['total'] == 0
    writer_started = threading.Event()
    allow_commit = threading.Event()

    def hold_uncommitted_write():
        with service.catalog() as catalog, catalog.db:
            catalog.db.execute('UPDATE photos SET rating=5 WHERE id=?', (photo_id,))
            writer_started.set()
            if not allow_commit.wait(timeout=10):
                raise TimeoutError('Test writer was not released')

    with ThreadPoolExecutor(max_workers=2) as pool:
        writer = pool.submit(hold_uncommitted_write)
        try:
            assert writer_started.wait(timeout=5)
            reader = pool.submit(service.dispatch, 'list_photos', params)
            during = reader.result(timeout=3)
            assert during['total'] == 0
            assert during['photos'] == []
        finally:
            allow_commit.set()
        writer.result(timeout=5)

    after = service.dispatch('list_photos', params)
    assert after['total'] == 1
    assert [row['id'] for row in after['photos']] == [photo_id]


def test_snapshot_is_read_only_does_not_construct_catalog_or_change_schema(photo_library, monkeypatch):
    service, root, _ = photo_library
    database = root / 'catalog.sqlite'
    with service.catalog() as catalog:
        before = [tuple(row) for row in catalog.db.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"
        )]
        version = catalog.db.execute('PRAGMA user_version').fetchone()[0]

    def forbidden_catalog_constructor(*_args, **_kwargs):
        raise AssertionError('CatalogReadSnapshot must not construct a writable Catalog')

    monkeypatch.setattr(Catalog, '__init__', forbidden_catalog_constructor)
    with CatalogReadSnapshot(root) as snapshot:
        assert snapshot.db.execute('PRAGMA query_only').fetchone()[0] == 1
        assert snapshot.db.execute('PRAGMA user_version').fetchone()[0] == CATALOG_VERSION
        with pytest.raises(sqlite3.OperationalError):
            snapshot.db.execute('CREATE TABLE snapshot_must_not_write(id INTEGER)')
        # The physical connection stays read-only even without the SQL guard.
        snapshot.db.execute('PRAGMA query_only=OFF')
        with pytest.raises(sqlite3.OperationalError):
            snapshot.db.execute('UPDATE photos SET rating=rating+1')
        assert LibraryQueries(snapshot).filtered_count(stacked=False) == 72

    with sqlite3.connect(database) as check:
        after = [tuple(row) for row in check.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"
        )]
        assert check.execute('PRAGMA user_version').fetchone()[0] == version
    assert after == before

    missing = root.parent / 'must-not-be-created'
    with pytest.raises((FileNotFoundError, sqlite3.OperationalError, ValueError)):
        with CatalogReadSnapshot(missing):
            pytest.fail('A read snapshot must not create an absent catalog directory')
    assert not missing.exists()


@pytest.mark.parametrize('version', [CATALOG_VERSION - 1, CATALOG_VERSION + 1])
def test_snapshot_rejects_schema_mismatch_without_migration_or_fallback(photo_library, version):
    service, root, _ = photo_library
    database = root / 'catalog.sqlite'
    with service.catalog() as catalog:
        before_schema = [tuple(row) for row in catalog.db.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"
        )]
    service.close()
    with sqlite3.connect(database) as writer:
        writer.execute(f'PRAGMA user_version={version}')
    with pytest.raises(ValueError, match='schema|catalog|version'):
        with CatalogReadSnapshot(root):
            pytest.fail('A mismatched catalog must not be opened as a writable fallback')
    with sqlite3.connect(database) as check:
        assert check.execute('PRAGMA user_version').fetchone()[0] == version
        after_schema = [tuple(row) for row in check.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"
        )]
    assert after_schema == before_schema


def test_normal_catalog_startup_migrates_old_schema_before_snapshot_access(tmp_path, monkeypatch):
    from legacy_catalog import migrate_to, seed_photo

    root = tmp_path / 'legacy-catalog'
    source = tmp_path / 'legacy.png'
    Image.new('RGB', (8, 8), (30, 50, 70)).save(source)
    with monkeypatch.context() as patch:
        patch.setattr(catalog_module, 'migrate', lambda db: migrate_to(db, 32))
        old = Catalog(root)
        seed_photo(old.db, source)
        assert old.db.execute('PRAGMA user_version').fetchone()[0] == 32
        old.close()

    upgraded = Service(root, presets_root=tmp_path / 'legacy-presets')
    try:
        upgraded.dispatch('queue_control', {'action': 'pause'})
        with upgraded.catalog() as catalog:
            assert catalog.db.execute('PRAGMA user_version').fetchone()[0] == CATALOG_VERSION
            assert catalog.db.execute('SELECT count(*) FROM photos').fetchone()[0] == 1
    finally:
        upgraded.close()

    with CatalogReadSnapshot(root) as snapshot:
        assert LibraryQueries(snapshot).filtered_count(stacked=False) == 1
