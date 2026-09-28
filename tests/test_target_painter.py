"""Captured-target Painter transactions and bounded membership validation.

Inputs: isolated collections, generated photographs, variants and revisions.
Outputs: atomic add/remove, original/recipe/metadata/job preservation, stack cleanup
and evidence that photo detail expansion is unnecessary. No desktop acceptance.
"""
import sqlite3

from PIL import Image
import pytest

from lumaraw.catalog import Catalog
from lumaraw.service import Service


@pytest.fixture
def library(tmp_path):
    paths=[tmp_path/f'{i}.png' for i in range(3)]
    for path in paths:
        Image.new('RGB',(8,8),'navy').save(path)
    s=Service(tmp_path/'catalog',presets_root=tmp_path/'presets')
    s.dispatch('queue_control',{'action':'pause'})
    s.dispatch('import_photos',{'paths':list(map(str,paths))})
    yield s,paths
    s.close()


def state(s):
    return s.dispatch('collection_state',{'photo_ids':[1,2,3]})


def stroke(s,ids=(1,2),action='add',captured=None):
    captured=captured or state(s)
    return s.dispatch('target_membership',{'collection_id':captured['target']['id'],
        'expected_state_revision':captured['revision'],'expected_revision':captured['target']['revision'],
        'photo_ids':list(ids),'action':action})


def photo(s,id_):
    return s.dispatch('get_photo',{'photo_id':id_})


def test_repeat_add_and_remove_preserve_metadata_recipes_jobs_and_originals(library,tmp_path):
    s,paths=library
    photos=[photo(s,i) for i in (1,2,3)]
    originals=[p.read_bytes() for p in paths]
    job=s.dispatch('enqueue_exports',{'photo_ids':[1],'destination':str(tmp_path/'exports'),
        'format':'jpeg','request_key':'before-target'})['job_ids'][0]
    frozen=s.dispatch('get_job',{'job_id':job})
    initial=state(s)
    assert set(stroke(s,ids=[1,1,2])['members'])=={1,2}
    assert set(stroke(s)['members'])=={1,2}  # Add is not a toggle.
    assert stroke(s,[1],action='remove')['members']==[]
    assert state(s)['members']==[2]
    assert state(s)['target']['revision']==initial['target']['revision']+3
    assert photos==[photo(s,i) for i in (1,2,3)]
    assert originals==[p.read_bytes() for p in paths]
    assert s.dispatch('get_job',{'job_id':job})==frozen


def test_membership_never_materializes_photo_or_keyword_details(library,monkeypatch):
    s,_=library
    def unexpected(*args):
        raise AssertionError('Membership must not expand complete photo metadata')
    monkeypatch.setattr(Catalog,'photo',unexpected)
    assert set(stroke(s)['members'])=={1,2}
    assert stroke(s,action='remove')['members']==[]
    before=state(s)
    with pytest.raises(ValueError,match='Photo does not exist'):
        stroke(s,[1,9999])
    assert state(s)==before


@pytest.mark.parametrize('change',['target','membership','rename','delete'])
def test_changed_captured_target_never_retargets_or_replays(library,change):
    s,_=library
    album=s.dispatch('save_collection',{'name':'Target','kind':'regular'})
    s.dispatch('set_target_collection',{'collection_id':album['id'],'expected_revision':state(s)['revision']})
    captured=state(s)
    if change=='target':
        s.dispatch('set_target_collection',{'collection_id':None,'expected_revision':captured['revision']})
    elif change=='membership':
        stroke(s,[3])
    elif change=='rename':
        s.dispatch('save_collection',{'collection_id':album['id'],'expected_revision':album['revision'],
            'name':'Renamed','kind':'regular'})
    else:
        s.dispatch('delete_collection',{'collection_id':album['id'],'expected_revision':album['revision']})
    before=state(s)
    with pytest.raises(ValueError,match='conflict'):
        stroke(s,captured=captured)
    assert state(s)==before


def test_partial_insert_failure_rolls_back_members_and_ancestor_revisions(library):
    s,_=library
    parent=s.dispatch('save_collection',{'name':'Parent','kind':'set'})
    album=s.dispatch('save_collection',{'name':'Target','kind':'regular','parent_id':parent['id']})
    s.dispatch('set_target_collection',{'collection_id':album['id'],'expected_revision':state(s)['revision']})
    before=state(s)
    ancestor=s.dispatch('get_collection',{'collection_id':parent['id']})
    with s.catalog() as c,c.db:
        c.db.execute("CREATE TRIGGER fail_target BEFORE INSERT ON collection_photos WHEN NEW.photo_id=2 BEGIN SELECT RAISE(ABORT,'injected'); END")
    with pytest.raises(sqlite3.IntegrityError,match='injected'):
        stroke(s)
    assert state(s)==before
    assert s.dispatch('get_collection',{'collection_id':parent['id']})==ancestor


def test_remove_updates_only_target_stack_and_preserves_folder_stack(library):
    s,_=library
    stroke(s,[1,2,3])
    target=state(s)['target']['id']
    for collection in (None,target):
        params={'action':'group','photo_ids':[1,2,3],'expected_revision':s.dispatch('stack_state')['revision']}
        if collection is not None:
            params['collection_id']=collection
        s.dispatch('stack_photos',params)
    stroke(s,[1,2],action='remove')
    with s.catalog() as c:
        assert c.db.execute("SELECT COUNT(*) FROM stack_members WHERE scope=?",(f'collection:{target}',)).fetchone()[0]==0
        assert c.db.execute("SELECT COUNT(*) FROM stack_members WHERE scope='folder'").fetchone()[0]==3
    assert state(s)['members']==[3]


def test_variants_are_independent_targets_and_metadata_changes_do_not_conflict(library):
    s,_=library
    original=photo(s,1)
    s.dispatch('create_virtual_copies',{'targets':[{'photo_id':1,'expected_revision':original['revision'],
        'expected_metadata_revision':original['metadata_revision']}]})
    with s.catalog() as c:
        copy=c.db.execute('SELECT id FROM photos WHERE is_virtual=1').fetchone()[0]
    captured=state(s)
    s.dispatch('edit_metadata',{'targets':[{'photo_id':1,'expected_metadata_revision':original['metadata_revision']}],
        'patch':{'title':'Updated independently'}})
    result=stroke(s,[copy],captured=captured)
    assert result['members']==[copy] and state(s)['members']==[]
    assert photo(s,1)['title']=='Updated independently'
