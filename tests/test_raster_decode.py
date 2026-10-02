"""Pixel and preprocessing regressions for strip-wise 8-bit raster conversion.

Purpose: prove the bounded conversion preserves the legacy float32
decode and load_source preprocessing behavior. Inputs are generated sRGB rasters;
outputs are numeric/profile/orientation assertions. It does not measure RSS or
claim RAW-decoder or desktop behavior.
"""
import hashlib
import io

import numpy as np
from PIL import Image, ImageCms, ImageOps
import pytest

from lumaraw.imaging import (
    PREVIEW_EDGE,
    SRGB_DECODE_U8,
    SRGB_TO_PROPHOTO,
    _raster_to_linear_prophoto,
    load_source,
    srgb_decode,
)
from lumaraw.model import Recipe


def _legacy_conversion(rgb_image, recipe):
    pixels = srgb_decode(np.asarray(rgb_image, dtype=np.float32) / 255) @ SRGB_TO_PROPHOTO.T
    pixels *= np.array([
        2 ** (recipe.temperature / 120),
        2 ** (-recipe.tint / 180),
        2 ** (-recipe.temperature / 120),
    ], dtype=np.float32)
    return pixels


def _legacy_load_source(path, recipe, preview):
    with Image.open(path) as opened:
        icc = opened.info.get('icc_profile')
        image = ImageOps.exif_transpose(opened)
        decoded_size = image.size
        if preview:
            image.thumbnail((PREVIEW_EDGE, PREVIEW_EDGE), Image.Resampling.LANCZOS)
        if icc:
            image = ImageCms.profileToProfile(
                image,
                ImageCms.ImageCmsProfile(io.BytesIO(icc)),
                ImageCms.createProfile('sRGB'),
                outputMode='RGB',
            )
        else:
            image = image.convert('RGB')
        pixels = _legacy_conversion(image, recipe)
        metadata = {
            'width': opened.width,
            'height': opened.height,
            'kind': opened.format,
            'decoded_width': decoded_size[0],
            'decoded_height': decoded_size[1],
            'profile': 'ICC → sRGB → linear ProPhoto D65' if icc else 'Assumed sRGB → linear ProPhoto D65',
            'input': 'Rendered image (not RAW)',
            'warnings': [] if icc else ['No ICC profile; interpreted as sRGB'],
        }
    return pixels, metadata


def test_u8_decode_lut_covers_all_codes_and_matches_legacy_float32():
    codes = np.arange(256, dtype=np.float32) / 255
    np.testing.assert_array_equal(SRGB_DECODE_U8, srgb_decode(codes))
    assert not SRGB_DECODE_U8.flags.writeable

    yy, xx = np.indices((257, 256), dtype=np.uint16)
    grid = ((xx + 37 * yy) % 256).astype(np.uint8)
    rgb = np.stack((grid, np.flipud(grid), np.roll(grid, 5, axis=1)), axis=2)
    image = Image.fromarray(rgb)
    recipe = Recipe(temperature=23, tint=-17)

    actual = _raster_to_linear_prophoto(image, recipe.temperature, recipe.tint)
    expected = _legacy_conversion(image, recipe)

    assert actual.dtype == np.float32
    assert actual.shape == (257, 256, 3)
    np.testing.assert_array_equal(actual, expected)


@pytest.mark.parametrize('orientation', range(1, 9))
@pytest.mark.parametrize('with_icc', (False, True))
@pytest.mark.parametrize('preview', (False, True))
def test_load_source_keeps_all_exif_orientations_and_icc_semantics(
    tmp_path, orientation, with_icc, preview
):
    height, width = 31, 47
    yy, xx = np.indices((height, width), dtype=np.uint16)
    rgb = np.stack((xx * 5 % 256, yy * 7 % 256, (xx * 3 + yy * 11) % 256), axis=2).astype(np.uint8)
    path = tmp_path / f'oriented-color-{orientation}-{int(with_icc)}-{int(preview)}.jpg'
    exif = Image.Exif()
    exif[274] = orientation
    save_options = {'format': 'JPEG', 'quality': 95, 'subsampling': 0, 'exif': exif}
    if with_icc:
        save_options['icc_profile'] = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    Image.fromarray(rgb).save(path, **save_options)
    original_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    recipe = Recipe(temperature=12, tint=-8)

    actual, actual_meta = load_source(path, recipe, 512, preview=preview)
    expected, expected_meta = _legacy_load_source(path, recipe, preview=preview)

    assert actual.dtype == np.float32
    assert actual.shape == expected.shape
    np.testing.assert_array_equal(actual, expected)
    assert actual_meta == expected_meta
    assert actual_meta['width'] == width and actual_meta['height'] == height
    if orientation in (5, 6, 7, 8):
        assert actual_meta['decoded_width'] == height and actual_meta['decoded_height'] == width
    else:
        assert actual_meta['decoded_width'] == width and actual_meta['decoded_height'] == height
    assert actual_meta['profile'] == (
        'ICC → sRGB → linear ProPhoto D65' if with_icc else 'Assumed sRGB → linear ProPhoto D65'
    )
    assert actual_meta['warnings'] == ([] if with_icc else ['No ICC profile; interpreted as sRGB'])
    assert hashlib.sha256(path.read_bytes()).hexdigest() == original_digest


def test_load_source_keeps_preview_downsize_before_conversion(tmp_path):
    # Just over the preview edge but intentionally short: exercise actual
    # thumbnailing without multiplying a large fixture across the matrix above.
    height, width = 18, PREVIEW_EDGE + 37
    yy, xx = np.indices((height, width), dtype=np.uint16)
    rgb = np.stack((xx % 256, yy * 9 % 256, (xx + yy * 17) % 256), axis=2).astype(np.uint8)
    path = tmp_path / 'preview-resize.png'
    exif = Image.Exif()
    exif[274] = 6
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    Image.fromarray(rgb).save(path, format='PNG', exif=exif, icc_profile=profile)
    recipe = Recipe(temperature=-9, tint=13)

    actual, actual_meta = load_source(path, recipe, 512, preview=True)
    expected, expected_meta = _legacy_load_source(path, recipe, preview=True)

    assert actual.shape == (PREVIEW_EDGE, height, 3)
    assert actual.dtype == np.float32
    np.testing.assert_array_equal(actual, expected)
    assert actual_meta == expected_meta


@pytest.mark.parametrize('mode', ('L', 'RGBA'))
def test_load_source_preserves_existing_grayscale_and_alpha_rgb_conversion(tmp_path, mode):
    height, width = 13, 19
    yy, xx = np.indices((height, width), dtype=np.uint16)
    gray = ((xx * 11 + yy * 17) % 256).astype(np.uint8)
    if mode == 'L':
        image = Image.fromarray(gray)
    else:
        gray_wide = gray.astype(np.uint16)
        rgb = np.stack((gray_wide, (gray_wide * 3) % 256, (255 - gray_wide)), axis=2).astype(np.uint8)
        alpha = ((xx * 13 + yy * 7) % 256).astype(np.uint8)
        image = Image.fromarray(np.dstack((rgb, alpha)))
    path = tmp_path / f'{mode.lower()}-source.png'
    image.save(path, format='PNG')
    recipe = Recipe()

    actual, actual_meta = load_source(path, recipe, 512)
    expected, expected_meta = _legacy_load_source(path, recipe, preview=False)

    assert actual.shape == (height, width, 3)
    assert actual.dtype == np.float32
    np.testing.assert_array_equal(actual, expected)
    assert actual_meta == expected_meta
