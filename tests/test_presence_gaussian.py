"""Actual Metal Gaussian precision, shared-pool boundaries and safe fallback.

Inputs are generated FP32 planes and recipes. Tests distinguish the CPU reference,
optional scalar GPU passes and remaining CPU equations. No RAW-camera accuracy,
Adobe matching, desktop input or application-throughput claim is established.
"""
import ctypes as C
from pathlib import Path
import sys
import os

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter
import pytest

from lumaraw import accelerators as accel
from lumaraw.color import decode
from lumaraw.model import Recipe
from lumaraw.render import RenderPlan, OrientedPlan, render_strip
from lumaraw.service import Service


@pytest.fixture(autouse=True)
def reset():
    accel.configure('cpu')
    yield
    accel.configure('auto')


def require_metal(budget_mb=4096):
    if sys.platform!='darwin' or not Path(accel.__file__).with_name('libLumaMetal.dylib').exists():
        if os.getenv('LUMARAW_REQUIRE_METAL'):
            pytest.fail('Actual Metal Gaussian dispatch required')
        pytest.skip('Optional Metal unavailable')
    accel.configure('metal',budget_mb)


@pytest.mark.parametrize('shape', ((1,1),(1,37),(19,1),(37,53),(128,321)))
@pytest.mark.parametrize('sigma', (.4,.8,1.5,4,12,16))
def test_actual_gaussian_matches_nearest_cpu_for_edges_and_log_range(shape,sigma):
    require_metal()
    source=np.random.default_rng(31).uniform(-26,3,shape).astype(np.float32)
    before=source.copy()
    actual=accel.presence_gaussian(source,sigma)
    expected=gaussian_filter(source,sigma,mode='nearest',truncate=4)
    np.testing.assert_allclose(actual,expected,atol=6e-6,rtol=0)
    np.testing.assert_array_equal(source,before)
    report=accel.report()
    assert report['presence_metal_gaussian_filters']==1
    assert report['presence_metal_gaussian_passes']==2
    assert report['presence_gaussian_backend']=='metal'
    assert report['shared_buffer_peak_mb']<=report['gpu_buffer_limit_mb']


@pytest.mark.parametrize('value', (-26.,-9.,-2.473931,0.,1.5))
def test_centered_gpu_fir_keeps_constant_fields_exact(value):
    require_metal()
    source=np.full((31,43),value,np.float32)
    for sigma in (.4,4,12,16):
        np.testing.assert_array_equal(accel.presence_gaussian(source,sigma),source)


def test_shared_pool_reuses_and_drops_scratch_to_keep_readouts_within_limit():
    require_metal(budget_mb=20)
    source=np.random.default_rng(17).uniform(-9,0,(256,250)).astype(np.float32)
    actual=accel.presence_gaussian(source,4)
    np.testing.assert_allclose(actual,gaussian_filter(source,4,mode='nearest'),atol=2e-6,rtol=0)
    context=accel._context
    gaussian_allocation=context.lib.lr_metal_allocated(context.handle)
    assert gaussian_allocation==source.size*29
    rgb=np.full((*source.shape,3),.18,np.float32)
    pixels,gamut,readouts=accel.grade_output(rgb,Recipe(),'srgb',capture_readouts=True)
    assert accel._context is context
    # 53 B/pixel would exceed 3 MiB; the no-longer-needed scratch plane must drop.
    assert context.lib.lr_metal_allocated(context.handle)==source.size*49
    assert np.isfinite(readouts).all() and pixels.shape==rgb.shape and not gamut.any()
    report=accel.report()
    assert report['metal_readout_tiles']==1 and report['cpu_tiles']==0
    assert report['shared_buffer_peak_mb']<=3
    accel.presence_gaussian(source,12)
    assert context.lib.lr_metal_allocated(context.handle)==source.size*29


def test_capacity_and_large_radius_use_exact_cpu_without_creating_gpu_context():
    accel.configure('metal',budget_mb=3)
    source=np.random.default_rng(29).uniform(-9,0,(128,256)).astype(np.float32)
    expected=gaussian_filter(source,4,mode='nearest')
    np.testing.assert_array_equal(accel.presence_gaussian(source,4),expected)
    np.testing.assert_array_equal(accel.presence_gaussian(source,17),gaussian_filter(source,17,mode='nearest'))
    assert accel._context is None
    assert accel.report()['presence_cpu_gaussian_filters']==2
    assert accel.report()['presence_gaussian_backend']=='cpu'


def test_failed_gpu_filter_uses_unmodified_cpu_input_and_suppresses_repeated_failure(monkeypatch):
    source=np.random.default_rng(9).uniform(-9,0,(128,256)).astype(np.float32)
    before=source.copy();attempts=[]
    class Failed:
        def gaussian(self,a,weights,radius):
            attempts.append(radius)
            # Failed private GPU work is not an output, even after dirty buffers.
            discarded=np.full_like(a,999)
            raise RuntimeError('injected command failure')
        def close(self):
            pass
    accel.configure('auto')
    monkeypatch.setattr(accel,'_context',Failed())
    for _ in range(2):
        np.testing.assert_array_equal(accel.presence_gaussian(source,4),gaussian_filter(source,4,mode='nearest'))
    assert attempts==[16] and not accel._disabled
    np.testing.assert_array_equal(source,before)
    assert accel._stats['presence_cpu_gaussian_filters']==2
    assert accel._stats['presence_metal_gaussian_filters']==0


