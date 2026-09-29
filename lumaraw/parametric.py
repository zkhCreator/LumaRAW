"""Smooth, monotone four-region tone adjustment for bounded linear RGB strips.

Inputs: validated -100…100 region amounts and three normalized input splits.
Outputs: cached small warp coefficients and a luminance-preserving RGB gain.
Each C1 smoothstep bump has derivative magnitude at most 0.75; composing the
four increasing maps in shadow-to-highlight order cannot invert the tonal scale.
Neighboring region centers bound each bump's support. Split edits change those
supports without changing stored amounts. Black, white and out-of-SDR luminance
are preserved; zero amounts are an exact no-op even with non-default splits.
This is LumaRAW's equation, not a recovered Adobe transform or an HDR tone mapper.
No I/O, catalog changes, UI or reinterpretation of legacy curve parameters.
"""
from functools import lru_cache

import numpy as np

from .color import encode,decode
from .imaging import LUMA
from .model import PARAMETRIC_FIELDS


@lru_cache(maxsize=128)
def coefficients(amounts,splits):
    edges=np.array([0,*splits,1],np.float64)
    centers=(edges[:-1]+edges[1:])/2
    lows=np.r_[0,centers[:-1]]
    highs=np.r_[centers[1:],1]
    amplitudes=.5*np.minimum(centers-lows,highs-centers)*np.asarray(amounts)/100
    block=np.column_stack([lows,centers,highs,amplitudes]).astype(np.float32)
    block.setflags(write=False)
    return block


def packed(recipe):
    return coefficients(tuple(getattr(recipe,key) for key in PARAMETRIC_FIELDS),tuple(recipe.parametric_splits))


def active(recipe):
    return any(getattr(recipe,key) for key in PARAMETRIC_FIELDS)


def evaluate(values,block):
    value=np.asarray(values,np.float32)
    for lo,center,hi,amplitude in block:
        if amplitude==0:
            continue
        t=np.clip(np.where(value<=center,(value-lo)/(center-lo),(hi-value)/(hi-center)),0,1)
        value=value+amplitude*t*t*(3-2*t)
    return value


def apply(image,recipe):
    if not active(recipe):
        return image
    lum=image@LUMA
    encoded=encode(lum)
    mapped=evaluate(encoded,packed(recipe))
    target=decode(mapped)
    gain=np.ones_like(lum)
    # Avoid an encoding round trip for unchanged tones (including white whose
    # float32 luminance may be just below one). This keeps unused regions exact.
    np.divide(target,lum,out=gain,where=(lum>0)&(lum<1)&(mapped!=encoded))
    return image*gain[:,:,None]
