"""Photo-targeted input map coordinates, cache boundaries and read-only drafts.

Synthetic coordinate images establish map alignment for all catalog orientations,
recipe geometry and detail ROIs. Independent array transforms check the map;
service cases verify real worker delivery without catalog or original writes.
This is not rendered desktop evidence or Adobe transform equivalence.
"""
from dataclasses import replace
import hashlib
from pathlib import Path
import struct

import numpy as np
from PIL import Image
import pytest

from lumaraw import accelerators, curve_tones, render
from lumaraw.color import encode
from lumaraw.imaging import LUMA
from lumaraw.model import Recipe
from lumaraw.service import Service, ConflictError


def read_map(receipt):
    data=Path(receipt['path']).read_bytes()
    assert data[:8]==curve_tones.MAGIC
    assert struct.unpack('<II',data[8:16])==(receipt['width'],receipt['height'])
    return np.frombuffer(data[16:],'<f4').reshape(receipt['height'],receipt['width'])


@pytest.mark.parametrize('orientation',range(8))
@pytest.mark.parametrize('geometry',[False,True])
def test_map_matches_upstream_pipeline_and_actual_oriented_viewport(tmp_path,monkeypatch,orientation,geometry):
    rng=np.random.default_rng(31)
    source=rng.uniform(.02,.8,(189,237,3)).astype(np.float32)
    path=tmp_path/'source';path.write_bytes(b'synthetic identity')
    cache=tmp_path/'cache';cache.mkdir()
    monkeypatch.setattr(render,'base_image',lambda *args,**kwargs:(source,{'width':237,'height':189},str(cache/'base.npy')))
    recipe=Recipe(exposure=.2,contrast=19,shadows=23,saturation=8,curve_midtones=7,
                  parametric_darks=60,curve_red_points=[[0,.1],[1,.9]],orange_hue=10,
                  sharpen=20,luma_noise=10,chroma_noise=15)
    if geometry:
        recipe=replace(recipe,rotation=90,crop_box=[.08,.13,.93,.89],crop='5:4',
                       straighten=3,perspective_h=7,distortion=4,ca_red=2,geometry_scale=1.1)
    plan=render.RenderPlan(source,recipe)
    filtered=render.detail_filter(plan.sample(0,0,plan.width,plan.height),recipe,plan.pixel_scale)
    expected=np.clip(encode(render.grade_before_parametric(filtered,recipe)@LUMA),0,1)
    if orientation>=4:expected=np.fliplr(expected)
    expected=np.rot90(expected,-orientation%4)
    accelerators.configure('cpu')
    try:
        fitted=render.make_preview(path,recipe,cache,512,orientation=orientation,include_before=False,include_curve_tones=True)
        np.testing.assert_allclose(read_map(fitted['curve_tones']),expected,atol=3e-7,rtol=0)
        detail=render.make_preview(path,recipe,cache,512,orientation=orientation,include_before=False,
            include_curve_tones=True,detail={'width':97,'height':79,'cx':.73,'cy':.35})
        x,y,w,h=detail['roi']
        np.testing.assert_allclose(read_map(detail['curve_tones']),expected[y:y+h,x:x+w],atol=3e-7,rtol=0)
        assert detail['curve_tones']['width']==w and detail['curve_tones']['height']==h
        assert detail['curve_tones']['path'] in detail['cache_keep']
        reduced_plan=render.RenderPlan(source,recipe,128)
        reduced_input=render.detail_filter(reduced_plan.sample(0,0,reduced_plan.width,reduced_plan.height),recipe,reduced_plan.pixel_scale)
        reduced_expected=np.clip(encode(render.grade_before_parametric(reduced_input,recipe)@LUMA),0,1)
        if orientation>=4:reduced_expected=np.fliplr(reduced_expected)
        reduced_expected=np.rot90(reduced_expected,-orientation%4)
        reduced=render.make_preview(path,recipe,cache,512,orientation=orientation,max_edge=128,include_before=False,include_curve_tones=True)
        np.testing.assert_allclose(read_map(reduced['curve_tones']),reduced_expected,atol=3e-7,rtol=0)
    finally:accelerators.configure('auto')


@pytest.mark.parametrize('patch',[
    {'exposure':1},{'temperature':20},{'tint':10},{'curve_midtones':10},{'saturation':20},
    {'crop_box':[.1,.1,.9,.9]},{'rotation':90},{'sharpen':10},{'luma_noise':10},{'highlight_recovery':True},
])
def test_upstream_edits_invalidate_map_identity(tmp_path,patch):
    path=tmp_path/'source';path.write_bytes(b'source')
    recipe=Recipe()
    assert curve_tones.target_path(path,recipe,tmp_path,[]) != curve_tones.target_path(path,replace(recipe,**patch),tmp_path,[])


