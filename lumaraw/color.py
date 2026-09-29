"""Explicit working/output color spaces, immutable LUT assets, and ICC soft proof.

Inputs: linear LibRaw ProPhoto D65 float tiles. Outputs: encoded RGB plus an ICC
that describes those exact output primaries/transfer curves. Creative LUTs are
explicit SDR sRGB operations and clip to their declared domain. No Nikon vendor
appearance is inferred. Soft proof simulates a supplied ICC, not printer hardware.
The eight overlapping Oklab mixer bands retain legacy hue/saturation equations;
new luminance and monochrome gains protect neutral pixels and use bounded tiles.
"""
from functools import lru_cache
import hashlib
import io
from pathlib import Path

import numpy as np
from PIL import Image, ImageCms
from scipy.ndimage import map_coordinates
from .model import MIXER_BANDS

WORK_FROM_SRGB = np.array([[.529317,.330092,.140588],[.098368,.873465,.028169],[.016879,.117663,.865457]],np.float32)
SRGB_FROM_WORK = np.linalg.inv(WORK_FROM_SRGB).astype(np.float32)
SRGB_XYZ = np.array([[.4124564,.3575761,.1804375],[.2126729,.7151522,.0721750],[.0193339,.1191920,.9503041]],np.float64)
D65_D50 = np.array([[1.0478112,.0228866,-.0501270],[.0295424,.9904844,-.0170491],[-.0092345,.0150436,.7521316]])
ADOBE_XYZ = np.array([[.5767309,.1855540,.1881852],[.2973769,.6273491,.0752741],[.0270343,.0706872,.9911085]])
P3_XYZ = np.array([[.48657095,.26566769,.19821729],[.22897456,.69173852,.07928691],[0,.04511338,1.04394437]])
PROPHOTO_XYZ = np.array([[.7976749,.1351917,.0313534],[.2880402,.7118741,.0000857],[0,0,.8252100]])
SPACE_NAMES = {'srgb':'sRGB','adobe':'Adobe RGB','p3':'Display P3','prophoto':'ProPhoto RGB D50'}


def encode(a, space='srgb'):
    a = np.clip(a,0,1)
    if space in ('srgb','p3'):
        return np.where(a <= .0031308,a*12.92,1.055*a**(1/2.4)-.055).astype(np.float32)
    if space == 'adobe':
        return a**(256/563)
    if space == 'prophoto':
        return np.where(a < 1/512,a*16,a**(1/1.8)).astype(np.float32)
    raise ValueError('Unknown color space')


def decode(a, space='srgb'):
    a = np.maximum(a,0)
    if space in ('srgb','p3'):
        return np.where(a<=.04045,a/12.92,((a+.055)/1.055)**2.4).astype(np.float32)
    if space == 'adobe':
        return a**(563/256)
    if space == 'prophoto':
        return np.where(a<.03125,a/16,a**1.8).astype(np.float32)
    raise ValueError('Unknown color space')


@lru_cache(maxsize=4)
def output_matrix(space):
    if space == 'srgb':
        return SRGB_FROM_WORK
    if space == 'adobe':
        return (np.linalg.inv(ADOBE_XYZ) @ SRGB_XYZ @ SRGB_FROM_WORK).astype(np.float32)
    if space == 'p3':
        return (np.linalg.inv(P3_XYZ) @ SRGB_XYZ @ SRGB_FROM_WORK).astype(np.float32)
    if space == 'prophoto':
        return (np.linalg.inv(PROPHOTO_XYZ) @ D65_D50 @ SRGB_XYZ @ SRGB_FROM_WORK).astype(np.float32)
    raise ValueError('Unknown color space')


@lru_cache(maxsize=4)
def icc_profile(space):
    if space not in ('srgb','adobe','p3','prophoto'):
        raise ValueError('Unknown color space')
    return (Path(__file__).parent / 'profiles' / (space + '.icc')).read_bytes()


