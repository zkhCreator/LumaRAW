"""Source-wide capture-time stack previews, application and bounded refresh.

Generated photos and explicit clock fixtures prove exact gap boundaries, stale
preview rejection, scope isolation and rollback. No Adobe desktop equivalence or
real-camera metadata coverage follows from these synthetic contracts.
"""
import json
import sqlite3

from PIL import Image
import pytest

from lumaraw.catalog import Catalog
from lumaraw.model import Recipe
from lumaraw.service import Service


@pytest.fixture
def library(tmp_path):
    s=Service(tmp_path/'catalog');paths=[]
    for i in range(6):
        path=tmp_path/f'{i}.png';Image.new('RGB',(12,8),(i*20,80,120)).save(path);paths.append(str(path))
    s.dispatch('import_photos',{'paths':paths})
    with s.catalog() as c:
        with c.db:
            c.db.executemany("UPDATE photos SET taken_us=?,capture_clock='camera' WHERE id=?",
                [(1000000+t,i+1) for i,t in enumerate((0,100000,400000,700000,1000000,2000000))])
    yield s,tmp_path
    s.close()


def preview(s,folder,seconds,**extra):
    return s.dispatch('preview_auto_stack',{'folder':str(folder),'seconds':seconds,**extra})


def apply(s,folder,seconds,plan):
    return s.dispatch('apply_auto_stack',{'folder':str(folder),'seconds':seconds,'token':plan['token']})


def groups(s):
    with s.catalog() as c:
        return [[r[0] for r in c.db.execute('SELECT photo_id FROM stack_members WHERE stack_id=? ORDER BY position',(row[0],))]
                for row in c.db.execute('SELECT id FROM photo_stacks ORDER BY id')]


def test_adjacent_gaps_and_exact_threshold_boundary(library):
    s,folder=library
    plan=preview(s,folder,.3)
    assert (plan['photos'],plan['stacks'],plan['stacked_photos'],plan['unstacked_photos'])==(6,1,2,4)
    assert groups(s)==[]
    apply(s,folder,.3,plan);assert groups(s)==[[1,2]]
    plan=preview(s,folder,.31);assert plan['stacks']==1 and plan['stacked_photos']==5
    apply(s,folder,.31,plan);assert groups(s)==[[1,2,3,4,5]]
    assert s.dispatch('list_photos')['total']==2
    assert s.dispatch('list_photos',{'stacked':False})['total']==6
    plan=preview(s,folder,0);apply(s,folder,0,plan);assert groups(s)==[]


def test_nanosecond_residual_is_not_rounded_at_boundary(library):
    s,folder=library
    with s.catalog() as c:
        with c.db:
            c.db.execute('UPDATE photos SET taken_us=NULL')
            c.db.execute("UPDATE photos SET taken_us=1000000,taken_submicro='000000000000000000001' WHERE id=1")
            c.db.execute("UPDATE photos SET taken_us=1000001,taken_submicro='' WHERE id=2")
    # The gap is strictly smaller than one microsecond even with a 21-digit tail.
    plan=preview(s,folder,.000001);assert plan['stacked_photos']==2
    apply(s,folder,.000001,plan);assert groups(s)==[[1,2]]
    with s.catalog() as c:
        with c.db:c.db.execute("UPDATE photos SET taken_submicro='' WHERE id=1")
    assert preview(s,folder,.000001)['stacks']==0


