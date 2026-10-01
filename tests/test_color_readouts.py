"""Develop readout color math, geometry, cache and read-only worker contracts.

Analytic neutrals and independently transformed full-frame rasters check values
and coordinates. Real workers and Metal check delivery, dispatch and preservation.
No Adobe RAW appearance, display calibration or desktop acceptance is implied.
"""
from dataclasses import replace
from pathlib import Path
import struct

import numpy as np
from PIL import Image
import pytest

from lumaraw import accelerators, color_readouts as colors, render
from lumaraw.color import output_matrix
from lumaraw.model import Recipe
from lumaraw.imaging import trim_cache
from lumaraw.service import Service, ConflictError
from test_metal import require_metal


@pytest.fixture(autouse=True)
def backend():
    accelerators.configure('cpu')
    yield
    accelerators.configure('auto')


def read_map(receipt):
    data=Path(receipt['path']).read_bytes()
    assert data[:8]==colors.MAGIC
    assert struct.unpack('<II',data[8:16])==(receipt['width'],receipt['height'])
    return np.frombuffer(data[16:],'<f4').reshape(receipt['height'],receipt['width'],6)


def test_analytic_d50_neutrals_and_sdr_endpoints():
    wide=np.array([[[0,0,0],[.18,.18,.18],[1,1,1],[-1,-1,-1],[2,2,2]]],np.float32)
    work=wide @ np.linalg.inv(output_matrix('prophoto')).T
    actual=colors.values(work)[0]
    np.testing.assert_allclose(actual[[0,3]],np.zeros((2,6)),atol=2e-4)
    np.testing.assert_allclose(actual[[2,4]],[[100,100,100,100,0,0]]*2,atol=2e-4)
    np.testing.assert_allclose(actual[1],[46.1356]*3+[49.4961,0,0],atol=3e-4)
    assert actual.dtype==np.float32


def test_map_bounds_header_and_atomic_replacement(tmp_path):
    path=tmp_path/'map.readouts'
    data=np.zeros((9,13,6),np.float32);data[3,7]=[12,23,34,45,-56,67]
    colors.write(path,data)
    np.testing.assert_array_equal(read_map(colors.receipt(path,13,9,False)),data)
    assert colors.cached(path,13,9) and not colors.cached(path,12,9)
    path.write_bytes(b'x'*path.stat().st_size)
    assert not colors.cached(path,13,9)
    for size in [(0,1),(2049,1),(2048,1537)]:
        with pytest.raises(ValueError):colors.header(*size)
    data[0,0,0]=np.nan
    with pytest.raises(ValueError):colors.write(path,data)
    assert not list(tmp_path.glob('*.part'))


def test_tiny_cache_files_are_bounded_without_evicting_current_receipts(tmp_path):
    import os
    cache=tmp_path/'cache';cache.mkdir()
    paths=[]
    for index in range(12):
        path=cache/str(index);path.write_bytes(b'pixel');os.utime(path,(index+1,index+1));paths.append(path)
    original=tmp_path/'original';original.write_bytes(b'never delete')
    (cache/'external-link').symlink_to(original)
    trim_cache(cache,maximum_mb=512,maximum_files=4,keep=[str(paths[0])])
    assert {p.name for p in cache.iterdir()}=={'0','9','10','11','external-link'}
    assert original.read_bytes()==b'never delete'
    trim_cache(cache,maximum_mb=0,maximum_files=4,keep=[str(paths[0])])
    assert paths[0].read_bytes()==b'pixel' and len(list(cache.iterdir()))==2


@pytest.mark.parametrize('orientation',range(8))
@pytest.mark.parametrize('geometry',[False,True])
def test_oriented_fit_and_detail_maps_match_full_pipeline(tmp_path,monkeypatch,orientation,geometry):
    source=np.random.default_rng(61).uniform(.03,.6,(189,237,3)).astype(np.float32)
    path=tmp_path/'identity';path.write_bytes(b'readout fixture')
    cache=tmp_path/'cache';cache.mkdir()
    meta={'width':237,'height':189,'decoded_width':237,'decoded_height':189}
    monkeypatch.setattr(render,'base_image',lambda *a,**k:(source,meta,str(cache/'base.npy')))
    recipe=Recipe(exposure=.2,contrast=13,sharpen=20,luma_noise=10,orange_hue=12,
                  parametric_darks=25,curve_blue_points=[[0,0],[.4,.5],[1,1]])
    if geometry:
        recipe=replace(recipe,rotation=90,crop_box=[.08,.13,.93,.89],crop='5:4',
                       straighten=3,perspective_h=7,distortion=4,geometry_scale=1.1)
    plan=render.RenderPlan(source,recipe)
    filtered=render.detail_filter(plan.sample(0,0,plan.width,plan.height),recipe,plan.pixel_scale)
    expected=colors.values(render.grade_tile(filtered,recipe,0,0,plan.width,plan.height))
    if orientation>=4:expected=np.fliplr(expected)
    expected=np.rot90(expected,-orientation%4)
    params={'orientation':orientation,'include_before':False,'include_color_readouts':True}
    fitted=render.make_preview(path,recipe,cache,512,**params)
    np.testing.assert_allclose(read_map(fitted['color_readouts']),expected,atol=2e-4,rtol=0)
    assert (fitted['image_width'],fitted['image_height'])==(expected.shape[1],expected.shape[0])
    detail=render.make_preview(path,recipe,cache,512,detail={'width':97,'height':79,'cx':.73,'cy':.35},**params)
    x,y,w,h=detail['roi']
    np.testing.assert_allclose(read_map(detail['color_readouts']),expected[y:y+h,x:x+w],atol=2e-4,rtol=0)
    repeated=render.make_preview(path,recipe,cache,512,**params)
    assert repeated['color_readouts']['cache_hit']
    assert repeated['color_readouts']['path'] in repeated['cache_keep']


