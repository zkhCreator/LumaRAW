"""Full-resolution worker adapter for the white-balance selector.

Purpose: turn one captured, stat-bound raster or supported Bayer click into a WB result.
Inputs: the catalog's path/recipe/orientation snapshot, cache/budget and the
preview's source fingerprint. Outputs: a candidate and the same fingerprint.
This is worker-side only: catalog state is never opened, no preview receipt is
reused, and source identity is checked around full decoding. RAW requires greybox
API 2, square Bayer geometry and a representable as-shot-relative result; other
layouts fail visibly. RAW processing allocates a full LibRaw frame and retains no
linear cache. Raster retains its current cache pair through cleanup. No Kelvin
calibration, source writes or camera-equivalence claim.
"""
from pathlib import Path

import numpy as np
import rawpy

from lumaraw.model import RAW_EXTENSIONS, Recipe
from lumaraw.orientation import validate as validate_orientation
from lumaraw.render import OrientedPlan, RenderPlan, base_image
from lumaraw.source_identity import fingerprint

from .white_balance import WhiteBalanceSampleError, sample_raster
from .raw_white_balance import GREYBOX_API_VERSION, inspect_raw_geometry, sample_raw_white_balance


UNSUPPORTED_RAW = 'White balance sampling is not supported for this RAW source'


def sample(path, recipe, orientation, point, cache, budget_mb, expected_source_fingerprint):
    """Decode one original, solve one click, and bind the reply to its source."""
    is_raw = Path(path).suffix.lower() in RAW_EXTENSIONS
    if is_raw and getattr(rawpy, 'GREYBOX_WB_API_VERSION', None) != GREYBOX_API_VERSION:
        raise WhiteBalanceSampleError(UNSUPPORTED_RAW)
    if fingerprint(path) != expected_source_fingerprint:
        raise ValueError('Source changed before white balance sampling; reload the photograph')

    recipe = recipe if isinstance(recipe, Recipe) else Recipe.parse(recipe)
    orientation = validate_orientation(orientation)
    if is_raw:
        from .imaging import check_budget
        from .performance import stage
        with rawpy.RawPy() as raw:
            raw.open_file(str(path))
            check_budget(raw.sizes.raw_width, raw.sizes.raw_height, budget_mb)
            with stage('raw_unpack'):
                raw.unpack()
            geometry = inspect_raw_geometry(raw, camera_make=raw.camera_make)
            # Geometry uses shape/strides only. No decoded image or frame-sized
            # coordinate array is allocated or cached for this point sample.
            source = np.broadcast_to(np.zeros((1, 1, 3), np.float32),
                (geometry.decoded_height, geometry.decoded_width, 3))
            plan = OrientedPlan(RenderPlan(source, recipe, max_edge=0), orientation)
            with stage('raw_white_balance'):
                result = sample_raw_white_balance(raw, plan, point, camera_make=raw.camera_make)
        cache_keep = []
    else:
        source, metadata, cache_path = base_image(path, recipe, cache, budget_mb, full=True)
        height, width = source.shape[:2]
        if (metadata.get('decoded_width'), metadata.get('decoded_height')) != (width, height):
            raise WhiteBalanceSampleError('Cached source dimensions do not match the full-resolution photograph')
        plan = OrientedPlan(RenderPlan(source, recipe, max_edge=0), orientation)
        result = sample_raster(plan, point, (width, height))
        cache_keep = [cache_path, str(Path(cache_path).with_suffix('.json'))]

    if fingerprint(path) != expected_source_fingerprint:
        raise ValueError('Source changed during white balance sampling; reload the photograph')
    return {**result, 'source_fingerprint': expected_source_fingerprint,
            'cache_keep': cache_keep}
