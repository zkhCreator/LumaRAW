"""Four-wheel tonal behavior, native draft contracts and durable shared workflows.

Generated linear pixels establish range selection, black/white protection and
pointwise strip agreement. Real workers check drafts, pixel cache admission and
revision/cancellation guards. Optional actual Metal checks do not establish Adobe
pixels, camera accuracy, desktop interaction or the proprietary grading equations.
"""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path

import jsonschema
import numpy as np
from PIL import Image
import pytest

from lumaraw import accelerators, color_grading, preview_cache
from lumaraw.color import decode, oklab, to_output
from lumaraw.model import Recipe, GRADING_FIELDS, GRADING_RANGES, LIMITS
from lumaraw.render import grade_tile, RenderPlan, OrientedPlan, render_strip
from lumaraw.service import Service, ConflictError
from lumaraw.source_identity import pixel_recipe_key_data


@pytest.fixture(autouse=True)
def cpu_default():
    accelerators.configure('cpu')
    yield
    accelerators.configure('auto')


@pytest.mark.parametrize('key',GRADING_FIELDS)
def test_additive_defaults_and_strict_limits(key):
    old=Recipe.parse({'version':1,'exposure':.25})
    assert getattr(old,key)==(50 if key=='grading_blending' else 0)
    lo,hi=LIMITS[key]
    for value in (lo,hi):
        assert getattr(Recipe.parse({key:value}),key)==value
    for value in (True,'1',float('nan'),float('inf'),lo-.001,hi+.001):
        with pytest.raises(ValueError):Recipe.parse({key:value})


def test_neutral_and_inactive_hue_are_exact_allocation_free_bypass():
    pixels=np.random.default_rng(43).uniform(-.02,8,(13,17,3)).astype(np.float32)
    before=pixels.copy()
    recipe=Recipe(**{**{f'grading_{r}_hue':275 for r in GRADING_RANGES},'grading_blending':100,'grading_balance':-100})
    assert color_grading.apply(pixels,recipe) is pixels
    np.testing.assert_array_equal(pixels,before)


@pytest.mark.parametrize('region',GRADING_RANGES)
def test_tint_protects_black_white_and_luminance_enables_them(region):
    pixels=np.array([[[0,0,0],[1,1,1],[.18,.18,.18]]],np.float32)
    recipe=Recipe(**{f'grading_{region}_hue':30,f'grading_{region}_saturation':80})
    result=color_grading.apply(pixels,recipe)
    np.testing.assert_array_equal(result[0,:2],pixels[0,:2])
    assert np.ptp(result[0,2])>.001
    bright=color_grading.apply(pixels,replace(recipe,**{f'grading_{region}_luminance':100}))
    dark=color_grading.apply(pixels,replace(recipe,**{f'grading_{region}_luminance':-100}))
    assert bright[0,0].max()>0 and np.ptp(bright[0,0])/bright[0,0].max()>1e-5
    assert dark[0,1].max()<1 and np.ptp(dark[0,1])>1e-7


def test_three_tonal_ranges_and_balance_direction_and_blending_overlap():
    tones=np.array([.08,.5,.92],np.float32)
    pixels=np.repeat(decode(tones)[None,:,None],3,axis=2)
    for i,region in enumerate(GRADING_RANGES[:3]):
        result=color_grading.apply(pixels,Recipe(**{f'grading_{region}_saturation':100,f'grading_{region}_hue':230,'grading_blending':0}))
        strength=np.linalg.norm(oklab(result)[0,:,1:]-oklab(pixels)[0,:,1:],axis=-1)/(4*tones*(1-tones))
        assert np.argmax(strength)==i and strength[i]>strength[(i+1)%3]*10
    low=color_grading.weights(tones,.12,0);wide=color_grading.weights(tones,.5,0)
    assert np.all(wide.max(axis=-1)<low.max(axis=-1))
    positive=color_grading.weights(tones,.3,.35);negative=color_grading.weights(tones,.3,-.35)
    assert np.all(positive[:,2]>negative[:,2]) and np.all(negative[:,0]>positive[:,0])


