"""Captured Sync source revisions through the real shared service contract.

Inputs: generated read-only rasters, disposable catalogs and concurrent commands.
Outputs: atomic target/history, frozen export and unchanged original assertions.
No rendering, desktop automation or Adobe numerical acceptance.
"""
import hashlib
import threading

from PIL import Image
import pytest

from lumaraw.service import Service, ConflictError


@pytest.fixture
def service(tmp_path):
    paths=[tmp_path/f'{i}.png' for i in range(3)]
    for path in paths:
        Image.new('RGB',(40,30),(80,110,150)).save(path)
    hashes=[hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
    service=Service(tmp_path/'catalog',presets_root=tmp_path/'presets')
    service.dispatch('queue_control',{'action':'pause'})
    service.dispatch('import_photos',{'paths':list(map(str,paths))})
    try:
        yield service
    finally:
        service.close()
        assert hashes==[hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]


def photo(service,id_):
    return service.dispatch('get_photo',{'photo_id':id_})


def sync(service,revision):
    return service.dispatch('sync_photos',{
        'source_id':1,'expected_source_revision':revision,'groups':['Presence'],
        'targets':[{'photo_id':2,'expected_revision':0},{'photo_id':3,'expected_revision':0}]})


def test_changed_source_rejects_all_targets_and_preserves_frozen_exports(service,tmp_path):
    first=service.dispatch('edit_photo',{'photo_id':1,'expected_revision':0,
        'patch':{'texture':45,'clarity':-35,'dehaze':55}})
    export=service.dispatch('enqueue_exports',{'photo_ids':[1],
        'destination':str(tmp_path/'exports'),'format':'tiff16','request_key':'sync-source'})
    service.dispatch('edit_photo',{'photo_id':1,'expected_revision':first['revision'],
        'patch':{'texture':-20}})
    before=[photo(service,id_) for id_ in (2,3)]
    with pytest.raises(ConflictError,match='current revision 2, requested revision 1'):
        sync(service,first['revision'])
    assert [photo(service,id_) for id_ in (2,3)]==before
    frozen=service.dispatch('get_job',{'job_id':export['job_ids'][0]})
    assert frozen['recipe']['texture']==45 and frozen['state']=='pending'
    assert sync(service,2)=={'synced':2}
    for id_ in (2,3):
        row=photo(service,id_)
        assert row['revision']==1 and row['recipe']['texture']==-20
        assert row['recipe']['clarity']==-35 and row['recipe']['dehaze']==55
        assert row['recipe']['exposure']==0
    assert photo(service,1)['revision']==2
    undo=service.dispatch('undo_photo',{'photo_id':2,'expected_revision':1})
    assert all(undo['recipe'][key]==0 for key in ('texture','clarity','dehaze'))


def test_source_returning_to_same_values_still_rejects_old_review(service):
    service.dispatch('edit_photo',{'photo_id':1,'expected_revision':0,'patch':{'texture':45}})
    reviewed=photo(service,1)
    service.dispatch('edit_photo',{'photo_id':1,'expected_revision':1,'patch':{'texture':-20}})
    restored=service.dispatch('undo_photo',{'photo_id':1,'expected_revision':2})
    assert restored['recipe']==reviewed['recipe'] and restored['revision']!=reviewed['revision']
    with pytest.raises(ConflictError):
        sync(service,reviewed['revision'])
    assert [photo(service,id_)['revision'] for id_ in (2,3)]==[0,0]


def test_concurrent_source_edit_never_syncs_new_unreviewed_values(service):
    service.dispatch('edit_photo',{'photo_id':1,'expected_revision':0,'patch':{'texture':45}})
    start=threading.Barrier(3)
    results=[]
    def edit():
        start.wait()
        service.dispatch('edit_photo',{'photo_id':1,'expected_revision':1,'patch':{'texture':-20}})
    def apply():
        start.wait()
        try:
            results.append(sync(service,1))
        except ConflictError:
            results.append('conflict')
    threads=[threading.Thread(target=edit),threading.Thread(target=apply)]
    for thread in threads:
        thread.start()
    start.wait()
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()
    assert photo(service,1)['recipe']['texture']==-20
    assert len(results)==1
    for id_ in (2,3):
        row=photo(service,id_)
        assert row['recipe']['texture']==(0 if results==['conflict'] else 45)
        assert row['revision']==(0 if results==['conflict'] else 1)
