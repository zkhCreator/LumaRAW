"""Keyword identity, migration, hierarchy and assignment contract regressions.

Inputs: generated photos and genuine schema-seven catalogs. Outputs: persistence,
bounded-query and rollback evidence. No desktop, XMP or Adobe pixel acceptance.
"""
import hashlib
import sqlite3

from PIL import Image
import pytest

from lumaraw.catalog import Catalog
from lumaraw.keywords import Keywords
from lumaraw.service import Service


@pytest.fixture
def library(tmp_path):
    paths = [tmp_path / f'photo-{i}.png' for i in range(3)]
    for path in paths:
        Image.new('RGB', (12, 8), 'navy').save(path)
    service = Service(tmp_path / 'catalog')
    service.dispatch('import_photos', {'paths':list(map(str, paths))})
    yield service, paths
    service.close()


def save(s, name, **kwargs):
    return s.dispatch('save_keyword', {'name':name,
        'expected_revision':s.dispatch('library_state')['keyword_revision'], **kwargs})['keyword_id']


def photo(s, id_):
    return s.dispatch('get_photo', {'photo_id':id_})


def targets(s, ids):
    return [{'photo_id':id_, 'expected_metadata_revision':photo(s, id_)['metadata_revision']} for id_ in ids]


def assign(s, tag, ids, action='add', **kwargs):
    return s.dispatch('keyword_membership', {'keyword_id':tag, 'targets':targets(s, ids),
        'action':action, 'expected_revision':s.dispatch('library_state')['keyword_revision'], **kwargs})


def edit(s, ids, values):
    return s.dispatch('edit_metadata', {'targets':targets(s, ids), 'patch':{'keywords':values}})


def test_nested_assignment_counts_filters_synonyms_and_original_safety(library):
    s, paths = library
    hashes = [hashlib.sha256(path.read_bytes()).digest() for path in paths]
    animal = save(s, 'Animals', synonyms=['Fauna'])
    dog = save(s, 'Dog', parent_id=animal, synonyms=['Canine', 'canine'])
    assign(s, dog, [1, 2])
    page = s.dispatch('list_keywords', {'parent_id':animal, 'photo_ids':[1, 2, 3]})
    tag = page['keywords'][0]
    assert (tag['name'], tag['photo_count'], tag['selected_count']) == ('Dog', 2, 2)
    assert tag['path'] == 'Animals | Dog' and tag['synonyms'] == ['canine']
    assert photo(s, 1)['keywords'] == ['Animals | Dog']
    assert photo(s, 1)['keyword_tags'] == [{'id':dog, 'path':'Animals | Dog'}]
    for filters in ({'keyword_id':animal}, {'keyword':'Fauna'}, {'keyword':'CANINE'}):
        assert s.dispatch('list_photos', {'filters':filters})['total'] == 2
    assert s.dispatch('list_photos', {'search':'fauna'})['total'] == 2
    assert s.dispatch('list_keywords', {'search':'can'})['keywords'][0]['id'] == dog
    assign(s, dog, [2], 'remove')
    assert s.dispatch('list_photos', {'filters':{'has_keywords':False}})['total'] == 2
    assert photo(s, 1)['revision'] == 0
    assert hashes == [hashlib.sha256(path.read_bytes()).digest() for path in paths]


def test_duplicate_leaf_identity_and_legacy_string_paths(library):
    s, _ = library
    france, usa = save(s, 'France'), save(s, 'USA')
    paris = save(s, 'Paris', parent_id=france)
    texas = save(s, 'Paris', parent_id=usa)
    with pytest.raises(ValueError, match='Ambiguous'):
        edit(s, [1], ['Paris'])
    edit(s, [1], ['France > Paris', 'USA | Paris'])
    assert {tag['id'] for tag in photo(s, 1)['keyword_tags']} == {paris, texas}
    edit(s, [2], ['Paris < France'])
    assert photo(s, 2)['keywords'] == ['France | Paris']
    edit(s, [3], ['Animals | Dog', 'animals > dog', 'Travel'])
    assert photo(s, 3)['keywords'] == ['Animals | Dog', 'Travel']
    assert s.dispatch('list_photos', {'filters':{'keyword_id':texas}})['total'] == 1
    assert s.dispatch('list_photos', {'filters':{'keyword':'paris'}})['total'] == 2


