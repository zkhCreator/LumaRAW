"""RGB point-curve behavior, old recipe safety and durable editing workflows.

Synthetic ramps verify interpolation, endpoint clipping, independent channels,
black lift, inversion and bounded rendering. Service cases use generated photos
and paused jobs. No Lightroom pixel-equivalence or desktop evidence is implied.
"""
from dataclasses import replace
import hashlib
import json
import jsonschema

import numpy as np
from PIL import Image
import pytest
from scipy.interpolate import PchipInterpolator

from lumaraw import accelerators as accel
from lumaraw.color import encode,decode
from lumaraw.curves import apply_rgb_curves,evaluate,packed_curve
from lumaraw.model import Recipe,POINT_CURVE_FIELDS,POINT_CURVE_PRESETS
from lumaraw.render import grade_tile,RenderPlan,render_strip
from lumaraw.service import Service,ConflictError
from lumaraw.catalog import Catalog
from lumaraw.library import save_recipe,load_recipe,backup_catalog,restore_catalog


CURVES=[[[0,0],[1,1]],[[.1,.2],[.4,.7],[.8,.9]],[[0,1],[.25,.1],[.5,.8],[1,0]],
        [[0,0],[.25,.3],[.2501,.9],[1,1]],[[0,.3],[.2,.3],[.7,.6],[1,.6]]]


@pytest.mark.parametrize('points',CURVES)
def test_float32_curve_matches_independent_spline_and_stays_in_segment_range(points):
    x=np.linspace(-.1,1.1,8192,dtype=np.float32)
    block=packed_curve(points);actual=evaluate(x,block)
    nodes=np.asarray(points)
    expected=PchipInterpolator(nodes[:,0],nodes[:,1])(np.clip(x,nodes[0,0],nodes[-1,0]))
    np.testing.assert_allclose(actual,expected,atol=5e-7,rtol=0)
    assert actual.min()>=0 and actual.max()<=1
    assert not block.flags.writeable and packed_curve(points) is block
    for a,b in zip(points,points[1:]):
        values=evaluate(np.linspace(a[0],b[0],80,dtype=np.float32),block)
        assert values.min()>=min(a[1],b[1])-1e-6 and values.max()<=max(a[1],b[1])+1e-6


@pytest.mark.parametrize('key',POINT_CURVE_FIELDS)
def test_new_curves_reject_invalid_points_but_allow_endpoint_moves_and_inversion(key):
    for points in ([],[[0,0]],[[0,0]]*17,[[0,False],[1,1]],[[0,float('nan')],[1,1]],
                   [[0,0],[float('inf'),1]],[[0,-.1],[1,1]],[[0,0],[1.1,1]],
                   [[0,0],[.5,.7],[.5,.9],[1,1]],[[0,0],[1e-7,.3],[1,1]]):
        with pytest.raises(ValueError):Recipe.parse({key:points})
    assert getattr(Recipe.parse({key:[[.2,1],[.8,0]]}),key)==[[.2,1],[.8,0]]
    for version in (1,2):
        assert getattr(Recipe.parse({'version':version,'curve_points':[[0,0],[.5,.4],[1,1]]}),key)==[[0,0],[1,1]]


def test_identity_preserves_negative_hdr_and_unaffected_channels_without_mutating_inputs():
    a=np.random.default_rng(64).uniform(-.1,2,(19,31,3)).astype(np.float32);before=a.copy()
    for points in ([[0,0],[1,1]],[[0,0],[.3,.3],[1,1]]):
        assert apply_rgb_curves(a,Recipe(**{key:points for key in POINT_CURVE_FIELDS})) is a
    changed=apply_rgb_curves(a,Recipe(curve_red_points=[[0,.2],[1,.9]]))
    np.testing.assert_array_equal(changed[:,:,1:],a[:,:,1:])
    assert not np.array_equal(changed[:,:,0],a[:,:,0])
    np.testing.assert_array_equal(a,before)


def test_rgb_master_lifts_black_and_applies_before_independent_channels():
    a=np.repeat(np.linspace(0,1,513,dtype=np.float32)[None,:,None],3,axis=2)
    master=[[0,.12],[.35,.22],[.7,.8],[1,.9]]
    red=[[0,1],[1,0]];blue=[[.2,.1],[.8,.95]]
    actual=apply_rgb_curves(a,Recipe(curve_rgb_points=master,curve_red_points=red,curve_blue_points=blue))
    baseline=PchipInterpolator(*np.asarray(master).T)(encode(a[:,:,0]))
    np.testing.assert_allclose(actual[:,:,0],decode((1-baseline).astype(np.float32)),atol=4e-7)
    np.testing.assert_allclose(actual[:,:,1],decode(baseline.astype(np.float32)),atol=4e-7)
    assert actual[0,0,1]>0
    for name,points in POINT_CURVE_PRESETS.items():
        if name=='Linear':continue
        values=evaluate(np.array([.25,.75],np.float32),packed_curve(points))
        assert values[0]<.25 and values[1]>.75


