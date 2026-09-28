"""Photo stack contracts using disposable catalogs and generated photographs.

Prove scoped ordering, bounded pages, optimistic conflicts and lifecycle cleanup.
No Lightroom desktop interaction or pixel parity is claimed by these tests.
"""
import json
from pathlib import Path

from PIL import Image
import pytest

from lumaraw.catalog import Catalog
from lumaraw.model import Recipe
from lumaraw.service import Service
from lumaraw.stacks import Stacks
from lumaraw.runtime import CATALOG_VERSION


@pytest.fixture
def service(tmp_path):
    s=Service(tmp_path/'catalog')
    s.dispatch('queue_control',{'action':'pause'})
    paths=[]
    for i in range(6):
        path=tmp_path/f'{i}.png'
        Image.new('RGB',(12,8),(i*30,80,120)).save(path)
        paths.append(str(path))
    s.dispatch('import_photos',{'paths':paths})
    yield s
    s.close()


def change(s, action, ids, **extra):
    return s.dispatch('stack_photos',{'action':action,'photo_ids':ids,
        'expected_revision':s.dispatch('stack_state')['revision'],**extra})


def page(s, **extra):
    return s.dispatch('list_photos',{'sort':'imported','descending':False,**extra})


def ids(s, **extra):
    return [row['id'] for row in page(s,**extra)['photos']]


def test_group_cover_collapse_and_atomic_conflict(service):
    s=service
    before=s.dispatch('stack_state')['revision']
    change(s,'group',[1,2,3],active_id=2)
    assert ids(s)==[2,4,5,6] and page(s)['total']==4
    cover=page(s)['photos'][0]
    assert (cover['stack_count'],cover['stack_top'],cover['stack_collapsed'])==(3,2,1)
    with pytest.raises(ValueError,match='Stack conflict'):
        s.dispatch('stack_photos',{'action':'unstack','photo_ids':[2],'expected_revision':before})
    assert ids(s)==[2,4,5,6]
    change(s,'expand',[2])
    assert ids(s)==[2,1,3,4,5,6]
    assert ids(s,descending=True)==[6,5,4,2,1,3]
    change(s,'top',[3])
    assert ids(s)==[3,2,1,4,5,6]
    change(s,'down',[3]); assert ids(s)==[2,3,1,4,5,6]
    change(s,'up',[1]); assert ids(s)==[2,1,3,4,5,6]
    change(s,'unstack',[1]); assert ids(s)==[1,2,3,4,5,6]


def test_folder_collection_and_smart_scopes_are_independent(service,tmp_path):
    s=service
    other=tmp_path/'other'/'7.png';other.parent.mkdir();Image.new('RGB',(8,8)).save(other)
    s.dispatch('import_photos',{'paths':[str(other)]})
    with pytest.raises(ValueError,match='same folder'):
        change(s,'group',[1,7])
    regular=s.dispatch('save_collection',{'name':'Album','kind':'regular','photo_ids':[1,2,7]})['id']
    change(s,'group',[1,7],collection_id=regular,active_id=7)
    assert ids(s,collection_id=regular)==[2,7]
    assert len(ids(s))==7
    change(s,'group',[1,2])
    assert ids(s)==[1,3,4,5,6,7]
    assert ids(s,collection_id=regular)==[2,7]
    smart=s.dispatch('save_collection',{'name':'Everything','kind':'smart'})['id']
    assert len(ids(s,collection_id=smart))==7
    with pytest.raises(ValueError,match='regular collection'):
        change(s,'group',[1,2],collection_id=smart)
    with pytest.raises(ValueError,match='belong'):
        change(s,'group',[1,3],collection_id=regular)
    assert len(ids(s,stacked=False))==7


def test_grouping_two_covers_moves_only_selected_photo(service):
    s=service
    change(s,'group',[1,2,3]);change(s,'group',[4,5,6])
    change(s,'group',[1,4],active_id=1)
    assert ids(s)==[1,5]
    change(s,'expand',[1,5])
    assert ids(s)==[1,2,3,4,5,6]
    byid={row['id']:row for row in page(s)['photos']}
    assert byid[4]['stack_top']==1 and byid[5]['stack_count']==2


def test_removing_cover_and_two_photo_stack_cleanup(service):
    s=service
    change(s,'group',[1,2,3]);change(s,'remove',[1])
    assert ids(s)==[1,2,4,5,6]
    assert page(s)['photos'][1]['stack_count']==2
    change(s,'remove',[2]);assert ids(s)==[1,2,3,4,5,6]
    with s.catalog() as c:
        assert c.db.execute('SELECT count(*) FROM photo_stacks').fetchone()[0]==0
        assert c.db.execute('SELECT count(*) FROM stack_members').fetchone()[0]==0


