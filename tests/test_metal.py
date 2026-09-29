"""GPU/CPU parity, dispatch failure and memory-boundary tests on real Metal.
Synthetic pixels cover numerical behavior, not Nikon colorimetric calibration.
Set LUMARAW_REQUIRE_METAL=1 on Apple Silicon to fail instead of skipping hardware.
"""
from dataclasses import replace
import os
import sys
from pathlib import Path
import numpy as np
import pytest
from lumaraw import accelerators as accel
from lumaraw.model import Recipe
from lumaraw.render import grade_tile,RenderPlan,render_strip
from lumaraw.color import to_output,decode

@pytest.fixture(autouse=True)
def reset_backend():
    accel.configure('cpu')
    yield
    accel.configure('auto')

def require_metal():
    if sys.platform!='darwin' or not Path(accel.__file__).with_name('libLumaMetal.dylib').exists():
        if os.environ.get('LUMARAW_REQUIRE_METAL'):pytest.fail('Required Metal backend missing')
        pytest.skip('Optional Metal library unavailable')
    accel.configure('metal')

RECIPES=[Recipe(),Recipe(exposure=.8,shadows=32,highlights=-45,whites=12,blacks=-9,contrast=27,saturation=13,vibrance=30),
         Recipe(exposure=-3,contrast=-85,saturation=-60,curve_shadows=20,curve_midtones=-10,curve_lights=25),
         Recipe(curve_points=[[0,0],[.09,.02],[.3,.45],[.7,.8],[1,1]],monochrome=True),
         Recipe(red_hue=21,red_sat=-33,orange_hue=-12,orange_sat=18,green_hue=11,green_sat=-28,blue_hue=-24,blue_sat=38),
         Recipe(yellow_hue=24,aqua_hue=-18,purple_hue=15,magenta_hue=-21,yellow_sat=-40,aqua_sat=35,purple_sat=60,magenta_sat=-30,
                red_lum=-25,orange_lum=45,yellow_lum=-15,green_lum=30,aqua_lum=-35,blue_lum=55,purple_lum=-50,magenta_lum=40),
         Recipe(monochrome=True,red_bw=-70,orange_bw=40,yellow_bw=60,green_bw=-45,aqua_bw=35,blue_bw=-55,purple_bw=65,magenta_bw=-20),
         Recipe(monochrome=True,red_hue=15,aqua_sat=-35,yellow_lum=-25,purple_lum=50,red_bw=60,blue_bw=-65),
         Recipe(curve_rgb_points=[[0,.05],[.3,.2],[.7,.8],[1,.98]],curve_red_points=[[0,0],[.4,.5],[1,1]],
                curve_green_points=[[.03,0],[.85,1]],curve_blue_points=[[0,.08],[.6,.5],[1,.95]]),
         Recipe(curve_rgb_points=[[0,1],[.25,.1],[.5,.8],[1,0]],curve_red_points=[[0,1],[1,0]],purple_lum=25,monochrome=True,red_bw=30),
         Recipe(camera_profile={'camera':'synthetic','matrix':[[1.05,-.02,.01],[.02,.98,-.01],[-.02,.04,1.02]],'space':'LibRaw-ProPhoto-D65-linear'})]

@pytest.mark.parametrize('space',['srgb','p3','adobe','prophoto'])
@pytest.mark.parametrize('recipe',RECIPES)
def test_real_metal_matches_cpu(recipe,space):
    require_metal()
    a=np.random.default_rng(910).uniform(-.03,1.5,(192,321,3)).astype(np.float32)
    gpu,gamut=accel.grade_output(a,recipe,space)
    cpu,reference=to_output(grade_tile(a,recipe),space)
    # Adobe RGB's pure gamma has an unbounded derivative at zero. Small
    # FP32 cancellation in saturated RGB can exceed the ordinary encoded tolerance
    # there. Bound both linear-light error and the exceptional dark code error;
    # all other pixels retain the original encoded tolerance. Real RAW 16-bit
    # export parity has its separate, stricter eight-code probe limit.
    dark=(cpu<.02)&(gpu<.02) if space=='adobe' else np.zeros(cpu.shape,bool)
    np.testing.assert_allclose(gpu[~dark],cpu[~dark],atol=1e-4,rtol=2e-5)
    if dark.any():
        assert np.max(np.abs(gpu[dark]-cpu[dark]))<=16/65535
        np.testing.assert_allclose(decode(gpu[dark],space),decode(cpu[dark],space),atol=1e-6,rtol=0)
    np.testing.assert_allclose(decode(gpu,space),decode(cpu,space),atol=1e-5,rtol=0)
    assert np.mean(np.abs(gpu-cpu))<2e-6
    assert np.count_nonzero(gamut!=reference)<=1
    assert accel.report()['metal_grade_tiles']==1

def test_masks_and_lut_preserve_cpu_grade_and_use_gpu_output(tmp_path):
    require_metal()
    import hashlib
    path=tmp_path/'identity.cube';path.write_text('LUT_3D_SIZE 2\n'+'\n'.join(f'{r} {g} {b}' for b in (0,1) for g in (0,1) for r in (0,1)))
    recipe=Recipe(lut={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()},masks=[{'kind':'radial','exposure':.4},{'kind':'brush','points':[[.1,.1],[.6,.8]],'saturation':20}])
    a=np.random.default_rng(4).uniform(.04,.8,(192,321,3)).astype(np.float32)
    gpu,gamut=accel.grade_output(a,recipe,'p3',40,70,800,600)
    cpu,reference=to_output(grade_tile(a,recipe,40,70,800,600),'p3')
    np.testing.assert_allclose(gpu,cpu,atol=2e-5)
    assert accel.report()['metal_output_tiles']==1
    assert accel.report()['backend']=='hybrid'

