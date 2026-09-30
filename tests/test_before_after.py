"""Persistent comparison snapshots, atomic copy/swap and bounded preview reuse.

Inputs: generated originals, actual workers and genuine legacy schemas. Outputs:
catalog/recipe invariants, cache behavior and exact reference pixels. No Adobe
processing equivalence, global application undo or desktop acceptance is claimed.
"""
from dataclasses import replace
from contextlib import closing
import json
from pathlib import Path
import sqlite3

import numpy as np
from PIL import Image
import pytest

from lumaraw.before_after import BeforeAfter, migrate
from lumaraw.catalog import Catalog
from lumaraw.model import Recipe
from lumaraw.service import Service, ConflictError
from lumaraw import render
from legacy_catalog import migrate_to, seed_photo


@pytest.fixture
def library(tmp_path):
    pixels=np.stack(np.broadcast_arrays(np.arange(192,dtype=np.uint8)[None,:],
        np.arange(128,dtype=np.uint8)[:,None],np.full((128,192),80,np.uint8)),axis=-1)
    path=tmp_path/'original.png';Image.fromarray(pixels).save(path)
    s=Service(tmp_path/'catalog',presets_root=tmp_path/'presets')
    s.dispatch('queue_control',{'action':'pause'});s.dispatch('import_photos',{'paths':[str(path)]})
    yield s,path
    s.close()


def photo(s,id_=1):return s.dispatch('get_photo',{'photo_id':id_})
def call(s,method,id_=1,**args):
    return s.dispatch(method,{'photo_id':id_,'expected_revision':photo(s,id_)['revision'],**args})
def edit(s,**patch):return call(s,'edit_photo',patch=patch)
def compare(s,action,**args):return call(s,'before_after',action=action,**args)
def before(s,id_=1):
    with s.catalog() as c:return BeforeAfter(c.db).read(id_)[0].dict()


def test_history_snapshot_survives_branch_clear_restart_and_originals(library):
    s,path=library;original=path.read_bytes()
    edit(s,exposure=1);step=call(s,'list_history')['cursor'];edit(s,exposure=2)
    original_history=call(s,'list_history')['steps'];after=photo(s)['recipe']
    result=compare(s,'history_to_before',step_id=step)
    assert result['changed_before'] and not result['changed_after']
    assert before(s)['exposure']==1 and photo(s)['recipe']==after
    assert call(s,'list_history')['steps']==original_history
    call(s,'select_history',step_id=0);edit(s,exposure=-1);call(s,'clear_history')
    assert before(s)['exposure']==1
    reopened=Service(s.root,presets_root=s.root/'other-presets')
    try:assert before(reopened)['exposure']==1
    finally:reopened.close()
    assert path.read_bytes()==original


def test_copy_swap_complete_recipe_noops_and_after_undo(library,tmp_path):
    s,path=library
    edit(s,exposure=1,crop='4:5',masks=[{'kind':'radial','exposure':.5}],blue_bw=35)
    expected=photo(s)['recipe'];compare(s,'after_to_before')
    revision=photo(s)['revision'];compare(s,'after_to_before')
    assert photo(s)['revision']==revision
    edit(s,exposure=-1,crop='16:9',masks=[])
    source=photo(s)
    job=s.dispatch('enqueue_exports',{'photo_ids':[1],'destination':str(tmp_path/'exports'),'format':'jpeg','request_key':'freeze'})['job_ids'][0]
    frozen=s.dispatch('get_job',{'job_id':job})
    result=compare(s,'swap')
    assert result['changed_before'] and result['changed_after'] and result['revision']==source['revision']+1
    assert photo(s)['recipe']==expected and before(s)==source['recipe']
    call(s,'undo_photo')
    assert photo(s)['recipe']==source['recipe'] and before(s)==source['recipe']
    # Develop history only affects After; global undo of comparison state is separate.
    compare(s,'swap');assert photo(s)['recipe']==source['recipe']
    call(s,'redo_photo');assert photo(s)['recipe']==expected
    copied=compare(s,'before_to_after')
    assert copied['changed_after'] and photo(s)['recipe']==source['recipe']
    assert s.dispatch('get_job',{'job_id':job})==frozen