def to_output(a,space='srgb'):
    linear=a @ output_matrix(space).T
    gamut=np.any((linear < -1e-5)|(linear>1.00001),axis=2)
    return encode(linear,space),gamut


def oklab(a):
    rgb=a @ SRGB_FROM_WORK.T
    lms=rgb @ np.array([[.41222147,.53633254,.05144599],[.21190350,.68069955,.10739696],[.08830246,.28171884,.62997870]],np.float32).T
    return np.cbrt(lms) @ np.array([[.21045426,.79361779,-.00407205],[1.97799850,-2.42859221,.45059371],[.02590404,.78277177,-.80867577]],np.float32).T


def from_oklab(lab):
    lms=lab @ np.array([[1,.39633778,.21580376],[1,-.10556135,-.06385417],[1,-.08948418,-1.29148555]],np.float32).T
    rgb=(lms**3) @ np.array([[4.07674166,-3.30771159,.23096993],[-1.26843800,2.60975740,-.34131940],[-.00419609,-.70341861,1.70761470]],np.float32).T
    return rgb @ WORK_FROM_SRGB.T


MIXER_CENTERS = (29,65,109,142,195,264,305,342)


def mixer_weight(h, center):
    return np.maximum(0,1-np.abs((h-center+180)%360-180)/50)**2


def mixer_neutral_weight(lab):
    # Rounded working-space matrices leave tiny chroma on equal-RGB neutrals.
    # Ignore that numerical residue before smoothly enabling selective gains.
    lightness=np.abs(lab[:,:,0])
    chroma=np.maximum(0,np.hypot(lab[:,:,1],lab[:,:,2])-lightness*1e-5)
    return np.minimum(1,chroma/(lightness*.1+1e-7))


def mix_hues(a,recipe):
    if not any(getattr(recipe,key+'_'+kind) for key in MIXER_BANDS for kind in ('hue','sat','lum')):
        return a
    lab=oklab(a);h=np.degrees(np.arctan2(lab[:,:,2],lab[:,:,1]))%360
    chroma=np.hypot(lab[:,:,1],lab[:,:,2]);dh=np.zeros_like(h);ds=np.zeros_like(h)
    dl=np.zeros_like(h)
    neutral=mixer_neutral_weight(lab)
    for key,center in zip(MIXER_BANDS,MIXER_CENTERS):
        if not any(getattr(recipe,key+'_'+kind) for kind in ('hue','sat','lum')):continue
        weight=mixer_weight(h,center)
        dh += weight*getattr(recipe,key+'_hue')
        ds += weight*getattr(recipe,key+'_sat')/100
        dl += weight*getattr(recipe,key+'_lum')/100
    angle=np.radians(h+dh);chroma *= np.maximum(0,1+ds)
    lab[:,:,1]=chroma*np.cos(angle);lab[:,:,2]=chroma*np.sin(angle)
    mixed=from_oklab(lab)
    if np.any(dl):mixed *= np.exp2(dl*2*neutral)[:,:,None]
    return mixed


def mix_monochrome(a,recipe,luma):
    gray=a@luma
    if any(getattr(recipe,key+'_bw') for key in MIXER_BANDS):
        lab=oklab(a);h=np.degrees(np.arctan2(lab[:,:,2],lab[:,:,1]))%360
        neutral=mixer_neutral_weight(lab)
        shift=np.zeros_like(h)
        for key,center in zip(MIXER_BANDS,MIXER_CENTERS):
            value=getattr(recipe,key+'_bw')
            if value:shift += mixer_weight(h,center)*value/100
        gray *= np.exp2(shift*2*neutral)
    return np.repeat(gray[:,:,None],3,axis=2)


