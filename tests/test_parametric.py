"""Four-region curve semantics, durable recipes and temporary-preview safety.

Synthetic ramps verify direction, monotonicity, supports and neutral behavior;
service cases use generated photographs and a paused export queue. No Adobe
pixel matching or rendered desktop acceptance is inferred from these tests.
"""
from dataclasses import replace
import hashlib
import itertools
import json

import jsonschema
import numpy as np
from PIL import Image
import pytest

from lumaraw import accelerators as accel
from lumaraw.catalog import Catalog
from lumaraw.color import decode
from lumaraw.develop_presets import FIELDS
from lumaraw.library import backup_catalog,restore_catalog,save_recipe,load_recipe
from lumaraw.model import Recipe,PARAMETRIC_FIELDS,PARAMETRIC_SPLITS
from lumaraw.parametric import apply,evaluate,packed
from lumaraw.render import grade_tile,RenderPlan,render_strip
from lumaraw.service import Service,ConflictError


@pytest.mark.parametrize('key',PARAMETRIC_FIELDS)
def test_amount_validation_and_old_recipe_defaults(key):
    for invalid in (True,float('nan'),float('inf'),-100.1,100.1,'10'):
        with pytest.raises(ValueError):Recipe.parse({key:invalid})
    for value in (-100,0,100):assert getattr(Recipe.parse({key:value}),key)==value
    old=Recipe.parse({'version':1,'curve_midtones':12,'curve_points':[[0,0],[.5,.6],[1,1]]})
    assert all(getattr(old,k)==0 for k in PARAMETRIC_FIELDS)
    assert old.parametric_splits==list(PARAMETRIC_SPLITS) and old.curve_midtones==12


@pytest.mark.parametrize('splits',([], [0,.5,.75], [.25,.5,1], [.2,.2,.8], [.2,.201,.8],
                                    [.75,.5,.25], [True,.5,.75], [.25,float('nan'),.75], [.2,.3,.4,.5]))
def test_splits_reject_invalid_or_unordered_regions(splits):
    with pytest.raises(ValueError):Recipe(parametric_splits=splits)


@pytest.mark.parametrize('splits',([.25,.5,.75],[.01,.02,.03],[.97,.98,.99],[.1,.5,.99]))
def test_extreme_combinations_never_reverse_clip_or_move_endpoints(splits):
    ramp=np.linspace(0,1,16385,dtype=np.float32)
    for amounts in itertools.product((-100,100),repeat=4):
        r=Recipe(**dict(zip(PARAMETRIC_FIELDS,amounts)),parametric_splits=splits)
        block=packed(r);out=evaluate(ramp,block)
        assert np.all(np.diff(out)>=0) and out[0]==0 and out[-1]==1
        assert out.min()==0 and out.max()==1 and np.isfinite(out).all()
        assert not block.flags.writeable and packed(r) is block


@pytest.mark.parametrize('region,center,expected',[(0,.125,.1875),(1,.375,.5),(2,.625,.75),(3,.875,.9375)])
def test_regions_have_expected_centers_direction_and_limited_support(region,center,expected):
    r=Recipe(**{PARAMETRIC_FIELDS[region]:100})
    value=evaluate(np.array([0,center,1],np.float32),packed(r))
    np.testing.assert_array_equal(value,[0,expected,1])
    ramp=np.linspace(0,1,1025,dtype=np.float32)
    lo,_,hi,_=packed(r)[region]
    values=evaluate(ramp,packed(r))
    np.testing.assert_array_equal(values[(ramp<=lo)|(ramp>=hi)],ramp[(ramp<=lo)|(ramp>=hi)])
    # Increasing any amount must not darken another tone, even with other regions.
    mixed=Recipe(parametric_shadows=75,parametric_darks=-55,parametric_lights=30,parametric_highlights=-40)
    low=evaluate(ramp,packed(replace(mixed,**{PARAMETRIC_FIELDS[region]:-100})))
    high=evaluate(ramp,packed(replace(mixed,**{PARAMETRIC_FIELDS[region]:100})))
    assert np.all(high>=low) and np.max(high-low)>.01


