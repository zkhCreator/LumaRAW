"""Hierarchy and Quick/target semantics with disposable catalogs and originals.

Verify ancestor conflicts, aggregate smart membership, cycle/depth rejection,
atomic save/clear, target races, subtree duplication, migration and backup state.
No desktop behavior or Lightroom mixed-selection shortcut equivalence claim.
"""
import hashlib

from PIL import Image
import pytest

from lumaraw.catalog import Catalog
from lumaraw.collections import Collections
from lumaraw.library import backup_catalog,restore_catalog
from lumaraw.service import Service
from lumaraw.runtime import CATALOG_VERSION


@pytest.fixture
def library(tmp_path):
    service=Service(tmp_path/'catalog')
    service.dispatch('queue_control',{'action':'pause'})
    paths=[]
    for index in range(3):
        path=tmp_path/f'{index}.png';Image.new('RGB',(20,16),(index*30,60,120)).save(path);paths.append(path)
    service.dispatch('import_photos',{'paths':list(map(str,paths))})
    yield service,paths
    service.close()


def create(service,name,kind='regular',parent=None,**extra):
    return service.dispatch('save_collection',{'name':name,'kind':kind,'parent_id':parent,**extra})


def get(service,id_):return service.dispatch('get_collection',{'collection_id':id_})


def members(service,id_):
    return {r['id'] for r in service.dispatch('list_photos',{'collection_id':id_})['photos']}


def add(service,id_,photos):
    return service.dispatch('collection_membership',{'collection_id':id_,'expected_revision':get(service,id_)['revision'],
                                                     'photo_ids':photos,'action':'add'})


def test_nested_sets_aggregate_regular_and_live_smart_members(library):
    s,_=library
    root=create(s,'Trip','set');child=create(s,'Day 1','set',root['id'])
    regular=create(s,'Choices',parent=child['id'],photo_ids=[1,2,2])
    smart=create(s,'Stars','smart',root['id'],rules={'rating_min':4})
    s.dispatch('rate_photo',{'photo_id':3,'rating':5})
    assert members(s,root['id'])=={1,2,3} and members(s,child['id'])=={1,2}
    s.dispatch('rate_photo',{'photo_id':3,'rating':0})
    assert members(s,root['id'])=={1,2}
    assert [r['id'] for r in get(s,regular['id'])['ancestors']]==[root['id'],child['id']]
    assert {r['id'] for r in s.dispatch('list_collections',{'parent_id':None})['collections']}=={root['id']}
    assert {r['id'] for r in s.dispatch('list_collections',{'parent_id':root['id']})['collections']}=={child['id'],smart['id']}


def test_hierarchy_rejects_cycles_wrong_parents_and_invalid_initial_members(library):
    s,_=library
    root=create(s,'Root','set');child=create(s,'Child','set',root['id']);regular=create(s,'Album')
    for parent in (root['id'],child['id']):
        with pytest.raises(ValueError,match='ancestor'):
            s.dispatch('save_collection',{'collection_id':root['id'],'expected_revision':get(s,root['id'])['revision'],
                'name':'Root','kind':'set','parent_id':parent})
    with pytest.raises(ValueError,match='Only a collection set'):
        create(s,'Invalid',parent=regular['id'])
    with pytest.raises(ValueError,match='Photo does not exist'):
        create(s,'Invalid',photo_ids=[1,9999])
    with pytest.raises(ValueError,match='contain collections'):
        add(s,root['id'],[1])
    assert s.dispatch('list_collections')['total']==3


