"""Color-managed RAW development and strip-wise export, used only in child workers.

Purpose: decode read-only originals into linear ProPhoto RGB, apply float32 edits,
then convert LibRaw ProPhoto D65 with the exact inverse LibRaw matrix to sRGB.
Inputs: source path, validated recipe, memory budget. Outputs: cached previews or
new exports. Never write originals. Never substitute embedded JPEGs for RAW export.
Boundaries: LibRaw uses full-frame native allocations, not a streaming RAW decoder.
Memory preflight plus a parent RSS watchdog bound risk; 128-row edits avoid multiple
full-frame float buffers. Preview uses half-size demosaic, exports full resolution.
No claim of Nikon Picture Control equivalence or recovery of clipped sensor data.
"""
import gc
import hashlib
import io
import json
import math
import os
from pathlib import Path
import tempfile

import numpy as np
from PIL import Image, ImageCms, ImageOps
import rawpy
import tifffile

from .model import Recipe, RAW_EXTENSIONS
from .performance import stage
from .source_identity import PIPELINE_VERSION, fingerprint, cache_key, thumbnail_path, cached_thumbnail

PREVIEW_EDGE = 1680
TILE_ROWS = 128
SRGB_ICC = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
# LibRaw's "ProPhoto" is ProPhoto D65, NOT standard ICC ProPhoto D50.
# Use the exact inverse of LibRaw 0.22 src/tables/colorconst.cpp prophoto_rgb.
# Applying a generic D50 Bradford transform here would introduce a color cast.
SRGB_TO_PROPHOTO = np.array([[.529317, .330092, .140588],
                             [.098368, .873465, .028169],
                             [.016879, .117663, .865457]], dtype=np.float32)
PROPHOTO_TO_SRGB = np.linalg.inv(SRGB_TO_PROPHOTO).astype(np.float32)
LUMA = (np.array([.2126729, .7151522, .0721750], dtype=np.float32) @ PROPHOTO_TO_SRGB).astype(np.float32)


def estimate_memory_mb(width, height, raw=True, preview=False):
    # Conservative allocation model including native demosaic buffers and JPEG copy.
    # This is admission control, not a guarantee about LibRaw's internal allocator.
    per_pixel = (44 if preview else 80) if raw else 90
    return 180 + width * height * per_pixel / (1024 * 1024)


def check_budget(width, height, budget_mb, raw=True, preview=False):
    estimate = estimate_memory_mb(width, height, raw, preview)
    if width <= 0 or height <= 0 or width * height > 250_000_000:
        raise ValueError('Image dimensions are invalid or exceed the 250-million-pixel safety limit')
    if estimate > budget_mb:
        raise MemoryError(f'Estimated {estimate:.0f} MB exceeds the worker budget of {budget_mb} MB. Increase the budget or use a smaller photo.')


def srgb_decode(a):
    return np.where(a <= .04045, a / 12.92, ((a + .055) / 1.055) ** 2.4).astype(np.float32)


def srgb_encode(a):
    a = np.clip(a, 0, 1)
    return np.where(a <= .0031308, a * 12.92, 1.055 * a ** (1 / 2.4) - .055).astype(np.float32)


def relative_wb(as_shot, temperature, tint):
    wb = np.asarray(as_shot, dtype=np.float64)
    if wb.size != 4 or not np.isfinite(wb[:3]).all() or np.any(wb[:3] <= 0):
        raise ValueError('Camera white balance metadata is missing; camera-baseline rendering is unavailable')
    if wb[3] <= 0:
        wb[3] = wb[1]
    wb /= wb[1]
    wb *= [2 ** (temperature / 120), 2 ** (-tint / 180), 2 ** (-temperature / 120), 2 ** (-tint / 180)]
    return wb.tolist()


def resize_linear(image, edge):
    h, w = image.shape[:2]
    if max(h, w) <= edge:
        return image.astype(np.float32) / (65535 if image.dtype == np.uint16 else 1)
    scale = edge / max(h, w)
    size = (max(1, round(w * scale)), max(1, round(h * scale)))
    result = np.empty((size[1], size[0], 3), dtype=np.float32)
    for c in range(3):
        channel = image[:, :, c].astype(np.float32)
        if image.dtype == np.uint16:
            channel /= 65535
        result[:, :, c] = np.asarray(Image.fromarray(channel).resize(size, Image.Resampling.BILINEAR))
    return result


