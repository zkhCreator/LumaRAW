"""Bounded, halo-aware renderer for preview, full-resolution viewports and export.

Purpose: one processing pipeline for all outputs. Inputs are a disk-backed linear
source and a versioned recipe. Geometry samples strips; neighborhood filters use
halos so strip boundaries do not change pixels. Only the requested 1:1 viewport is
encoded for the GUI. LibRaw itself still decodes a full frame in one child process.
Manual lens coefficients are user corrections, not an auto-selected lens database.
Review callers can omit the before image and request a smaller fitted preview;
full-resolution detail coordinates and export pixels retain the same pipeline.
Export metadata is a frozen catalog snapshot encoded separately from pixels;
internal recipes, source names and asset paths are never embedded as descriptions.
Independent catalog orientation maps output strips back to canonical Develop
coordinates, then losslessly rotates/flips each tile. Masks/crops stay attached.
"""
from dataclasses import replace
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, map_coordinates
import tifffile

from .model import Recipe, ExportOptions
from .performance import stage
from .accelerators import grade_output
from .color import to_output, output_matrix, encode, decode, icc_profile, mix_hues, mix_monochrome, apply_lut, soft_proof
from .imaging import load_source, fingerprint, cache_key, write_thumbnail, LUMA
from .source_identity import thumbnail_path, cached_thumbnail
from .orientation import validate as validate_orientation, inverse_rect, apply_array

ROWS=128
HALO=32
CACHE_MB=1024


def atomic_json(path,data):
    temp=Path(str(path)+'.part');temp.write_text(json.dumps(data,ensure_ascii=True));os.replace(temp,path)


def base_image(path,recipe,cache,budget_mb,full=False):
    cache=Path(cache);cache.mkdir(parents=True,exist_ok=True)
    base_recipe=Recipe(temperature=recipe.temperature,tint=recipe.tint,highlight_recovery=recipe.highlight_recovery)
    key=cache_key(path,base_recipe,'full-linear-v3' if full else 'proxy-linear-v3')
    pixels=cache/(key+'.npy');metadata=cache/(key+'.json')
    if pixels.exists() and metadata.exists():
        try:
            a=np.load(pixels,mmap_mode='r',allow_pickle=False)
            if a.ndim!=3 or a.shape[2]!=3 or a.dtype not in (np.float32,np.uint16): raise ValueError('bad cache')
            meta=json.loads(metadata.read_text());os.utime(pixels,None);os.utime(metadata,None)
            return a,meta,str(pixels)
        except (ValueError,OSError,json.JSONDecodeError):
            pixels.unlink(missing_ok=True);metadata.unlink(missing_ok=True)
    with stage("source_decode"):
        a,meta=load_source(path,base_recipe,budget_mb,preview=not full)
    if shutil.disk_usage(cache).free < a.nbytes + 64*1024**2:
        raise OSError('Insufficient cache disk space; free space and retry')
    part=Path(str(pixels)+'.part')
    mapped=np.lib.format.open_memmap(part,mode='w+',dtype=a.dtype,shape=a.shape)
    for y in range(0,a.shape[0],512): mapped[y:y+512]=a[y:y+512]
    mapped.flush();del mapped,a
    os.replace(part,pixels);atomic_json(metadata,meta)
    return np.load(pixels,mmap_mode='r',allow_pickle=False),meta,str(pixels)