def test_downstream_edits_reuse_maps_but_sources_and_viewports_do_not(tmp_path):
    path=tmp_path/'source';path.write_bytes(b'source')
    baseline=curve_tones.target_path(path,Recipe(),tmp_path,[])
    changed=Recipe(parametric_darks=30,parametric_splits=[.2,.5,.8],curve_blue_points=[[0,.1],[1,.9]],
                   blue_bw=20,orange_hue=8,red_lum=20,monochrome=True,
                   masks=[{'kind':'radial','x':.5,'y':.5,'radius':.2,'exposure':1}])
    assert curve_tones.target_path(path,changed,tmp_path,[])==baseline
    assert curve_tones.target_path(path,Recipe(),tmp_path,[1])!=baseline
    path.write_bytes(b'changed source')
    assert curve_tones.target_path(path,Recipe(),tmp_path,[])!=baseline


def test_map_format_bounds_atomic_replacement_and_corruption(tmp_path):
    target=tmp_path/'tones';values=np.linspace(0,1,24,dtype=np.float32).reshape(4,6)
    curve_tones.write(target,values)
    assert curve_tones.cached(target,6,4)
    np.testing.assert_array_equal(read_map(curve_tones.receipt(target,6,4,True)),values)
    target.write_bytes(b'wrong format'+target.read_bytes()[12:])
    assert not curve_tones.cached(target,6,4)
    curve_tones.write(target,values)
    target.write_bytes(target.read_bytes()[:-1]);assert not curve_tones.cached(target,6,4)
    for w,h in [(0,1),(2049,1),(2048,2048)]:
        with pytest.raises(ValueError):curve_tones.header(w,h)
    for invalid in (float('nan'),float('inf'),-1,2):
        with pytest.raises(ValueError):curve_tones.write(target,np.array([[invalid]],np.float32))
    assert not list(tmp_path.glob('*.part'))


def test_real_worker_maps_are_opt_in_reusable_and_drafts_are_read_only(tmp_path):
    path=tmp_path/'photo.png';Image.new('RGB',(170,130),(90,120,180)).save(path)
    original=hashlib.sha256(path.read_bytes()).hexdigest()
    service=Service(tmp_path/'catalog',presets_root=tmp_path/'presets')
    try:
        service.dispatch('queue_control',{'action':'pause'})
        service.dispatch('import_photos',{'paths':[str(path)]})
        options={'photo_id':1,'include_before':False,'max_edge':128}
        normal=service.dispatch('preview_photo',options)
        assert 'curve_tones' not in normal
        normal_pixels=np.array(Image.open(normal['preview']))
        first=service.dispatch('preview_photo',{**options,'include_curve_tones':True})
        assert not first['curve_tones']['cache_hit']
        np.testing.assert_array_equal(np.array(Image.open(first['preview'])),normal_pixels)
        draft=service.dispatch('preview_photo',{**options,'include_curve_tones':True,'expected_revision':0,
            'curve_patch':{'parametric_darks':80,'parametric_splits':[.2,.5,.8]}})
        assert draft['curve_tones']['cache_hit'] and draft['curve_tones']['path']==first['curve_tones']['path']
        assert draft['curve_draft'] and not np.array_equal(np.array(Image.open(first['preview'])),np.array(Image.open(draft['preview'])))
        np.testing.assert_array_equal(read_map(first['curve_tones']),read_map(draft['curve_tones']))
        warned=service.dispatch('preview_photo',{**options,'include_curve_tones':True,'display':{'gamut':True}})
        assert warned['curve_tones']['cache_hit'] and warned['curve_tones']['path']==first['curve_tones']['path']
        assert service.dispatch('get_photo',{'photo_id':1})['revision']==0
        with service.catalog() as catalog:assert catalog.db.execute('SELECT COUNT(*) FROM history').fetchone()[0]==0
        service.dispatch('edit_photo',{'photo_id':1,'expected_revision':0,'patch':{'exposure':.5}})
        updated=service.dispatch('preview_photo',{**options,'include_curve_tones':True})
        assert updated['curve_tones']['path']!=first['curve_tones']['path']
        with pytest.raises(ConflictError):
            service.dispatch('preview_photo',{**options,'include_curve_tones':True,'expected_revision':0,'curve_patch':{'parametric_darks':50}})
        assert hashlib.sha256(path.read_bytes()).hexdigest()==original
    finally:service.close()