def test_splits_change_support_without_changing_amounts_and_zero_is_exact():
    r=Recipe(parametric_darks=100)
    changed=replace(r,parametric_splits=[.1,.6,.8])
    ramp=np.linspace(0,1,10001,dtype=np.float32)
    shift=evaluate(ramp,packed(changed))-ramp
    assert abs(float(ramp[np.argmax(shift)])-.35)<.001
    assert changed.parametric_darks==100 and not np.array_equal(evaluate(ramp,packed(r)),ramp+shift)
    a=np.random.default_rng(2).uniform(-.2,3,(19,31,3)).astype(np.float32)
    assert apply(a,Recipe(parametric_splits=[.01,.4,.99])) is a
    np.testing.assert_array_equal(evaluate(ramp,packed(Recipe())),ramp)


def test_gain_preserves_color_ratios_black_white_hdr_and_input_bytes():
    values=np.array([-.1,0,.05,.2,.6,1,1.2,2],np.float32)
    gray=np.repeat(values[None,:,None],3,axis=2)
    r=Recipe(parametric_shadows=80,parametric_darks=60,parametric_lights=-40,parametric_highlights=-90)
    adjusted=apply(gray,r)
    np.testing.assert_array_equal(adjusted[:,[0,1,5,6,7]],gray[:,[0,1,5,6,7]])
    a=np.array([[[.12,.25,.35],[.5,.2,.06],[-.01,.35,.18]]],np.float32);before=a.copy()
    result=apply(a,r)
    np.testing.assert_allclose(result/a,(result[:,:,1]/a[:,:,1])[:,:,None]*np.ones_like(a),atol=3e-7,rtol=0)
    np.testing.assert_array_equal(a,before)
    # The shadow-only support ends below these tones. Skip encode/decode too,
    # so an adjustment in another region cannot introduce one-ULP pixel changes.
    untouched=np.repeat(np.linspace(.4,2,200,dtype=np.float32)[None,:,None],3,axis=2)
    np.testing.assert_array_equal(apply(untouched,Recipe(parametric_shadows=100)),untouched)


def test_smooth_join_and_bounded_composition_derivative():
    # A one-sided derivative at every support edge/center approaches the same
    # baseline slope; this detects a piecewise-linear or discontinuous substitute.
    r=Recipe(parametric_darks=100)
    for x in (0.125,0.375,0.625):
        h=1e-4;v=evaluate(np.array([x-h,x,x+h],np.float32),packed(r))
        assert abs(float((v[1]-v[0])/h)-float((v[2]-v[1])/h))<.005
    ramp=np.linspace(0,1,4097,dtype=np.float32)
    for amounts in ([100]*4,[-100]*4,[-100,100,-100,100]):
        out=evaluate(ramp,packed(Recipe(**dict(zip(PARAMETRIC_FIELDS,amounts)))))
        derivative=np.diff(out)/np.diff(ramp)
        assert derivative.min()>0 and derivative.max()<1.75**4+.001


def test_parametric_strips_and_viewport_match_whole_with_point_curves():
    a=np.random.default_rng(123).uniform(.01,.7,(213,237,3)).astype(np.float32)
    r=Recipe(parametric_shadows=65,parametric_darks=-70,parametric_lights=85,parametric_highlights=-40,
             parametric_splits=[.17,.55,.88],curve_rgb_points=[[0,.02],[.4,.35],[1,1]],blue_lum=20)
    accel.configure('cpu')
    try:
        plan=RenderPlan(a,r);whole,_=render_strip(plan,0,0,plan.width,plan.height)
        strips=np.concatenate([render_strip(plan,0,y,plan.width,min(37,plan.height-y))[0] for y in range(0,plan.height,37)])
        np.testing.assert_array_equal(strips,whole)
        np.testing.assert_array_equal(render_strip(plan,13,18,133,109)[0],whole[18:127,13:146])
    finally:accel.configure('auto')


