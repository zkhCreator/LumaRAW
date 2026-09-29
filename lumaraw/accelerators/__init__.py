"""Portable compute adapter with optional Metal, deterministic CPU reference/fallback.

Inputs: linear FP32 tiles, validated recipes and output spaces. Outputs: encoded
RGB/gamut plus per-request evidence. NEF unpack/demosaic stay in LibRaw. Metal never
changes RAW decoding, ICC definitions, recipe semantics or publication rules.
CPU handles geometry/detail and complex masks/LUTs; their output can use Metal's
color transform. A failed GPU command never exposes a partial output buffer.
"""
import ctypes as C
from pathlib import Path
import os
import sys
import time
import numpy as np

_context=None
_mode=os.environ.get('LUMARAW_COMPUTE','auto')
_limit=100*1024**2
_stats={}
_disabled=''
PARAMETER_COUNT=640

def configure(mode='auto',budget_mb=4096):
    global _mode,_limit,_stats,_disabled,_context
    if mode not in ('auto','cpu','metal'):raise ValueError('Compute backend must be auto, cpu or metal')
    if _context is not None:_context.close()
    _context=None;_mode=mode;_limit=min(100*1024**2,int(budget_mb*1024**2*.15));_disabled=''
    _stats={'requested':mode,'metal_grade_tiles':0,'metal_output_tiles':0,'cpu_tiles':0,'gpu_seconds':0.,'dispatch_seconds':0.,'initialization_seconds':0.,'shared_buffer_peak_mb':0.,'fallback_reasons':[]}

class Metal:
    def __init__(self):
        if sys.platform!='darwin':raise RuntimeError('Metal is available only on macOS')
        root=Path(__file__).parent
        self.lib=C.CDLL(str(root/'libLumaMetal.dylib'))
        lib=self.lib
        try:
            parameter_count=lib.lr_metal_parameter_count
        except AttributeError as error:
            raise RuntimeError('Metal adapter is outdated; rebuild it for this engine') from error
        parameter_count.argtypes=[];parameter_count.restype=C.c_uint
        if parameter_count()!=PARAMETER_COUNT:
            raise RuntimeError('Metal adapter parameter layout does not match this engine')
        lib.lr_metal_create.argtypes=[C.c_char_p,C.c_size_t,C.c_char_p,C.c_size_t];lib.lr_metal_create.restype=C.c_void_p
        lib.lr_metal_destroy.argtypes=[C.c_void_p];lib.lr_metal_destroy.restype=None
        lib.lr_metal_run_v2.argtypes=[C.c_void_p,C.c_void_p,C.c_void_p,C.c_void_p,C.c_uint,C.c_void_p,C.c_uint,C.c_char_p,C.c_size_t];lib.lr_metal_run_v2.restype=C.c_int
        lib.lr_metal_device.argtypes=[C.c_void_p];lib.lr_metal_device.restype=C.c_char_p
        lib.lr_metal_allocated.argtypes=[C.c_void_p];lib.lr_metal_allocated.restype=C.c_size_t
        lib.lr_metal_seconds.argtypes=[C.c_void_p];lib.lr_metal_seconds.restype=C.c_double
        error=C.create_string_buffer(4096)
        self.handle=lib.lr_metal_create((root/'grade.metal').read_bytes(),_limit,error,len(error))
        if not self.handle:raise RuntimeError(error.value.decode(errors='replace'))
        self.device=lib.lr_metal_device(self.handle).decode()
    def close(self):
        if self.handle:self.lib.lr_metal_destroy(self.handle);self.handle=None
    def run(self,a,p):
        if p.dtype!=np.float32 or p.shape!=(PARAMETER_COUNT,) or not p.flags.c_contiguous:
            raise RuntimeError('Invalid Metal parameter buffer')
        a=np.ascontiguousarray(a,dtype=np.float32);out=np.empty_like(a);mask=np.empty(a.shape[:2],np.uint8)
        error=C.create_string_buffer(4096)
        rc=self.lib.lr_metal_run_v2(self.handle,a.ctypes.data,out.ctypes.data,mask.ctypes.data,mask.size,p.ctypes.data,p.size,error,len(error))
        if rc:raise RuntimeError(error.value.decode(errors='replace') or f'Metal error {rc}')
        return out,mask.astype(bool)

