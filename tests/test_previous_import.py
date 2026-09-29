"""Last-import source membership across real import and catalog transactions.

Generated originals prove exact checked scope, replacement, persistence, family
identity, rollback, legacy partial commits and bounded filtering. These tests do
not infer unavailable historical batches or claim rendered Adobe parity.
"""
import json
import sqlite3

import pytest

from lumaraw.catalog import Catalog
from lumaraw.library import backup_catalog, restore_catalog
from lumaraw.model import Recipe
from lumaraw.previous_import import migrate, state
from lumaraw.runtime import CATALOG_VERSION
from lumaraw.service import Service
from test_import_review import picture, prepare, scan, apply
from test_folder_sync import prepare as prepare_sync, scan as scan_sync, apply as apply_sync
from test_virtual_copies import copy, target


@pytest.fixture
def library(tmp_path):
    s=Service(tmp_path/'catalog',presets_root=tmp_path/'presets')
    s.dispatch('queue_control',{'action':'pause'})
    yield s,tmp_path
    s.close()


def previous(s,**kwargs):
    return s.dispatch('list_photos',{'mode':'previous_import','stacked':False,**kwargs})


def ids(s,**kwargs):
    return [p['id'] for p in previous(s,**kwargs)['photos']]


def test_review_replaces_only_after_checked_import_and_preserves_empty_cancelled(library):
    s,root=library
    paths=[picture(root/f'{i}.png') for i in range(4)]
    assert previous(s)['total']==0
    s.dispatch('import_photos',{'paths':[str(paths[0])]})
    first=previous(s)['previous_import']
    p=scan(s,prepare(s,paths))
    assert ids(s)==[1] and previous(s)['previous_import']==first
    new=s.dispatch('get_import',{'plan_id':p['id'],'kind':'new'})['items']
    p=s.dispatch('select_import_items',{'plan_id':p['id'],'expected_revision':p['revision'],
        'item_ids':[new[0]['id']],'selected':False})['plan']
    result=apply(s,p)
    assert result['imported']==2 and set(ids(s))=={2,3}
    assert previous(s)['previous_import']['kind']=='reviewed'
    saved=previous(s)['previous_import']
    s.dispatch('import_photos',{'paths':[str(paths[0])]})
    assert previous(s)['previous_import']==saved
    p=scan(s,prepare(s,paths))
    s.dispatch('cancel_import',{'plan_id':p['id']})
    assert previous(s)['previous_import']==saved
    p=scan(s,prepare(s,[paths[0]]))
    with pytest.raises(ValueError,match='at least one'):
        apply(s,p)
    assert previous(s)['previous_import']==saved


def test_late_import_failure_rolls_back_previous_membership_and_photos(library):
    s,root=library
    s.dispatch('import_photos',{'paths':[str(picture(root/'old.png'))]})
    before=previous(s)
    p=scan(s,prepare(s,[picture(root/'new.png')]))
    with s.catalog() as c:
        with c.db:c.db.execute("CREATE TRIGGER fail_receipt BEFORE UPDATE OF state ON import_plans WHEN NEW.state='applied' BEGIN SELECT RAISE(ABORT,'test receipt failure'); END")
    result=apply(s,p)
    assert result['state']=='failed' and 'test receipt failure' in result['error']
    assert previous(s)==before and s.dispatch('status')['photos']==1


def test_folder_sync_imports_replace_source_but_metadata_only_does_not(library):
    s,root=library
    a=picture(root/'Photos'/'a.png')
    s.dispatch('import_photos',{'paths':[str(a)]})
    picture(root/'Photos'/'b.png')
    p=scan_sync(s,prepare_sync(s))
    result=apply_sync(s,p)
    assert result['imported']==1 and ids(s)==[2]
    before=previous(s)['previous_import']
    result=apply_sync(s,scan_sync(s,prepare_sync(s)))
    assert result['imported']==0 and previous(s)['previous_import']==before
    (root/'Photos'/'b.png').unlink()
    apply_sync(s,scan_sync(s,prepare_sync(s)),remove_missing=True)
    assert previous(s)['total']==0
    with s.catalog() as c:
        assert c.db.execute('SELECT count(*) FROM previous_import_sources').fetchone()[0]==0


def test_family_membership_survives_copy_promotion_relink_and_backup(library):
    s,root=library
    original=picture(root/'a.png');data=original.read_bytes()
    s.dispatch('import_photos',{'paths':[str(original)]})
    copied=copy(s)
    assert set(ids(s))=={1,copied}
    s.dispatch('set_copy_as_master',target(s,copied,source=True))
    moved=root/'moved.png';original.rename(moved)
    s.dispatch('relink_photo',{'photo_id':copied,'path':str(moved)})
    assert set(ids(s))=={1,copied} and moved.read_bytes()==data
    with s.catalog() as c:backup_catalog(c,root/'backup.sqlite')
    restored=restore_catalog(root/'backup.sqlite',root/'restored')
    with_catalog=Catalog(restored)
    try:
        assert {p['id'] for p in with_catalog.filtered_page(mode='previous_import',stacked=False)}=={1,copied}
    finally:with_catalog.close()