def test_maps_precede_proof_overlay_and_preserve_display_pixels(tmp_path,monkeypatch):
    path=tmp_path/'gradient.png'
    Image.fromarray(np.random.default_rng(5).integers(0,256,(120,160,3),dtype=np.uint8)).save(path)
    recipe=Recipe(exposure=.4,saturation=20)
    plain=render.make_preview(path,recipe,tmp_path/'cache',512,include_before=False)
    pixels=np.asarray(Image.open(plain['preview'])).copy()
    mapped=render.make_preview(path,recipe,tmp_path/'cache',512,include_before=False,include_color_readouts=True)
    np.testing.assert_array_equal(np.asarray(Image.open(mapped['preview'])),pixels)
    expected=read_map(mapped['color_readouts']).copy()
    monkeypatch.setattr(render,'soft_proof',lambda p,*a:np.full_like(p,7))
    proofed=render.make_preview(path,recipe,tmp_path/'proof-cache',512,include_before=False,
        include_color_readouts=True,display={'proof_path':'injected','proof_sha':'test','gamut':True})
    assert np.asarray(Image.open(proofed['preview'])).max()==7
    np.testing.assert_array_equal(read_map(proofed['color_readouts']),expected)


def test_real_worker_before_cache_revisions_and_original_safety(tmp_path):
    path=tmp_path/'photo.png';Image.new('RGB',(480,320),(30,70,150)).save(path)
    original=path.read_bytes();s=Service(tmp_path/'catalog',presets_root=tmp_path/'presets')
    try:
        s.dispatch('queue_control',{'action':'pause'})
        s.dispatch('import_photos',{'paths':[str(path)]})
        s.dispatch('edit_photo',{'photo_id':1,'expected_revision':0,'patch':{'exposure':1}})
        photo=s.dispatch('get_photo',{'photo_id':1})
        history=s.dispatch('list_history',{'photo_id':1,'expected_revision':1})
        params={'photo_id':1,'expected_revision':1,'include_color_readouts':True}
        first=s.dispatch('preview_photo',params)
        before=read_map(first['before_color_readouts']).copy()
        assert not np.array_equal(before,read_map(first['color_readouts']))
        second=s.dispatch('preview_photo',params)
        assert second['color_readouts']['cache_hit'] and second['before_color_readouts']['cache_hit']
        np.testing.assert_array_equal(read_map(second['before_color_readouts']),before)
        assert second['before_cache_hit']
        one=s.dispatch('preview_photo',{**params,'include_before':False,
            'detail':{'width':1,'height':1,'cx':.2,'cy':.8}})
        assert read_map(one['color_readouts']).shape==(1,1,6) and 'before_color_readouts' not in one
        assert s.dispatch('get_photo',{'photo_id':1})['recipe']==photo['recipe']
        assert s.dispatch('list_history',{'photo_id':1,'expected_revision':1})==history
        with pytest.raises(ConflictError):s.dispatch('preview_photo',{**params,'expected_revision':0})
        assert path.read_bytes()==original
    finally:s.close()


def test_metal_capture_grades_once_and_matches_cpu():
    pixels=np.random.default_rng(6).uniform(.02,.8,(192,321,3)).astype(np.float32)
    recipe=Recipe(exposure=.3,contrast=22,orange_hue=9,parametric_darks=45)
    expected=accelerators.grade_output(pixels,recipe,'srgb',capture_work=True)
    require_metal()
    actual=accelerators.grade_output(pixels,recipe,'srgb',capture_work=True)
    np.testing.assert_allclose(actual[0],expected[0],atol=1e-4,rtol=2e-5)
    np.testing.assert_allclose(colors.values(actual[2]),colors.values(expected[2]),atol=.002,rtol=0)
    report=accelerators.report()
    assert report['metal_grade_tiles']==1 and report['cpu_tiles']==0
    assert report['cpu_readout_output_tiles']==1 and report['backend']=='hybrid'


def test_complex_capture_retains_cpu_work_and_real_metal_output():
    pixels=np.random.default_rng(8).uniform(.02,.8,(192,321,3)).astype(np.float32)
    recipe=Recipe(masks=[{'kind':'radial','exposure':.4}],exposure=.2)
    expected=accelerators.grade_output(pixels,recipe,'srgb',capture_work=True)
    require_metal()
    actual=accelerators.grade_output(pixels,recipe,'srgb',capture_work=True)
    np.testing.assert_allclose(actual[0],expected[0],atol=2e-5)
    np.testing.assert_array_equal(actual[2],expected[2])
    report=accelerators.report()
    assert report['metal_output_tiles']==1 and report['cpu_readout_output_tiles']==0
    assert report['backend']=='hybrid'
