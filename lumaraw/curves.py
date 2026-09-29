"""Bounded RGB point curves shared by CPU rendering and Metal parameter packing.

Inputs: validated normalized control points and linear working RGB strips.
Outputs: shape-preserving cubic coefficients and non-destructive RGB adjustments.
The master curve precedes independent channels in the existing sRGB-shaped tone
encoding of working-space channels. Identity curves preserve HDR/negative values.
Active curves clamp to their end points; they are SDR controls, not an HDR grade.
Legacy luminance curves remain a separate earlier stage with unchanged equations.
No files, catalogs, GUI, Adobe parameter translation or camera calibration.
"""
from functools import lru_cache

import numpy as np

from .color import encode,decode
from .model import POINT_CURVE_FIELDS


def is_identity(points):
    return points[0]==[0,0] and points[-1]==[1,1] and all(x==y for x,y in points)


@lru_cache(maxsize=128)
def coefficients(key):
    # Compute a small spline once per immutable point tuple, not once per pixel.
    # Normalized interval coefficients avoid enormous powers for narrow segments.
    from scipy.interpolate import PchipInterpolator
    points=np.asarray(key,np.float64)
    widths=np.diff(points[:,0])
    spline=PchipInterpolator(points[:,0],points[:,1],extrapolate=False)
    block=np.zeros((len(points),6),np.float32)
    block[:,0]=points[:,0]
    block[:-1,1]=widths
    block[:-1,2:6]=(spline.c*widths[None,:]**np.arange(3,-1,-1)[:,None]).T
    block[-1,5]=points[-1,1]
    block.setflags(write=False)
    return block


def packed_curve(points):
    return coefficients(tuple(tuple(p) for p in points))


def reference_required(recipe):
    # Very narrow, steep segments amplify tiny backend encoding differences.
    # Use CPU grading for those recipes rather than silently changing their shape.
    # Check endpoints and the quadratic derivative's vertex, at most 4*15 pieces.
    for key in POINT_CURVE_FIELDS:
        points=getattr(recipe,key)
        if is_identity(points):
            continue
        block=packed_curve(points)[:-1]
        a,b,c=block[:,2],block[:,3],block[:,4]
        vertex=np.clip(np.divide(-b,3*a,out=np.zeros_like(a),where=a!=0),0,1)
        bound=np.maximum.reduce([np.abs(c),np.abs(3*a+2*b+c),np.abs((3*a*vertex+2*b)*vertex+c)])/block[:,1]
        if np.any(bound>32):
            return True
    return False


def evaluate(values,block):
    values=np.asarray(values,np.float32)
    index=np.clip(np.searchsorted(block[:,0],values,side='right')-1,0,len(block)-2)
    x,width,a,b,c,d=(block[index,k] for k in range(6))
    t=np.clip((values-x)/width,0,1)
    result=((a*t+b)*t+c)*t+d
    result=np.where(values<=block[0,0],block[0,5],result)
    result=np.where(values>=block[-1,0],block[-1,5],result)
    return np.clip(result,0,1).astype(np.float32)


def apply_rgb_curves(image,recipe):
    curves=[getattr(recipe,key) for key in POINT_CURVE_FIELDS]
    active=[not is_identity(points) for points in curves]
    if not any(active):
        return image
    encoded=encode(image)
    if active[0]:
        encoded=evaluate(encoded,packed_curve(curves[0]))
    result=image.copy()
    for channel in range(3):
        values=encoded[:,:,channel]
        if active[channel+1]:
            values=evaluate(values,packed_curve(curves[channel+1]))
        if active[0] or active[channel+1]:
            result[:,:,channel]=decode(values)
    return result
