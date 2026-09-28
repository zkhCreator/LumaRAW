"""Bounded synchronization review over real IPC and complete staged metadata.

Inputs: generated PNG/XMP fixtures, including long Unicode descriptions/paths.
Outputs: byte-bounded summaries/details, exact values, revision isolation and
atomic application. Only private fixture files and disposable catalogs are used.
"""
import hashlib
import json
from multiprocessing.connection import Client
from pathlib import Path
import subprocess
import sys
import time

from PIL import Image
import pytest

from lumaraw.bridge import call,endpoint,MAX_MESSAGE
from lumaraw.service import Service
from test_xmp_read import packet


def test_sixty_long_descriptions_scan_review_and_apply_through_real_broker(tmp_path):
    photos=tmp_path/'Photos';photos.mkdir();paths=[]
    for index in range(60):
        path=photos/f'{index:03}.png';Image.new('RGB',(4,4)).save(path);paths.append(path)
    caption='🌊'*5000
    for path in paths:path.with_suffix('.xmp').write_bytes(packet('<dc:description>'+caption+'</dc:description>'))
    before=[hashlib.sha256(path.read_bytes()).digest() for path in paths]
    catalog=tmp_path/'catalog'
    with (tmp_path/'broker.log').open('w') as log:
        process=subprocess.Popen([sys.executable,'-m','lumaraw.bridge','--broker','--catalog',str(catalog)],stdout=log,stderr=log)
        try:
            address,family=endpoint(catalog)
            deadline=time.monotonic()+15
            while True:
                assert process.poll() is None
                try:
                    with Client(address,family=family):pass
                    break
                except OSError:
                    if time.monotonic()>deadline:raise AssertionError('Broker startup timed out')
                    time.sleep(.02)
            def rpc(method,params=None):
                result=call(catalog,method,params or {})
                assert result['ok'],result
                assert len(json.dumps(result,ensure_ascii=False).encode())<MAX_MESSAGE
                return result['result']
            rpc('import_photos',{'paths':list(map(str,paths))})
            folder=rpc('get_folder',{'photo_id':1})
            result=rpc('prepare_folder_sync',{'folder_id':folder['id'],'expected_revision':folder['folder_revision'],'scan_metadata':True})
            while result['plan']['state']=='planning':
                result=rpc('scan_folder_sync',{'plan_id':result['plan']['id'],'expected_revision':result['plan']['revision']})
            plan=result['plan'];assert plan['state']=='ready' and result['total']==60
            assert all(item['metadata_deferred'] and item['patch']=={} for item in result['items'])
            assert len(json.dumps(result,ensure_ascii=False).encode())<100000
            request={'plan_id':plan['id'],'item_id':result['items'][0]['id'],'expected_revision':plan['revision']}
            assert rpc('get_folder_sync_metadata',request)['item']['patch']['caption']==caption
            changed=rpc('select_folder_sync_items',{'plan_id':plan['id'],'expected_revision':plan['revision'],
                'selected':True,'kind':'updated'})['plan']
            stale=call(catalog,'get_folder_sync_metadata',request)
            assert not stale['ok'] and 'changed' in stale['error']
            request['expected_revision']=changed['revision']
            assert rpc('get_folder_sync_metadata',request)['item']['patch']['caption']==caption
            applied=rpc('apply_folder_sync',{'plan_id':plan['id'],'expected_revision':changed['revision']})['plan']
            assert applied['state']=='applied' and applied['modified']==60
            assert rpc('get_photo',{'photo_id':1})['caption']==caption
            assert rpc('get_photo',{'photo_id':60})['caption']==caption
            gone=call(catalog,'get_folder_sync_metadata',{**request,'expected_revision':applied['revision']})
            assert not gone['ok'] and 'no longer available' in gone['error']
            assert before==[hashlib.sha256(path.read_bytes()).digest() for path in paths]
        finally:
            process.terminate();process.wait(timeout=10)


@pytest.mark.parametrize('with_iptc',[False,True])
def test_worst_case_keyword_detail_pages_preserve_every_path(tmp_path,with_iptc):
    folder=tmp_path/'Photos';folder.mkdir()
    source=folder/'photo.png';Image.new('RGB',(4,4)).save(source)
    branch=[str(i)+('🌊'*118) for i in range(31)]
    paths=[branch+[str(i)+('🌊'*118)] for i in range(100)]
    data=packet('<lr:hierarchicalSubject><rdf:Bag>'+''.join('<rdf:li>'+'|'.join(path)+'</rdf:li>' for path in paths)+'</rdf:Bag></lr:hierarchicalSubject>')
    iptc={}
    if with_iptc:
        from lumaraw.export_metadata import xmp_packet
        iptc={'instructions':'🌊'*5000,'alt_text':'🌊'*5000,'rights_usage_terms':'🌊'*5000}
        data=xmp_packet({'version':1,'mode':'catalog','fields':{'iptc':iptc},'keywords':[],
                         'hierarchy':['|'.join(path) for path in paths]})
    source.with_suffix('.xmp').write_bytes(data)
    s=Service(tmp_path/'catalog')
    try:
        s.dispatch('import_photos',{'paths':[str(source)]})
        folder=s.dispatch('get_folder',{'photo_id':1})
        result=s.dispatch('prepare_folder_sync',{'folder_id':folder['id'],'expected_revision':folder['folder_revision'],'scan_metadata':True})
        while result['plan']['state']=='planning':
            result=s.dispatch('scan_folder_sync',{'plan_id':result['plan']['id'],'expected_revision':result['plan']['revision']})
        assert result['plan']['state']=='ready' and result['items'][0]['metadata_deferred']
        request={'plan_id':result['plan']['id'],'item_id':result['items'][0]['id'],'expected_revision':result['plan']['revision']}
        restored=[]
        page_size=12 if with_iptc else 20
        for offset in range(0,100,page_size):
            detail=s.dispatch('get_folder_sync_metadata',{**request,'offset':offset})
            assert len(json.dumps({'ok':True,'result':detail},ensure_ascii=False).encode())<512*1024
            assert len(json.dumps({'ok':True,'result':detail}).encode())<MAX_MESSAGE
            assert detail['total']==100 and detail['offset']==offset and detail['page_size']==page_size
            if with_iptc:assert detail['item']['patch']['iptc']==iptc
            restored+=detail['item']['patch']['keyword_paths']
        assert restored==paths and source.with_suffix('.xmp').read_bytes()==data
        assert s.dispatch('get_folder_sync_metadata',{**request,'offset':9999})['offset']==99//page_size*page_size
        with pytest.raises(ValueError,match='no longer available'):
            s.dispatch('get_folder_sync_metadata',{**request,'item_id':999999})
    finally:s.close()