def raw_metadata(raw, path):
    sizes = raw.sizes
    meta = {'width': sizes.width, 'height': sizes.height, 'kind': Path(path).suffix.upper()[1:],
            'white_balance': list(raw.camera_whitebalance), 'black_levels': list(raw.black_level_per_channel),
            'white_level': raw.white_level, 'libraw': '.'.join(map(str, rawpy.libraw_version)),
            'profile': 'LibRaw camera matrix → linear ProPhoto D65 → sRGB',
            'input': 'RAW sensor data', 'warnings': []}
    try:
        # Header/EXIF only; never decode the NEF as a raster or read arbitrary files.
        with Image.open(path) as header:
            exif = header.getexif()
            meta['camera'] = str(exif.get(272, ''))[:100]
    except (OSError, ValueError):
        meta['camera'] = ''
    if not meta['camera']:
        try:
            with tifffile.TiffFile(path) as header:
                tag=header.pages[0].tags.get(272)
                if tag and isinstance(tag.value,str):meta['camera']=tag.value[:100]
        except (OSError,ValueError):pass
    # Current rawpy exposes optional metadata; older wheel versions may omit it.
    try:
        other = raw.other
        for key in ('iso_speed', 'shutter_speed', 'aperture', 'focal_length'):
            val = getattr(other, key, None)
            if val is not None:
                meta[key] = float(val)
    except AttributeError:
        pass
    return meta


def load_source(path, recipe, budget_mb, preview=False):
    """RAW returns linear ProPhoto uint16; raster returns linear ProPhoto float32."""
    if Path(path).suffix.lower() in RAW_EXTENSIONS:
        with rawpy.RawPy() as raw:
            raw.open_file(str(path))
            check_budget(raw.sizes.raw_width, raw.sizes.raw_height, budget_mb, preview=preview)
            with stage("raw_unpack"):
                raw.unpack()
            meta = raw_metadata(raw, path)
            wb = relative_wb(raw.camera_whitebalance, recipe.temperature, recipe.tint)
            with stage("raw_demosaic_color"):
                data = raw.postprocess(
                    user_wb=wb, use_camera_wb=False, use_auto_wb=False,
                    output_color=rawpy.ColorSpace.ProPhoto, output_bps=16,
                    gamma=(1, 1), no_auto_bright=True, bright=1,
                    half_size=preview, demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD,
                    highlight_mode=rawpy.HighlightMode.Blend if recipe.highlight_recovery else rawpy.HighlightMode.Clip)
        if preview:
            reduced = resize_linear(data, PREVIEW_EDGE)
            del data
            return reduced, meta
        return data, meta
    with Image.open(path) as opened:
        check_budget(opened.width, opened.height, budget_mb, raw=False, preview=preview)
        # Pillow can silently downconvert high-bit-depth TIFF RGB. Refuse that path.
        if Path(path).suffix.lower() in ('.tif', '.tiff'):
            with tifffile.TiffFile(path) as tf:
                if tf.pages[0].dtype != np.dtype('uint8'):
                    raise ValueError('Only 8-bit TIFF import is supported; 16-bit TIFF is export-only to avoid silent precision loss')
        if opened.format == 'PNG':
            with open(path, 'rb') as header:
                png_header = header.read(26)
            if len(png_header) > 24 and png_header[24] > 8:
                raise ValueError('Only 8-bit PNG import is supported; high-bit-depth PNG is rejected to avoid silent precision loss')
        icc = opened.info.get('icc_profile')
        img = ImageOps.exif_transpose(opened)
        if preview:
            img.thumbnail((PREVIEW_EDGE, PREVIEW_EDGE), Image.Resampling.LANCZOS)
        if icc:
            img = ImageCms.profileToProfile(img, ImageCms.ImageCmsProfile(io.BytesIO(icc)),
                                           ImageCms.createProfile('sRGB'), outputMode='RGB')
        else:
            img = img.convert('RGB')
        a = srgb_decode(np.asarray(img, dtype=np.float32) / 255) @ SRGB_TO_PROPHOTO.T
        a *= np.array([2 ** (recipe.temperature / 120), 2 ** (-recipe.tint / 180),
                       2 ** (-recipe.temperature / 120)], dtype=np.float32)
        return a, {'width': opened.width, 'height': opened.height, 'kind': opened.format,
                   'profile': 'ICC → sRGB → linear ProPhoto D65' if icc else 'Assumed sRGB → linear ProPhoto D65',
                   'input': 'Rendered image (not RAW)', 'warnings': [] if icc else ['No ICC profile; interpreted as sRGB']}