def packed(recipe,space,output_only=False):
    from ..imaging import LUMA
    from ..model import MIXER_BANDS,POINT_CURVE_FIELDS
    from ..curves import is_identity,packed_curve
    from ..parametric import active,packed as parametric_packed
    from ..color import output_matrix,SRGB_FROM_WORK,WORK_FROM_SRGB
    p=np.zeros(PARAMETER_COUNT,np.float32);r=recipe
    p[:12]=[int(output_only),2**r.exposure,r.shadows/100,r.highlights/100,r.blacks/100,r.whites/100,r.contrast/200,1+r.saturation/100,r.vibrance/100,int(r.monochrome),int(any([r.curve_shadows,r.curve_midtones,r.curve_lights])),len(r.curve_points) if r.curve_points!=[[0.,0.],[1.,1.]] else 0]
    p[12:15]=LUMA;p[16:25]=np.asarray(r.camera_profile.get('matrix',np.eye(3)),np.float32).ravel()
    p[28:37]=output_matrix(space).ravel();p[38]=['srgb','adobe','p3','prophoto'].index(space)
    for i,name in enumerate(MIXER_BANDS):
        p[176+4*i:180+4*i]=[getattr(r,name+'_hue'),getattr(r,name+'_sat'),
                            getattr(r,name+'_lum'),getattr(r,name+'_bw')]
    p[39]=int(np.any(p[176:208].reshape(8,4)[:,:3]))
    p[48]=int(r.monochrome and np.any(p[179:208:4]))
    p[53]=int(active(r))
    if p[53]:p[592:608]=parametric_packed(r).ravel()
    for i,name in enumerate(POINT_CURVE_FIELDS):
        points=getattr(r,name)
        if not is_identity(points):
            block=packed_curve(points).ravel();start=208+i*96
            p[49+i]=len(points);p[start:start+len(block)]=block
    values=np.maximum.accumulate(np.clip([0,.25+r.curve_shadows/100,.5+r.curve_midtones/100,.75+r.curve_lights/100,1],0,1))
    p[64:74]=np.column_stack(([0,.25,.5,.75,1],values)).ravel()
    points=np.asarray(r.curve_points,np.float32).ravel();p[80:80+len(points)]=points
    matrices=[SRGB_FROM_WORK,[[.41222147,.53633254,.05144599],[.21190350,.68069955,.10739696],[.08830246,.28171884,.62997870]],[[.21045426,.79361779,-.00407205],[1.97799850,-2.42859221,.45059371],[.02590404,.78277177,-.80867577]],[[1,.39633778,.21580376],[1,-.10556135,-.06385417],[1,-.08948418,-1.29148555]],[[4.07674166,-3.30771159,.23096993],[-1.26843800,2.60975740,-.34131940],[-.00419609,-.70341861,1.70761470]],WORK_FROM_SRGB]
    for i,m in enumerate(matrices):p[120+i*9:129+i*9]=np.asarray(m,np.float32).ravel()
    return p

def reason(text):
    if text not in _stats['fallback_reasons']:_stats['fallback_reasons'].append(text)

def grade_output(a,recipe,space,x=0,y=0,total_w=None,total_h=None):
    global _context,_disabled
    from ..render import grade_tile
    from ..color import to_output
    from ..curves import reference_required
    if not _stats:configure(_mode)
    def cpu():
        _stats['cpu_tiles']+=1
        return to_output(grade_tile(a,recipe,x,y,total_w,total_h),space)
    if _mode=='cpu':return cpu()
    count=a.shape[0]*a.shape[1]
    if count*25>_limit or count>4000000:
        reason('tile_exceeds_bounded_gpu_buffer');return cpu()
    if _mode=='auto' and count<16384:
        reason('small_tile_uses_cpu');return cpu()
    if _disabled:
        reason(_disabled);return cpu()
    try:
        if _context is None:
            start=time.perf_counter()
            try:_context=Metal()
            finally:_stats['initialization_seconds']+=time.perf_counter()-start
        sharp_curve=reference_required(recipe)
        if sharp_curve:reason('steep_point_curve_uses_cpu_grade')
        complex_recipe=sharp_curve or any(m.get('enabled',True) for m in recipe.masks) or (bool(recipe.lut) and recipe.lut_amount!=0)
        data=grade_tile(a,recipe,x,y,total_w,total_h) if complex_recipe else a
        params=packed(recipe,space,complex_recipe)
        start=time.perf_counter();out=_context.run(data,params)
        _stats['dispatch_seconds']+=time.perf_counter()-start
        _stats['gpu_seconds']+=_context.lib.lr_metal_seconds(_context.handle)
        _stats['shared_buffer_peak_mb']=max(_stats['shared_buffer_peak_mb'],_context.lib.lr_metal_allocated(_context.handle)/1024**2)
        _stats['metal_output_tiles' if complex_recipe else 'metal_grade_tiles']+=1
        return out
    except (OSError,RuntimeError) as error:
        if _mode=='metal':raise RuntimeError(f'Metal requested but failed: {error}') from error
        _disabled='metal_unavailable_or_failed: '+str(error);reason(_disabled)
        if _context is not None:_context.close();_context=None
        return cpu()

def report():
    if not _stats:configure(_mode)
    gpu=_stats['metal_grade_tiles']+_stats['metal_output_tiles']
    result={**_stats,'backend':'hybrid' if gpu and (_stats['cpu_tiles'] or _stats['metal_output_tiles']) else 'metal' if gpu else 'cpu','device':_context.device if _context else None,'raw_decode_backend':'LibRaw CPU','gpu_buffer_limit_mb':round(_limit/1024**2,2)}
    return {k:round(v,6) if isinstance(v,float) else v for k,v in result.items()}

def availability():
    return {'platform_supported':sys.platform=='darwin','library_present':(Path(__file__).parent/'libLumaMetal.dylib').is_file(),'probe':'Actual device availability is checked inside each image worker'}
