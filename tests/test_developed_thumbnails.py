"""Developed-grid correctness, cache identity and cancellation regressions.

Generated color gradients verify geometry/color against the shared fitted preview,
warm worker bypass, metadata independence, undo reuse, source/LUT invalidation and
late revision labels. No camera-specific accuracy or desktop acceptance claim.
"""
import hashlib
import subprocess
import sys

import numpy as np
from PIL import Image
import pytest

from lumaraw.model import Recipe
from lumaraw.render import make_preview, make_thumbnail
from lumaraw.service import Service
from lumaraw.source_identity import cached_thumbnail, thumbnail_path


@pytest.fixture
def photo(tmp_path):
    x=np.linspace(0,220,800,dtype=np.uint8)[None,:]
    y=np.linspace(0,220,600,dtype=np.uint8)[:,None]
    path=tmp_path/'gradient.png'
    Image.fromarray(np.stack(np.broadcast_arrays(x,y,x//2+y//2),axis=-1)).save(path)
    return path


@pytest.mark.parametrize('patch',[
    {'exposure':1.2,'monochrome':True},
    {'rotation':90,'crop_box':[.1,.05,.8,.9],'crop':'4:5'},
    {'temperature':20,'shadows':15,'blue_sat':-50,'sharpen':40,
     'masks':[{'kind':'radial','x':.4,'y':.5,'exposure':-1}]},
])
def test_developed_thumbnail_matches_edited_preview(photo,tmp_path,patch):
    original=hashlib.sha256(photo.read_bytes()).hexdigest()
    recipe=Recipe.parse(patch)
    thumb=make_thumbnail(photo,recipe,tmp_path/'cache',2048)
    preview=make_preview(photo,recipe,tmp_path/'cache',2048,include_before=False,max_edge=320)
    with Image.open(thumb['thumbnail']) as image, Image.open(preview['preview']) as expected:
        assert image.size==expected.size and max(image.size)<=320
        assert image.info.get('icc_profile')==expected.info.get('icc_profile')
        # JPEG output has quantization/chroma subsampling; compare the whole image.
        error=np.abs(np.asarray(image).astype(float)-np.asarray(expected).astype(float))
        assert error.mean()<1.3 and np.quantile(error,.99)<5
    assert hashlib.sha256(photo.read_bytes()).hexdigest()==original


def test_recipe_cache_invalidation_metadata_independence_and_undo(photo,tmp_path,monkeypatch):
    service=Service(tmp_path/'catalog')
    try:
        service.dispatch('queue_control',{'action':'pause'})
        service.dispatch('import_photos',{'paths':[str(photo)]})
        source=service.dispatch('thumbnail',{'photo_id':1})
        initial=service.dispatch('thumbnail',{'photo_id':1,'kind':'developed'})
        assert source['thumbnail'] != initial['thumbnail']
        service.dispatch('edit_photo',{'photo_id':1,'expected_revision':0,'patch':{'exposure':1}})
        assert service.dispatch('cached_thumbnails',{'photo_ids':[1],'kind':'developed'})['thumbnails']==[]
        edited=service.dispatch('thumbnail',{'photo_id':1,'kind':'developed'})
        assert edited['revision']==1 and edited['thumbnail'] != initial['thumbnail']
        def forbidden(*args,**kwargs):raise AssertionError('Cache hit must not start a worker')
        monkeypatch.setattr(service,'run_worker',forbidden)
        service.dispatch('edit_metadata',{'targets':[{'photo_id':1,'expected_metadata_revision':0}],
                                         'patch':{'title':'Only metadata','keywords':['test']}})
        warm=service.dispatch('thumbnail',{'photo_id':1,'kind':'developed'})
        assert warm['cache_hit'] and warm['thumbnail']==edited['thumbnail'] and warm['revision']==1
        service.dispatch('undo_photo',{'photo_id':1,'expected_revision':1})
        page=service.dispatch('cached_thumbnails',{'photo_ids':[1,1],'kind':'developed'})
        assert page['thumbnails']==[{'photo_id':1,'revision':2,'kind':'developed',
                                    'thumbnail':initial['thumbnail'],'source':str(photo)}]
        assert service.dispatch('thumbnail',{'photo_id':1,'kind':'developed'})['thumbnail']==initial['thumbnail']
        Image.new('RGB',(800,600),'red').save(photo)
        assert service.dispatch('cached_thumbnails',{'photo_ids':[1],'kind':'developed'})['thumbnails']==[]
    finally:
        service.close()


def test_external_lut_change_cannot_reuse_thumbnail(photo,tmp_path):
    lut=tmp_path/'look.cube';lut.write_text('LUT_3D_SIZE 2\n0 0 0\n')
    recipe=Recipe(lut={'path':str(lut),'sha256':hashlib.sha256(lut.read_bytes()).hexdigest()})
    cache=tmp_path/'cache';cache.mkdir()
    target=thumbnail_path(photo,cache,recipe)
    Image.new('RGB',(50,40),'green').save(target)
    assert cached_thumbnail(photo,cache,recipe)==str(target)
    lut.write_text('changed asset contents')
    assert cached_thumbnail(photo,cache,recipe) is None
    lut.unlink()
    assert cached_thumbnail(photo,cache,recipe) is None


def test_source_change_during_render_does_not_publish_wrong_identity(photo,tmp_path,monkeypatch):
    from lumaraw import render
    real=render.render_u8
    def changing(*args,**kwargs):
        result=real(*args,**kwargs)
        Image.new('RGB',(801,601),'red').save(photo)
        return result
    monkeypatch.setattr(render,'render_u8',changing)
    with pytest.raises(ValueError,match='changed during'):
        make_thumbnail(photo,Recipe(),tmp_path/'cache',2048)
    assert cached_thumbnail(photo,tmp_path/'cache',Recipe()) is None


def test_thumbnail_reply_keeps_captured_recipe_revision(photo,tmp_path,monkeypatch):
    service=Service(tmp_path/'catalog')
    try:
        service.dispatch('queue_control',{'action':'pause'})
        service.dispatch('import_photos',{'paths':[str(photo)]})
        real=service.run_worker
        def external_edit(request):
            service.dispatch('edit_photo',{'photo_id':1,'expected_revision':0,'patch':{'exposure':2}})
            return real(request)
        monkeypatch.setattr(service,'run_worker',external_edit)
        result=service.dispatch('thumbnail',{'photo_id':1,'kind':'developed'})
        assert result['revision']==0
        assert service.dispatch('get_photo',{'photo_id':1})['revision']==1
        assert service.dispatch('cached_thumbnails',{'photo_ids':[1],'kind':'developed'})['thumbnails']==[]
    finally:
        service.close()


def test_page_generation_cancels_only_obsolete_thumbnail_worker(tmp_path):
    service=Service(tmp_path/'catalog')
    process=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])
    try:
        service.dispatch('queue_control',{'action':'pause'})
        with service.state_lock:
            service.process=process
            service.active={'operation':'thumbnail','client_id':'page','generation':1}
        assert service.dispatch('cancel_preview',{'client_id':'page','generation':2})['cancelled']
        process.wait(timeout=5)
        assert process.returncode != 0
    finally:
        if process.poll() is None:process.kill();process.wait()
        service.active=None;service.close()