def test_filters_pagination_source_exclusivity_and_metadata_edits(library):
    s,root=library
    s.dispatch('import_photos',{'paths':[str(picture(root/'old.png'))]})
    paths=[str(picture(root/f'new-{i:03}.png')) for i in range(65)]
    s.dispatch('import_photos',{'paths':paths})
    result=previous(s,sort='name',descending=False)
    assert result['total']==65 and len(result['photos'])==60 and result['photos'][0]['name']=='new-000.png'
    assert len(previous(s,offset=60)['photos'])==5
    assert previous(s,offset=999)['offset']==60
    assert ids(s,search='old')==[]
    s.dispatch('rate_photo',{'photo_id':2,'rating':5})
    assert ids(s,filters={'rating_min':5})==[2]
    folder=s.dispatch('get_folder',{'photo_id':2})
    collection=s.dispatch('save_collection',{'name':'A','kind':'regular'})
    for source in ({'folder_id':folder['id']},{'collection_id':collection['id']}):
        with pytest.raises(ValueError,match='cannot be combined'):
            previous(s,**source)
    assert 'recipe' not in result['photos'][0] and 'metadata' not in result['photos'][0]


def test_legacy_partial_commits_keep_exact_membership_after_failure(tmp_path):
    c=Catalog(tmp_path/'catalog')
    try:
        old=picture(tmp_path/'old.png');c.import_paths([old])
        paths=[picture(tmp_path/f'{i}.png') for i in range(105)]
        def failing():
            yield from paths
            raise RuntimeError('interrupted iterator')
        with pytest.raises(RuntimeError,match='interrupted iterator'):
            c.import_paths(failing())
        c.db.rollback()
        assert c.count()==101 and c.filtered_count(mode='previous_import',stacked=False)==100
        assert state(c.db)['imported']==100
        assert 1 not in set(c.filtered_ids('previous_import'))
    finally:c.close()


def test_cancelled_legacy_import_records_only_committed_new_sources(tmp_path):
    c=Catalog(tmp_path/'catalog')
    try:
        old=picture(tmp_path/'old.png');c.import_paths([old])
        paths=[picture(tmp_path/f'{i}.png') for i in range(4)]
        calls=0
        def cancelled():
            nonlocal calls
            calls+=1
            return calls>2
        assert c.import_paths(paths,cancelled)==(2,0)
        assert c.filtered_count(mode='previous_import',stacked=False)==2 and state(c.db)['imported']==2
    finally:c.close()


def test_preference_and_source_survive_restart(library):
    s,root=library
    assert s.dispatch('settings')['select_previous_import'] is True
    s.dispatch('settings',{'select_previous_import':False})
    s.dispatch('import_photos',{'paths':[str(picture(root/'a.png'))]})
    before=previous(s)['previous_import']
    s.close()
    other=Service(root/'catalog',presets_root=root/'presets')
    try:
        assert other.dispatch('settings')['select_previous_import'] is False
        assert previous(other)['previous_import']==before and ids(other)==[1]
    finally:other.close()


def test_genuine_schema20_migration_never_infers_old_batches_and_rolls_back(tmp_path,monkeypatch):
    from lumaraw import catalog as module
    from legacy_catalog import migrate_to
    with monkeypatch.context() as context:
        context.setattr(module,'migrate',lambda db:migrate_to(db,20))
        c=Catalog(tmp_path/'old')
        with c.db:c.db.execute('INSERT INTO photos(path,name,bytes,mtime,recipe,created) VALUES(?,?,?,?,?,?)',
                              ('/fixture/a.png','a.png',1,0,json.dumps(Recipe().dict()),0))
        c.db.set_authorizer(lambda action,a,b,d,t:sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_CREATE_TRIGGER and a=='previous_import_photo_deleted' else sqlite3.SQLITE_OK)
        with pytest.raises(sqlite3.DatabaseError):migrate(c.db)
        c.db.set_authorizer(None)
        assert c.db.execute('PRAGMA user_version').fetchone()[0]==20
        assert not c.db.execute("SELECT 1 FROM sqlite_master WHERE name='previous_import_sources'").fetchone()
        c.close()
    c=Catalog(tmp_path/'old')
    try:
        assert c.db.execute('PRAGMA user_version').fetchone()[0]==CATALOG_VERSION
        assert c.count()==1 and c.filtered_count(mode='previous_import',stacked=False)==0
    finally:c.close()