def test_membership_and_collection_deletion_clean_scoped_stacks(service):
    s=service
    album=s.dispatch('save_collection',{'name':'Album','kind':'regular','photo_ids':[1,2,3]})
    change(s,'group',[1,2,3],collection_id=album['id'])
    change(s,'group',[1,2])
    current=s.dispatch('get_collection',{'collection_id':album['id']})
    s.dispatch('collection_membership',{'collection_id':album['id'],'expected_revision':current['revision'],'photo_ids':[1,2],'action':'remove'})
    assert ids(s,collection_id=album['id'])==[3]
    assert ids(s)==[1,3,4,5,6]
    current=s.dispatch('get_collection',{'collection_id':album['id']})
    s.dispatch('delete_collection',{'collection_id':album['id'],'expected_revision':current['revision']})
    assert ids(s)==[1,3,4,5,6]
    with s.catalog() as c:
        assert c.db.execute("SELECT count(*) FROM stack_members WHERE scope!='folder'").fetchone()[0]==0


def test_virtual_copy_joins_expanded_folder_stack_and_deletion_repairs(service):
    s=service
    change(s,'group',[1,2])
    album=s.dispatch('save_collection',{'name':'Copies','kind':'regular','photo_ids':[1]})
    copy=s.dispatch('create_virtual_copies',{'targets':[{'photo_id':1,'expected_revision':0,'expected_metadata_revision':0}],
        'collection_id':album['id'],'expected_collection_revision':0})['photos'][0]
    assert ids(s)[:3]==[1,copy['id'],2]
    assert page(s)['photos'][0]['stack_count']==3 and not page(s)['photos'][0]['stack_collapsed']
    assert len(ids(s,collection_id=album['id']))==2
    assert all(row['stack_id'] is None for row in page(s,collection_id=album['id'])['photos'])
    s.dispatch('remove_virtual_copies',{'targets':[{'photo_id':copy['id'],'expected_revision':0,
        'expected_metadata_revision':0,'expected_source_revision':copy['source_revision']}]})
    assert page(s)['photos'][0]['stack_count']==2
    change(s,'remove',[2]);assert all(row['stack_id'] is None for row in page(s)['photos'])


def test_collapsed_mutations_and_search_do_not_select_hidden_members(service):
    s=service
    change(s,'group',[1,2,3])
    s.dispatch('rate_photos',{'photo_ids':ids(s),'rating':5})
    assert s.dispatch('get_photo',{'photo_id':2})['rating']==0
    assert ids(s,filters={'rating_min':5})==[1,4,5,6]
    assert ids(s,search='2.png')==[]
    assert ids(s,search='2.png',stacked=False)==[3]
    change(s,'expand',[1]);assert ids(s,search='2.png')==[3]


def test_large_stack_stays_contiguous_across_pages_and_reopens(tmp_path):
    root=tmp_path/'catalog';c=Catalog(root)
    recipe=json.dumps(Recipe().dict())
    with c.db:
        c.db.executemany('INSERT INTO photos(path,name,bytes,mtime,recipe,created) VALUES(?,?,0,0,?,0)',
            [(str(tmp_path/f'{i:03}.png'),f'{i:03}.png',recipe) for i in range(130)])
    stacks=Stacks(c)
    for group in (list(range(1,61)),[1,*range(61,120)],[1,*range(120,131)]):
        stacks.change('group',group,stacks.revision())
    assert c.filtered_count()==1
    stacks.change('expand',[1],stacks.revision())
    pages=[c.filtered_page(offset,sort='name',descending=True) for offset in (0,60,120)]
    assert list(map(len,pages))==[60,60,10]
    assert [r['id'] for rows in pages for r in rows]==list(range(1,131))
    assert all('recipe' not in row for rows in pages for row in rows)
    revision=stacks.revision();c.close();c=Catalog(root)
    assert Stacks(c).revision()==revision and c.filtered_count()==130
    c.close()


def test_relink_to_other_folder_detaches_only_folder_stack(service,tmp_path):
    s=service
    row=s.dispatch('get_photo',{'photo_id':1})
    album=s.dispatch('save_collection',{'name':'A','kind':'regular','photo_ids':[1,2]})['id']
    change(s,'group',[1,2]);change(s,'group',[1,2],collection_id=album)
    new=tmp_path/'moved'/'0.png';new.parent.mkdir();Path(row['path']).rename(new)
    s.dispatch('relink_photo',{'photo_id':1,'path':str(new)})
    assert len(ids(s))==6 and len(ids(s,collection_id=album))==1


def test_v3_migration_retains_photos_without_inventing_stacks(service):
    s=service
    with s.catalog() as c:
        original=c.summaries([1,2])
        with c.db:
            triggers=c.db.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE '%stack%'").fetchall()
            for row in triggers:c.db.execute('DROP TRIGGER '+row[0])
            for table in ('stack_state','stack_members','photo_stacks'):c.db.execute('DROP TABLE '+table)
            c.db.execute('PRAGMA user_version=3')
    with s.catalog() as c:
        assert c.db.execute('PRAGMA user_version').fetchone()[0]==CATALOG_VERSION
        assert c.summaries([1,2])==original
        assert Stacks(c).revision()==0 and c.filtered_count()==6