@pytest.mark.parametrize('action',['history_to_before','after_to_before','before_to_after','swap'])
def test_stale_operations_preserve_both_sides(library,action):
    s,_=library;edit(s,exposure=1);a=photo(s);b=before(s)
    params={'photo_id':1,'expected_revision':0,'action':action}
    if action=='history_to_before':params['step_id']=0
    with pytest.raises(ConflictError):s.dispatch('before_after',params)
    assert photo(s)==a and before(s)==b


def test_invalid_step_and_atomic_swap_rollback(library):
    s,_=library;edit(s,exposure=1);a=photo(s);b=before(s)
    for args in ({'action':'history_to_before'},{'action':'history_to_before','step_id':999},{'action':'swap','step_id':0}):
        with pytest.raises(ValueError):call(s,'before_after',**args)
    with s.catalog() as c,c.db:
        c.db.execute("CREATE TRIGGER deny_after BEFORE UPDATE OF recipe ON photos BEGIN SELECT RAISE(ABORT,'injected'); END")
    with pytest.raises(sqlite3.IntegrityError,match='injected'):compare(s,'swap')
    assert photo(s)==a and before(s)==b


def test_virtual_copy_before_starts_at_inherited_after_and_removes_cleanly(library):
    s,_=library;edit(s,exposure=2);p=photo(s)
    copy=s.dispatch('create_virtual_copies',{'targets':[{'photo_id':1,'expected_revision':p['revision'],'expected_metadata_revision':p['metadata_revision']}]})['photos'][0]['id']
    assert before(s)['exposure']==0 and before(s,copy)['exposure']==2
    p=photo(s,copy)
    s.dispatch('remove_virtual_copies',{'targets':[{'photo_id':copy,'expected_revision':p['revision'],'expected_metadata_revision':p['metadata_revision'],'expected_source_revision':p['source_revision']}]})
    with s.catalog() as c:
        assert c.db.execute('SELECT photo_id FROM photo_before').fetchall()[0][0]==1
        assert c.db.execute('SELECT COUNT(*) FROM photo_before').fetchone()[0]==1


def test_before_only_asset_backup_and_restore(library,tmp_path):
    s,_=library;cube=tmp_path/'identity.cube'
    cube.write_text('LUT_3D_SIZE 2\n0 0 0\n1 0 0\n0 1 0\n1 1 0\n0 0 1\n1 0 1\n0 1 1\n1 1 1\n')
    asset=s.dispatch('import_asset',{'path':str(cube),'kind':'lut'})['asset']
    edit(s,lut=asset);compare(s,'after_to_before');edit(s,lut={});call(s,'clear_history')
    backup=tmp_path/'backup.sqlite';dest=tmp_path/'restored'
    s.dispatch('backup_catalog',{'path':str(backup)})
    s.dispatch('restore_catalog',{'path':str(backup),'destination':str(dest)})
    with closing(Catalog(dest)) as restored:
        recipe,_=BeforeAfter(restored.db).read(1)
        assert Path(recipe.lut['path']).parent==dest/'assets' and Path(recipe.lut['path']).is_file()


def test_preview_before_pixels_alignment_cache_and_omission(library,tmp_path,monkeypatch):
    s,path=library
    selected=Recipe(exposure=.8,temperature=12,contrast=8,crop='4:5',monochrome=True)
    after=Recipe(exposure=-.4,crop='16:9',straighten=3)
    cache=tmp_path/'preview-cache';original=path.read_bytes()
    first=render.make_preview(path,after,cache,512,before_recipe=selected.dict(),max_edge=128)
    assert not first['before_cache_hit']
    reference=render.make_preview(path,replace(selected,crop=after.crop,straighten=after.straighten),cache,512,include_before=False,max_edge=128)
    with Image.open(first['before']) as a,Image.open(reference['preview']) as b:
        np.testing.assert_array_equal(np.array(a),np.array(b));assert a.info.get('icc_profile')
    actual=render.render_u8;calls=[]
    def counted(*args,**kwargs):calls.append(1);return actual(*args,**kwargs)
    monkeypatch.setattr(render,'render_u8',counted)
    warm=render.make_preview(path,replace(after,exposure=.2),cache,512,before_recipe=selected.dict(),max_edge=128)
    assert warm['before_cache_hit'] and warm['before']==first['before'] and len(calls)==1
    calls.clear()
    changed=render.make_preview(path,replace(after,crop='1:1'),cache,512,before_recipe=selected.dict(),max_edge=128)
    assert not changed['before_cache_hit'] and len(calls)==2 and changed['before']!=first['before']
    calls.clear()
    skipped=render.make_preview(path,after,cache,512,before_recipe=selected.dict(),max_edge=128,include_before=False)
    assert 'before' not in skipped and len(calls)==1
    Path(first['before']).write_bytes(b'broken')
    repaired=render.make_preview(path,after,cache,512,before_recipe=selected.dict(),max_edge=128)
    assert not repaired['before_cache_hit'] and path.read_bytes()==original


