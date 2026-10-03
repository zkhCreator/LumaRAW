"""Presence direction/frequency behavior, strip agreement and durable workflows.

Generated linear images establish LumaRAW's model and bounded spatial support.
Catalog tests verify additive old JSON, selected presets/sync, undo, frozen jobs
and original safety. Neither these nor optional Metal establish Adobe pixels.
"""
import hashlib
import json
import os

import numpy as np
from PIL import Image
import pytest

from lumaraw import accelerators, presence
from lumaraw.catalog import Catalog
from lumaraw.color import decode
from lumaraw.library import backup_catalog, restore_catalog, save_recipe, load_recipe
from lumaraw.model import Recipe
from lumaraw.render import RenderPlan, OrientedPlan, detail_filter, detail_support, render_strip
from lumaraw.service import Service, ConflictError

KEYS = ('texture', 'clarity', 'dehaze')


@pytest.mark.parametrize('key', KEYS)
def test_additive_defaults_and_strict_finite_ranges(key):
    old = Recipe.parse({'version': 1, 'exposure': .25})
    assert all(getattr(old, name) == 0 for name in KEYS)
    for value in (-100, 0, 100):
        assert getattr(Recipe.parse({key: value}), key) == value
    for value in (True, '1', float('nan'), float('inf'), -100.01, 100.01):
        with pytest.raises(ValueError):
            Recipe.parse({key: value})


def test_zero_is_exact_bypass_and_allocates_no_rgb_copy():
    pixels = np.random.default_rng(41).uniform(-.02, 2, (9, 11, 3)).astype(np.float32)
    original = pixels.copy()
    assert presence.apply(pixels, Recipe()) is pixels
    np.testing.assert_array_equal(pixels, original)


def amplitude(period, key, amount, scale=1):
    x = np.arange(1024, dtype=np.float32)
    wave = .18 * np.exp2(.08 * np.cos(2 * np.pi * x / period))
    pixels = np.broadcast_to(wave[None, :, None], (9, 1024, 3)).copy()
    adjusted = presence.apply(pixels, Recipe(**{key: amount}), scale)
    return np.std(np.log2(adjusted[4, 128:-128, 0])) / np.std(np.log2(wave[128:-128]))


@pytest.mark.parametrize('key', ('texture', 'clarity'))
def test_positive_enhances_negative_smooths_medium_detail(key):
    assert amplitude(16, key, 100) > 1.4
    assert amplitude(16, key, -100) < .6


def test_texture_distinguishes_finest_noise_and_broad_tones():
    assert abs(amplitude(2, 'texture', 100) - 1) < .1
    assert abs(amplitude(256, 'texture', 100) - 1) < .01
    assert amplitude(64, 'clarity', 100) > amplitude(64, 'texture', 100) + .3
    # A half-size decode represents the same source frequency at half the period.
    # Discrete small-radius kernels approximate source-scale equivalence.
    assert abs(amplitude(8, 'texture', 100, .5) - amplitude(16, 'texture', 100)) < .025


@pytest.mark.parametrize('key', ('texture', 'clarity'))
def test_local_contrast_preserves_channel_ratios_and_constant_neutrals(key):
    x = np.arange(256, dtype=np.float32)
    wave = .18 * np.exp2(.15 * np.cos(x / 3))
    pixels = np.broadcast_to(wave[None, :, None] * np.array([1.2, 1, .8], np.float32), (17, 256, 3)).copy()
    original = pixels.copy()
    adjusted = presence.apply(pixels, Recipe(**{key: 100}))
    np.testing.assert_allclose(adjusted[:, :, 0] / adjusted[:, :, 1], 1.2, atol=3e-7)
    np.testing.assert_allclose(adjusted[:, :, 2] / adjusted[:, :, 1], .8, atol=3e-7)
    assert np.max(abs(adjusted - original)) > .01
    constant = np.full((17, 19, 3), .18, np.float32)
    np.testing.assert_allclose(presence.apply(constant.copy(), Recipe(**{key: -100})), constant, atol=2e-8)


def test_dehaze_restores_veiled_contrast_and_negative_adds_veil():
    x = np.arange(256, dtype=np.float32)
    clear = np.broadcast_to((x % 16 / 15 * .6)[None, :, None], (64, 256, 3)).copy()
    hazy = clear * .55 + .45
    restored = presence.apply(hazy.copy(), Recipe(dehaze=100))
    added = presence.apply(hazy.copy(), Recipe(dehaze=-100))
    assert restored.std() > hazy.std() * 1.5
    assert np.mean(abs(restored - clear)) < np.mean(abs(hazy - clear)) * .3
    assert added.std() < hazy.std() * .5 and added.min() > hazy.min()
    white = np.ones((17, 19, 3), np.float32)
    np.testing.assert_array_equal(presence.apply(white, Recipe(dehaze=100)), white)