def test_subtree_deletion_conflicts_with_descendant_edits_and_preserves_photos(library):
    s,paths=library;before=[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
    root=create(s,'Root','set');child=create(s,'Child','set',root['id']);album=create(s,'Album',parent=child['id'])
    stale=get(s,root['id']);state=s.dispatch('collection_state')
    s.dispatch('set_target_collection',{'collection_id':album['id'],'expected_revision':state['revision']})
    add(s,album['id'],[1,2])
    with pytest.raises(ValueError,match='Collection conflict'):
        s.dispatch('delete_collection',{'collection_id':root['id'],'expected_revision':stale['revision']})
    s.dispatch('delete_collection',{'collection_id':root['id'],'expected_revision':get(s,root['id'])['revision']})
    assert s.dispatch('list_collections')['total']==0
    state=s.dispatch('collection_state');assert state['target']['id']==state['quick']['id']
    assert s.dispatch('list_photos')['total']==3
    assert before==[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
    with s.catalog() as c:assert c.db.execute('SELECT count(*) FROM collection_photos').fetchone()[0]==0


def test_quick_save_clear_and_target_conflicts_are_atomic(library):
    s,_=library;state=s.dispatch('collection_state');quick=state['quick']
    add(s,quick['id'],[1,2])
    quick=get(s,quick['id'])
    saved=s.dispatch('quick_collection',{'action':'save','name':'Permanent','expected_revision':quick['revision']})['saved']
    assert members(s,saved['id'])==members(s,quick['id'])=={1,2}
    with pytest.raises(ValueError,match='blank'):
        s.dispatch('quick_collection',{'action':'save','name':'   ','clear_after':True,'expected_revision':quick['revision']})
    assert members(s,quick['id'])=={1,2}
    copied=s.dispatch('quick_collection',{'action':'save','name':'Moved','clear_after':True,'expected_revision':quick['revision']})['saved']
    assert members(s,copied['id'])=={1,2} and members(s,quick['id'])==set()
    stale=s.dispatch('collection_state')
    s.dispatch('set_target_collection',{'collection_id':saved['id'],'expected_revision':stale['revision']})
    with pytest.raises(ValueError,match='Target collection conflict'):
        s.dispatch('target_membership',{'collection_id':quick['id'],'expected_state_revision':stale['revision'],
            'expected_revision':stale['quick']['revision'],'photo_ids':[3],'action':'add'})
    assert members(s,quick['id'])==set()
    fresh=s.dispatch('collection_state')
    s.dispatch('target_membership',{'collection_id':saved['id'],'expected_state_revision':fresh['revision'],
        'expected_revision':fresh['target']['revision'],'photo_ids':[3],'action':'add'})
    assert set(s.dispatch('collection_state',{'photo_ids':[1,3]})['members'])=={1,3}
    with pytest.raises(ValueError,match='cannot be deleted'):
        s.dispatch('delete_collection',{'collection_id':quick['id'],'expected_revision':get(s,quick['id'])['revision']})


def test_target_rejects_smart_sets_and_stale_membership(library):
    s,_=library
    for kind in ('smart','set'):
        row=create(s,kind,kind)
        with pytest.raises(ValueError,match='Only a regular'):
            s.dispatch('set_target_collection',{'collection_id':row['id'],'expected_revision':0})
    state=s.dispatch('collection_state');add(s,state['quick']['id'],[1])
    with pytest.raises(ValueError,match='Collection conflict'):
        s.dispatch('target_membership',{'collection_id':state['quick']['id'],'expected_state_revision':0,
            'expected_revision':0,'photo_ids':[2],'action':'add'})
    assert members(s,state['quick']['id'])=={1}


def test_duplicate_subtree_and_move_preserve_rules_and_membership(library):
    s,_=library
    root=create(s,'Trip','set');child=create(s,'Day','set',root['id']);album=create(s,'Album',parent=child['id'],photo_ids=[1,2])
    create(s,'All','smart',root['id'],rules={'rating_min':0})
    duplicate=s.dispatch('duplicate_collection',{'collection_id':root['id'],'expected_revision':get(s,root['id'])['revision'],'name':'Copy'})
    assert duplicate['copied_collections']==4 and members(s,duplicate['id'])=={1,2,3}
    updated=s.dispatch('save_collection',{'collection_id':album['id'],'expected_revision':get(s,album['id'])['revision'],
        'name':'Moved','kind':'regular','parent_id':None})
    assert updated['parent_id'] is None and members(s,album['id'])=={1,2}
    copychildren=s.dispatch('list_collections',{'parent_id':duplicate['id']})['collections']
    assert {row['kind'] for row in copychildren}=={'set','smart'}


def test_legacy_collection_migration_persistence_and_backup(tmp_path,monkeypatch):
    from lumaraw import catalog as module
    from lumaraw.organization import migrate_metadata
    root=tmp_path/'legacy'
    with monkeypatch.context() as patch:
        patch.setattr(module,'migrate',migrate_metadata)
        c=Catalog(root)
        with c.db:
            regular=c.db.execute("INSERT INTO collections(name,kind,created) VALUES('Existing','regular',0)").lastrowid
        assert c.db.execute('PRAGMA user_version').fetchone()[0]==1
        c.close()
    c=Catalog(root);store=Collections(c)
    assert store.get(regular)['name']=='Existing'
    store.set_target(0,regular);state=store.state()
    assert c.db.execute("SELECT count(*) FROM collections WHERE kind='quick'").fetchone()[0]==1
    backup_catalog(c,tmp_path/'backup');c.close()
    restored=restore_catalog(tmp_path/'backup',tmp_path/'restored');c=Catalog(restored)
    assert Collections(c).state()==state
    assert c.db.execute('PRAGMA user_version').fetchone()[0]==CATALOG_VERSION
    c.close()


def test_child_pagination_is_bounded_and_depth_limit_cannot_be_bypassed_by_move(library):
    s,_=library;root=create(s,'Root','set')
    for i in range(62):create(s,f'Album {i:03}',parent=root['id'])
    page=s.dispatch('list_collections',{'parent_id':root['id'],'offset':999})
    assert page['offset']==60 and len(page['collections'])==2 and page['total']==62
    parent=root
    for i in range(30):parent=create(s,f'Level {i}','set',parent['id'])
    subtree=create(s,'Subtree','set');create(s,'Nested','set',subtree['id'])
    with pytest.raises(ValueError,match='32 levels'):
        s.dispatch('save_collection',{'collection_id':subtree['id'],'expected_revision':get(s,subtree['id'])['revision'],
            'name':'Subtree','kind':'set','parent_id':parent['id']})
    assert get(s,subtree['id'])['parent_id'] is None