class RenderPlan:
    def __init__(self,source,recipe,max_edge=0):
        self.source=np.rot90(source,-recipe.rotation//90) if recipe.rotation else source
        self.recipe=recipe
        self.sh,self.sw=self.source.shape[:2]
        x0,y0,x1,y1=recipe.crop_box
        self.x0,self.y0=x0*self.sw,y0*self.sh
        cw,ch=(x1-x0)*self.sw,(y1-y0)*self.sh
        if recipe.crop!='original':
            n,d=map(int,recipe.crop.split(':'));ratio=n/d
            if cw/ch>ratio:
                width=ch*ratio;self.x0+=(cw-width)/2;cw=width
            else:
                height=cw/ratio;self.y0+=(ch-height)/2;ch=height
        self.crop_w,self.crop_h=cw,ch
        self.width,self.height=max(1,round(cw)),max(1,round(ch))
        if max_edge and max(self.width,self.height)>max_edge:
            factor=max_edge/max(self.width,self.height)
            self.width=max(1,round(self.width*factor));self.height=max(1,round(self.height*factor))
        self.pixel_scale=max(self.width/cw,self.height/ch)

    def sample(self,x,y,w,h):
        r=self.recipe
        if not any((r.straighten,r.perspective_v,r.perspective_h,r.distortion,r.ca_red,r.ca_blue,r.vignette)) and r.geometry_scale==1 and self.width==self.sw and self.height==self.sh and self.x0==0 and self.y0==0:
            a=self.source[y:y+h,x:x+w].astype(np.float32)
            return a/65535 if self.source.dtype==np.uint16 else a
        # Pixel centers stay exactly aligned at full resolution when geometry is neutral.
        xx=(np.arange(x,x+w,dtype=np.float32)+.5)/self.width
        yy=(np.arange(y,y+h,dtype=np.float32)+.5)/self.height
        u=(self.x0+xx[None,:]*self.crop_w-self.sw/2)/(self.sw/2)
        v=(self.y0+yy[:,None]*self.crop_h-self.sh/2)/(self.sh/2)
        u,v=np.broadcast_arrays(u,v)
        angle=math.radians(r.straighten)
        # Coordinates account for physical pixel aspect ratio, then inverse perspective.
        px=u*self.sw;py=v*self.sh
        us=(math.cos(angle)*px+math.sin(angle)*py)/self.sw/r.geometry_scale
        vs=(-math.sin(angle)*px+math.cos(angle)*py)/self.sh/r.geometry_scale
        den=1+vs*r.perspective_v/160+us*r.perspective_h/160
        us=us/den;vs=vs/den
        radius2=us*us+vs*vs
        radial=1+r.distortion/400*radius2
        us*=radial;vs*=radial
        a=np.empty((h,w,3),np.float32)
        for c,ca in enumerate((r.ca_red,0,r.ca_blue)):
            scale=1+ca/10000
            sx=(us*scale+1)*(self.sw/2)-.5
            sy=(vs*scale+1)*(self.sh/2)-.5
            # Clamp numerical epsilon only; meaningful out-of-frame regions remain black.
            sx=np.where((sx<0)&(sx>-.001),0,sx);sy=np.where((sy<0)&(sy>-.001),0,sy)
            sx=np.where((sx>self.sw-1)&(sx<self.sw-1+.001),self.sw-1,sx)
            sy=np.where((sy>self.sh-1)&(sy<self.sh-1+.001),self.sh-1,sy)
            a[:,:,c]=map_coordinates(self.source[:,:,c],[sy,sx],output=np.float32,order=1,mode='constant',cval=0,prefilter=False)
        if self.source.dtype==np.uint16: a/=65535
        if r.vignette: a*=np.exp2(r.vignette/100*np.minimum(radius2,4))[:,:,None]
        return a


class OrientedPlan:
    """Output-coordinate adapter; no full-frame allocation or resampling."""
    def __init__(self, base, orientation):
        self.base=base
        self.orientation=validate_orientation(orientation)
        self.width,self.height=(base.height,base.width) if orientation % 2 else (base.width,base.height)

    @property
    def pixel_scale(self):
        return self.base.pixel_scale

    @pixel_scale.setter
    def pixel_scale(self, value):
        self.base.pixel_scale=value


def detail_filter(a,r,pixel_scale=1,output_sharpen=0):
    """Operate on an owned writable strip, reusing its memory where possible."""
    y=np.maximum(a@LUMA,1e-8)
    if r.chroma_noise:
        chroma=a-y[:,:,None]
        smooth=gaussian_filter(chroma,sigma=(max(.4,1.8*pixel_scale),max(.4,1.8*pixel_scale),0),mode='nearest',truncate=4)
        a=y[:,:,None]+chroma*(1-r.chroma_noise/100)+smooth*(r.chroma_noise/100)
    if r.luma_noise:
        smooth=gaussian_filter(y,max(.4,1.25*pixel_scale),mode='nearest',truncate=4)
        threshold=.003+.04*(1-r.detail_protect/100)
        blend=r.luma_noise/100*np.exp(-((y-smooth)/(threshold*np.sqrt(y+.02)))**2)
        target=y+(smooth-y)*blend
        a*= (target/y)[:,:,None];y=target
    if r.defringe:
        # Selective purple chroma suppression, preserving the luminance estimate.
        strength=np.maximum(0,np.minimum(a[:,:,0],a[:,:,2])-a[:,:,1]*1.25)
        strength=np.minimum(strength/(y+.01),1)*r.defringe/100
        a=y[:,:,None]+(a-y[:,:,None])*(1-strength[:,:,None])
    amount=r.sharpen+output_sharpen
    if amount:
        smooth=gaussian_filter(y,max(.3,r.sharpen_radius*pixel_scale),mode='nearest',truncate=4)
        detail=y-smooth
        threshold=r.detail_protect/100*.003
        protect=np.clip((np.abs(detail)-threshold)/(.003+threshold),0,1)
        target=np.maximum(0,y+detail*protect*amount/100)
        a*= (target/np.maximum(y,1e-8))[:,:,None]
    return a


def mask_weight(mask,x,y,w,h,total_w,total_h,luminance):
    xx=(np.arange(x,x+w,dtype=np.float32)+.5)/total_w
    yy=(np.arange(y,y+h,dtype=np.float32)+.5)/total_h
    mx,my=mask.get('x',.5),mask.get('y',.5)
    feather=mask.get('feather',.5);radius=mask.get('radius',.25)
    kind=mask['kind']
    if kind=='radial':
        d=np.sqrt(((xx[None,:]-mx)*total_w/min(total_w,total_h))**2+((yy[:,None]-my)*total_h/min(total_w,total_h))**2)/radius
        a=np.clip((1-d)/feather,0,1)
    elif kind=='linear':
        dx,dy=mask.get('x2',1)-mx,mask.get('y2',1)-my
        t=((xx[None,:]-mx)*dx+(yy[:,None]-my)*dy)/max(dx*dx+dy*dy,1e-5)
        a=np.clip(t,0,1)
    elif kind=='luminance':
        lo,hi=mask.get('low',0),mask.get('high',1)
        value=encode(luminance)
        width=max(.01,feather*.2)
        a=np.clip((value-lo+width)/width,0,1)*np.clip((hi+width-value)/width,0,1)
    else:
        a=np.zeros((h,w),np.float32)
        points=mask.get('points',[])
        aspect_x=total_w/min(total_w,total_h);aspect_y=total_h/min(total_w,total_h)
        for i,(px,py) in enumerate(points):
            qx,qy=points[i-1] if i else (px,py)
            if max(py,qy)+radius<yy[0] or min(py,qy)-radius>yy[-1] or max(px,qx)+radius<xx[0] or min(px,qx)-radius>xx[-1]:continue
            dx=(px-qx)*aspect_x;dy=(py-qy)*aspect_y
            X=(xx[None,:]-qx)*aspect_x;Y=(yy[:,None]-qy)*aspect_y
            t=np.clip((X*dx+Y*dy)/max(dx*dx+dy*dy,1e-12),0,1)
            distance=np.sqrt((X-t*dx)**2+(Y-t*dy)**2)/radius
            a=np.maximum(a,np.clip((1-distance)/feather,0,1))
    a=a*a*(3-2*a)
    return 1-a if mask.get('invert',False) else a


def grade_tile(a,r,x=0,y=0,total_w=None,total_h=None):
    a=a.astype(np.float32,copy=True)
    if r.camera_profile: a=a@np.asarray(r.camera_profile['matrix'],np.float32).T
    a*=2**r.exposure
    luminance=np.maximum(a@LUMA,1e-7)
    shadow=np.exp(-luminance/.16);light=luminance/(luminance+.35)
    gain=np.exp2(r.shadows/100*shadow*1.5+r.highlights/100*light*1.5+r.blacks/100*np.exp(-luminance/.045)+r.whites/100*light**4)
    a*=gain[:,:,None];luminance=np.maximum(a@LUMA,1e-7)
    if r.contrast:
        target=.18*(luminance/.18)**(1+r.contrast/200)
        a*=(target/luminance)[:,:,None];luminance=target
    spread=np.maximum(a.max(axis=2)-a.min(axis=2),0)/np.maximum(a.max(axis=2),1e-7)
    sat=(1+r.saturation/100)*(1+r.vibrance/100*(1-np.minimum(spread,1)))
    a=luminance[:,:,None]+(a-luminance[:,:,None])*sat[:,:,None]
    curve=[r.curve_shadows,r.curve_midtones,r.curve_lights]
    if any(curve) or r.curve_points!=[[0.,0.],[1.,1.]]:
        encoded=encode(luminance)
        if any(curve):
            fp=np.maximum.accumulate(np.clip([0,.25+curve[0]/100,.5+curve[1]/100,.75+curve[2]/100,1],0,1))
            encoded=np.interp(encoded,[0,.25,.5,.75,1],fp).astype(np.float32)
        if r.curve_points!=[[0.,0.],[1.,1.]]:
            points=np.asarray(r.curve_points);encoded=np.interp(encoded,points[:,0],points[:,1]).astype(np.float32)
        target=decode(encoded)
        a*=(target/luminance)[:,:,None]
    a=mix_hues(a,r)
    if r.monochrome: a=mix_monochrome(a,r,LUMA)
    total_w=total_w or a.shape[1];total_h=total_h or a.shape[0]
    for m in r.masks:
        if not m.get('enabled',True): continue
        lum=np.maximum(a@LUMA,1e-7)
        weight=mask_weight(m,x,y,a.shape[1],a.shape[0],total_w,total_h,lum)
        a*=np.exp2(weight*m.get('exposure',0))[:,:,None]
        lum=a@LUMA
        a=lum[:,:,None]+(a-lum[:,:,None])*(1+weight*m.get('saturation',0)/100)[:,:,None]
    return apply_lut(a,r.lut,r.lut_amount)


def validate_camera(recipe,meta):
    if recipe.camera_profile and str(meta.get('camera','')).strip().casefold() in ('','raw camera','nikon raw'):
        raise ValueError('Camera model is unidentified; cannot apply a camera calibration profile')
    if recipe.camera_profile and recipe.camera_profile['camera'].strip().casefold()!=str(meta.get('camera','')).strip().casefold():
        raise ValueError(f'Camera profile requires {recipe.camera_profile["camera"]}; this file is {meta.get("camera","Unknown camera")}')


def render_strip(plan,x,y,w,h,space='srgb',output_sharpen=0):
    if isinstance(plan,OrientedPlan):
        rect=inverse_rect(x,y,w,h,plan.base.width,plan.base.height,plan.orientation)
        pixels,gamut=render_strip(plan.base,*rect,space,output_sharpen)
        return apply_array(pixels,plan.orientation),apply_array(gamut,plan.orientation)
    start=max(0,y-HALO);end=min(plan.height,y+h+HALO)
    left=max(0,x-HALO);right=min(plan.width,x+w+HALO)
    with stage("geometry"):
        a=plan.sample(left,start,right-left,end-start)
    with stage("detail_filters"):
        a=detail_filter(a,plan.recipe,plan.pixel_scale,output_sharpen)
    with stage("grade_and_output"):
        pixels,gamut=grade_output(a,plan.recipe,space,left,start,plan.width,plan.height)
    return pixels[y-start:y-start+h,x-left:x-left+w],gamut[y-start:y-start+h,x-left:x-left+w]


def render_u8(plan,rect=None,display=None):
    display=display or {}
    x,y,w,h=rect or (0,0,plan.width,plan.height)
    pixels=np.empty((h,w,3),np.uint8);hist=np.zeros((3,64),np.int64);out_count=0
    for row in range(0,h,ROWS):
        data,gamut=render_strip(plan,x,y+row,w,min(ROWS,h-row),'srgb')
        out_count+=int(gamut.sum())
        data=np.rint(data*255).astype(np.uint8)
        for c in range(3): hist[c]+=np.histogram(data[:,:,c],64,(0,256))[0]
        if display.get('gamut') and not display.get('proof_path'):
            data[gamut]=[245,40,140]
        pixels[row:row+len(data)]=data
    if display.get('proof_path'):
        pixels=soft_proof(pixels,display['proof_path'],display['proof_sha'],display.get('gamut',False))
    return pixels,hist.tolist(),out_count/(w*h)*100


def make_thumbnail(path, recipe, cache, budget_mb, orientation=0):
    """Render a 320-pixel edited thumbnail using the same geometry/color pipeline."""
    existing=cached_thumbnail(path,cache,recipe,orientation)
    if existing:
        return {'thumbnail':existing,'kind':'developed','cache_hit':True}
    target=thumbnail_path(path,cache,recipe,orientation)
    source,meta,base=base_image(path,recipe,cache,budget_mb)
    validate_camera(recipe,meta)
    plan=OrientedPlan(RenderPlan(source,recipe,320),orientation)
    plan.pixel_scale *= max(source.shape[:2])/max(meta['width'],meta['height'])
    pixels,_,_=render_u8(plan)
    if thumbnail_path(path,cache,recipe,orientation) != target:
        raise ValueError('Source or LUT changed during thumbnail processing; retry with the current file')
    write_thumbnail(Image.fromarray(pixels),target,icc_profile('srgb'),quality=88)
    return {'thumbnail':str(target),'kind':'developed','metadata':meta,
            'width':plan.width,'height':plan.height,
            'cache_keep':[base,str(Path(base).with_suffix('.json')),str(target)]}


def make_preview(path,recipe,cache,budget_mb,detail=None,display=None,include_before=True,max_edge=None,orientation=0):
    if detail and max_edge is not None:
        raise ValueError('A detail viewport cannot also request a fitted preview size')
    if max_edge is not None and (isinstance(max_edge,bool) or not isinstance(max_edge,int) or not 128 <= max_edge <= 1680):
        raise ValueError('Preview edge must be between 128 and 1680 pixels')
    cache=Path(cache);full=bool(detail)
    source,meta,base=base_image(path,recipe,cache,budget_mb,full=full)
    validate_camera(recipe,meta)
    plan=OrientedPlan(RenderPlan(source,recipe,max_edge or 0),orientation)
    if not full:
        plan.pixel_scale *= max(source.shape[:2])/max(meta['width'],meta['height'])
    rect=None
    if full:
        w=max(1,min(int(detail.get('width',1024)),2048,plan.width))
        h=max(1,min(int(detail.get('height',768)),1536,plan.height))
        cx=float(detail.get('cx',.5));cy=float(detail.get('cy',.5))
        if not math.isfinite(cx+cy): raise ValueError('Invalid viewport')
        x=max(0,min(plan.width-w,round(cx*plan.width-w/2)));y=max(0,min(plan.height-h,round(cy*plan.height-h/2)))
        rect=(x,y,w,h)
    pixels,hist,gamut=render_u8(plan,rect,display)
    key=hashlib.sha256((cache_key(path,recipe,'render-v5')+json.dumps([detail,display,include_before,max_edge,orientation],sort_keys=True)).encode()).hexdigest()
    target=cache/(key+'.png');Image.fromarray(pixels).save(target,icc_profile=icc_profile('srgb'))
    h,w=pixels.shape[:2]
    result={'preview':str(target),'metadata':meta,'histogram':hist,
            'clipped_percent':round(gamut,2),'width':w,'height':h,'full_width':plan.width,'full_height':plan.height,
            'detail':full,'roi':rect,'cache_keep':[base,str(Path(base).with_suffix('.json')),str(target)]}
    canonical=plan.base
    result['geometry']={'orientation':orientation,'crop_box':[canonical.x0/canonical.sw,canonical.y0/canonical.sh,
        (canonical.x0+canonical.crop_w)/canonical.sw,(canonical.y0+canonical.crop_h)/canonical.sh]}
    if not include_before:
        return result
    before_path=cache/(key+'-before.png')
    # A baseline keeps the same geometric corrections so split comparison aligns.
    keep=('rotation','crop','crop_box','straighten','perspective_h','perspective_v','geometry_scale','distortion','ca_red','ca_blue')
    baseline=Recipe(**{k:getattr(recipe,k) for k in keep})
    base_source,_,base_before=base_image(path,baseline,cache,budget_mb,full=full)
    before_plan=OrientedPlan(RenderPlan(base_source,baseline,max_edge or 0),orientation)
    if not full:
        before_plan.pixel_scale *= max(base_source.shape[:2])/max(meta['width'],meta['height'])
    before,_,_=render_u8(before_plan,rect,display)
    Image.fromarray(before).save(before_path,icc_profile=icc_profile('srgb'))
    result['before']=str(before_path)
    result['cache_keep'].extend([base_before,str(Path(base_before).with_suffix('.json')),str(before_path)])
    return result


def estimate_export_bytes(width,height,options,fmt):
    if options.max_edge and max(width,height)>options.max_edge:
        scale=options.max_edge/max(width,height);width=max(1,round(width*scale));height=max(1,round(height*scale))
    # JPEG quality depends on content; use conservative 6 bytes/pixel plus scratch.
    return int(width*height*(6 if fmt=='tiff16' else 9)+4*1024**2)


def export_image(path,recipe,destination,fmt,budget_mb,job_id,options=None,cache=None,metadata_snapshot=None,orientation=0):
    options=ExportOptions.parse(options) if not isinstance(options,ExportOptions) else options
    if fmt not in ('tiff16','jpeg'): raise ValueError('Unknown export format')
    from .export_metadata import xmp_packet, jpeg_segments
    snapshot=metadata_snapshot or {}
    packet=xmp_packet(snapshot)
    segments=jpeg_segments(snapshot) if fmt=='jpeg' else b''
    dest=Path(destination).resolve(strict=True);source_path=Path(path).resolve(strict=True)
    own_cache=None
    if cache is None:
        own_cache=tempfile.TemporaryDirectory(prefix='.lumaraw-cache-',dir=dest);cache=Path(own_cache.name)
    temp=None;scratch=None
    try:
        source,meta,_=base_image(source_path,recipe,cache,budget_mb,full=True)
        validate_camera(recipe,meta)
        plan=OrientedPlan(RenderPlan(source,recipe,options.max_edge),orientation);h,w=plan.height,plan.width
        required=estimate_export_bytes(w,h,options,fmt)
        if shutil.disk_usage(dest).free<required+64*1024**2:
            raise OSError(f'Insufficient output disk space; estimated minimum is {required/1024**2:.0f} MB plus 64 MB headroom')
        fd,name=tempfile.mkstemp(prefix=f'.lumaraw-{job_id}-',suffix='.part',dir=dest);os.close(fd);temp=Path(name)
        if fmt=='tiff16':
            def strips():
                for y in range(0,h,ROWS):
                    rgb,_=render_strip(plan,0,y,w,min(ROWS,h-y),options.space,options.output_sharpen)
                    yield np.rint(rgb*65535).astype(np.uint16)
            tifffile.imwrite(temp,data=strips(),shape=(h,w,3),dtype=np.uint16,photometric='rgb',rowsperstrip=ROWS,metadata=None,
                             software='LumaRAW 0.4.1',iccprofile=icc_profile(options.space),bigtiff=h*w*6>3_800_000_000,
                             extratags=[(700,'B',len(packet),packet,True)] if packet else [])
        else:
            fd,name=tempfile.mkstemp(prefix=f'.lumaraw-{job_id}-',suffix='.pixels',dir=dest);os.close(fd);scratch=Path(name)
            pixels=np.memmap(scratch,mode='w+',dtype=np.uint8,shape=(h,w,3))
            for y in range(0,h,ROWS):
                rgb,_=render_strip(plan,0,y,w,min(ROWS,h-y),options.space,options.output_sharpen)
                pixels[y:y+len(rgb)]=np.rint(rgb*255).astype(np.uint8)
            pixels.flush();Image.fromarray(pixels).save(temp,format='JPEG',quality=options.quality,subsampling=0,icc_profile=icc_profile(options.space),extra=segments);del pixels
        with temp.open('rb') as f: os.fsync(f.fileno())
        stem=options.name.format(stem=source_path.stem,seq=job_id,width=w,height=h,space=options.space)
        # Sanitize only the source-derived stem; templates themselves were validated.
        stem=''.join('_' if c in '/\\:<>"|?*' or ord(c)<32 else c for c in stem)[:180].strip('. ')
        if not stem: stem=f'Luma-{job_id}'
        if stem.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}:stem='Luma-'+stem
        suffix='.tif' if fmt=='tiff16' else '.jpg';index=0
        while True:
            target=dest/(stem+(f'-{index}' if index else '')+suffix)
            try: os.link(temp,target);break
            except FileExistsError: index+=1
        return {'output':str(target),'width':w,'height':h,'metadata':meta,'space':options.space}
    finally:
        if temp: temp.unlink(missing_ok=True)
        if scratch: scratch.unlink(missing_ok=True)
        if own_cache: own_cache.cleanup()
