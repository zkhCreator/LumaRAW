"""Catalog orientation, coordinate parity, bounded rendering and frozen exports.

Inputs: asymmetric synthetic images, real isolated worker IPC and genuine v14
catalogs. Outputs: independent reset/undo, transactional failure, all eight exact
orientations, CPU/Metal strip/viewport agreement, cache and original safety.
No Adobe pixel/color equivalence or rendered desktop acceptance is claimed.
"""
import json
import sqlite3
import time

import numpy as np
from PIL import Image
import pytest
import tifffile

from lumaraw import accelerators
from lumaraw.catalog import Catalog
from lumaraw.model import Recipe
from lumaraw.orientation import ACTIONS, Orientations, apply_array, compose, inverse_rect, migrate
from lumaraw.render import OrientedPlan, RenderPlan, render_strip
from lumaraw.service import Service
from test_metal import require_metal


@pytest.fixture(autouse=True)
def cpu_default():
    accelerators.configure('cpu')
    yield
    accelerators.configure('auto')


def reference(array,orientation):
    return np.rot90(np.fliplr(array) if orientation>=4 else array,-(orientation%4))


@pytest.mark.parametrize('orientation',range(8))
def test_all_orthogonal_states_and_compositions(orientation):
    source=np.arange(7*11*3,dtype=np.uint16).reshape(7,11,3)
    actual=apply_array(source,orientation)
    np.testing.assert_array_equal(actual,reference(source,orientation))
    assert np.shares_memory(source,actual) and actual.dtype==source.dtype
    operations={'rotate_left':lambda a:np.rot90(a,1),'rotate_right':lambda a:np.rot90(a,-1),
        'flip_horizontal':np.fliplr,'flip_vertical':np.flipud}
    for action,operation in operations.items():
        np.testing.assert_array_equal(apply_array(source,compose(orientation,action)),operation(actual))
    for x,y,w,h in ((0,0,3,2),(1,2,4,3),(actual.shape[1]-2,actual.shape[0]-2,2,2)):
        cx,cy,cw,ch=inverse_rect(x,y,w,h,11,7,orientation)
        np.testing.assert_array_equal(apply_array(source[cy:cy+ch,cx:cx+cw],orientation),actual[y:y+h,x:x+w])


@pytest.mark.parametrize('orientation',range(8))
@pytest.mark.parametrize('backend',['cpu','metal'])
def test_oriented_strips_keep_masks_crop_geometry_and_detail(orientation,backend):
    if backend=='metal':
        require_metal()
    source=np.random.default_rng(8).uniform(.04,.8,(291,437,3)).astype(np.float32)
    recipe=Recipe(rotation=90,crop_box=[.07,.11,.89,.94],crop='4:5',straighten=3,
        distortion=8,perspective_h=3,sharpen=25,luma_noise=12,chroma_noise=8,
        masks=[{'kind':'radial','x':.23,'y':.63,'radius':.18,'exposure':1.3},
               {'kind':'linear','x':.1,'y':.1,'x2':.9,'y2':.7,'exposure':-.8},
               {'kind':'brush','points':[[.1,.3],[.4,.5],[.8,.3]],'radius':.05,'exposure':.7}])
    base=RenderPlan(source,recipe)
    canonical,gamut=render_strip(base,0,0,base.width,base.height)
    expected=reference(canonical,orientation)
    plan=OrientedPlan(base,orientation)
    pieces=[render_strip(plan,0,y,plan.width,min(37,plan.height-y))[0] for y in range(0,plan.height,37)]
    np.testing.assert_allclose(np.concatenate(pieces),expected,atol=2e-6,rtol=2e-6)
    detail,clipped=render_strip(plan,9,13,67,59)
    np.testing.assert_allclose(detail,expected[13:72,9:76],atol=2e-6,rtol=2e-6)
    np.testing.assert_array_equal(clipped,reference(gamut,orientation)[13:72,9:76])
    if backend=='metal':
        assert accelerators.report()['metal_output_tiles']>0


@pytest.mark.parametrize('ratio',['3:2','2:3','4:5','5:4','16:9','9:16'])
def test_oriented_portrait_and_landscape_crop_ratios(ratio):
    source=np.zeros((900,1200,3),np.uint16)
    for orientation in range(8):
        canonical=':'.join(reversed(ratio.split(':'))) if orientation%2 else ratio
        plan=OrientedPlan(RenderPlan(source,Recipe(crop=canonical)),orientation)
        numerator,denominator=map(int,ratio.split(':'))
        assert abs(plan.width/plan.height-numerator/denominator)<.003


@pytest.fixture
def library(tmp_path):
    a=np.zeros((96,144,3),np.uint8)
    a[:48,:72]=[220,30,20];a[:48,72:]=[20,190,40]
    a[48:,:72]=[20,40,220];a[48:,72:]=[190,160,30]
    paths=[tmp_path/f'{i}.png' for i in range(3)]
    for path in paths:
        Image.fromarray(a).save(path)
    s=Service(tmp_path/'catalog',presets_root=tmp_path/'presets')
    s.dispatch('queue_control',{'action':'pause'})
    s.dispatch('import_photos',{'paths':list(map(str,paths))})
    yield s,paths
    s.close()