def test_folder_scope_excludes_subfolders_and_collection_scope_crosses_folders(library):
    s,folder=library
    other=folder/'child';other.mkdir();path=other/'child.png';Image.new('RGB',(8,8)).save(path)
    s.dispatch('import_photos',{'paths':[str(path)]})
    with s.catalog() as c:
        with c.db:c.db.execute("UPDATE photos SET taken_us=1000001,capture_clock='camera' WHERE id=7")
    assert preview(s,folder,1)['photos']==6
    album=s.dispatch('save_collection',{'name':'Cross folder','kind':'regular','photo_ids':[1,7]})
    plan=s.dispatch('preview_auto_stack',{'collection_id':album['id'],'seconds':1})
    s.dispatch('apply_auto_stack',{'collection_id':album['id'],'seconds':1,'token':plan['token']})
    assert groups(s)==[[1,7]]
    assert s.dispatch('list_photos')['total']==7
    assert s.dispatch('list_photos',{'collection_id':album['id']})['total']==1
    assert s.dispatch('get_collection',{'collection_id':album['id']})['revision']>album['revision']
    smart=s.dispatch('save_collection',{'name':'Smart','kind':'smart'})
    with pytest.raises(ValueError,match='regular collection'):
        s.dispatch('preview_auto_stack',{'collection_id':smart['id'],'seconds':1})


@pytest.mark.parametrize('change',['time','stacks','import','duration'])
def test_preview_rejects_relevant_changes_before_replacement(library,change):
    s,folder=library;plan=preview(s,folder,.3);seconds=.3
    if change=='time':
        with s.catalog() as c:
            with c.db:c.db.execute('UPDATE photos SET taken_us=taken_us+1 WHERE id=2')
    elif change=='stacks':
        s.dispatch('stack_photos',{'action':'group','photo_ids':[3,4],'expected_revision':plan['stack_revision']})
    elif change=='import':
        path=folder/'new.png';Image.new('RGB',(8,8)).save(path);s.dispatch('import_photos',{'paths':[str(path)]})
    else:seconds=1
    before=groups(s)
    with pytest.raises(ValueError,match='Auto-stack conflict'):apply(s,folder,seconds,plan)
    assert groups(s)==before


def test_preview_rejects_membership_change_but_preserves_unrelated_edits(library):
    s,folder=library
    album=s.dispatch('save_collection',{'name':'A','kind':'regular','photo_ids':[1,2]})
    plan=s.dispatch('preview_auto_stack',{'collection_id':album['id'],'seconds':1})
    s.dispatch('collection_membership',{'collection_id':album['id'],'expected_revision':0,'photo_ids':[3],'action':'add'})
    with pytest.raises(ValueError,match='Auto-stack conflict'):
        s.dispatch('apply_auto_stack',{'collection_id':album['id'],'seconds':1,'token':plan['token']})
    plan=preview(s,folder,.3)
    s.dispatch('edit_photo',{'photo_id':1,'expected_revision':0,'patch':{'exposure':1.2}})
    apply(s,folder,.3,plan)
    assert s.dispatch('get_photo',{'photo_id':1})['recipe']['exposure']==1.2


def test_unknown_clocks_do_not_destroy_existing_stacks(library):
    s,folder=library
    revision=s.dispatch('stack_state')['revision']
    s.dispatch('stack_photos',{'action':'group','photo_ids':[1,2],'expected_revision':revision})
    with s.catalog() as c:
        with c.db:c.db.execute('UPDATE photos SET taken_us=NULL')
    plan=preview(s,folder,1)
    assert plan['unknown']==6 and plan['existing_stacks']==1
    with pytest.raises(ValueError,match='No capture times'):apply(s,folder,1,plan)
    assert groups(s)==[[1,2]]


def test_failed_apply_rolls_back_old_stacks(library):
    s,folder=library
    plan=preview(s,folder,.3);apply(s,folder,.3,plan)
    with s.catalog() as c:
        from lumaraw.auto_stacks import AutoStacks
        store=AutoStacks(c);plan=store.preview(1,folder=str(folder))
        before=[tuple(row) for row in c.db.execute('SELECT * FROM stack_members')]
        c.db.set_authorizer(lambda action,a,b,d,t:sqlite3.SQLITE_DENY
            if action==sqlite3.SQLITE_INSERT and a=='stack_members' else sqlite3.SQLITE_OK)
        with pytest.raises(sqlite3.DatabaseError):store.apply(1,plan['token'],folder=str(folder))
        c.db.set_authorizer(None)
        assert [tuple(row) for row in c.db.execute('SELECT * FROM stack_members')]==before
        assert store.preview(1,folder=str(folder))['token']==plan['token']