def test_gpu_strips_match_viewport_without_seams():
    require_metal()
    a=np.random.default_rng(5).uniform(.03,.7,(410,340,3)).astype(np.float32)
    plan=RenderPlan(a,Recipe(sharpen=70,curve_midtones=4,green_hue=7))
    whole,_=render_strip(plan,0,0,340,410)
    pieces=np.concatenate([render_strip(plan,0,y,340,min(97,410-y))[0] for y in range(0,410,97)])
    np.testing.assert_allclose(whole,pieces,atol=1e-6)
    view,_=render_strip(plan,40,110,170,150)
    np.testing.assert_allclose(view,whole[110:260,40:210],atol=1e-6)

def test_auto_falls_back_and_forced_metal_reports_failure(monkeypatch):
    def unavailable():raise RuntimeError('simulated GPU fault')
    monkeypatch.setattr(accel,'Metal',unavailable)
    a=np.full((192,128,3),.2,np.float32);r=Recipe(exposure=.4)
    accel.configure('auto');actual,_=accel.grade_output(a,r,'srgb')
    np.testing.assert_array_equal(actual,to_output(grade_tile(a,r))[0])
    assert accel.report()['backend']=='cpu' and 'simulated GPU fault' in accel.report()['fallback_reasons'][0]
    accel.configure('metal')
    with pytest.raises(RuntimeError,match='Metal requested but failed'):accel.grade_output(a,r,'srgb')

def test_small_tile_and_shared_buffer_limit_do_not_allocate_gpu(monkeypatch):
    def forbidden():raise AssertionError('GPU allocation not allowed')
    monkeypatch.setattr(accel,'Metal',forbidden)
    accel.configure('auto',budget_mb=1)
    accel.grade_output(np.ones((192,128,3),np.float32),Recipe(),'srgb')
    assert accel.report()['shared_buffer_peak_mb']==0
    assert 'tile_exceeds_bounded_gpu_buffer' in accel.report()['fallback_reasons']
    accel.configure('auto');accel.grade_output(np.ones((10,10,3),np.float32),Recipe(),'srgb')
    assert 'small_tile_uses_cpu' in accel.report()['fallback_reasons']

def test_gpu_failure_after_initialization_recomputes_from_original(monkeypatch):
    require_metal();a=np.full((192,128,3),.3,np.float32);r=Recipe(exposure=.3)
    accel.configure('auto');accel.grade_output(a,r,'srgb')
    def failure(*args):raise RuntimeError('command failed after dispatch')
    monkeypatch.setattr(accel._context,'run',failure)
    actual,_=accel.grade_output(a,r,'srgb')
    np.testing.assert_array_equal(actual,to_output(grade_tile(a,r))[0])
    assert any('after dispatch' in s for s in accel.report()['fallback_reasons'])

def test_old_adapter_layout_falls_back_before_allocating_or_dispatching(monkeypatch):
    monkeypatch.setattr(accel.C,'CDLL',lambda path:object())
    a=np.full((192,128,3),.3,np.float32)
    r=Recipe(curve_red_points=[[0,0],[.5,.6],[1,1]])
    accel.configure('auto')
    actual,_=accel.grade_output(a,r,'srgb')
    np.testing.assert_array_equal(actual,to_output(grade_tile(a,r))[0])
    assert 'outdated' in accel.report()['fallback_reasons'][0]
    assert accel.report()['shared_buffer_peak_mb']==0
    accel.configure('metal')
    with pytest.raises(RuntimeError,match='outdated'):accel.grade_output(a,r,'srgb')

def test_parameter_buffer_capacity_is_checked_in_python_and_c_abi():
    require_metal();ctx=accel.Metal()
    try:
        a=np.full((2,2,3),.3,np.float32)
        with pytest.raises(RuntimeError,match='parameter buffer'):
            ctx.run(a,np.zeros(256,np.float32))
        error=accel.C.create_string_buffer(256)
        # Capacity rejection precedes pointer reads, including a deliberately
        # absent parameter pointer. No GPU buffers are allocated for this call.
        result=ctx.lib.lr_metal_run_v2(ctx.handle,None,None,None,1,None,256,error,len(error))
        assert result!=0 and b'layout mismatch' in error.value
        assert ctx.lib.lr_metal_allocated(ctx.handle)==0
    finally:ctx.close()

def test_steep_curve_retains_exact_shape_through_reported_hybrid_path():
    require_metal()
    a=np.random.default_rng(54).uniform(.005,.6,(192,128,3)).astype(np.float32)
    r=Recipe(curve_red_points=[[0,0],[.25,.1],[.2501,.9],[1,1]])
    gpu,_=accel.grade_output(a,r,'prophoto')
    cpu,_=to_output(grade_tile(a,r),'prophoto')
    np.testing.assert_allclose(gpu,cpu,atol=2e-5)
    report=accel.report()
    assert report['backend']=='hybrid' and report['metal_output_tiles']==1
    assert report['fallback_reasons']==['steep_point_curve_uses_cpu_grade']