def photo(s,id_=1):
    return s.dispatch('get_photo',{'photo_id':id_})


def orient(s,action='rotate_right',ids=(1,2),targets=None):
    targets=targets or [{'photo_id':i,'expected_revision':photo(s,i)['revision']} for i in ids]
    return s.dispatch('orient_photos',{'targets':targets,'action':action})


def undo(s,**override):
    state=s.dispatch('orientation_state')
    return s.dispatch('undo_orientation',{'action_id':state['latest']['id'],'expected_revision':state['revision'],**override})


def test_catalog_reset_develop_undo_and_orientation_undo_are_independent(library):
    s,paths=library;originals=[p.read_bytes() for p in paths]
    s.dispatch('edit_photo',{'photo_id':1,'expected_revision':0,'patch':{'exposure':1,'crop_box':[.1,.2,.8,.9],
        'masks':[{'kind':'radial','x':.2,'y':.7,'radius':.1,'exposure':1}]}})
    before=photo(s)
    first=orient(s)
    assert photo(s)['recipe']==before['recipe'] and photo(s)['metadata_revision']==before['metadata_revision']
    assert photo(s)['orientation']==1 and photo(s,2)['orientation']==1 and photo(s,3)['orientation']==0
    with s.catalog() as c:
        assert c.db.execute('SELECT COUNT(*) FROM history').fetchone()[0]==1
    s.dispatch('edit_photo',{'photo_id':1,'expected_revision':photo(s)['revision'],'patch':Recipe().dict()})
    assert photo(s)['orientation']==1
    undo(s)
    assert photo(s)['orientation']==0 and photo(s)['recipe']==Recipe().dict() and photo(s,2)['orientation']==0
    s.dispatch('undo_photo',{'photo_id':1,'expected_revision':photo(s)['revision']})
    assert photo(s)['recipe']==before['recipe'] and photo(s)['orientation']==0
    assert s.dispatch('orientation_state')['latest'] is None
    orient(s,'flip_horizontal');orient(s,'rotate_left');undo(s)
    assert photo(s)['orientation']==4
    undo(s)
    assert photo(s)['orientation']==0 and [p.read_bytes() for p in paths]==originals


def test_all_targets_and_undo_validate_before_any_write(library):
    s,_=library
    targets=[{'photo_id':1,'expected_revision':0},{'photo_id':2,'expected_revision':1}]
    with pytest.raises(ValueError,match='conflict'):
        orient(s,targets=targets)
    assert photo(s)['orientation']==0 and s.dispatch('orientation_state')['latest'] is None
    with pytest.raises(ValueError,match='does not exist'):
        orient(s,targets=[{'photo_id':1,'expected_revision':0},{'photo_id':999,'expected_revision':0}])
    first=orient(s)
    orient(s,ids=[3])
    with pytest.raises(ValueError,match='history changed'):
        undo(s,action_id=first['latest']['id'],expected_revision=first['revision'])
    undo(s)
    with s.catalog() as c,c.db:
        c.db.execute('DELETE FROM photos WHERE id=2')
    with pytest.raises(ValueError,match='missing or changed'):
        undo(s)
    assert photo(s)['orientation']==1


def test_injected_failure_rolls_back_entire_batch(library):
    s,_=library
    with s.catalog() as c,c.db:
        c.db.execute("CREATE TRIGGER stop_orientation BEFORE UPDATE OF orientation ON photos WHEN NEW.id=2 BEGIN SELECT RAISE(ABORT,'injected'); END")
    with pytest.raises(sqlite3.IntegrityError,match='injected'):
        orient(s)
    assert photo(s)['revision']==0 and photo(s)['orientation']==0
    assert s.dispatch('orientation_state')['latest'] is None


def test_variants_inherit_orientation_then_remain_independent_and_history_is_bounded(library):
    s,_=library
    orient(s,'flip_vertical',ids=[1])
    row=photo(s)
    s.dispatch('create_virtual_copies',{'targets':[{'photo_id':1,'expected_revision':row['revision'],
        'expected_metadata_revision':row['metadata_revision']}]})
    with s.catalog() as c:
        id_=c.db.execute('SELECT id FROM photos WHERE is_virtual=1').fetchone()[0]
    assert photo(s,id_)['orientation']==6
    orient(s,ids=[id_])
    assert photo(s,id_)['orientation']==7 and photo(s)['orientation']==6
    for _ in range(52):
        orient(s,ids=[3])
    with s.catalog() as c:
        assert c.db.execute('SELECT COUNT(*) FROM orientation_history').fetchone()[0]==50


