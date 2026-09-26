"""Camera-bound 24-patch matrix fitting with held-out reference measurements.

Inputs: a RAW chart capture, a user-provided reference render, and two normalized
axis-aligned chart rectangles (6 columns × 4 rows, same orientation). Outputs:
validated matrix profile and Delta E 76 diagnostics. This is a per-lighting fit,
not a Nikon Picture Control implementation or a claim of independent colorimetry.
"""
from pathlib import Path
import json
import numpy as np

from .model import Recipe
from .color import lab_d50
from .render import base_image
from .imaging import load_source


def chart_samples(image,rectangle):
    if len(rectangle)!=4 or any(not np.isfinite(v) or not 0<=v<=1 for v in rectangle):
        raise ValueError('Chart bounds must be within 0–1')
    x0,y0,x1,y1=rectangle
    if x1<=x0 or y1<=y0: raise ValueError('Invalid chart bounds')
    h,w=image.shape[:2];values=[]
    for row in range(4):
        for col in range(6):
            xa=round((x0+(x1-x0)*(col+.28)/6)*w);xb=round((x0+(x1-x0)*(col+.72)/6)*w)
            ya=round((y0+(y1-y0)*(row+.28)/4)*h);yb=round((y0+(y1-y0)*(row+.72)/4)*h)
            if xb-xa<3 or yb-ya<3: raise ValueError('Chart area is too small; each patch needs at least 3×3 interior pixels')
            patch=image[ya:yb,xa:xb].astype(np.float32)
            if image.dtype==np.uint16: patch/=65535
            values.append(np.median(patch,axis=(0,1)))
    return np.asarray(values)


def fit_matrix(source,target,camera,name='Custom Camera Profile',lighting='User-specified lighting'):
    source=np.asarray(source,np.float64);target=np.asarray(target,np.float64)
    if source.shape!=(24,3) or target.shape!=(24,3) or not np.isfinite(source).all() or not np.isfinite(target).all():
        raise ValueError('24 valid linear RGB patches are required')
    if not camera or camera.strip().casefold() in ('','raw camera','nikon raw'): raise ValueError('The profile must be bound to an identified camera model')
    held=np.array([2,6,10,14,18,22]);train=np.array([i for i in range(24) if i not in held])
    if np.linalg.cond(source[train].T@source[train])>1e5: raise ValueError('Patches lack independent color information for a reliable matrix fit')
    def fit(x,y):
        regularizer=.0001
        return np.linalg.solve(x.T@x+regularizer*np.eye(3),x.T@y+regularizer*np.eye(3)).T
    validation=fit(source[train],target[train])
    before=np.linalg.norm(lab_d50(source[held])-lab_d50(target[held]),axis=1)
    after=np.linalg.norm(lab_d50(source[held]@validation.T)-lab_d50(target[held]),axis=1)
    # Keep the evaluated training fit; do not silently replace it by an unevaluated all-patch fit.
    profile={'name':str(name)[:120],'camera':str(camera)[:100],'space':'LibRaw-ProPhoto-D65-linear',
             'lighting':str(lighting)[:120],'matrix':validation.tolist(),
             'measurement':{'method':'24 patch / 18 fit + 6 holdout / CIE76',
                            'before_mean':round(float(before.mean()),3),'after_mean':round(float(after.mean()),3),
                            'after_max':round(float(after.max()),3),'holdout_indices':held.tolist(),
                            'scope':'One supplied reference under one lighting; not independent camera certification'}}
    Recipe(camera_profile=profile)
    return profile


def calibrate(path,reference,source_rect,reference_rect,cache,budget_mb,name,lighting):
    raw,meta,_=base_image(path,Recipe(),cache,budget_mb,full=False)
    target,_=load_source(reference,Recipe(),budget_mb,preview=True)
    profile=fit_matrix(chart_samples(raw,source_rect),chart_samples(target,reference_rect),meta.get('camera',''),name,lighting)
    return {'profile':profile,'measurement':profile['measurement']}