def test_global_is_independent_luminance_works_at_zero_saturation_and_hue_wraps():
    pixels=np.full((3,5,3),.18,np.float32)
    r=Recipe(grading_global_hue=0,grading_global_saturation=40,grading_global_luminance=25)
    expected=color_grading.apply(pixels,r)
    np.testing.assert_array_equal(color_grading.apply(pixels,replace(r,grading_blending=0,grading_balance=100)),expected)
    np.testing.assert_array_equal(color_grading.apply(pixels,replace(r,grading_global_hue=360)),expected)
    neutral=color_grading.apply(pixels,Recipe(grading_global_luminance=40))
    assert neutral.min()>pixels.max() and np.ptp(neutral)<1e-7
    assert color_grading.apply(pixels,Recipe(grading_global_luminance=-40)).max()<pixels.min()
    combined=color_grading.apply(pixels,replace(r,grading_midtones_saturation=80,grading_midtones_hue=200))
    assert not np.array_equal(combined,expected)


@pytest.mark.parametrize('amount',(-100,100))
def test_extremes_are_finite_do_not_mutate_source_and_bw_can_be_tinted(amount):
    pixels=np.random.default_rng(13).uniform(-.02,8,(19,37,3)).astype(np.float32);original=pixels.copy()
    values={f'grading_{r}_{c}':(360 if c=='hue' else 100 if c=='saturation' else amount) for r in GRADING_RANGES for c in ('hue','saturation','luminance')}
    result=color_grading.apply(pixels,Recipe(**values,grading_balance=amount,grading_blending=100))
    assert result.dtype==np.float32 and np.isfinite(result).all()
    np.testing.assert_array_equal(pixels,original)
    bw=grade_tile(np.full((4,5,3),.18,np.float32),Recipe(monochrome=True,grading_global_hue=210,grading_global_saturation=45))
    assert np.max(np.ptp(bw,axis=-1))>.01


@pytest.mark.parametrize('orientation',(0,3,6))
def test_grading_has_no_spatial_halo_and_strips_viewports_match(orientation):
    pixels=np.random.default_rng(15).uniform(.02,.8,(143,157,3)).astype(np.float32)
    recipe=Recipe(exposure=.25,monochrome=True,red_bw=35,grading_shadows_hue=240,grading_shadows_saturation=35,
        grading_midtones_luminance=25,grading_highlights_hue=45,grading_highlights_saturation=50,grading_global_luminance=-15)
    plan=OrientedPlan(RenderPlan(pixels,recipe),orientation)
    whole,_=render_strip(plan,0,0,plan.width,plan.height)
    strips=np.concatenate([render_strip(plan,0,y,plan.width,min(37,plan.height-y))[0] for y in range(0,plan.height,37)])
    np.testing.assert_allclose(strips,whole,atol=3e-6,rtol=0)
    view,_=render_strip(plan,21,31,49,57)
    np.testing.assert_allclose(view,whole[31:88,21:70],atol=3e-6,rtol=0)


