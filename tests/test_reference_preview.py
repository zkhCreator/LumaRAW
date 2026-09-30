"""Revision-bound ordinary previews for independent Reference/Active workflows.

Generated photographs and real workers establish stale-read rejection, bounded
geometry and unchanged catalog/recipe/original state. Injected edits during work
prove the second revision check. No Adobe color or desktop equivalence claim.
"""
import jsonschema
from PIL import Image
import pytest

from lumaraw.service import ConflictError, Service


@pytest.fixture
def library(tmp_path):
    path=tmp_path/'reference.png';Image.new('RGB',(480,320),(30,70,150)).save(path)
    s=Service(tmp_path/'catalog',presets_root=tmp_path/'presets')
    s.dispatch('queue_control',{'action':'pause'})
    s.dispatch('import_photos',{'paths':[str(path)]})
    yield s,path
    s.close()


def test_expected_revision_rejects_before_worker(library,monkeypatch):
    s,path=library;original=path.read_bytes()
    s.dispatch('edit_photo',{'photo_id':1,'expected_revision':0,'patch':{'exposure':1}})
    monkeypatch.setattr(s,'run_worker',lambda _:pytest.fail('Stale preview started worker'))
    with pytest.raises(ConflictError):
        s.dispatch('preview_photo',{'photo_id':1,'expected_revision':0,'include_before':False})
    assert path.read_bytes()==original


def test_expected_revision_rejects_edit_during_worker(library,monkeypatch):
    s,_=library
    def worker(request):
        assert request['recipe']['exposure']==0 and 'expected_revision' not in request
        s.dispatch('edit_photo',{'photo_id':1,'expected_revision':0,'patch':{'exposure':.5}})
        return {'preview':'unreturned.png','metadata':{'camera':'STALE'}}
    monkeypatch.setattr(s,'run_worker',worker)
    with pytest.raises(ConflictError):
        s.dispatch('preview_photo',{'photo_id':1,'expected_revision':0,'include_before':False})
    p=s.dispatch('get_photo',{'photo_id':1})
    assert p['revision']==1 and p['recipe']['exposure']==.5 and p['metadata'].get('camera')!='STALE'


def test_bound_preview_rejects_source_change_during_worker(library,monkeypatch):
    s,path=library
    def worker(request):
        Image.new('RGB',(481,320),'red').save(path)
        return {'preview':'unreturned.png','metadata':{'camera':'STALE'}}
    monkeypatch.setattr(s,'run_worker',worker)
    with pytest.raises(ValueError,match='Source changed during preview'):
        s.dispatch('preview_photo',{'photo_id':1,'expected_revision':0,'include_before':False})
    assert s.dispatch('get_photo',{'photo_id':1})['metadata'].get('camera')!='STALE'


def test_bound_fit_detail_preserve_history_and_before(library):
    s,path=library;original=path.read_bytes()
    before=s.dispatch('get_photo',{'photo_id':1})
    history=s.dispatch('list_history',{'photo_id':1,'expected_revision':0})
    params={'photo_id':1,'expected_revision':0,'include_before':False}
    fit=s.dispatch('preview_photo',{**params,'max_edge':256})
    detail=s.dispatch('preview_photo',{**params,'detail':{'width':180,'height':120,'cx':.9,'cy':.8}})
    assert (fit['width'],fit['height'])==(256,171) and 'before' not in fit
    assert detail['roi']==[300,196,180,120] and detail['revision']==0
    assert detail['geometry']['orientation']==0
    for reply in (fit,detail):
        with Image.open(reply['preview']) as im:assert im.info.get('icc_profile')
    after=s.dispatch('get_photo',{'photo_id':1})
    assert before['recipe']==after['recipe'] and after['revision']==0
    assert history==s.dispatch('list_history',{'photo_id':1,'expected_revision':0})
    assert path.read_bytes()==original


def test_metadata_change_does_not_conflict_with_visual_revision(library,monkeypatch):
    s,_=library
    def worker(request):
        s.dispatch('rate_photo',{'photo_id':1,'rating':5})
        return {'preview':'unchanged-visual.png'}
    monkeypatch.setattr(s,'run_worker',worker)
    result=s.dispatch('preview_photo',{'photo_id':1,'expected_revision':0,'include_before':False})
    assert result['revision']==0 and s.dispatch('get_photo',{'photo_id':1})['rating']==5


def test_expected_revision_contract_retains_legacy_reads(library,monkeypatch):
    s,_=library;monkeypatch.setattr(s,'run_worker',lambda _:{'preview':'legacy.png'})
    assert s.dispatch('preview_photo',{'photo_id':1,'include_before':False})['revision']==0
    for value in (-1,True,'0'):
        with pytest.raises(jsonschema.ValidationError):
            s.dispatch('preview_photo',{'photo_id':1,'expected_revision':value})
