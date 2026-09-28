"""Regression evidence for originals safety, color math, precision and catalog bounds.

These tests verify observable file/pixel behavior, not Nikon colorimetric accuracy.
RAW integration tests use a caller-supplied real NEF fixture and skip without it.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
from PIL import Image, ImageCms
import pytest
import rawpy
import tifffile

from lumaraw.catalog import Catalog, walk_images
from lumaraw.imaging import (PROPHOTO_TO_SRGB, SRGB_TO_PROPHOTO, develop_tile, srgb_decode,
    srgb_encode, relative_wb, geometry, export_image, estimate_memory_mb, check_budget,
    make_preview, load_source, trim_cache)
from lumaraw.model import Recipe

@pytest.fixture
def raster(tmp_path):
    rng = np.random.default_rng(12)
    data = rng.integers(10, 235, (72, 96, 3), dtype=np.uint8)
    path = tmp_path / 'color-test-\U0001f4f7.png'
    Image.fromarray(data).save(path, icc_profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes())
    return path, data


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_srgb_transfer_roundtrip():
    x = np.linspace(0, 1, 65536, dtype=np.float32)
    np.testing.assert_allclose(srgb_encode(srgb_decode(x)), x, atol=3e-7)


def test_libraw_d65_matrix_inverse_and_neutral():
    np.testing.assert_allclose(PROPHOTO_TO_SRGB @ SRGB_TO_PROPHOTO, np.eye(3), atol=2e-7)
    neutral = np.full((3, 3, 3), .18, dtype=np.float32)
    output = develop_tile(neutral, Recipe())
    assert np.ptp(output[0, 0]) < 1e-5


def test_exposure_is_linear_ev():
    a = np.full((4, 4, 3), .1, dtype=np.float32)
    neutral = srgb_decode(develop_tile(a, Recipe()))
    raised = srgb_decode(develop_tile(a, Recipe(exposure=1)))
    np.testing.assert_allclose(raised, neutral * 2, atol=1e-6)


def test_camera_wb_is_used_and_relative_adjustment_is_not_kelvin():
    np.testing.assert_allclose(relative_wb([576, 256, 432, 0], 0, 0), [2.25, 1, 1.6875, 1])
    warm = relative_wb([576, 256, 432, 256], 60, 0)
    assert warm[0] > 2.25 and warm[2] < 1.6875
    with pytest.raises(ValueError):
        relative_wb([0, 0, 0, 0], 0, 0)


@pytest.mark.parametrize('data', [{'exposure': float('nan')}, {'exposure': 8}, {'rotation': 20}, {'crop': 'free'}, {'version': 99}, {'unknown': 1}])
def test_invalid_recipes_are_rejected(data):
    with pytest.raises(ValueError):
        Recipe.parse(data)


def test_raster_identity_keeps_icc_color(raster):
    path, original = raster
    linear, meta = load_source(path, Recipe(), 512)
    developed = np.rint(develop_tile(linear, Recipe()) * 255).astype(np.uint8)
    assert np.abs(developed.astype(int) - original).max() <= 1
    assert meta['warnings'] == []


def test_tiff16_precision_icc_and_no_source_overwrite(tmp_path, raster):
    path, original = raster
    before = digest(path)
    result = export_image(path, Recipe(), tmp_path, 'tiff16', 512, 1)
    again = export_image(path, Recipe(), tmp_path, 'tiff16', 512, 1)
    assert result['output'] != again['output']
    assert digest(path) == before
    with tifffile.TiffFile(result['output']) as tiff:
        a = tiff.asarray()
        assert a.dtype == np.uint16
        assert a.shape == original.shape
        assert tiff.pages[0].tags[34675].value[36:40] == b'acsp'
        assert 270 not in tiff.pages[0].tags  # Internal recipes/paths never become image descriptions.
    assert not list(tmp_path.glob('.lumaraw-*'))


def test_jpeg_crop_rotate_and_icc(tmp_path, raster):
    path, _ = raster
    result = export_image(path, Recipe(rotation=90, crop='1:1'), tmp_path, 'jpeg', 512, 2)
    with Image.open(result['output']) as img:
        assert img.size == (72, 72)
        assert img.info['icc_profile'][36:40] == b'acsp'
    assert not list(tmp_path.glob('.lumaraw-*'))


def test_failed_export_cleans_partials(tmp_path):
    broken = tmp_path / 'broken.NEF'
    broken.write_bytes(b'not a raw image')
    with pytest.raises(Exception):
        export_image(broken, Recipe(), tmp_path, 'tiff16', 512, 88)
    assert not list(tmp_path.glob('.lumaraw-*'))
    assert broken.read_bytes() == b'not a raw image'


def test_reject_high_depth_raster_instead_of_silent_truncation(tmp_path):
    p = tmp_path / '16bit.tif'
    tifffile.imwrite(p, np.full((32, 32, 3), 12000, dtype=np.uint16), photometric='rgb')
    with pytest.raises(ValueError, match='16-bit TIFF'):
        load_source(p, Recipe(), 512)
    p = tmp_path / '16bit.png'
    Image.fromarray(np.full((32, 32), 12000, dtype=np.uint16)).save(p)
    with pytest.raises(ValueError, match='high-bit-depth PNG'):
        load_source(p, Recipe(), 512)


def test_memory_admission():
    assert estimate_memory_mb(8256, 5504) > 3000
    with pytest.raises(MemoryError):
        check_budget(8256, 5504, 1024)


def test_cache_is_bounded(tmp_path):
    cache = tmp_path / 'cache'
    cache.mkdir()
    for i in range(8):
        (cache / f'{i}.npy').write_bytes(b'0' * 300_000)
    pinned = cache / '0.npy'
    trim_cache(cache, maximum_mb=1, keep=[pinned])
    assert sum(p.stat().st_size for p in cache.iterdir()) <= 1024 ** 2
    assert pinned.exists()


def test_history_queue_snapshot_recovery_and_pagination(tmp_path, raster):
    p, _ = raster
    catalog = Catalog(tmp_path / 'catalog')
    assert catalog.import_paths([p, p]) == (1, 1)
    photo_id = catalog.page()[0]['id']
    catalog.edit(photo_id, Recipe(exposure=1))
    catalog.enqueue([photo_id], tmp_path / 'export', 'jpeg')
    catalog.edit(photo_id, Recipe(exposure=2))
    job = catalog.next_job()
    assert json.loads(job['recipe'])['exposure'] == 1
    assert catalog.undo(photo_id).exposure == 1
    catalog.recover_jobs()
    assert catalog.jobs()[0]['state'] == 'interrupted'
    assert catalog.next_job() is None
    catalog.retry_failed()
    assert catalog.next_job()['id'] == job['id']
    # A large catalog must still return no more than one page.
    with catalog.db:
        catalog.db.executemany('INSERT INTO photos(path,name,bytes,mtime,recipe,created) VALUES(?,?,?,?,?,?)',
            ((f'/fixture/{i}.nef', f'{i}.nef', 1, 1, json.dumps(Recipe().dict()), i) for i in range(10000)))
    assert catalog.count() == 10001
    assert len(catalog.page(limit=10000)) == 60
    assert len(catalog.page(offset=10000)) == 1
    catalog.close()


def test_import_skips_symlinks(tmp_path, raster):
    p, _ = raster
    link = tmp_path / 'linked.png'
    link.symlink_to(p)
    catalog = Catalog(tmp_path / 'catalog')
    assert catalog.import_paths([link, p]) == (1, 1)
    catalog.close()


@pytest.fixture
def nef():
    path = os.environ.get('LUMARAW_TEST_NEF')
    if not path:
        pytest.skip('Set LUMARAW_TEST_NEF to a real NEF fixture')
    return Path(path).resolve(strict=True)


def test_real_nef_preview_and_full_16bit_export(tmp_path, nef):
    before = digest(nef)
    preview = make_preview(nef, Recipe(exposure=.5), tmp_path / 'cache', 4096)
    assert max(preview['width'], preview['height']) <= 1680
    result = export_image(nef, Recipe(exposure=.5), tmp_path, 'tiff16', 4096, 7)
    with tifffile.TiffFile(result['output']) as tiff:
        assert tiff.pages[0].dtype == np.dtype('uint16')
        assert tiff.pages[0].shape[0] > preview['height']
        assert 34675 in tiff.pages[0].tags
    assert digest(nef) == before


def test_real_nef_color_matrix_matches_libraw_reference(nef):
    params = dict(use_camera_wb=True, output_bps=16, gamma=(1, 1), no_auto_bright=True, half_size=True)
    with rawpy.imread(str(nef)) as raw:
        reference = raw.postprocess(output_color=rawpy.ColorSpace.sRGB, **params)
    with rawpy.imread(str(nef)) as raw:
        wide = raw.postprocess(output_color=rawpy.ColorSpace.ProPhoto, **params)
    converted = wide.astype(np.float32) @ PROPHOTO_TO_SRGB.T
    # Compare only colors unclipped in both representations; gamut-clipped data is irreversible.
    mask = ((wide > 100) & (wide < 65400)).all(axis=2) & ((reference > 100) & (reference < 65400)).all(axis=2)
    error = np.abs(converted[mask] - reference[mask])
    assert mask.sum() > 10000
    assert float(error.mean()) < 2.0  # 16-bit code values, rounding in two matrix paths.
    assert float(np.quantile(error, .99)) < 5.0