def geometry(a, recipe):
    if recipe.rotation:
        a = np.rot90(a, -(recipe.rotation // 90))
    if recipe.crop != 'original':
        num, den = map(int, recipe.crop.split(':'))
        ratio = num / den
        h, w = a.shape[:2]
        if w / h > ratio:
            new_w = max(1, round(h * ratio))
            x = (w - new_w) // 2
            a = a[:, x:x + new_w]
        else:
            new_h = max(1, round(w / ratio))
            y = (h - new_h) // 2
            a = a[y:y + new_h]
    return a


def rgb_to_hsv(a):
    mx, mn = a.max(axis=2), a.min(axis=2)
    d = mx - mn
    safe = np.maximum(d, 1e-8)
    h = np.zeros_like(mx)
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    h = np.where(mx == r, ((g - b) / safe) % 6, h)
    h = np.where((mx == g) & (mx != r), (b - r) / safe + 2, h)
    h = np.where((mx == b) & (mx != r) & (mx != g), (r - g) / safe + 4, h)
    return h / 6, np.where(mx > 0, d / np.maximum(mx, 1e-8), 0), mx


def hsv_to_rgb(h, s, v):
    basis = np.abs(((h[:, :, None] * 6 + np.array([0, 4, 2], dtype=np.float32)) % 6) - 3)
    return v[:, :, None] * (1 + (np.clip(basis - 1, 0, 1) - 1) * s[:, :, None])


def develop_tile(tile, recipe):
    from .render import grade_tile
    from .color import to_output
    data=tile.astype(np.float32)
    if tile.dtype==np.uint16: data/=65535
    return to_output(grade_tile(data,recipe))[0]


def make_preview(path, recipe, cache, budget_mb, **kwargs):
    from .render import make_preview as render
    return render(path,recipe,cache,budget_mb,**kwargs)


def make_thumbnail(path, cache, budget_mb, recipe=None):
    """Source thumbnails may use camera JPEG; developed ones use the shared renderer."""
    if recipe is not None:
        from .render import make_thumbnail as developed_thumbnail
        return developed_thumbnail(path, recipe, cache, budget_mb)
    target = thumbnail_path(path, cache)
    existing = cached_thumbnail(path, cache)
    if existing:
        return {'thumbnail': existing}
    target.parent.mkdir(parents=True, exist_ok=True)
    if Path(path).suffix.lower() in RAW_EXTENSIONS:
        with rawpy.RawPy() as raw:
            raw.open_file(str(path))
            check_budget(raw.sizes.raw_width, raw.sizes.raw_height, budget_mb, preview=True)
            thumb = raw.extract_thumb()
            if thumb.format == rawpy.ThumbFormat.JPEG:
                with Image.open(io.BytesIO(thumb.data)) as embedded:
                    img = ImageOps.exif_transpose(embedded)
                    img.thumbnail((220, 140))
                    img = img.convert('RGB')
            else:
                img = Image.fromarray(thumb.data)
                img.thumbnail((220, 140))
    else:
        with Image.open(path) as original:
            check_budget(original.width, original.height, budget_mb, raw=False, preview=True)
            img = ImageOps.exif_transpose(original)
            img.thumbnail((220, 140))
            icc = original.info.get('icc_profile')
            if icc:
                img = ImageCms.profileToProfile(img, ImageCms.ImageCmsProfile(io.BytesIO(icc)), ImageCms.createProfile('sRGB'), outputMode='RGB')
            else:
                img = img.convert('RGB')
    write_thumbnail(img, target, SRGB_ICC)
    return {'thumbnail': str(target)}


def write_thumbnail(image, target, profile, quality=82):
    """Publish a complete ICC-tagged cache JPEG, replacing only its cache entry."""
    # Publish complete cache entries atomically so the broker's cheap lookup
    # never exposes a JPEG while it is still being encoded.
    descriptor, temporary = tempfile.mkstemp(prefix='.thumbnail-', suffix='.part', dir=target.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            image.save(stream, format='JPEG', quality=quality, icc_profile=profile)
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def export_image(path, recipe, destination, fmt, budget_mb, job_id, **kwargs):
    from .render import export_image as render
    return render(path,recipe,destination,fmt,budget_mb,job_id,**kwargs)


def trim_cache(directory, maximum_mb=512, keep=()):
    """Keep cache bounded on disk; never follows symlinks or touches originals."""
    folder = Path(directory)
    files = [p for p in folder.iterdir() if p.is_file() and not p.is_symlink()]
    total = sum(p.stat().st_size for p in files)
    pinned = {str(p) for p in keep}
    for p in sorted(files, key=lambda x: x.stat().st_mtime):
        if total <= maximum_mb * 1024 * 1024:
            break
        if str(p) not in pinned:
            total -= p.stat().st_size
            p.unlink(missing_ok=True)