@lru_cache(maxsize=2)
def read_cube(path,sha256):
    p=Path(path)
    if p.stat().st_size>32*1024**2:
        raise ValueError('LUT exceeds 32 MB')
    data=p.read_bytes()
    if hashlib.sha256(data).hexdigest()!=sha256:
        raise ValueError('LUT has changed; import it again before use')
    size=None;values=[];minimum=[0,0,0];maximum=[1,1,1]
    for raw in data.decode('utf-8-sig').splitlines():
        line=raw.split('#',1)[0].strip()
        if not line: continue
        parts=line.split()
        if parts[0]=='TITLE': continue
        if parts[0]=='LUT_3D_SIZE':
            size=int(parts[1])
            if not 2<=size<=65: raise ValueError('Only 3D LUT sizes 2–65 are supported')
        elif parts[0]=='DOMAIN_MIN': minimum=list(map(float,parts[1:]))
        elif parts[0]=='DOMAIN_MAX': maximum=list(map(float,parts[1:]))
        elif parts[0].startswith('LUT_'): raise ValueError('Only a single LUT_3D .cube file is supported')
        else:
            if len(parts)!=3: raise ValueError('Invalid LUT row')
            values.append(list(map(float,parts)))
            if len(values)>65**3: raise ValueError('LUT is too large')
    if size is None or len(values)!=size**3 or len(minimum)!=3 or len(maximum)!=3:
        raise ValueError('LUT data count does not match its dimensions')
    cube=np.asarray(values,np.float32).reshape(size,size,size,3)
    lo=np.asarray(minimum,np.float32);hi=np.asarray(maximum,np.float32)
    if not np.isfinite(cube).all() or not np.isfinite(lo).all() or not np.isfinite(hi).all() or np.any(hi<=lo):
        raise ValueError('Invalid LUT values')
    return cube,lo,hi


def apply_lut(a,reference,amount):
    if not reference or amount==0: return a
    cube,lo,hi=read_cube(reference['path'],reference['sha256'])
    encoded=encode(a @ SRGB_FROM_WORK.T)
    coords=np.clip((encoded-lo)/(hi-lo),0,1)*(cube.shape[0]-1)
    # .cube orders red fastest, then green, then blue.
    rgb=np.empty_like(encoded)
    for c in range(3):
        rgb[:,:,c]=map_coordinates(cube[:,:,:,c],[coords[:,:,2],coords[:,:,1],coords[:,:,0]],order=1,prefilter=False,mode='nearest')
    mapped=decode(rgb) @ WORK_FROM_SRGB.T
    return a*(1-amount/100)+mapped*(amount/100)


def soft_proof(rgb,profile_path,sha256,gamut=False):
    p=Path(profile_path)
    if p.stat().st_size>8*1024**2: raise ValueError('ICC file exceeds 8 MB')
    data=p.read_bytes()
    if hashlib.sha256(data).hexdigest()!=sha256:
        raise ValueError('Soft-proof ICC has changed; import it again')
    proof=ImageCms.ImageCmsProfile(io.BytesIO(data))
    srgb=ImageCms.ImageCmsProfile(io.BytesIO(icc_profile('srgb')))
    flags=ImageCms.Flags.SOFTPROOFING|ImageCms.Flags.BLACKPOINTCOMPENSATION
    if gamut: flags |= ImageCms.Flags.GAMUTCHECK
    transform=ImageCms.buildProofTransform(srgb,srgb,proof,'RGB','RGB',renderingIntent=0,proofRenderingIntent=1,flags=flags)
    return np.asarray(ImageCms.applyTransform(Image.fromarray(rgb),transform)).copy()


def lab_d50(work):
    xyz=work @ (D65_D50 @ SRGB_XYZ @ SRGB_FROM_WORK).T
    ratio=xyz/np.array([.96422,1,.82521])
    f=np.where(ratio>(6/29)**3,np.cbrt(ratio),ratio/(3*(6/29)**2)+4/29)
    return np.stack([116*f[...,1]-16,500*(f[...,0]-f[...,1]),200*(f[...,1]-f[...,2])],axis=-1)