def test_rename_move_and_stale_photo_editor_cannot_restore_old_hierarchy(library):
    s, _ = library
    root, destination = save(s, 'Root'), save(s, 'Destination')
    child = save(s, 'Child', parent_id=root)
    leaf = save(s, 'Leaf', parent_id=child)
    assign(s, leaf, [1])
    before = photo(s, 1)
    save(s, 'Renamed', keyword_id=child, parent_id=destination)
    after = photo(s, 1)
    assert after['keywords'] == ['Destination | Renamed | Leaf']
    assert after['metadata_revision'] == before['metadata_revision']+1
    assert after['revision'] == before['revision']
    with pytest.raises(ValueError, match='Metadata conflict'):
        s.dispatch('edit_metadata', {'targets':[{'photo_id':1, 'expected_metadata_revision':before['metadata_revision']}],
                                     'patch':{'keywords':before['keywords']}})
    with pytest.raises(ValueError, match='descendants'):
        save(s, 'Destination', keyword_id=destination, parent_id=leaf)
    with pytest.raises(ValueError, match='already exists'):
        save(s, 'renamed', parent_id=destination)
    assert photo(s, 1)['keywords'] == after['keywords']


def test_membership_revision_conflicts_atomic_rollback_and_limits(library):
    s, _ = library
    tag = save(s, 'Travel')
    stale = targets(s, [1, 2])
    edit(s, [2], ['Other'])
    with pytest.raises(ValueError, match='Metadata conflict'):
        assign(s, tag, [1, 2], targets=stale)
    assert photo(s, 1)['keywords'] == []
    revision = s.dispatch('library_state')['keyword_revision']
    save(s, 'Added')
    with pytest.raises(ValueError, match='Keyword list changed'):
        assign(s, tag, [1], expected_revision=revision)
    edit(s, [1], [f'K{i}' for i in range(100)])
    before = photo(s, 1)
    with pytest.raises(ValueError, match='100'):
        assign(s, tag, [3, 1])
    assert photo(s, 3)['keywords'] == [] and photo(s, 1) == before
    with pytest.raises(ValueError):
        edit(s, [3], ['Created first', 'Invalid;tag'])
    assert s.dispatch('list_keywords', {'search':'Created first'})['total'] == 0


def test_subtree_deletion_copy_independence_and_nonreused_ids(library):
    s, _ = library
    root = save(s, 'Root')
    leaf = save(s, 'Leaf', parent_id=root)
    assign(s, leaf, [1])
    p = photo(s, 1)
    copy_id = s.dispatch('create_virtual_copies', {'targets':[{'photo_id':1,
        'expected_revision':p['revision'], 'expected_metadata_revision':p['metadata_revision']}]})['photos'][0]['id']
    assert photo(s, copy_id)['keyword_tags'] == p['keyword_tags']
    assign(s, leaf, [copy_id], 'remove')
    assert photo(s, 1)['keywords'] == ['Root | Leaf'] and photo(s, copy_id)['keywords'] == []
    assign(s, leaf, [copy_id])
    s.dispatch('delete_keyword', {'keyword_id':root, 'expected_revision':s.dispatch('library_state')['keyword_revision']})
    assert photo(s, 1)['keywords'] == [] and photo(s, copy_id)['keywords'] == []
    assert save(s, 'New') > leaf
    assert s.dispatch('list_photos', {'filters':{'keyword_id':root}})['total'] == 0


def test_pages_unicode_literal_search_and_depth_cap(library):
    s, _ = library
    with s.catalog() as c:
        with c.db:
            c.db.executemany('INSERT INTO keywords(name,normalized) VALUES(?,?)', [(f'K{i:03}', f'k{i:03}') for i in range(130)])
    page = s.dispatch('list_keywords', {'offset':60})
    assert len(page['keywords']) == 60 and page['total'] == 130 and page['offset'] == 60
    assert s.dispatch('list_keywords', {'offset':999})['offset'] == 120
    tag = save(s, 'Straße 100%')
    assert s.dispatch('list_keywords', {'search':'STRASSE'})['keywords'][0]['id'] == tag
    assert s.dispatch('list_keywords', {'search':'%'})['total'] == 1
    parent = None
    for i in range(32):
        parent = save(s, f'D{i}', parent_id=parent)
    with pytest.raises(ValueError, match='32 levels'):
        save(s, 'Too deep', parent_id=parent)


