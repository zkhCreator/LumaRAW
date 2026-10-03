"""Cheap read-only source identity and thumbnail cache lookup for broker/worker.

Inputs: source stat information, recipe, orientation and catalog cache. Outputs:
stable keys or an existing thumbnail path. Pixel keys include the process-cached
RAW backend namespace initialized at engine startup. No NumPy, image decoding,
SQL or UI; backend discovery/hashing runs only once per process, not per lookup.
Pixel identities omit mask display names and provably inactive grading hue/overlap
controls. Stored recipes and revision guards retain them. Unknown future fields
stay in the key; incomplete or invalid grading values are never normalized.
Stat identity invalidates on path/size/mtime changes; it is not a content hash.
Only the image worker creates pixels; the broker can reuse completed JPEG files.
"""
import hashlib
import json
import math
import os
from pathlib import Path
from .runtime import pixel_cache_namespace
from .model import GRADING_FIELDS, GRADING_RANGES, LIMITS

PIPELINE_VERSION = 'libraw-prophoto-d65-v3'


def fingerprint(path):
    source = Path(path).resolve(strict=True)
    stat = source.stat()
    return hashlib.sha256(
        f'{source}|{stat.st_size}|{stat.st_mtime_ns}|{PIPELINE_VERSION}'.encode()
    ).hexdigest()[:24]


def pixel_fingerprint(path):
    return hashlib.sha256((fingerprint(path) + pixel_cache_namespace()).encode()).hexdigest()


def pixel_recipe_key_data(recipe):
    """Hashing only: omit labels/inactive grading without changing the recipe.

    Callers supply validated recipe dictionaries. Preserve mask order, all pixel
    controls and unknown fields conservatively; this is not storage normalization.
    Complete validated grading retains luminance even at zero saturation. Hue then
    has no effect; overlap has no effect when all three tonal wheels are inactive.
    No pixel imports, scene inference or normalization of unknown controls.
    """
    masks = recipe.get('masks')
    result=recipe
    if isinstance(masks,list):
        result={**result,'masks':[
            {key:value for key,value in mask.items() if key!='name'}
            if isinstance(mask,dict) else mask for mask in masks]}
    if all(type(recipe.get(key)) in (int,float) and math.isfinite(recipe[key]) and
           LIMITS[key][0]<=recipe[key]<=LIMITS[key][1] for key in GRADING_FIELDS):
        result=dict(result)
        for region in GRADING_RANGES:
            if recipe[f'grading_{region}_saturation']==0:
                result[f'grading_{region}_hue']=0
        if all(recipe[f'grading_{region}_{component}']==0 for region in GRADING_RANGES[:3]
               for component in ('saturation','luminance')):
            result['grading_blending']=50;result['grading_balance']=0
    return result


def cache_key(path, recipe, kind):
    return hashlib.sha256((pixel_fingerprint(path) + kind +
                           json.dumps(pixel_recipe_key_data(recipe.dict()), sort_keys=True)).encode()).hexdigest()


def thumbnail_path(path, cache, recipe=None, orientation=0):
    from .orientation import validate
    validate(orientation)
    suffix=f'-orientation-{orientation}' if orientation else ''
    if recipe is None:
        return Path(cache) / (pixel_fingerprint(path) + suffix + '-thumb.jpg')
    # Imported LUTs are immutable by contract. Stat identity prevents reusing a
    # thumbnail after external removal/replacement; the worker verifies its SHA.
    asset = fingerprint(recipe.lut['path']) if recipe.lut else ''
    key = cache_key(path, recipe, 'developed-thumb-320-v1' + asset + suffix)
    return Path(cache) / (key + '-developed.jpg')


def cached_thumbnail(path, cache, recipe=None, orientation=0):
    """Do not return partial legacy writes or follow a cache-entry symlink."""
    try:
        target = thumbnail_path(path, cache, recipe, orientation)
        if target.is_symlink() or not target.is_file() or not 4 <= target.stat().st_size <= 2*1024**2:
            return None
        with target.open('rb') as stream:
            if stream.read(2) != b'\xff\xd8':
                return None
            stream.seek(-2, os.SEEK_END)
            if stream.read(2) != b'\xff\xd9':
                return None
        os.utime(target, None)
        return str(target)
    except OSError:
        return None
