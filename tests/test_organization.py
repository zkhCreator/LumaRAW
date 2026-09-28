"""Library workflow evidence with disposable catalogs and read-only raster inputs.

Checks observable collection membership, live rules, atomic metadata conflicts,
literal Unicode queries, pagination, old-catalog migration and backup recovery.
No Lightroom pixel matching, real camera coverage or desktop interaction claim.
"""
import hashlib
import json
import sqlite3

from PIL import Image
import pytest

from lumaraw.catalog import Catalog
from lumaraw.library import backup_catalog, restore_catalog
from lumaraw.model import Recipe
from lumaraw.service import Service


@pytest.fixture
def library(tmp_path):
    service = Service(tmp_path / 'catalog')
    service.dispatch('queue_control', {'action': 'pause'})
    paths = []
    for name in ('forest.png', 'portrait.png', 'urban_100%.png'):
        path = tmp_path / name
        Image.new('RGB', (32, 24), (70, 110, 150)).save(path)
        paths.append(path)
    service.dispatch('import_photos', {'paths': [str(path) for path in paths]})
    yield service, paths
    service.close()


def metadata(service, ids, patch, revision=0):
    return service.dispatch('edit_metadata', {
        'targets': [{'photo_id': photo_id, 'expected_metadata_revision': revision} for photo_id in ids],
        'patch': patch,
    })


def ids(service, **params):
    return [row['id'] for row in service.dispatch('list_photos', params)['photos']]


def test_regular_membership_is_many_to_many_and_removal_preserves_originals(library):
    service, paths = library
    before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
    a = service.dispatch('save_collection', {'name': 'Portfolio', 'kind': 'regular'})
    b = service.dispatch('save_collection', {'name': 'Delivery', 'kind': 'regular'})
    for collection in (a, b):
        service.dispatch('collection_membership', {'collection_id': collection['id'],
            'expected_revision': 0, 'photo_ids': [1, 2, 2], 'action': 'add'})
        assert ids(service, collection_id=collection['id']) == [2, 1]
    service.dispatch('collection_membership', {'collection_id': a['id'],
        'expected_revision': 1, 'photo_ids': [1], 'action': 'remove'})
    assert ids(service, collection_id=a['id']) == [2]
    service.dispatch('delete_collection', {'collection_id': a['id'], 'expected_revision': 2})
    assert ids(service, collection_id=b['id']) == [2, 1]
    assert ids(service) == [3, 2, 1]
    assert before == [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]


def test_metadata_conflict_rolls_back_entire_batch_and_preserves_recipe_revision(library):
    service, _ = library
    service.dispatch('edit_photo', {'photo_id': 1, 'expected_revision': 0, 'patch': {'exposure': 1}})
    metadata(service, [2], {'title': 'External edit'})
    with pytest.raises(ValueError, match='Metadata conflict'):
        metadata(service, [1, 2], {'title': 'Stale batch', 'keywords': ['New']})
    first = service.dispatch('get_photo', {'photo_id': 1})
    assert first['title'] == '' and first['keywords'] == [] and first['metadata_revision'] == 0
    metadata(service, [1], {'title': 'First', 'keywords': ['Travel', 'travel', 'Straße', '  海边  ']})
    first = service.dispatch('get_photo', {'photo_id': 1})
    assert first['revision'] == 1 and first['recipe']['exposure'] == 1
    assert first['metadata_revision'] == 1 and set(first['keywords']) == {'Travel', 'Straße', '海边'}
    with service.catalog() as catalog:
        catalog.update_metadata(1, {'camera': 'Decoder report'})
    assert service.dispatch('get_photo', {'photo_id': 1})['title'] == 'First'


def test_live_smart_collections_all_any_and_revisions(library):
    service, _ = library
    rules = {'rating_min': 4, 'color_label': 'red'}
    all_ = service.dispatch('save_collection', {'name': 'Best red', 'kind': 'smart', 'rules': rules})
    any_ = service.dispatch('save_collection', {'name': 'Either', 'kind': 'smart', 'rules': rules, 'match': 'any'})
    service.dispatch('rate_photo', {'photo_id': 1, 'rating': 5})
    metadata(service, [2], {'color_label': 'red'})
    assert ids(service, collection_id=all_['id']) == []
    assert ids(service, collection_id=any_['id']) == [2, 1]
    metadata(service, [1], {'color_label': 'red'})
    assert ids(service, collection_id=all_['id']) == [1]
    with pytest.raises(ValueError, match='determined by its rules'):
        service.dispatch('collection_membership', {'collection_id': all_['id'],
            'expected_revision': 0, 'photo_ids': [3], 'action': 'add'})
    changed = service.dispatch('save_collection', {'collection_id': all_['id'], 'expected_revision': 0,
        'name': 'Unkeyworded', 'kind': 'smart', 'rules': {'has_keywords': False}})
    assert changed['revision'] == 1 and ids(service, collection_id=all_['id']) == [3, 2, 1]
    with pytest.raises(ValueError, match='Collection conflict'):
        service.dispatch('delete_collection', {'collection_id': all_['id'], 'expected_revision': 0})


