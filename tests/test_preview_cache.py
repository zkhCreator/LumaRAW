"""Completed preview reuse, invalidation and broker safety through real workers.

Generated originals exercise full receipts, corruption, source/asset identity,
revisions and cancellation without UI automation. Cache hits must avoid both
pixel libraries and image-worker admission; no desktop latency claim is implied.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

from PIL import Image
import pytest

from lumaraw import preview_cache
from lumaraw.model import Recipe
from lumaraw.runtime import engine_identity
from lumaraw.service import ConflictError, Service


@pytest.fixture
def library(tmp_path):
    path=tmp_path/'photo.png';Image.new('RGB',(480,320),(30,70,150)).save(path)
    s=Service(tmp_path/'catalog',presets_root=tmp_path/'presets')
    s.dispatch('queue_control',{'action':'pause'})
    s.dispatch('settings',{'compute_backend':'cpu'})
    s.dispatch('import_photos',{'paths':[str(path)]})
    yield s,path
    s.close()


def params(**extra):
    return {'photo_id':1,'expected_revision':0,'include_color_readouts':True,**extra}


def request(s,path,**extra):
    photo=s.dispatch('get_photo',{'photo_id':1})
    return {'path':str(path),'recipe':photo['recipe'],'orientation':photo['orientation'],
            'include_before':False,**extra}


def test_completed_hit_preserves_all_outputs_and_bypasses_busy_worker(library,monkeypatch):
    s,path=library;original=path.read_bytes()
    options=params(include_curve_tones=True,mixer_target='hsl')
    first=s.dispatch('preview_photo',options)
    assert first['worker_spawned'] and not first['preview_cache_hit']
    assert len(list(s.cache.glob('*.preview.json')))==1
    photo=s.dispatch('get_photo',{'photo_id':1})
    def forbidden(_):pytest.fail('Completed preview started a worker')
    monkeypatch.setattr(s,'run_worker',forbidden)
    # A busy export must not block an already complete preview.
    with s.image_lock:
        hit=s.dispatch('preview_photo',options)
    assert hit['preview_cache_hit'] and not hit['worker_spawned'] and hit['peak_mb']==0
    assert hit['processing']['backend']=='cache' and hit['processing']['metal_grade_tiles']==0
    assert hit['processing']['cpu_tiles']==0 and hit['processing']['worker_seconds']==0
    for field in ('preview','before','histogram','clipped_percent','geometry','roi','metadata','width','height'):
        assert hit[field]==first[field]
    for field in preview_cache.MAPS:
        assert hit[field]['path']==first[field]['path'] and hit[field]['cache_hit']
        assert hit[field]['path'] in hit['cache_keep']
    assert hit['before_cache_hit']
    assert s.dispatch('get_photo',{'photo_id':1})==photo and path.read_bytes()==original


def test_completed_preview_survives_restart_and_decoded_source_eviction(library,monkeypatch):
    s,path=library;options=params(include_before=False,detail={'width':200,'height':130,'cx':.8,'cy':.7})
    first=s.dispatch('preview_photo',options)
    for base in s.cache.glob('*.npy'):base.unlink()
    s.close()
    restored=Service(s.root,presets_root=s.root/'presets')
    try:
        monkeypatch.setattr(restored,'run_worker',lambda _:pytest.fail('Hit decoded the source again'))
        hit=restored.dispatch('preview_photo',options)
        assert hit['preview_cache_hit'] and hit['roi']==first['roi']
        assert 'before' not in hit and not list(s.cache.glob('*.npy'))
    finally:restored.close()


@pytest.mark.parametrize('extra',[
    {'max_edge':256},{'include_before':False},{'include_color_readouts':False},
    {'detail':{'width':180,'height':120}},{'include_curve_tones':True},
    {'mixer_target':'hsl'},{'display':{'gamut':True}},
    {'curve_patch':{'parametric_darks':20}},{'mixer_patch':{'blue_hue':12}}])
def test_visual_options_never_reuse_wrong_completed_receipt(library,extra):
    s,_=library;s.dispatch('preview_photo',params())
    changed=s.dispatch('preview_photo',params(**extra))
    assert changed['worker_spawned'] and not changed['preview_cache_hit']
    assert s.dispatch('preview_photo',params(**extra))['preview_cache_hit']


def test_keys_bind_backend_engine_source_lut_and_proof_assets(library,tmp_path):
    s,path=library;r=request(s,path);identity=engine_identity()
    first=preview_cache.key(r,identity,'cpu')
    assert first!=preview_cache.key(r,identity,'metal')
    assert first!=preview_cache.key(r,{**identity,'digest':'f'*64},'cpu')
    assert first==preview_cache.key({**r,'client_id':'another','generation':99},identity,'cpu')
    lut=tmp_path/'lut.cube';lut.write_bytes(b'asset one')
    proof=tmp_path/'proof.icc';proof.write_bytes(b'profile one')
    r={**r,'recipe':{**r['recipe'],'lut':{'path':str(lut),'sha256':'0'*64}},
       'display':{'proof_path':str(proof),'proof_sha':'1'*64}}
    a=preview_cache.key(r,identity,'cpu');lut.write_bytes(b'changed external LUT')
    b=preview_cache.key(r,identity,'cpu');proof.write_bytes(b'changed external proof')
    c=preview_cache.key(r,identity,'cpu');assert len({a,b,c})==3
    proof.unlink();assert preview_cache.key(r,identity,'cpu') is None
    Image.new('RGB',(481,320),'red').save(path)
    assert preview_cache.key(request(s,path),identity,'cpu')!=first


@pytest.mark.parametrize('damage',['missing','png_header','png_body','readout','manifest','traversal','symlink'])
def test_incomplete_or_corrupt_artifacts_fall_back_without_returning_them(library,monkeypatch,damage):
    s,path=library;first=s.dispatch('preview_photo',params())
    target=Path(first['preview']);manifest=next(s.cache.glob('*.preview.json'))
    if damage=='missing':target.unlink()
    elif damage=='png_header':target.write_bytes(b'x'*target.stat().st_size)
    elif damage=='png_body':
        before=target.stat();data=bytearray(target.read_bytes());data[45]^=1;target.write_bytes(data)
        os.utime(target,ns=(before.st_atime_ns,before.st_mtime_ns))
    elif damage=='readout':Path(first['color_readouts']['path']).write_bytes(b'partial')
    elif damage=='manifest':manifest.write_text('{broken')
    elif damage=='traversal':
        value=json.loads(manifest.read_text());value['result']['preview']='../'+target.name
        manifest.write_text(json.dumps(value))
    elif damage=='symlink':
        target.unlink();target.symlink_to(path)
    monkeypatch.setattr(s,'run_worker',lambda _: {'cache_miss_fallback':True})
    assert s.dispatch('preview_photo',params())['cache_miss_fallback']


@pytest.mark.parametrize('change',['edit','before','source','cancel'])
def test_changes_during_cache_validation_cannot_return_stale_reply(library,monkeypatch,change):
    s,path=library;options=params(client_id='hover',generation=10)
    s.dispatch('preview_photo',options)
    original=preview_cache.load
    def racing(*args,**kwargs):
        result=original(*args,**kwargs);assert result is not None
        if change=='edit':s.dispatch('edit_photo',{'photo_id':1,'expected_revision':0,'patch':{'exposure':1}})
        elif change=='before':s.dispatch('before_after',{'photo_id':1,'expected_revision':0,'action':'after_to_before'})
        elif change=='source':Image.new('RGB',(481,320),'green').save(path)
        else:s.dispatch('cancel_preview',{'client_id':'hover','generation':11})
        return result
    monkeypatch.setattr(preview_cache,'load',racing)
    error=InterruptedError if change=='cancel' else ValueError if change=='source' else ConflictError
    with pytest.raises(error):s.dispatch('preview_photo',options)


def test_cache_hashing_accepts_cancellation_at_chunk_boundaries(library):
    s,path=library;s.dispatch('preview_photo',params(include_before=False))
    r=request(s,path,include_color_readouts=True)
    key=preview_cache.key(r,s.worker_identity,'cpu');calls=0
    def stop():
        nonlocal calls
        calls+=1
        if calls==3:raise InterruptedError('cancelled during map verification')
    with pytest.raises(InterruptedError,match='map verification'):
        preview_cache.load(s.cache,key,r,'cpu',stop)
    assert calls==3


def test_cache_module_does_not_import_pixel_libraries():
    subprocess.run([sys.executable,'-c',
        "import sys; from lumaraw import preview_cache; assert not any(m in sys.modules for m in ('numpy','PIL','rawpy','scipy'))"],check=True)


def test_replaced_before_only_lut_cannot_reuse_old_pixels(library,tmp_path):
    s,_=library
    cube=tmp_path/'identity.cube'
    cube.write_text('LUT_3D_SIZE 2\n'+'\n'.join(f'{r} {g} {b}' for b in (0,1) for g in (0,1) for r in (0,1)))
    asset=s.dispatch('import_asset',{'path':str(cube),'kind':'lut'})['asset']
    s.dispatch('edit_photo',{'photo_id':1,'expected_revision':0,'patch':{'lut':asset}})
    s.dispatch('before_after',{'photo_id':1,'expected_revision':1,'action':'after_to_before'})
    s.dispatch('edit_photo',{'photo_id':1,'expected_revision':2,'patch':{'lut':{}}})
    options=params(expected_revision=3)
    s.dispatch('preview_photo',options)
    assert s.dispatch('preview_photo',options)['preview_cache_hit']
    Path(asset['path']).write_text('changed external asset')
    with pytest.raises(RuntimeError,match='LUT has changed'):
        s.dispatch('preview_photo',options)


@pytest.mark.parametrize('field',['color_readouts','curve_tones','mixer_target'])
def test_damaged_map_body_is_rebuilt_instead_of_reused_by_worker(library,field):
    s,path=library;original=path.read_bytes()
    options=params(include_curve_tones=True,mixer_target='hsl')
    first=s.dispatch('preview_photo',options)
    target=Path(first[field]['path']);expected=target.read_bytes()
    bad=bytearray(expected);bad[32]^=64;target.write_bytes(bad)
    repaired=s.dispatch('preview_photo',options)
    assert repaired['worker_spawned'] and not repaired['preview_cache_hit']
    assert target.read_bytes()==expected
    assert s.dispatch('preview_photo',options)['preview_cache_hit']
    assert path.read_bytes()==original


@pytest.mark.parametrize('replace_file',[False,True])
def test_concurrent_cache_touches_or_atomic_replacement_never_purge_valid_maps(library,replace_file):
    s,path=library;first=s.dispatch('preview_photo',params(include_before=False))
    r=request(s,path,include_color_readouts=True)
    key=preview_cache.key(r,s.worker_identity,'cpu')
    target=Path(first['color_readouts']['path']);expected=target.read_bytes();calls=0
    def concurrent_access():
        nonlocal calls
        calls+=1
        # Initial checkpoint, small PNG checksum, then map checksum.
        if calls==3:
            if replace_file:
                temporary=target.with_suffix('.replacement');temporary.write_bytes(expected)
                os.replace(temporary,target)
            else:os.utime(target,None)
    hit=preview_cache.load(s.cache,key,r,'cpu',concurrent_access)
    assert (hit is None)==replace_file
    assert target.read_bytes()==expected
    assert preview_cache.load(s.cache,key,r,'cpu')['preview_cache_hit']