def test_real_worker_uses_persistent_before_at_captured_revision(library):
    s,_=library;edit(s,exposure=.75);compare(s,'after_to_before');edit(s,exposure=-1)
    first=s.dispatch('preview_photo',{'photo_id':1,'max_edge':128})
    assert first['before_label']=='Copied from After' and not first['before_cache_hit']
    warm=s.dispatch('preview_photo',{'photo_id':1,'max_edge':128})
    assert warm['before_cache_hit'] and warm['before']==first['before']
    with Image.open(first['preview']) as a,Image.open(first['before']) as b:
        assert not np.array_equal(np.array(a),np.array(b))
    assert first['revision']==photo(s)['revision']


def test_source_replacement_cannot_publish_a_mixed_comparison(library,tmp_path,monkeypatch):
    _,path=library;actual=render.render_u8
    def replaced(*args,**kwargs):
        result=actual(*args,**kwargs)
        Image.new('RGB',(192,128),'orange').save(path)
        return result
    monkeypatch.setattr(render,'render_u8',replaced)
    with pytest.raises(ValueError,match='Source changed'):
        render.make_preview(path,Recipe(exposure=1),tmp_path/'replacement-cache',512,before_recipe=Recipe().dict())
    assert not list((tmp_path/'replacement-cache').glob('*-before.png'))


def test_genuine_schema22_migration_rollback_and_initial_state(tmp_path,monkeypatch):
    from lumaraw import catalog as module
    path=tmp_path/'photo.png';Image.new('RGB',(8,8)).save(path)
    root=tmp_path/'old'
    with monkeypatch.context() as context:
        context.setattr(module,'migrate',lambda db:migrate_to(db,22))
        c=Catalog(root);seed_photo(c.db,path);c.edit(1,Recipe(exposure=2))
        c.db.set_authorizer(lambda action,a,b,d,t:sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_CREATE_TRIGGER and a=='photo_before_created' else sqlite3.SQLITE_OK)
        with pytest.raises(sqlite3.DatabaseError):migrate(c.db)
        c.db.set_authorizer(None)
        assert c.db.execute('PRAGMA user_version').fetchone()[0]==22
        assert not c.db.execute("SELECT 1 FROM sqlite_master WHERE name='photo_before'").fetchone()
        c.close()
    with closing(Catalog(root)) as c:
        migrate(c.db)
        assert BeforeAfter(c.db).read(1)[0].exposure==0 and c.recipe(1).exposure==2


@pytest.mark.parametrize('orientation',range(8))
def test_detail_before_uses_same_roi_and_orientation(library,tmp_path,orientation):
    _,path=library;cache=tmp_path/'detail-cache'
    after=Recipe(crop_box=[.1,.1,.9,.9],exposure=-1,rotation=90)
    chosen=Recipe(exposure=.75,blue_sat=20)
    options={'orientation':orientation,'detail':{'width':80,'height':70,'cx':.8,'cy':.7}}
    result=render.make_preview(path,after,cache,512,before_recipe=chosen.dict(),**options)
    reference=render.make_preview(path,replace(chosen,crop_box=after.crop_box,rotation=after.rotation),cache,512,include_before=False,**options)
    assert result['roi']==reference['roi']
    with Image.open(result['before']) as a,Image.open(reference['preview']) as b:
        assert a.size==(result['width'],result['height'])
        np.testing.assert_array_equal(np.array(a),np.array(b))
