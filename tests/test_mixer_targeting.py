"""Targeted color weights, processing-stage order and durable preview boundaries.

Independent dense circular supports check sparse float32 transport. Synthetic
coordinate images verify orientation/crop/detail alignment; real workers verify
cache reuse, treatment-aware upstream invalidation and read-only mixer drafts.
No desktop interaction or Adobe color-equivalence claims are inferred.
"""
from dataclasses import replace
import hashlib
from pathlib import Path
import struct

import jsonschema
import numpy as np
from PIL import Image
import pytest

from lumaraw import accelerators, mixer_targets, render
from lumaraw.color import from_oklab, oklab, mix_hues, MIXER_CENTERS
from lumaraw.curves import apply_rgb_curves
from lumaraw.parametric import apply as apply_parametric
from lumaraw.model import Recipe, MIXER_BANDS
from lumaraw.service import Service, ConflictError


def unpack(packed):
    result=np.zeros((*packed.shape[:2],8),np.float32)
    counts=packed[...,0]>>24
    assert counts.max()<=3
    for slot in range(3):
        rows,cols=np.nonzero(counts>slot)
        indices=(packed[rows,cols,0]>>(8*slot))&255
        values=packed[rows,cols,slot+1].copy().view(np.float32)
        assert np.all(indices<8) and np.all((values>0)&(values<=1))
        result[rows,cols,indices]=values
    return result


def read_map(receipt):
    data=Path(receipt['path']).read_bytes()
    assert data[:8]==mixer_targets.MAGIC
    assert struct.unpack('<II',data[8:16])==(receipt['width'],receipt['height'])
    return np.frombuffer(data[16:],'<u4').reshape(receipt['height'],receipt['width'],4)


def test_sparse_weights_preserve_all_three_overlaps_and_neutral_protection():
    angles=np.radians(np.linspace(0,360,36001,dtype=np.float32))
    lab=np.stack([np.full_like(angles,.55),.08*np.cos(angles),.08*np.sin(angles)],axis=-1)[None,:,:]
    image=from_oklab(lab)
    actual=unpack(mixer_targets.packed_weights(image))
    analyzed=oklab(image);h=np.degrees(np.arctan2(analyzed[...,2],analyzed[...,1]))%360
    distance=np.abs((h[...,None]-np.array(MIXER_CENTERS)+180)%360-180)
    expected=np.maximum(0,1-distance/50)**2
    expected/=expected.max(axis=2,keepdims=True)
    # Circular arithmetic is float32 in the engine and float64 in this reference;
    # require less than 0.0004 control units across a 200-unit pointer range.
    np.testing.assert_allclose(actual,expected,atol=2e-6,rtol=0)
    assert np.max(np.count_nonzero(actual,axis=2))==3
    gray=np.repeat(np.linspace(0,2,100,dtype=np.float32)[None,:,None],3,axis=2)
    assert not np.any(mixer_targets.packed_weights(gray))
    low=from_oklab(np.array([[[.55,.0001,.0001]]],np.float32))
    assert 0<unpack(mixer_targets.packed_weights(low)).max()<.01


@pytest.mark.parametrize('component',['hue','sat','lum','bw'])
def test_linked_weight_changes_adjust_matching_colors_in_the_requested_direction(component):
    angles=np.radians(np.array([97,180,270],np.float32))
    image=from_oklab(np.stack([np.full(3,.55),.09*np.cos(angles),.09*np.sin(angles)],axis=-1).astype(np.float32)[None,:,:])
    weights=unpack(mixer_targets.packed_weights(image))[0,0]
    delta=10 if component=='hue' else 30
    recipe=Recipe(monochrome=component=='bw',**{b+'_'+component:float(delta*w) for b,w in zip(MIXER_BANDS,weights)})
    baseline=render.grade_tile(image,Recipe(monochrome=component=='bw'))
    changed=render.grade_tile(image,recipe)
    if component=='hue':
        lab=oklab(changed);angle=np.degrees(np.arctan2(lab[0,0,2],lab[0,0,1]))
        assert 0<(angle-97+180)%360-180<11
    elif component=='sat':
        assert np.linalg.norm(oklab(changed)[0,0,1:])>np.linalg.norm(oklab(baseline)[0,0,1:])
    else:
        assert np.mean(changed[0,0])>np.mean(baseline[0,0])
    np.testing.assert_allclose(changed[0,2],baseline[0,2],atol=3e-7,rtol=0)


@pytest.mark.parametrize('orientation',range(8))
@pytest.mark.parametrize('mode',['hsl','bw'])
def test_sparse_maps_follow_color_stage_and_oriented_crop_detail(tmp_path,monkeypatch,orientation,mode):
    source=np.random.default_rng(12).uniform(.01,.9,(179,211,3)).astype(np.float32)
    path=tmp_path/'source';path.write_bytes(b'identity');cache=tmp_path/'cache';cache.mkdir()
    monkeypatch.setattr(render,'base_image',lambda *a,**kw:(source,{'width':211,'height':179},str(cache/'base.npy')))
    recipe=Recipe(rotation=90,crop_box=[.05,.1,.91,.93],crop='5:4',straighten=2,perspective_h=4,
                  exposure=.3,luma_noise=8,sharpen=12,curve_midtones=6,parametric_darks=30,
                  curve_blue_points=[[0,.03],[1,.9]],orange_hue=18,red_sat=-25,blue_lum=30,monochrome=mode=='bw')
    accelerators.configure('cpu')
    try:
        for edge,detail in [(128,None),(None,{'width':73,'height':91,'cx':.7,'cy':.3})]:
            plan=render.RenderPlan(source,recipe,edge or 0)
            inputs=render.detail_filter(plan.sample(0,0,plan.width,plan.height),recipe,plan.pixel_scale)
            inputs=apply_rgb_curves(apply_parametric(render.grade_before_parametric(inputs,recipe),recipe),recipe)
            if mode=='bw':inputs=mix_hues(inputs,recipe)
            expected=mixer_targets.packed_weights(inputs)
            if orientation>=4:expected=np.fliplr(expected)
            expected=np.rot90(expected,-orientation%4)
            result=render.make_preview(path,recipe,cache,512,orientation=orientation,max_edge=edge,detail=detail,
                                       mixer_target=mode,include_before=False)
            if result['roi']:
                x,y,w,h=result['roi'];expected=expected[y:y+h,x:x+w]
            # SIMD edge lanes and float32 color transforms differ slightly with
            # strip shape. Bound the resulting control delta to 0.01 units over
            # the entire 200-unit slider range, not packed integer bit identity.
            np.testing.assert_allclose(unpack(read_map(result['mixer_target'])),unpack(expected),atol=.01/200,rtol=0)
            assert result['mixer_target']['path'] in result['cache_keep']
    finally:accelerators.configure('auto')


