"""Review rendering and cancellation contracts using synthetic read-only originals.

Verifies optional baseline work, bounded fitted output, exact detail pixels,
lightweight summaries and client-specific invalidation with real subprocesses.
No Lightroom color equivalence or native desktop interaction claim.
"""
import hashlib
from pathlib import Path
import subprocess
import sys

import numpy as np
from PIL import Image
import pytest

from lumaraw import render
from lumaraw.model import Recipe
from lumaraw.service import Service


@pytest.fixture
def photo(tmp_path):
    x=np.linspace(0,255,800,dtype=np.uint8)[None,:]
    y=np.linspace(0,255,600,dtype=np.uint8)[:,None]
    pixels=np.stack(np.broadcast_arrays(x,y,x//2+y//2),axis=-1)
    path=tmp_path/'review.png';Image.fromarray(pixels).save(path)
    return path


def test_review_skips_baseline_without_changing_edited_pixels(photo,tmp_path,monkeypatch):
    before=hashlib.sha256(photo.read_bytes()).hexdigest()
    recipe=Recipe(exposure=.4,sharpen=20,crop='4:5')
    expected=render.make_preview(photo,recipe,tmp_path/'cache',2048)
    with Image.open(expected['preview']) as image: pixels=np.array(image)
    actual_render=render.render_u8;calls=[]
    def counted(*args,**kwargs):
        calls.append(1)
        return actual_render(*args,**kwargs)
    monkeypatch.setattr(render,'render_u8',counted)
    result=render.make_preview(photo,recipe,tmp_path/'cache',2048,include_before=False)
    assert len(calls)==1 and 'before' not in result
    assert not Path(result['preview']).with_stem(Path(result['preview']).stem+'-before').exists()
    with Image.open(result['preview']) as image:
        np.testing.assert_array_equal(np.array(image),pixels)
        assert image.info.get('icc_profile')
    assert hashlib.sha256(photo.read_bytes()).hexdigest()==before


def test_survey_size_and_detail_viewport_are_distinct(photo,tmp_path):
    recipe=Recipe(exposure=.2)
    fitted=render.make_preview(photo,recipe,tmp_path/'cache',2048,include_before=False,max_edge=256)
    assert (fitted['width'],fitted['height']) == (256,192)
    assert fitted['detail'] is False
    whole=render.make_preview(photo,recipe,tmp_path/'cache',2048,
        detail={'width':800,'height':600},include_before=False)
    detail=render.make_preview(photo,recipe,tmp_path/'cache',2048,
        detail={'width':200,'height':160,'cx':.75,'cy':.6},include_before=False)
    x,y,w,h=detail['roi']
    with Image.open(whole['preview']) as image: expected=np.array(image)[y:y+h,x:x+w]
    with Image.open(detail['preview']) as image: np.testing.assert_array_equal(np.array(image),expected)
    assert (detail['full_width'],detail['full_height']) == (800,600)
    with pytest.raises(ValueError,match='cannot also'):
        render.make_preview(photo,recipe,tmp_path/'cache',2048,detail={'width':200},max_edge=256)


def test_review_api_and_summaries_exclude_heavy_payloads(photo,tmp_path):
    service=Service(tmp_path/'catalog')
    try:
        service.dispatch('queue_control',{'action':'pause'})
        service.dispatch('import_photos',{'paths':[str(photo)]})
        service.dispatch('edit_photo',{'photo_id':1,'expected_revision':0,'patch':{'exposure':.5}})
        rows=service.dispatch('photo_summaries',{'photo_ids':[1,1,999]})['photos']
        assert len(rows)==1 and rows[0]['revision']==1
        assert 'recipe' not in rows[0] and 'metadata' not in rows[0]
        preview=service.dispatch('preview_photo',{'photo_id':1,'include_before':False,'max_edge':256})
        assert preview['revision']==1 and preview['width']==256 and 'before' not in preview
        service.dispatch('cancel_preview',{'client_id':'review','generation':10})
        with pytest.raises(InterruptedError,match='superseded'):
            service.dispatch('preview_photo',{'photo_id':1,'client_id':'review','generation':9})
        assert service.dispatch('cancel_preview',{'client_id':'review','generation':8})['superseded']
    finally:
        service.close()


def test_cancel_only_stops_older_preview_of_same_client(tmp_path):
    service=Service(tmp_path/'catalog')
    process=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])
    try:
        service.dispatch('queue_control',{'action':'pause'})
        with service.state_lock:
            service.process=process
            service.active={'operation':'preview','client_id':'review-A','generation':1}
        assert not service.dispatch('cancel_preview',{'client_id':'review-B','generation':5})['cancelled']
        assert process.poll() is None
        assert not service.dispatch('cancel_preview',{'client_id':'review-A','generation':1})['cancelled']
        assert process.poll() is None
        assert service.dispatch('cancel_preview',{'client_id':'review-A','generation':2})['cancelled']
        process.wait(timeout=5)
        assert process.returncode != 0
        service.active=None
    finally:
        if process.poll() is None:process.kill();process.wait()
        service.active=None;service.close()


def test_cancel_preview_preserves_export_even_with_same_client_label(tmp_path):
    service=Service(tmp_path/'catalog')
    process=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])
    try:
        service.dispatch('queue_control',{'action':'pause'})
        with service.state_lock:
            service.process=process
            service.active={'operation':'export','client_id':'review-A','generation':1}
        assert not service.dispatch('cancel_preview',{'client_id':'review-A','generation':2})['cancelled']
        assert process.poll() is None
    finally:
        process.kill();process.wait();service.active=None;service.close()