def test_old_luminance_equation_and_curved_strips_remain_compatible():
    # Frozen from 1800fc0's grade_tile, including black and out-of-range channels.
    samples=np.array([[[.07,.12,.21],[.4,.06,.03],[.18,.32,.04],[.4,.03,.42],[0,0,0],[1.1,.4,-.01]]],np.float32)
    frozen=np.array([[[.1272606701,.2181611359,.3817819953],[.6949192882,.1042378992,.0521189496],
        [.2639982700,.4693302512,.0586662702],[.7045227885,.0528392084,.7397488952],
        [0,0,0],[1.1981679201,.4356974065,-.0108924247]]],np.float32)
    np.testing.assert_allclose(grade_tile(samples,Recipe(curve_points=[[0,0],[.3,.4],[1,1]],curve_midtones=7)),frozen,atol=1e-8,rtol=0)
    a=np.random.default_rng(82).uniform(.02,.8,(173,205,3)).astype(np.float32)
    old=Recipe(curve_points=[[0,0],[.3,.4],[1,1]])
    # New identity channel fields do not reinterpret the prior luminance curve.
    np.testing.assert_array_equal(grade_tile(a,old),grade_tile(a,Recipe.parse({'version':2,'curve_points':old.curve_points})))
    r=replace(old,curve_rgb_points=[[0,.03],[.4,.35],[1,1]],curve_red_points=[[0,0],[.5,.6],[1,1]],curve_blue_points=[[.08,0],[.9,1]])
    accel.configure('cpu')
    try:
        plan=RenderPlan(a,r)
        whole,_=render_strip(plan,0,0,plan.width,plan.height)
        pieces=np.concatenate([render_strip(plan,0,y,plan.width,min(57,plan.height-y))[0] for y in range(0,plan.height,57)])
        np.testing.assert_array_equal(whole,pieces)
        np.testing.assert_array_equal(render_strip(plan,11,19,60,99)[0],whole[19:118,11:71])
    finally:accel.configure('auto')