@pytest.mark.parametrize('amount', (-100, 100))
def test_extremes_are_finite_for_black_highlights_and_saturated_pixels(amount):
    pixels = np.random.default_rng(9).uniform(0, 8, (19, 37, 3)).astype(np.float32)
    pixels[0] = 0
    adjusted = presence.apply(pixels, Recipe(texture=amount, clarity=amount, dehaze=amount))
    assert adjusted.dtype == np.float32 and np.isfinite(adjusted).all()
    assert adjusted.min() >= 0


@pytest.mark.parametrize('orientation', range(8))
@pytest.mark.parametrize('scale', (.25, .5, 1))
def test_combined_filters_strips_detail_and_orientation_match_full(orientation, scale):
    pixels = np.random.default_rng(12).uniform(.02, .8, (269, 293, 3)).astype(np.float32)
    recipe = Recipe(texture=75, clarity=-65, dehaze=55, luma_noise=60, chroma_noise=45,
                    defringe=40, sharpen=110, sharpen_radius=3, detail_protect=20,
                    exposure=.15, blue_sat=-12, distortion=5, perspective_v=8)
    accelerators.configure('cpu')
    try:
        base = RenderPlan(pixels, recipe)
        base.pixel_scale = scale
        plan = OrientedPlan(base, orientation)
        whole, _ = render_strip(plan, 0, 0, plan.width, plan.height, output_sharpen=20)
        strips = np.concatenate([render_strip(plan, 0, y, plan.width, min(37, plan.height-y),
                                               output_sharpen=20)[0] for y in range(0, plan.height, 37)])
        # Existing pointwise color matrices may round FP32 tail lanes differently
        # for a one-column edge tile. Neither encoding may differ by >1 code value.
        np.testing.assert_allclose(strips, whole, atol=3e-6, rtol=0)
        for maximum in (255,65535):
            assert np.max(abs(np.rint(strips*maximum)-np.rint(whole*maximum))) <= 1
        detail, _ = render_strip(plan, 73, 91, 87, 65, output_sharpen=20)
        np.testing.assert_allclose(detail, whole[91:156, 73:160], atol=3e-6, rtol=0)
    finally:
        accelerators.configure('auto')


def test_halo_is_bounded_to_requested_strip_dependencies():
    pixels = np.ones((1200, 1300, 3), np.float32) * .18
    recipe = Recipe(texture=100, clarity=100, dehaze=100, chroma_noise=100,
                    luma_noise=100, sharpen=100, sharpen_radius=3)
    plan = RenderPlan(pixels, recipe)
    sampled = []
    original = plan.sample
    def capture(x, y, w, h):
        sampled.append((x, y, w, h))
        return original(x, y, w, h)
    plan.sample = capture
    accelerators.configure('cpu')
    try:
        render_strip(plan, 500, 500, 64, 128)
    finally:
        accelerators.configure('auto')
    assert len(sampled) == 1
    assert sampled[0][2] < 250 and sampled[0][3] < 320
    assert sampled[0][2] * sampled[0][3] < pixels.shape[0] * pixels.shape[1] / 20


@pytest.mark.parametrize('scale', (.25,.5,1))
@pytest.mark.parametrize('sign', (-1,1))
def test_spatial_prefix_exactly_matches_full_before_pointwise_color_rounding(scale,sign):
    pixels = np.random.default_rng(72).uniform(.01,.8,(271,301,3)).astype(np.float32)
    recipe = Recipe(texture=80*sign,clarity=90*sign,dehaze=60*sign,
                    luma_noise=75,chroma_noise=80,sharpen=120,sharpen_radius=3)
    plan = RenderPlan(pixels,recipe);plan.pixel_scale=scale
    whole = detail_filter(plan.sample(0,0,plan.width,plan.height),recipe,scale,30)
    halo = detail_support(recipe,scale,30)
    for x,y,w,h in ((0,0,37,41),(264,230,37,41),(117,108,51,63)):
        left,top=max(0,x-halo),max(0,y-halo)
        right,bottom=min(plan.width,x+w+halo),min(plan.height,y+h+halo)
        tile=detail_filter(plan.sample(left,top,right-left,bottom-top),recipe,scale,30)
        np.testing.assert_array_equal(tile[y-top:y-top+h,x-left:x-left+w],whole[y:y+h,x:x+w])


