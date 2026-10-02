"""Full-resolution worker adapter for the raster white-balance selector.

Purpose: turn one captured, stat-bound raster click into a bounded WB result.
Inputs: the catalog's path/recipe/orientation snapshot, cache/budget and the
preview's source fingerprint. Outputs: a candidate and the same fingerprint.
This is worker-side only: RAW fails closed, catalog state is never opened, no
preview receipt is reused, and source identity is checked around full decoding.
The current linear cache pair is retained through this worker's cleanup, matching
preview behavior; later cache cleanup can evict it normally.
"""
from pathlib import Path

from lumaraw.model import RAW_EXTENSIONS, Recipe
from lumaraw.orientation import validate as validate_orientation
from lumaraw.render import OrientedPlan, RenderPlan, base_image
from lumaraw.source_identity import fingerprint

from .white_balance import WhiteBalanceSampleError, sample_raster


UNSUPPORTED_RAW = 'White balance sampling is not supported for this RAW source'


def sample(path, recipe, orientation, point, cache, budget_mb, expected_source_fingerprint):
    """Decode one full raster, solve one click, and bind the reply to its source."""
    if Path(path).suffix.lower() in RAW_EXTENSIONS:
        raise WhiteBalanceSampleError(UNSUPPORTED_RAW)
    if fingerprint(path) != expected_source_fingerprint:
        raise ValueError('Source changed before white balance sampling; reload the photograph')

    recipe = recipe if isinstance(recipe, Recipe) else Recipe.parse(recipe)
    orientation = validate_orientation(orientation)
    source, metadata, cache_path = base_image(path, recipe, cache, budget_mb, full=True)
    height, width = source.shape[:2]
    if (metadata.get('decoded_width'), metadata.get('decoded_height')) != (width, height):
        raise WhiteBalanceSampleError('Cached source dimensions do not match the full-resolution photograph')
    plan = OrientedPlan(RenderPlan(source, recipe, max_edge=0), orientation)
    result = sample_raster(plan, point, (width, height))

    if fingerprint(path) != expected_source_fingerprint:
        raise ValueError('Source changed during white balance sampling; reload the photograph')
    return {**result, 'source_fingerprint': expected_source_fingerprint,
            'cache_keep': [cache_path, str(Path(cache_path).with_suffix('.json'))]}