def test_real_worker_preview_before_detail_thumbnails_and_frozen_export(library,tmp_path):
    s,paths=library
    before=s.dispatch('preview_photo',{'photo_id':1})
    pixels=np.asarray(Image.open(before['preview']))
    source=s.dispatch('thumbnail',{'photo_id':1})['thumbnail']
    developed=s.dispatch('thumbnail',{'photo_id':1,'kind':'developed'})['thumbnail']
    old=s.dispatch('enqueue_exports',{'photo_ids':[1],'destination':str(tmp_path/'old'),'format':'tiff16','request_key':'old'})['job_ids'][0]
    orient(s,ids=[1])
    after=s.dispatch('preview_photo',{'photo_id':1})
    np.testing.assert_array_equal(np.asarray(Image.open(after['preview'])),np.rot90(pixels,-1))
    np.testing.assert_array_equal(np.asarray(Image.open(after['before'])),np.rot90(pixels,-1))
    assert after['geometry']['orientation']==1 and after['geometry']['crop_box']==[0,0,1,1]
    detail=s.dispatch('preview_photo',{'photo_id':1,'detail':{'cx':.5,'cy':.5,'width':35,'height':27}})
    x,y,w,h=detail['roi']
    np.testing.assert_array_equal(np.asarray(Image.open(detail['preview'])),np.rot90(pixels,-1)[y:y+h,x:x+w])
    assert s.dispatch('cached_thumbnails',{'photo_ids':[1]})['thumbnails']==[]
    assert s.dispatch('cached_thumbnails',{'photo_ids':[1],'kind':'developed'})['thumbnails']==[]
    new_source=s.dispatch('thumbnail',{'photo_id':1})['thumbnail']
    new_developed=s.dispatch('thumbnail',{'photo_id':1,'kind':'developed'})['thumbnail']
    assert source!=new_source and developed!=new_developed
    assert Image.open(new_source).size==Image.open(source).size[::-1]
    assert Image.open(new_developed).size==Image.open(developed).size[::-1]
    assert len(s.dispatch('cached_thumbnails',{'photo_ids':[1]})['thumbnails'])==1
    new=s.dispatch('enqueue_exports',{'photo_ids':[1],'destination':str(tmp_path/'new'),'format':'tiff16','request_key':'new'})['job_ids'][0]
    orient(s,'flip_horizontal',ids=[1])
    assert s.dispatch('get_job',{'job_id':old})['orientation']==0
    assert s.dispatch('get_job',{'job_id':new})['orientation']==1
    s.dispatch('queue_control',{'action':'resume'})
    deadline=time.monotonic()+20
    while time.monotonic()<deadline:
        jobs=[s.dispatch('get_job',{'job_id':id_}) for id_ in (old,new)]
        if all(j['state']=='done' for j in jobs):
            break
        time.sleep(.05)
    assert all(j['state']=='done' for j in jobs),jobs
    np.testing.assert_array_equal(tifffile.imread(jobs[1]['output']),np.rot90(tifffile.imread(jobs[0]['output']),-1))


def test_genuine_v14_migration_rolls_back_and_preserves_old_jobs(tmp_path,monkeypatch):
    import lumaraw.catalog as module
    from legacy_catalog import migrate_to
    from lumaraw.library import backup_catalog,restore_catalog
    with monkeypatch.context() as patch:
        patch.setattr(module,'migrate',lambda db:migrate_to(db,14))
        c=Catalog(tmp_path/'old')
    recipe=json.dumps(Recipe(rotation=90,exposure=1).dict())
    with c.db:
        c.db.execute('INSERT INTO photos(path,name,bytes,mtime,recipe,created) VALUES(?,?,?,?,?,?)',('original.png','Original',0,0,recipe,0))
        c.db.execute('INSERT INTO jobs(photo_id,source,recipe,destination,format,created) VALUES(1,?,?,?,?,0)',('original.png',recipe,'export','jpeg'))
    c.db.set_authorizer(lambda action,name,*rest:sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_CREATE_TABLE else sqlite3.SQLITE_OK)
    with pytest.raises(sqlite3.DatabaseError):
        migrate(c.db)
    c.db.set_authorizer(None)
    assert c.db.execute('PRAGMA user_version').fetchone()[0]==14
    assert 'orientation' not in [r[1] for r in c.db.execute('PRAGMA table_info(photos)')]
    migrate(c.db);migrate(c.db)
    assert c.db.execute('SELECT recipe,orientation FROM jobs').fetchone()[:]==(recipe,0)
    Orientations(c).apply([{'photo_id':1,'expected_revision':0}],'flip_horizontal')
    backup_catalog(c,tmp_path/'backup');c.close()
    restored=Catalog(restore_catalog(tmp_path/'backup',tmp_path/'restored'))
    try:
        assert restored.photo(1)['orientation']==4 and restored.photo(1)['recipe']==recipe
        assert Orientations(restored).state()['latest'] is not None
    finally:
        restored.close()