def test_parametric_presets_drafts_sync_jobs_and_old_json(tmp_path,monkeypatch):
    s=Service(tmp_path/'catalog',presets_root=tmp_path/'presets');s.dispatch('queue_control',{'action':'pause'})
    paths=[]
    for i in range(3):
        path=tmp_path/f'{i}.png';Image.new('RGB',(40,30),(100,100,100)).save(path);paths.append(path)
    hashes=[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
    patch=dict(zip(PARAMETRIC_FIELDS,[40,60,-20,-35]));patch['parametric_splits']=[.2,.5,.8]
    try:
        s.dispatch('import_photos',{'paths':list(map(str,paths))})
        row=s.dispatch('edit_photo',{'photo_id':1,'expected_revision':0,'patch':{**patch,'curve_red_points':[[0,0],[.5,.6],[1,1]]}})
        s.dispatch('enqueue_exports',{'photo_ids':[1],'destination':str(tmp_path/'exports'),'format':'tiff16','request_key':'parametric'})
        options={'photo_id':1,'max_edge':128,'include_before':False}
        normal=np.array(Image.open(s.dispatch('preview_photo',options)['preview']))
        draft=s.dispatch('preview_photo',{**options,'expected_revision':1,'curve_patch':{'parametric_darks':-100,'parametric_splits':[.1,.6,.9]}})
        assert draft['curve_draft'] and np.array(Image.open(draft['preview'])).mean()<normal.mean()-5
        np.testing.assert_array_equal(np.array(Image.open(s.dispatch('preview_photo',options)['preview'])),normal)
        current=s.dispatch('get_photo',{'photo_id':1});assert current['recipe']==row['recipe'] and current['revision']==1
        with s.catalog() as c:assert c.db.execute('SELECT COUNT(*) FROM history').fetchone()[0]==1
        all_preset=s.dispatch('save_develop_preset',{'photo_id':1,'expected_photo_revision':1,'fields':list(FIELDS),
            'name':'All settings','group_name':'Tests','expected_revision':s.dispatch('list_develop_presets')['revision']})
        assert set(patch).issubset(FIELDS)
        s.dispatch('apply_develop_preset',{'preset_id':all_preset['preset_id'],'expected_revision':all_preset['revision'],'targets':[{'photo_id':2,'expected_revision':0}]})
        assert all(s.dispatch('get_photo',{'photo_id':2})['recipe'][k]==v for k,v in patch.items())
        with pytest.raises(ConflictError):s.dispatch('sync_photos',{'source_id':1,'groups':['Tone Curve'],
            'targets':[{'photo_id':2,'expected_revision':1},{'photo_id':3,'expected_revision':99}]})
        assert s.dispatch('get_photo',{'photo_id':2})['revision']==1
        undone=s.dispatch('undo_photo',{'photo_id':2,'expected_revision':1})
        assert all(undone['recipe'][k]==0 for k in PARAMETRIC_FIELDS)
        s.dispatch('edit_photo',{'photo_id':2,'expected_revision':undone['revision'],'patch':{'exposure':1}})
        s.dispatch('sync_photos',{'source_id':1,'groups':['Tone Curve'],'targets':[{'photo_id':2,'expected_revision':3}]})
        assert s.dispatch('get_photo',{'photo_id':2})['recipe']['exposure']==1
        s.dispatch('edit_photo',{'photo_id':1,'expected_revision':1,'patch':{'parametric_darks':-80}})
        with s.catalog() as c:
            assert json.loads(c.db.execute('SELECT recipe FROM jobs').fetchone()[0])==row['recipe']
            save_recipe(tmp_path/'curve.lumarecipe',c.recipe(1))
            assert load_recipe(tmp_path/'curve.lumarecipe',c.root).parametric_darks==-80
            backup_catalog(c,tmp_path/'backup.sqlite')
            old=c.recipe(1).dict()
            for key in (*PARAMETRIC_FIELDS,'parametric_splits'):old.pop(key)
            c.db.execute('UPDATE photos SET recipe=? WHERE id=1',(json.dumps(old),));c.db.commit()
        restored=Catalog(restore_catalog(tmp_path/'backup.sqlite',tmp_path/'restored'))
        try:assert restored.recipe(2).parametric_splits==patch['parametric_splits']
        finally:restored.close()
        s.dispatch('sync_photos',{'source_id':1,'groups':['Tone Curve'],'targets':[{'photo_id':2,'expected_revision':4}]})
        reset=s.dispatch('get_photo',{'photo_id':2})['recipe']
        assert reset['parametric_splits']==list(PARAMETRIC_SPLITS) and all(reset[k]==0 for k in PARAMETRIC_FIELDS)
        assert s.dispatch('get_photo',{'photo_id':1})['recipe']==old
        monkeypatch.setattr(s,'run_worker',lambda _:pytest.fail('Invalid/stale draft started pixels'))
        with pytest.raises(ConflictError):s.dispatch('preview_photo',{**options,'expected_revision':0,'curve_patch':{'parametric_lights':20}})
        with pytest.raises(ValueError):s.dispatch('preview_photo',{**options,'expected_revision':2,'curve_patch':{'parametric_splits':[.3,.2,.8]}})
        with pytest.raises(jsonschema.ValidationError):s.dispatch('preview_photo',{**options,'curve_patch':{'parametric_lights':20}})
        assert hashes==[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
    finally:s.close()