@pytest.mark.parametrize('space',('srgb','p3','adobe','prophoto'))
@pytest.mark.parametrize('recipe',(
    Recipe(grading_shadows_hue=240,grading_shadows_saturation=75,grading_midtones_hue=30,grading_midtones_saturation=45,
           grading_highlights_hue=120,grading_highlights_saturation=90,grading_blending=0,grading_balance=65),
    Recipe(monochrome=True,grading_global_hue=210,grading_global_saturation=65,grading_global_luminance=25,grading_blending=100,grading_balance=-100),
    Recipe(grading_shadows_luminance=100,grading_midtones_luminance=-100,grading_highlights_luminance=-100),
    Recipe(exposure=.5,blue_hue=20,blue_sat=-40,grading_global_hue=360,grading_global_saturation=100,grading_global_luminance=-100,
           grading_shadows_hue=60,grading_shadows_saturation=100,grading_shadows_luminance=100,grading_balance=-100),
))
def test_real_metal_grade_dispatch_matches_cpu(space,recipe):
    if not Path(accelerators.__file__).with_name('libLumaMetal.dylib').exists():
        if os.environ.get('LUMARAW_REQUIRE_METAL'):pytest.fail('Required Metal backend missing')
        pytest.skip('Optional Metal unavailable')
    pixels=np.random.default_rng(61).uniform(0,2,(131,139,3)).astype(np.float32)
    pixels[0,:2]=[[0,0,0],[1,1,1]]
    expected,_=to_output(grade_tile(pixels,recipe),space)
    accelerators.configure('metal')
    actual,_=accelerators.grade_output(pixels,recipe,space)
    report=accelerators.report()
    assert report['metal_grade_tiles']==1 and not report['fallback_reasons']
    np.testing.assert_allclose(decode(actual,space),decode(expected,space),atol=1e-5,rtol=0)
    assert np.mean(abs(actual-expected))<2e-6
    # Adobe RGB pure gamma magnifies near-zero FP32 cancellation; existing Metal
    # policy bounds that exceptional dark error separately from ordinary pixels.
    dark=(actual<.02)&(expected<.02) if space=='adobe' else np.zeros(actual.shape,bool)
    np.testing.assert_allclose(actual[~dark],expected[~dark],atol=1e-4,rtol=2e-5)
    if dark.any():assert np.max(abs(actual[dark]-expected[dark]))<=16/65535


@pytest.fixture
def library(tmp_path):
    paths=[tmp_path/f'{i}.png' for i in range(3)]
    for path in paths:Image.new('RGB',(240,160),(85,115,150)).save(path)
    service=Service(tmp_path/'catalog',presets_root=tmp_path/'presets')
    service.dispatch('queue_control',{'action':'pause'});service.dispatch('settings',{'compute_backend':'cpu'})
    service.dispatch('import_photos',{'paths':list(map(str,paths))})
    try:yield service,paths
    finally:service.close()