def test_c_abi_rejected_requests_never_touch_caller_output():
    require_metal()
    source=np.full((17,19),-3,np.float32)
    accel.presence_gaussian(source,4)
    context=accel._context;lib=context.lib
    weights,radius=accel._gaussian_weights(4)
    output=np.full_like(source,123);before=output.copy();error=C.create_string_buffer(4096)
    for width,height,requested_radius,count in ((19,17,65,131),(0,17,radius,len(weights)),
                                               (19,17,radius,len(weights)-1),(2**32-1,2**32-1,radius,len(weights))):
        result=lib.lr_metal_gaussian_v1(context.handle,source.ctypes.data,output.ctypes.data,
            width,height,weights.ctypes.data,requested_radius,count,error,len(error))
        assert result!=0
        np.testing.assert_array_equal(output,before)
    root=Path(accel.__file__).parent
    old=lib.lr_metal_create((root/'grade.metal').read_bytes(),accel._limit,error,len(error))
    assert old
    try:
        result=lib.lr_metal_gaussian_v1(old,source.ctypes.data,output.ctypes.data,19,17,
            weights.ctypes.data,radius,len(weights),error,len(error))
        assert result!=0 and b'unavailable' in error.value
        np.testing.assert_array_equal(output,before)
    finally:
        lib.lr_metal_destroy(old)


def test_completed_preview_hit_reports_unused_filters_without_worker(tmp_path,monkeypatch):
    require_metal()
    path=tmp_path/'source.png';Image.new('RGB',(480,320),(70,110,150)).save(path)
    original=path.read_bytes()
    service=Service(tmp_path/'catalog',presets_root=tmp_path/'presets')
    try:
        service.dispatch('queue_control',{'action':'pause'})
        service.dispatch('settings',{'compute_backend':'metal'})
        service.dispatch('import_photos',{'paths':[str(path)]})
        saved=service.dispatch('edit_photo',{'photo_id':1,'expected_revision':0,
            'patch':{'texture':45,'clarity':30,'dehaze':35}})
        options={'photo_id':1,'expected_revision':saved['revision'],'include_before':False}
        first=service.dispatch('preview_photo',options)
        assert first['worker_spawned'] and first['processing']['presence_metal_gaussian_passes']>0
        def forbidden(_):
            pytest.fail('Completed preview started a worker')
        monkeypatch.setattr(service,'run_worker',forbidden)
        with service.image_lock:
            hit=service.dispatch('preview_photo',options)
        assert hit['preview_cache_hit'] and not hit['worker_spawned']
        assert hit['preview']==first['preview']
        report=hit['processing']
        assert report['backend']=='cache' and report['presence_gaussian_backend']=='unused'
        assert report['presence_other_operations_backend']=='unused'
        assert all(report[key]==0 for key in ('presence_metal_gaussian_filters',
            'presence_metal_gaussian_passes','presence_cpu_gaussian_filters',
            'presence_gaussian_gpu_seconds','presence_gaussian_dispatch_seconds',
            'gpu_seconds','dispatch_seconds','initialization_seconds','worker_seconds'))
        assert path.read_bytes()==original
    finally:
        service.close()


@pytest.mark.parametrize('orientation', (0,1,4,7))
@pytest.mark.parametrize('sign', (-1,1))
def test_gpu_gaussian_complete_renderer_preserves_reference_and_viewport(orientation,sign):
    source=np.random.default_rng(12).uniform(.02,.7,(271,293,3)).astype(np.float32)
    recipe=Recipe(texture=80*sign,clarity=70*sign,dehaze=40*sign,luma_noise=45,chroma_noise=60,
                  sharpen=100,sharpen_radius=3,blue_lum=25,
                  masks=[{'kind':'radial','exposure':.25}])
    plan=OrientedPlan(RenderPlan(source,recipe),orientation)
    expected,_=render_strip(plan,0,0,plan.width,plan.height)
    require_metal()
    actual,_=render_strip(plan,0,0,plan.width,plan.height)
    np.testing.assert_allclose(actual,expected,atol=1e-4,rtol=2e-5)
    np.testing.assert_allclose(decode(actual),decode(expected),atol=1e-5,rtol=0)
    detail,_=render_strip(plan,73,91,87,65)
    np.testing.assert_allclose(detail,actual[91:156,73:160],atol=3e-6,rtol=0)
    assert np.max(abs(np.rint(detail*65535)-np.rint(actual[91:156,73:160]*65535)))<=1
    report=accel.report()
    assert report['presence_metal_gaussian_passes']>0 and report['metal_output_tiles']>0
    assert report['shared_buffer_peak_mb']<=report['gpu_buffer_limit_mb']
