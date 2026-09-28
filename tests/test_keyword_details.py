"""Large keyword workflows retain complete identities across bounded IPC.

Inputs: generated photos and maximal Unicode XMP paths, captured revisions and
explicit replacements. Outputs: complete paged reads, compact mutation receipts,
atomic identity edits, independent copies and a real exported derivative.
No personal photographs or rendered-desktop claims.
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

from lumaraw.bridge import call, endpoint, MAX_MESSAGE
from lumaraw.service import Service
from test_xmp_read import packet
from test_keywords import save, targets, photo


@pytest.fixture
def broker(tmp_path):
    catalog=tmp_path/'catalog'
    with (tmp_path/'broker.log').open('w') as log:
        process=subprocess.Popen([sys.executable,'-m','lumaraw.bridge','--broker','--catalog',str(catalog)],stdout=log,stderr=log)
        try:
            address,family=endpoint(catalog);deadline=time.monotonic()+15
            while True:
                assert process.poll() is None
                try:
                    with Client(address,family=family):pass
                    break
                except OSError:
                    if time.monotonic()>deadline:raise AssertionError('Broker startup timed out')
                    time.sleep(.02)
            def rpc(method,params=None,ok=True):
                result=call(catalog,method,params or {})
                assert len(json.dumps(result,ensure_ascii=False).encode())<MAX_MESSAGE
                assert result['ok'] is ok,result
                return result['result'] if ok else result
            yield rpc
        finally:process.terminate();process.wait(timeout=10)


def test_deep_photo_read_edit_copy_and_export_through_real_broker(broker,tmp_path):
    rpc=broker;folder=tmp_path/'Photos';folder.mkdir()
    paths=[folder/'original.png',folder/'second.png']
    for path in paths:Image.new('RGB',(12,8),'navy').save(path)
    original_hash=hashlib.sha256(paths[0].read_bytes()).digest()
    branch=[str(i)+('🌊'*118) for i in range(31)]
    expected=[' | '.join(branch+[str(i)+('🌊'*118)]) for i in range(100)]
    paths[0].with_suffix('.xmp').write_bytes(packet('<lr:hierarchicalSubject><rdf:Bag>'+''.join(
        '<rdf:li>'+value.replace(' | ','|')+'</rdf:li>' for value in expected)+'</rdf:Bag></lr:hierarchicalSubject>'))
    rpc('queue_control',{'action':'pause'})
    rpc('import_photos',{'paths':list(map(str,paths))})
    root=rpc('get_folder',{'photo_id':1})
    plan=rpc('prepare_folder_sync',{'folder_id':root['id'],'expected_revision':root['folder_revision'],'scan_metadata':True})['plan']
    while plan['state']=='planning':plan=rpc('scan_folder_sync',{'plan_id':plan['id'],'expected_revision':plan['revision']})['plan']
    assert rpc('apply_folder_sync',{'plan_id':plan['id'],'expected_revision':plan['revision']})['plan']['state']=='applied'
    initial=rpc('get_photo',{'photo_id':1})
    assert initial['keywords_deferred'] and initial['keyword_count']==100
    assert initial['keywords']==[] and initial['keyword_tags']==[] and len(initial['keyword_ids'])==100
    assert len(json.dumps(initial,ensure_ascii=False).encode())<32768
    read={'photo_id':1,'expected_metadata_revision':initial['metadata_revision']}
    restored=[]
    for offset in range(0,100,20):
        page=rpc('get_photo_keywords',{**read,'offset':offset})
        assert page['page_size']==20 and page['total']==100 and len(page['keywords'])==20
        assert len(json.dumps(page,ensure_ascii=False).encode())<400000
        restored.extend(row['path'] for row in page['keywords'])
        chosen=rpc('keyword_choices',{'keyword_ids':initial['keyword_ids'],'offset':offset})
        assert len(chosen['keywords'])==20 and len(json.dumps(chosen,ensure_ascii=False).encode())<400000
    assert sorted(restored)==sorted(expected)
    assert rpc('get_photo_keywords',{**read,'offset':9999})['offset']==80
    edited=rpc('edit_photo',{'photo_id':1,'expected_revision':0,'patch':{'exposure':1}})
    assert edited['keywords_deferred'] and edited['keyword_ids']==initial['keyword_ids']
    assert rpc('rate_photo',{'photo_id':1,'rating':4})['keyword_count']==100
    second=rpc('get_photo',{'photo_id':2})
    replacement={'targets':[{'photo_id':1,'expected_metadata_revision':initial['metadata_revision']},
                             {'photo_id':2,'expected_metadata_revision':second['metadata_revision']}],
                 'patch':{'keyword_ids':initial['keyword_ids'][:-1],'keyword_additions':['New | Branch'],'title':'By identity'}}
    receipt=rpc('edit_metadata',replacement)
    assert receipt['patch']['keywords_deferred'] and receipt['patch']['keyword_count']==100
    assert len(json.dumps(receipt,ensure_ascii=False).encode())<32768
    first=rpc('get_photo',{'photo_id':1});second=rpc('get_photo',{'photo_id':2})
    assert first['keyword_ids']==second['keyword_ids'] and first['title']==second['title']=='By identity'
    assert 'conflict' in rpc('get_photo_keywords',read,ok=False)['error']
    assert 'conflict' in rpc('edit_metadata',replacement,ok=False)['error']
    copy=rpc('create_virtual_copies',{'targets':[{'photo_id':1,'expected_revision':first['revision'],
         'expected_metadata_revision':first['metadata_revision']}]})['photos'][0]
    variant=rpc('get_photo',{'photo_id':copy['id']})
    assert variant['keyword_ids']==first['keyword_ids']
    rpc('edit_metadata',{'targets':[{'photo_id':variant['id'],'expected_metadata_revision':variant['metadata_revision']}],
                         'patch':{'keyword_ids':[]}})
    assert rpc('get_photo',{'photo_id':1})['keyword_count']==100
    assert rpc('get_photo',{'photo_id':variant['id']})['keywords']==[]
    job=rpc('enqueue_exports',{'photo_ids':[1],'destination':str(tmp_path/'exports'),'format':'jpeg',
        'options':{'keyword_hierarchy':True},'request_key':'deep-paths'})['job_ids'][0]
    rpc('queue_control',{'action':'resume'});deadline=time.monotonic()+30
    while True:
        result=rpc('get_job',{'job_id':job})
        if result['state'] not in ('pending','running'):break
        assert time.monotonic()<deadline;time.sleep(.03)
    assert result['state']=='done' and Path(result['output']).exists()
    assert result['export_metadata']['hierarchy_count']==100
    assert hashlib.sha256(paths[0].read_bytes()).digest()==original_hash


@pytest.fixture
def library(tmp_path):
    source=tmp_path/'photo.png';Image.new('RGB',(8,8)).save(source)
    s=Service(tmp_path/'catalog');s.dispatch('import_photos',{'paths':[str(source)]})
    yield s
    s.close()


def test_identity_replacement_rejects_ambiguous_invalid_or_overlarge_batches_atomically(library):
    s=library;tag=save(s,'Keep')
    s.dispatch('edit_metadata',{'targets':targets(s,[1]),'patch':{'keyword_ids':[tag]}})
    before=photo(s,1)
    patches=[{'keyword_ids':[tag,99999],'title':'Must not persist'},
             {'keyword_ids':[tag],'keywords':['Bad mix']},
             {'keyword_additions':['No IDs']},
             {'keyword_ids':[tag],'keyword_additions':[f'Temporary {i}' for i in range(100)]}]
    for patch in patches:
        with pytest.raises(ValueError):s.dispatch('edit_metadata',{'targets':targets(s,[1]),'patch':patch})
        assert photo(s,1)==before
    assert s.dispatch('keyword_choices',{'search':'Temporary'})['total']==0
    parent=save(s,'A');save(s,'Same',parent_id=parent)
    other=save(s,'B');save(s,'Same',parent_id=other)
    with pytest.raises(ValueError,match='Ambiguous'):
        s.dispatch('edit_metadata',{'targets':targets(s,[1]),'patch':{'keyword_ids':[tag],'keyword_additions':['Same']}})
    assert photo(s,1)==before


def test_ancestor_rename_invalidates_pages_and_legacy_literals_keep_identity(library):
    s=library;parent=save(s,'Parent');child=save(s,'Child',parent_id=parent,synonyms=['Alias'])
    with s.catalog() as c:
        with c.db:literal=c.db.execute("INSERT INTO keywords(name,normalized) VALUES('A,B | literal','a,b | literal')").lastrowid
    s.dispatch('edit_metadata',{'targets':targets(s,[1]),'patch':{'keyword_ids':[child,literal]}})
    p=photo(s,1);request={'photo_id':1,'expected_metadata_revision':p['metadata_revision']}
    assert {row['id'] for row in s.dispatch('get_photo_keywords',request)['keywords']}=={child,literal}
    assert s.dispatch('keyword_choices',{'search':'alias'})['keywords'][0]['id']==child
    assert s.dispatch('keyword_choices',{'keyword_ids':[]})['total']==0
    save(s,'Changed',keyword_id=parent)
    with pytest.raises(ValueError,match='conflict'):s.dispatch('get_photo_keywords',request)
    p=photo(s,1)
    s.dispatch('edit_metadata',{'targets':targets(s,[1]),'patch':{'keyword_ids':p['keyword_ids'],'caption':'Preserve literal'}})
    assert photo(s,1)['keyword_ids']==p['keyword_ids']
    assert 'A,B | literal' in photo(s,1)['keywords']