def test_real_grading_drafts_are_scoped_read_only_cache_safe_and_stale(library):
    service,paths=library;hashes=[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
    opts={'photo_id':1,'expected_revision':0,'include_before':False,'max_edge':128,'include_curve_tones':True,'mixer_target':'hsl'}
    normal=service.dispatch('preview_photo',opts)
    patch={'grading_midtones_hue':225,'grading_midtones_saturation':80,'grading_highlights_luminance':-30}
    draft=service.dispatch('preview_photo',{**opts,'grading_patch':patch})
    assert draft['grading_draft'] and not draft['curve_draft'] and not draft['mixer_draft']
    assert Path(normal['preview']).read_bytes()!=Path(draft['preview']).read_bytes()
    for field in ('curve_tones','mixer_target'):
        assert draft[field]['path']==normal[field]['path'] and draft[field]['cache_hit']
    assert service.dispatch('get_photo',{'photo_id':1})['revision']==0
    with service.catalog() as c:assert c.db.execute('SELECT count(*) FROM history').fetchone()[0]==0
    for invalid in ({'grading_patch':{}},{'grading_patch':{'exposure':1}}, {'grading_patch':{'grading_global_hue':361}},
        {'grading_patch':patch,'expected_revision':None},{'grading_patch':patch,'curve_patch':{'parametric_darks':20}},
        {'grading_patch':patch,'mixer_patch':{'blue_sat':20}}):
        with pytest.raises(jsonschema.ValidationError):service.dispatch('preview_photo',{**opts,**invalid})
    omitted={k:v for k,v in opts.items() if k!='expected_revision'}
    with pytest.raises(jsonschema.ValidationError):service.dispatch('preview_photo',{**omitted,'grading_patch':patch})
    restored=service.dispatch('preview_photo',opts)
    assert restored['preview']==normal['preview'] and restored['preview_cache_hit']
    service.dispatch('edit_photo',{'photo_id':1,'expected_revision':0,'patch':patch})
    with pytest.raises(ConflictError):service.dispatch('preview_photo',{**opts,'grading_patch':patch})
    assert hashes==[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]


def test_inactive_grading_pixel_reuse_keeps_history_and_source_revision_guards(library,monkeypatch):
    service,paths=library
    opts={'photo_id':1,'expected_revision':0,'include_before':True,'include_color_readouts':True,'max_edge':128}
    original=service.dispatch('preview_photo',opts)
    thumbnail=service.dispatch('thumbnail',{'photo_id':1,'kind':'developed'})
    saved=service.dispatch('edit_photo',{'photo_id':1,'expected_revision':0,'patch':{
        'grading_global_hue':210,'grading_blending':100,'grading_balance':-100}})
    assert saved['recipe']['grading_global_hue']==210
    with service.catalog() as c:
        history=c.db.execute('SELECT label FROM history WHERE photo_id=1').fetchall()
        assert len(history)==1 and history[0][0].startswith('Color Grading')
    def forbidden(_):pytest.fail('Inactive grading admitted a worker')
    with monkeypatch.context() as m:
        m.setattr(service,'run_worker',forbidden)
        hit=service.dispatch('preview_photo',{**opts,'expected_revision':saved['revision']})
        assert hit['preview_cache_hit'] and not hit['worker_spawned'] and hit['revision']==1
        for field in ('preview','before','color_readouts','before_color_readouts'):
            if isinstance(hit[field],dict):
                assert {k:v for k,v in hit[field].items() if k!='cache_hit'}=={k:v for k,v in original[field].items() if k!='cache_hit'}
            else:assert hit[field]==original[field]
        warm=service.dispatch('thumbnail',{'photo_id':1,'kind':'developed'})
        assert warm['thumbnail']==thumbnail['thumbnail'] and warm['cache_hit']
        with pytest.raises(ConflictError):service.dispatch('preview_photo',opts)
    edited=service.dispatch('edit_photo',{'photo_id':1,'expected_revision':1,'patch':{'grading_global_saturation':65}})
    active=service.dispatch('preview_photo',{**opts,'expected_revision':edited['revision']})
    assert active['worker_spawned'] and active['preview']!=original['preview']
    before=paths[0].stat();os.utime(paths[0],ns=(before.st_atime_ns,before.st_mtime_ns+1_000_000))
    moved=service.dispatch('preview_photo',{**opts,'expected_revision':edited['revision']})
    assert moved['worker_spawned'] and moved['source_fingerprint']!=active['source_fingerprint']


def test_pixel_canonicalization_retains_luminance_active_hue_unknown_and_invalid():
    r=Recipe(grading_global_luminance=30).dict();copy=json.loads(json.dumps(r))
    canonical=pixel_recipe_key_data(r)
    assert canonical['grading_global_luminance']==30 and r==copy
    assert pixel_recipe_key_data({**r,'grading_global_hue':210})==canonical
    assert pixel_recipe_key_data({**r,'grading_global_hue':True})['grading_global_hue'] is True
    assert pixel_recipe_key_data({**r,'future_control':17})['future_control']==17
    assert pixel_recipe_key_data({**r,'grading_shadows_luminance':20,'grading_balance':90})['grading_balance']==90
    assert pixel_recipe_key_data({**r,'grading_global_saturation':60,'grading_global_hue':210})['grading_global_hue']==210


@pytest.mark.parametrize('change',('revision','cancel'))
def test_grading_draft_cache_handoff_rechecks_revision_and_cancellation(library,monkeypatch,change):
    service,_=library
    opts={'photo_id':1,'expected_revision':0,'include_before':False,'max_edge':128,
          'client_id':'grading','generation':10,'grading_patch':{'grading_midtones_hue':225,'grading_midtones_saturation':65}}
    service.dispatch('preview_photo',opts)
    original=preview_cache.load
    def racing(*args,**kwargs):
        result=original(*args,**kwargs);assert result is not None
        if change=='revision':service.dispatch('edit_photo',{'photo_id':1,'expected_revision':0,'patch':{'exposure':1}})
        else:service.dispatch('cancel_preview',{'client_id':'grading','generation':11})
        return result
    monkeypatch.setattr(preview_cache,'load',racing)
    with pytest.raises(ConflictError if change=='revision' else InterruptedError):service.dispatch('preview_photo',opts)


def test_presets_sync_history_old_json_and_frozen_jobs_preserve_all_grading(library,tmp_path):
    service,paths=library
    patch={key:(35 if key=='grading_blending' else -20 if key=='grading_balance' else 230 if key.endswith('_hue') else 45 if key.endswith('_saturation') else -15) for key in GRADING_FIELDS}
    source=service.dispatch('edit_photo',{'photo_id':1,'expected_revision':0,'patch':patch})
    schema=service.dispatch('recipe_schema');assert schema['groups']['Color Grading']==list(GRADING_FIELDS)
    jobs=service.dispatch('enqueue_exports',{'photo_ids':[1],'destination':str(tmp_path/'exports'),'format':'tiff16','request_key':'grading'})
    preset=service.dispatch('save_develop_preset',{'photo_id':1,'expected_photo_revision':1,'fields':list(GRADING_FIELDS),
        'name':'Four wheels','group_name':'Tests','expected_revision':service.dispatch('list_develop_presets')['revision']})
    service.dispatch('edit_photo',{'photo_id':2,'expected_revision':0,'patch':{'exposure':1,'blue_sat':22}})
    service.dispatch('apply_develop_preset',{'preset_id':preset['preset_id'],'expected_revision':preset['revision'],'targets':[{'photo_id':2,'expected_revision':1}]})
    target=service.dispatch('get_photo',{'photo_id':2})
    assert all(target['recipe'][k]==v for k,v in patch.items()) and target['recipe']['exposure']==1 and target['recipe']['blue_sat']==22
    with pytest.raises(ConflictError):service.dispatch('sync_photos',{'source_id':1,'expected_source_revision':0,'groups':['Color Grading'],'targets':[{'photo_id':3,'expected_revision':0}]})
    assert service.dispatch('get_photo',{'photo_id':3})['revision']==0
    with pytest.raises(ConflictError):service.dispatch('sync_photos',{'source_id':1,'expected_source_revision':1,'groups':['Color Grading'],'targets':[{'photo_id':3,'expected_revision':0},{'photo_id':2,'expected_revision':99}]})
    assert service.dispatch('get_photo',{'photo_id':3})['revision']==0
    service.dispatch('sync_photos',{'source_id':1,'expected_source_revision':1,'groups':['Color Grading'],'targets':[{'photo_id':3,'expected_revision':0}]})
    undo=service.dispatch('undo_photo',{'photo_id':2,'expected_revision':2})
    assert all(undo['recipe'][k]==getattr(Recipe(),k) for k in GRADING_FIELDS)
    service.dispatch('edit_photo',{'photo_id':1,'expected_revision':1,'patch':{'grading_global_saturation':0}})
    with service.catalog() as c:
        frozen=json.loads(c.db.execute('SELECT recipe FROM jobs WHERE id=?',(jobs['job_ids'][0],)).fetchone()[0])
        assert all(frozen[k]==v for k,v in patch.items())
        legacy=source['recipe'].copy()
        for key in GRADING_FIELDS:legacy.pop(key)
        c.db.execute('UPDATE photos SET recipe=? WHERE id=1',(json.dumps(legacy),));c.db.commit()
        assert all(getattr(c.recipe(1),k)==getattr(Recipe(),k) for k in GRADING_FIELDS)
    current=service.dispatch('get_photo',{'photo_id':1});assert current['recipe']==legacy