def test_presence_before_actual_metal_grade_matches_cpu():
    if os.uname().sysname != 'Darwin':
        pytest.skip('Metal requires macOS')
    pixels = np.random.default_rng(6).uniform(.03, .7, (129, 131, 3)).astype(np.float32)
    recipe = Recipe(texture=80, clarity=-50, dehaze=45, exposure=.3, blue_lum=15)
    plan = RenderPlan(pixels, recipe)
    accelerators.configure('cpu')
    reference, _ = render_strip(plan, 0, 0, plan.width, plan.height)
    try:
        accelerators.configure('metal')
        actual, _ = render_strip(plan, 0, 0, plan.width, plan.height)
        report = accelerators.report()
        if not report['metal_grade_tiles']:
            if os.getenv('LUMARAW_REQUIRE_METAL'):
                pytest.fail('Actual Metal grading is required')
            pytest.skip('Actual Metal dispatch unavailable')
        assert report['backend'] == 'metal'
        np.testing.assert_allclose(actual, reference, atol=1e-4, rtol=0)
        np.testing.assert_allclose(decode(actual), decode(reference), atol=1e-5, rtol=0)
    finally:
        accelerators.configure('auto')


def test_presence_presets_sync_undo_frozen_exports_and_old_json(tmp_path):
    service = Service(tmp_path/'catalog', presets_root=tmp_path/'presets')
    service.dispatch('queue_control', {'action':'pause'})
    paths = [tmp_path/f'{i}.png' for i in range(3)]
    for path in paths:
        Image.new('RGB', (40, 30), (80, 110, 150)).save(path)
    hashes = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
    patch = {'texture':40, 'clarity':-30, 'dehaze':60}
    try:
        service.dispatch('import_photos', {'paths':list(map(str, paths))})
        schema = service.dispatch('recipe_schema')
        assert schema['groups']['Presence'] == list(KEYS)
        assert all(schema['defaults'][key] == 0 and tuple(schema['limits'][key]) == (-100,100) for key in KEYS)
        source = service.dispatch('edit_photo', {'photo_id':1, 'expected_revision':0, 'patch':patch})
        service.dispatch('enqueue_exports', {'photo_ids':[1], 'destination':str(tmp_path/'exports'),
                                           'format':'tiff16', 'request_key':'presence'})
        preset = service.dispatch('save_develop_preset', {'photo_id':1, 'expected_photo_revision':source['revision'],
            'fields':list(KEYS), 'name':'Presence only', 'group_name':'Tests',
            'expected_revision':service.dispatch('list_develop_presets')['revision']})
        service.dispatch('edit_photo', {'photo_id':2, 'expected_revision':0, 'patch':{'exposure':1,'blue_sat':22}})
        service.dispatch('apply_develop_preset', {'preset_id':preset['preset_id'], 'expected_revision':preset['revision'],
            'targets':[{'photo_id':2,'expected_revision':1}]})
        target = service.dispatch('get_photo', {'photo_id':2})
        assert all(target['recipe'][key] == value for key,value in patch.items())
        assert target['recipe']['exposure'] == 1 and target['recipe']['blue_sat'] == 22
        with pytest.raises(ConflictError):
            service.dispatch('sync_photos', {'source_id':1,'groups':['Presence'],
                'targets':[{'photo_id':2,'expected_revision':2},{'photo_id':3,'expected_revision':99}]})
        assert service.dispatch('get_photo', {'photo_id':2})['revision'] == 2
        undo = service.dispatch('undo_photo', {'photo_id':2,'expected_revision':2})
        assert all(undo['recipe'][key] == 0 for key in KEYS)
        service.dispatch('sync_photos', {'source_id':1,'groups':['Presence'],
            'targets':[{'photo_id':2,'expected_revision':undo['revision']}]})
        service.dispatch('edit_photo', {'photo_id':1,'expected_revision':1,'patch':{'texture':-90}})
        with service.catalog() as catalog:
            frozen = json.loads(catalog.db.execute('SELECT recipe FROM jobs').fetchone()[0])
            assert all(frozen[key] == value for key,value in patch.items())
            save_recipe(tmp_path/'presence.lumarecipe', catalog.recipe(1))
            assert load_recipe(tmp_path/'presence.lumarecipe',catalog.root).texture == -90
            backup_catalog(catalog,tmp_path/'backup.sqlite')
            legacy = catalog.recipe(1).dict()
            for key in KEYS:
                legacy.pop(key)
            catalog.db.execute('UPDATE photos SET recipe=? WHERE id=1', (json.dumps(legacy),))
            catalog.db.commit()
        restored = Catalog(restore_catalog(tmp_path/'backup.sqlite',tmp_path/'restored'))
        try:
            assert restored.recipe(2).dict() | patch == restored.recipe(2).dict()
        finally:
            restored.close()
        target = service.dispatch('get_photo', {'photo_id':2})
        service.dispatch('sync_photos', {'source_id':1,'groups':['Presence'],
            'targets':[{'photo_id':2,'expected_revision':target['revision']}]})
        assert all(service.dispatch('get_photo', {'photo_id':2})['recipe'][key] == 0 for key in KEYS)
        assert service.dispatch('get_photo', {'photo_id':1})['recipe'] == legacy
        assert hashes == [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
    finally:
        service.close()