def test_copy_collection_and_quick_save_preserve_stack_organization(service):
    s=service
    parent=s.dispatch('save_collection',{'name':'Parent','kind':'set'})
    album=s.dispatch('save_collection',{'name':'A','kind':'regular','parent_id':parent['id'],'photo_ids':[1,2,3]})
    parent=s.dispatch('get_collection',{'collection_id':parent['id']})
    change(s,'group',[2,3],collection_id=album['id'],active_id=3)
    with pytest.raises(ValueError,match='Collection conflict'):
        s.dispatch('delete_collection',{'collection_id':parent['id'],'expected_revision':parent['revision']})
    album=s.dispatch('get_collection',{'collection_id':album['id']})
    cloned=s.dispatch('duplicate_collection',{'collection_id':album['id'],'expected_revision':album['revision'],'name':'B'})
    assert ids(s,collection_id=cloned['id'])==[1,3]
    change(s,'expand',[3],collection_id=cloned['id'])
    assert ids(s,collection_id=cloned['id'])==[1,3,2] and ids(s,collection_id=album['id'])==[1,3]
    quick=s.dispatch('collection_state')['quick']
    s.dispatch('collection_membership',{'collection_id':quick['id'],'expected_revision':quick['revision'],
        'photo_ids':[4,5,6],'action':'add'})
    change(s,'group',[5,6],collection_id=quick['id'])
    quick=s.dispatch('collection_state')['quick']
    saved=s.dispatch('quick_collection',{'action':'save','name':'Saved','expected_revision':quick['revision'],'clear_after':True})['saved']
    assert ids(s,collection_id=saved['id'])==[4,5] and ids(s,collection_id=quick['id'])==[]


def test_bulk_visibility_is_source_scoped_and_conflict_checked(service,tmp_path):
    s=service
    album=s.dispatch('save_collection',{'name':'A','kind':'regular','photo_ids':[1,2]})['id']
    change(s,'group',[1,2]);change(s,'group',[3,4]);change(s,'group',[1,2],collection_id=album)
    revision=s.dispatch('stack_state')['revision']
    result=s.dispatch('set_stack_visibility',{'collapsed':False,'expected_revision':revision,'folder':str(tmp_path/'unrelated')})
    assert result['changed']==0 and result['revision']==revision
    result=s.dispatch('set_stack_visibility',{'collapsed':False,'expected_revision':revision,'folder':str(tmp_path)})
    assert result['changed']==2 and len(ids(s))==6 and ids(s,collection_id=album)==[1]
    with pytest.raises(ValueError,match='Stack conflict'):
        s.dispatch('set_stack_visibility',{'collapsed':True,'expected_revision':revision})
    s.dispatch('set_stack_visibility',{'collapsed':False,'expected_revision':result['revision'],'collection_id':album})
    assert ids(s,collection_id=album)==[1,2]


def test_removed_unstacked_collection_invalidates_captured_scope(service):
    s=service
    old=s.dispatch('save_collection',{'name':'Old','kind':'regular','photo_ids':[1,2]})
    revision=s.dispatch('stack_state')['revision']
    s.dispatch('delete_collection',{'collection_id':old['id'],'expected_revision':old['revision']})
    new=s.dispatch('save_collection',{'name':'New','kind':'regular','photo_ids':[1,2]})
    # A deleted source invalidates captured stack requests; the new collection
    # also gets a fresh identity, even if it has exactly the same members.
    assert new['id']>old['id']
    with pytest.raises(ValueError,match='Stack conflict'):
        s.dispatch('stack_photos',{'action':'group','photo_ids':[1,2],
            'collection_id':old['id'],'expected_revision':revision})
    assert ids(s,collection_id=new['id'])==[1,2]


def test_split_selected_subset_preserves_order_and_both_remaining_groups(service):
    s=service
    change(s,'group',[1,2,3,4,5])
    with pytest.raises(ValueError,match='Expand'):change(s,'split',[2,4])
    change(s,'expand',[1])
    with pytest.raises(ValueError,match='beyond its cover'):change(s,'split',[1])
    with pytest.raises(ValueError,match='at least one'):change(s,'split',[1,2,3,4,5])
    change(s,'split',[4,2])
    rows=page(s)['photos'];byid={row['id']:row for row in rows}
    assert byid[1]['stack_count']==3 and byid[2]['stack_count']==2
    assert byid[4]['stack_top']==2 and ids(s)==[1,3,5,2,4,6]
    change(s,'split',[4])
    assert page(s)['total']==6 and all(byid['stack_id'] is None for byid in page(s)['photos'] if byid['id'] in (2,4))