def test_schema_seven_migration_rollback_legacy_names_and_backup(tmp_path, monkeypatch):
    import lumaraw.keywords as module
    real = module.migrate
    monkeypatch.setattr(module, 'migrate', lambda db:None)
    c = Catalog(tmp_path / 'legacy')
    assert c.db.execute('PRAGMA user_version').fetchone()[0] == 7
    path = tmp_path / 'photo.png'
    Image.new('RGB', (8, 8)).save(path)
    c.import_paths([path])
    with c.db:
        c.db.execute("INSERT INTO photo_keywords VALUES(1,'legacy|literal','Legacy|literal')")
    c.db.set_authorizer(lambda action, name, *args:sqlite3.SQLITE_DENY
                        if action == sqlite3.SQLITE_DROP_TABLE and name == 'photo_keywords' else sqlite3.SQLITE_OK)
    with pytest.raises(sqlite3.DatabaseError):
        real(c.db)
    c.db.set_authorizer(None)
    assert c.db.execute('PRAGMA user_version').fetchone()[0] == 7
    assert c.db.execute('SELECT keyword FROM photo_keywords').fetchone()[0] == 'Legacy|literal'
    assert not c.db.execute("SELECT 1 FROM sqlite_master WHERE name='keywords'").fetchone()
    c.close()
    monkeypatch.setattr(module, 'migrate', real)
    s = Service(tmp_path / 'legacy')
    try:
        assert photo(s, 1)['keywords'] == ['Legacy|literal']
        edit(s, [1], ['Legacy|literal'])
        legacy_id = photo(s, 1)['keyword_tags'][0]['id']
        child = save(s, 'Child', parent_id=legacy_id)
        assign(s, child, [1])
        before = photo(s, 1)['keyword_tags']
        edit(s, [1], photo(s, 1)['keywords'])
        assert photo(s, 1)['keyword_tags'] == before
        backup = tmp_path / 'backup.sqlite'
        s.dispatch('backup_catalog', {'path':str(backup)})
        s.dispatch('restore_catalog', {'path':str(backup), 'destination':str(tmp_path/'restored')})
        restored = Catalog(tmp_path/'restored')
        assert Keywords(restored).photo(1) == photo(s, 1)['keyword_tags']
        restored.close()
    finally:
        s.close()


def test_create_and_assign_is_one_transaction_with_captured_photo_revisions(library):
    s, _ = library
    captured = targets(s, [1, 2])
    edit(s, [2], ['External'])
    with pytest.raises(ValueError, match='Metadata conflict'):
        save(s, 'Must not remain', targets=captured)
    assert s.dispatch('list_keywords', {'search':'Must not remain'})['total'] == 0
    tag = save(s, 'New and assigned', targets=targets(s, [1, 2]))
    assert photo(s, 1)['keyword_tags'][0]['id'] == tag
    assert set(photo(s, 2)['keywords']) == {'External', 'New and assigned'}
    edit(s, [3], [f'K{i}' for i in range(100)])
    with pytest.raises(ValueError, match='100'):
        save(s, 'Exceeds limit', targets=targets(s, [1, 3]))
    assert s.dispatch('list_keywords', {'search':'Exceeds limit'})['total'] == 0
    assert photo(s, 1)['keywords'] == ['New and assigned']


def test_keyword_filters_intersect_sources_and_stored_smart_rules(library):
    s, _ = library
    root = save(s, 'Places')
    child = save(s, 'Coast', parent_id=root)
    assign(s, child, [1, 2])
    regular = s.dispatch('save_collection', {'name':'Album', 'kind':'regular', 'photo_ids':[2, 3]})
    smart = s.dispatch('save_collection', {'name':'Smart', 'kind':'smart', 'rules':{'keyword_id':root}})
    assert s.dispatch('list_photos', {'collection_id':regular['id'], 'filters':{'keyword_id':root}})['photos'][0]['id'] == 2
    assert s.dispatch('list_photos', {'collection_id':smart['id']})['total'] == 2
    save(s, 'Elsewhere', keyword_id=child)
    assert s.dispatch('list_photos', {'collection_id':smart['id']})['total'] == 0


def test_legacy_separator_path_collision_rejects_ambiguous_replacement(library):
    s, _ = library
    edit(s, [1], ['A | B'])
    with s.catalog() as c:
        with c.db:
            literal = c.db.execute("INSERT INTO keywords(name,normalized) VALUES('A | B','a | b')").lastrowid
            c.db.execute('INSERT INTO keyword_photos VALUES(?,?)', (2, literal))
    before = photo(s, 1)
    with pytest.raises(ValueError, match='Ambiguous legacy'):
        edit(s, [1], ['A | B'])
    assert photo(s, 1) == before
    # The identity command remains unambiguous even for a legacy textual collision.
    assign(s, literal, [3])
    assert photo(s, 3)['keyword_tags'][0]['id'] == literal