def test_point_curves_presets_sync_history_frozen_jobs_and_backup(tmp_path):
    s=Service(tmp_path/'catalog',presets_root=tmp_path/'presets')
    s.dispatch('queue_control',{'action':'pause'})
    paths=[]
    for i in range(3):
        path=tmp_path/f'{i}.png';Image.new('RGB',(24,18),(60,110,160)).save(path);paths.append(path)
    hashes=[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
    patch={key:[[0,.05],[.4,.3],[1,.95]] for key in POINT_CURVE_FIELDS}
    try:
        s.dispatch('import_photos',{'paths':list(map(str,paths))})
        row=s.dispatch('edit_photo',{'photo_id':1,'expected_revision':0,'patch':patch})
        s.dispatch('enqueue_exports',{'photo_ids':[1],'destination':str(tmp_path/'exports'),'format':'tiff16','request_key':'point-curves'})
        preset=s.dispatch('save_develop_preset',{'photo_id':1,'expected_photo_revision':row['revision'],'fields':list(POINT_CURVE_FIELDS),
            'name':'RGB curves','group_name':'Tests','expected_revision':s.dispatch('list_develop_presets')['revision']})
        s.dispatch('edit_photo',{'photo_id':2,'expected_revision':0,'patch':{'exposure':1,'red_bw':30}})
        s.dispatch('apply_develop_preset',{'preset_id':preset['preset_id'],'expected_revision':preset['revision'],
            'targets':[{'photo_id':2,'expected_revision':1}]})
        target=s.dispatch('get_photo',{'photo_id':2})
        assert all(target['recipe'][key]==patch[key] for key in POINT_CURVE_FIELDS)
        assert target['recipe']['exposure']==1 and target['recipe']['red_bw']==30
        with pytest.raises(ConflictError):
            s.dispatch('sync_photos',{'source_id':1,'groups':['Tone Curve'],
                'targets':[{'photo_id':2,'expected_revision':2},{'photo_id':3,'expected_revision':99}]})
        assert s.dispatch('get_photo',{'photo_id':2})['revision']==2
        undo=s.dispatch('undo_photo',{'photo_id':2,'expected_revision':2})
        assert all(undo['recipe'][key]==[[0,0],[1,1]] for key in POINT_CURVE_FIELDS)
        s.dispatch('sync_photos',{'source_id':1,'groups':['Tone Curve'],'targets':[{'photo_id':2,'expected_revision':undo['revision']}]})
        s.dispatch('edit_photo',{'photo_id':1,'expected_revision':1,'patch':{'curve_blue_points':[[0,1],[1,0]]}})
        with s.catalog() as c:
            frozen=json.loads(c.db.execute('SELECT recipe FROM jobs').fetchone()[0])
            assert frozen['curve_blue_points']==patch['curve_blue_points']
            save_recipe(tmp_path/'curves.lumarecipe',c.recipe(1))
            assert load_recipe(tmp_path/'curves.lumarecipe',c.root).curve_blue_points==[[0,1],[1,0]]
            backup_catalog(c,tmp_path/'backup.sqlite')
        restored=Catalog(restore_catalog(tmp_path/'backup.sqlite',tmp_path/'restored'))
        try:assert restored.recipe(2).curve_red_points==patch['curve_red_points']
        finally:restored.close()
        # A genuinely old JSON object has no new curve keys. Sync reads defaults
        # without rewriting the source or reinterpreting its luminance curve.
        with s.catalog() as c:
            legacy=c.recipe(1).dict()
            for key in POINT_CURVE_FIELDS:legacy.pop(key)
            c.db.execute('UPDATE photos SET recipe=? WHERE id=1',(json.dumps(legacy),));c.db.commit()
        target=s.dispatch('get_photo',{'photo_id':2})
        s.dispatch('sync_photos',{'source_id':1,'groups':['Tone Curve'],
            'targets':[{'photo_id':2,'expected_revision':target['revision']}]})
        assert all(s.dispatch('get_photo',{'photo_id':2})['recipe'][key]==[[0,0],[1,1]] for key in POINT_CURVE_FIELDS)
        assert s.dispatch('get_photo',{'photo_id':1})['recipe']==legacy
        assert hashes==[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
    finally:s.close()


def test_temporary_curve_preview_changes_pixels_without_saving_or_poisoning_cache(tmp_path,monkeypatch):
    s=Service(tmp_path/'catalog',presets_root=tmp_path/'presets')
    s.dispatch('queue_control',{'action':'pause'})
    path=tmp_path/'black.png';Image.new('RGB',(32,24),'black').save(path)
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    try:
        s.dispatch('import_photos',{'paths':[str(path)]})
        s.dispatch('enqueue_exports',{'photo_ids':[1],'destination':str(tmp_path/'exports'),'format':'tiff16','request_key':'draft'})
        saved=s.dispatch('get_photo',{'photo_id':1})
        options={'photo_id':1,'max_edge':128,'include_before':False}
        normal=s.dispatch('preview_photo',options)
        normal_pixels=np.array(Image.open(normal['preview']))
        draft=s.dispatch('preview_photo',{**options,'expected_revision':0,'curve_patch':{'curve_rgb_points':[[0,.5],[1,.9]]}})
        assert draft['curve_draft'] and draft['revision']==0
        assert np.array(Image.open(draft['preview'])).mean()>normal_pixels.mean()+40
        restored=s.dispatch('preview_photo',options)
        assert not restored['curve_draft']
        np.testing.assert_array_equal(np.array(Image.open(restored['preview'])),normal_pixels)
        current=s.dispatch('get_photo',{'photo_id':1})
        assert current['recipe']==saved['recipe'] and current['revision']==0
        with s.catalog() as c:
            assert c.db.execute('SELECT COUNT(*) FROM history').fetchone()[0]==0
            assert json.loads(c.db.execute('SELECT recipe FROM jobs').fetchone()[0])==saved['recipe']
        def forbidden(_):raise AssertionError('Invalid or stale curve preview launched pixels')
        monkeypatch.setattr(s,'run_worker',forbidden)
        with pytest.raises(ConflictError):
            s.dispatch('preview_photo',{**options,'expected_revision':99,'curve_patch':{'curve_red_points':[[0,0],[1,1]]}})
        with pytest.raises(jsonschema.ValidationError):
            s.dispatch('preview_photo',{**options,'curve_patch':{'curve_red_points':[[0,0],[1,1]]}})
        with pytest.raises(jsonschema.ValidationError):
            s.dispatch('preview_photo',{**options,'expected_revision':0,'curve_patch':{'exposure':1}})
        with pytest.raises(ValueError):
            s.dispatch('preview_photo',{**options,'expected_revision':0,'curve_patch':{'curve_red_points':[[1,0],[0,1]]}})
        assert hashlib.sha256(path.read_bytes()).hexdigest()==before
    finally:s.close()