def test_cache_stage_boundaries_and_binary_bounds(tmp_path):
    path=tmp_path/'source';path.write_bytes(b'identity')
    recipe=Recipe();key=lambda r,mode='hsl',geometry=[]:mixer_targets.target_path(path,r,tmp_path,geometry,mode)
    assert key(recipe)==key(replace(recipe,red_hue=20,green_sat=40,blue_bw=30,monochrome=True))
    assert key(recipe,'bw')!=key(replace(recipe,red_hue=20),'bw')
    assert key(recipe,'bw')==key(replace(recipe,red_bw=30,monochrome=True),'bw')
    for patch in [{'exposure':1},{'temperature':20},{'parametric_darks':30},{'curve_blue_points':[[0,.2],[1,.9]]},{'rotation':90},{'luma_noise':10}]:
        assert key(recipe)!=key(replace(recipe,**patch))
    assert key(recipe)!=key(recipe,geometry=[1]) and key(recipe)!=key(recipe,'bw')
    target=tmp_path/'map';packed=mixer_targets.packed_weights(np.ones((2,3,3),np.float32)*.5)
    mixer_targets.write(target,packed);assert mixer_targets.cached(target,3,2)
    np.testing.assert_array_equal(read_map(mixer_targets.receipt(target,3,2,True,'hsl')),packed)
    target.write_bytes(target.read_bytes()[:-1]);assert not mixer_targets.cached(target,3,2)
    for w,h in [(0,1),(2049,1),(2048,2048)]:
        with pytest.raises(ValueError):mixer_targets.header(w,h)
    old=key(recipe);path.write_bytes(b'changed');assert key(recipe)!=old


def test_real_mixer_drafts_are_scoped_read_only_and_reuse_matching_maps(tmp_path):
    path=tmp_path/'photo.png';Image.new('RGB',(170,130),(225,140,25)).save(path)
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    service=Service(tmp_path/'catalog',presets_root=tmp_path/'presets')
    try:
        service.dispatch('queue_control',{'action':'pause'})
        service.dispatch('import_photos',{'paths':[str(path)]})
        opts={'photo_id':1,'include_before':False,'max_edge':128}
        normal=service.dispatch('preview_photo',opts);pixels=np.array(Image.open(normal['preview']))
        assert 'mixer_target' not in normal
        base=service.dispatch('preview_photo',{**opts,'mixer_target':'hsl'})
        np.testing.assert_array_equal(np.array(Image.open(base['preview'])),pixels)
        draft=service.dispatch('preview_photo',{**opts,'mixer_target':'hsl','mixer_patch':{'orange_hue':20,'yellow_lum':-50},'expected_revision':0})
        assert draft['mixer_draft'] and not draft['curve_draft'] and draft['mixer_target']['cache_hit']
        assert draft['mixer_target']['path']==base['mixer_target']['path']
        assert not np.array_equal(np.array(Image.open(draft['preview'])),pixels)
        current=service.dispatch('get_photo',{'photo_id':1});assert current['revision']==0 and current['recipe']['orange_hue']==0
        with service.catalog() as c:assert c.db.execute('SELECT COUNT(*) FROM history').fetchone()[0]==0
        for invalid in [{'mixer_patch':{'exposure':1},'expected_revision':0},{'mixer_patch':{'orange_hue':31},'expected_revision':0},
                        {'mixer_patch':{'orange_sat':20}},{'mixer_patch':{'orange_sat':20},'curve_patch':{'parametric_darks':20},'expected_revision':0}]:
            with pytest.raises(jsonschema.ValidationError):service.dispatch('preview_photo',{**opts,**invalid})
        service.dispatch('edit_photo',{'photo_id':1,'expected_revision':0,'patch':{'monochrome':True,'orange_hue':15}})
        bw=service.dispatch('preview_photo',{**opts,'mixer_target':'bw'})
        bw_pixels=np.array(Image.open(bw['preview']))
        bw_draft=service.dispatch('preview_photo',{**opts,'mixer_target':'bw','mixer_patch':{'orange_bw':70},'expected_revision':1})
        assert bw_draft['mixer_target']['path']==bw['mixer_target']['path'] and bw_draft['mixer_target']['cache_hit']
        with pytest.raises(ConflictError):service.dispatch('preview_photo',{**opts,'mixer_patch':{'orange_bw':10},'expected_revision':0})
        restored=service.dispatch('preview_photo',opts)
        np.testing.assert_array_equal(np.array(Image.open(restored['preview'])),bw_pixels)
        assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
    finally:service.close()