def test_literal_unicode_search_and_combined_filters(library):
    service, paths = library
    metadata(service, [1], {'title': 'Café 海边', 'caption': 'Morning 100%', 'keywords': ['Straße']})
    metadata(service, [2], {'copyright': 'Example Photographer', 'color_label': 'green'})
    assert ids(service, search='CAFÉ') == [1]
    assert ids(service, search='STRASSE') == [1]
    assert ids(service, search='Photographer') == [2]
    assert ids(service, search='%') == [3, 1]
    assert ids(service, search="' OR 1=1 --") == []
    assert ids(service, filters={'keyword': 'STRASSE', 'folder': str(paths[0].parent)}) == [1]
    assert ids(service, filters={'has_keywords': False, 'color_label': 'green'}) == [2]
    assert ids(service, filters={'folder': str(paths[0].parent) + '-not-this'}) == []
    assert ids(service, sort='name', descending=False) == [1, 2, 3]


def test_pagination_deterministic_bounded_and_clamped(library):
    service, _ = library
    with service.catalog() as catalog:
        payload = json.dumps(Recipe().dict())
        catalog.db.executemany('INSERT INTO photos(path,name,bytes,mtime,recipe,created,rating) '
            'VALUES(?,?,?,?,?,?,?)', [(f'/synthetic/{i}.png', 'same.png', 0, 0, payload, 0, 3) for i in range(135)])
        catalog.db.commit()
    seen = []
    for offset in (0, 60, 120):
        result = service.dispatch('list_photos', {'offset': offset, 'sort': 'rating', 'descending': False})
        assert result['total'] == 138 and len(result['photos']) <= 60
        assert all('recipe' not in row and 'metadata' not in row for row in result['photos'])
        seen += [row['id'] for row in result['photos']]
    assert len(seen) == len(set(seen)) == 138
    result = service.dispatch('list_photos', {'offset': 120, 'search': 'forest'})
    assert result['offset'] == 0 and [p['id'] for p in result['photos']] == [1]


def test_invalid_membership_and_metadata_do_not_partially_apply(library):
    service, _ = library
    collection = service.dispatch('save_collection', {'name': 'Selection', 'kind': 'regular'})
    with pytest.raises(ValueError, match='does not exist'):
        service.dispatch('collection_membership', {'collection_id': collection['id'],
            'expected_revision': 0, 'photo_ids': [1, 999], 'action': 'add'})
    assert ids(service, collection_id=collection['id']) == []
    with pytest.raises(ValueError, match='blank'):
        metadata(service, [1, 2], {'keywords': ['   ']})
    with pytest.raises(ValueError, match='Duplicate'):
        metadata(service, [1, 1], {'title': 'No'})
    with pytest.raises(ValueError, match='exceeds'):
        service.dispatch('list_photos', {'filters': {'rating_min': 5, 'rating_max': 1}})
    assert service.dispatch('get_photo', {'photo_id': 1})['metadata_revision'] == 0


def test_legacy_migration_preserves_rows_and_backup_keeps_organization(tmp_path):
    root = tmp_path / 'old'
    root.mkdir()
    db = sqlite3.connect(root / 'catalog.sqlite')
    # Deliberately reproduce the pre-organization schema rather than migrating a
    # database created by the new Catalog implementation.
    db.execute("CREATE TABLE photos(id INTEGER PRIMARY KEY, path TEXT UNIQUE, name TEXT, bytes INTEGER, "
               "mtime INTEGER, rating INTEGER DEFAULT 0, recipe TEXT, metadata TEXT DEFAULT '{}', "
               "error TEXT DEFAULT '', revision INTEGER DEFAULT 0, created REAL)")
    db.execute('INSERT INTO photos(id,path,name,bytes,mtime,recipe,created,revision) VALUES(?,?,?,?,?,?,?,?)',
               (42, '/synthetic/old.png', 'old.png', 10, 20, json.dumps(Recipe(exposure=1).dict()), 0, 7))
    db.commit()
    db.close()
    service = Service(root)
    try:
        row = service.dispatch('get_photo', {'photo_id': 42})
        assert row['revision'] == 7 and row['recipe']['exposure'] == 1 and row['metadata_revision'] == 0
        metadata(service, [42], {'keywords': ['Legacy'], 'color_label': 'blue'})
        collection = service.dispatch('save_collection', {'name': 'Archive', 'kind': 'smart', 'rules': {'keyword': 'Legacy'}})
        with service.catalog() as catalog:
            backup_catalog(catalog, tmp_path / 'backup.sqlite')
    finally:
        service.close()
    restored = restore_catalog(tmp_path / 'backup.sqlite', tmp_path / 'restored')
    for _ in range(2):
        catalog = Catalog(restored)
        try:
            assert catalog.photo(42)['keywords'] == ['Legacy']
            assert catalog.photo(42)['color_label'] == 'blue'
            assert catalog.filtered_count(collection_id=collection['id']) == 1
        finally:
            catalog.close()