def test_refresh_is_paged_by_physical_family_and_does_not_hash(tmp_path):
    c=Catalog(tmp_path/'catalog');payload=json.dumps(Recipe().dict())
    with c.db:
        for i in range(62):
            path=tmp_path/f'{i}.jpg';exif=Image.Exif();exif[34665]={36867:'2026:09:26 12:00:00',37521:'99'}
            Image.new('RGB',(8,8)).save(path,exif=exif)
            c.db.execute('INSERT INTO photos(path,name,bytes,mtime,recipe,created) VALUES(?,?,0,0,?,0)',(str(path),path.name,payload))
    from lumaraw.virtual_copies import VirtualCopies
    copy=VirtualCopies(c).create([{'photo_id':1,'expected_revision':0,'expected_metadata_revision':0}])['photos'][0]['id']
    from lumaraw.auto_stacks import AutoStacks
    store=AutoStacks(c);first=store.refresh_times(folder=str(tmp_path))
    assert first['processed']==first['known']==60 and not first['done']
    assert c.photo(copy)['taken_us']==c.photo(1)['taken_us'] and c.photo(1)['sha256']==''
    second=store.refresh_times(folder=str(tmp_path),after_source_id=first['after_source_id'])
    assert second['processed']==2 and second['done']
    assert store.preview(1,folder=str(tmp_path))['photos']==63
    c.close()


def test_examples_and_pages_remain_bounded_for_large_groups(tmp_path):
    c=Catalog(tmp_path/'catalog');payload=json.dumps(Recipe().dict())
    with c.db:
        c.db.executemany('INSERT INTO photos(path,name,bytes,mtime,recipe,created,taken_us) VALUES(?,?,0,0,?,0,?)',
            [(str(tmp_path/f'{i}.png'),str(i),payload,i//2*1000000) for i in range(130)])
    from lumaraw.auto_stacks import AutoStacks
    store=AutoStacks(c);plan=store.preview(.1,folder=str(tmp_path))
    assert plan['stacks']==65 and len(plan['examples'])==20
    store.apply(.1,plan['token'],folder=str(tmp_path))
    assert c.filtered_count()==65 and len(c.filtered_page())==60
    plan=store.preview(3600,folder=str(tmp_path));store.apply(3600,plan['token'],folder=str(tmp_path))
    assert c.filtered_count()==1 and c.filtered_page()[0]['stack_count']==130
    c.close()


def test_backup_restores_precise_clocks_stacks_and_retired_collection_ids(library):
    from lumaraw.auto_stacks import AutoStacks
    from lumaraw.collections import Collections
    from lumaraw.library import backup_catalog, restore_catalog

    service, folder = library
    removed = service.dispatch('save_collection', {'name': 'Retired', 'kind': 'regular'})
    service.dispatch('delete_collection', {
        'collection_id': removed['id'], 'expected_revision': removed['revision']})
    with service.catalog() as catalog:
        with catalog.db:
            catalog.db.execute("UPDATE photos SET taken_submicro='123456789' WHERE id=1")
        stacks = AutoStacks(catalog)
        plan = stacks.preview(0.3, folder=str(folder))
        stacks.apply(0.3, plan['token'], folder=str(folder))
        expected = stacks.preview(0.3, folder=str(folder))
        backup_catalog(catalog, folder / 'backup')
    restored = Catalog(restore_catalog(folder / 'backup', folder / 'restored'))
    try:
        assert AutoStacks(restored).preview(0.3, folder=str(folder)) == expected
        assert restored.photo(1)['taken_submicro'] == '123456789'
        assert restored.filtered_count() == 5
        assert Collections(restored).save('After restore')['id'] > removed['id']
    finally:
        restored.close()
