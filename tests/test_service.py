"""Integration contracts for UI/agent concurrency, durable exports and MCP framing.

Uses disposable catalogs and generated raster originals. Public NEF paths are
opt-in. Verifies actual output files, SQLite state and subprocess transport.
"""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest
from PIL import Image
import tifffile
from lumaraw.service import Service, ConflictError
from lumaraw.bridge import call
from lumaraw.mcp import run

@pytest.fixture
def service(tmp_path):
    s=Service(tmp_path/'catalog');s.dispatch('queue_control',{'action':'pause'})
    paths=[]
    for i in range(3):
        p=tmp_path/f'photo-{i}.png';Image.new('RGB',(160,100),(70+i*30,110,150)).save(p);paths.append(str(p))
    s.dispatch('import_photos',{'paths':paths})
    yield s,paths
    s.close()

def enqueue(s,folder,key='test',ids=[1]):
    return s.dispatch('enqueue_exports',{'photo_ids':ids,'destination':str(folder),'format':'tiff16','request_key':key})

def wait_jobs(s):
    until=time.monotonic()+30
    while time.monotonic()<until:
        result=s.dispatch('list_jobs')
        if not any(j['state'] in ('pending','running') for j in result['jobs']):return result
        time.sleep(.05)
    raise AssertionError('queue timed out')

def test_two_clients_cannot_overwrite_same_revision(service):
    s,_=service;results=[]
    def change(value):
        try:results.append(s.dispatch('edit_photo',{'photo_id':1,'expected_revision':0,'patch':{'exposure':value}}))
        except ConflictError:results.append('conflict')
    threads=[threading.Thread(target=change,args=(v,)) for v in (1,2)]
    for t in threads:t.start()
    for t in threads:t.join()
    assert results.count('conflict')==1
    assert s.dispatch('get_photo',{'photo_id':1})['revision']==1
    assert s.dispatch('undo_photo',{'photo_id':1,'expected_revision':1})['recipe']['exposure']==0

def test_sync_is_atomic_on_stale_target(service):
    s,_=service
    s.dispatch('edit_photo',{'photo_id':1,'expected_revision':0,'patch':{'exposure':1}})
    with pytest.raises(ConflictError):
        s.dispatch('sync_photos',{'source_id':1,'groups':['Light'],'targets':[{'photo_id':2,'expected_revision':0},{'photo_id':3,'expected_revision':42}]})
    assert s.dispatch('get_photo',{'photo_id':2})['revision']==0

def test_english_schema_groups_sync_without_changing_other_adjustments(service):
    s,_=service
    schema=s.dispatch('recipe_schema')
    group=next(name for name,fields in schema['groups'].items() if 'exposure' in fields)
    assert group=='Light'
    source=s.dispatch('edit_photo',{'photo_id':1,'expected_revision':0,
        'patch':{'exposure':1.25,'temperature':15,'crop':'1:1'}})
    target=s.dispatch('edit_photo',{'photo_id':2,'expected_revision':0,
        'patch':{'temperature':-10,'crop':'16:9'}})
    result=s.dispatch('sync_photos',{'source_id':source['id'],'groups':[group],
        'targets':[{'photo_id':target['id'],'expected_revision':target['revision']}]})
    assert result=={'synced':1}
    synced=s.dispatch('get_photo',{'photo_id':target['id']})
    assert synced['recipe']['exposure']==1.25
    assert synced['recipe']['temperature']==-10 and synced['recipe']['crop']=='16:9'
    assert synced['revision']==target['revision']+1


def test_idempotency_snapshot_original_and_no_overwrite(service,tmp_path):
    s,paths=service;before=hashlib.sha256(Path(paths[0]).read_bytes()).hexdigest()
    first=enqueue(s,tmp_path/'export');assert enqueue(s,tmp_path/'export')==first
    assert s.dispatch('get_job',{'job_id':first['job_ids'][0]})['recipe']['exposure']==0
    with pytest.raises(ValueError):enqueue(s,tmp_path/'different')
    s.dispatch('edit_photo',{'photo_id':1,'expected_revision':0,'patch':{'exposure':2}})
    s.dispatch('queue_control',{'action':'resume'});result=wait_jobs(s)
    assert result['counts']=={'done':1}
    output=Path(result['jobs'][0]['output']);assert output.exists()
    with tifffile.TiffFile(output) as tif:
        assert tif.asarray().dtype.name=='uint16'
        assert 270 not in tif.pages[0].tags
        first_mean=tif.asarray().mean()
    digest=hashlib.sha256(output.read_bytes()).hexdigest()
    enqueue(s,tmp_path/'export',key='second');assert wait_jobs(s)['counts']=={'done':2}
    assert tifffile.imread(wait_jobs(s)['jobs'][0]['output']).mean()>first_mean*1.5
    assert hashlib.sha256(output.read_bytes()).hexdigest()==digest
    assert hashlib.sha256(Path(paths[0]).read_bytes()).hexdigest()==before

def test_cancel_and_retry_are_explicit(service,tmp_path):
    s,_=service;job=enqueue(s,tmp_path/'export')['job_ids'][0]
    s.dispatch('queue_control',{'action':'cancel','job_id':job})
    s.dispatch('queue_control',{'action':'retry'})
    assert s.dispatch('list_jobs')['counts']=={'cancelled':1}
    s.dispatch('queue_control',{'action':'retry_cancelled','job_id':job})
    assert s.dispatch('list_jobs')['counts']=={'pending':1}

def test_restart_does_not_replay_pending_or_running(service,tmp_path):
    s,_=service;enqueue(s,tmp_path/'export');s.close()
    with s.catalog() as c:c.db.execute("UPDATE jobs SET state='running'");c.db.commit()
    second=Service(s.root)
    try:assert second.dispatch('list_jobs')['counts']=={'interrupted':1}
    finally:second.close()

def test_preview_and_detail_are_real_files(service):
    s,_=service
    result=s.dispatch('preview_photo',{'photo_id':1})
    assert Path(result['preview']).exists() and Path(result['before']).exists()
    roi=s.dispatch('preview_photo',{'photo_id':1,'detail':{'width':50,'height':40,'cx':0.2,'cy':0.2}})
    assert Image.open(roi['preview']).size==(50,40)
    assert roi['detail'] and roi['revision']==0

def test_service_has_no_qt_runtime_import():
    code='import sys; from lumaraw.service import Service; from lumaraw import color, library; print(any(k.startswith("PySide") for k in sys.modules)); print(len(color.icc_profile("p3")))'
    result=subprocess.check_output([sys.executable,'-c',code],text=True)
    assert result.splitlines()[0]=='False'

def test_mcp_handshake_validation_and_shared_broker(tmp_path):
    root=tmp_path/'catalog'
    fixture=tmp_path/'original.png';Image.new('RGB',(64,48),'gray').save(fixture)
    assert call(root,'import_photos',{'paths':[str(fixture)]})['ok']
    messages=[
        {'jsonrpc':'2.0','id':0,'method':'tools/list'},
        {'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'test','version':'1'}}},
        {'jsonrpc':'2.0','method':'notifications/initialized'},
        {'jsonrpc':'2.0','id':2,'method':'tools/list'},
        {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'lumaraw_edit_photo','arguments':{'photo_id':1,'expected_revision':0,'patch':{'exposure':0.75}}}},
        {'jsonrpc':'2.0','id':4,'method':'tools/call','params':{'name':'lumaraw_edit_photo','arguments':{'photo_id':1,'expected_revision':0,'patch':{'exposure':1}}}},
        {'jsonrpc':'2.0','id':5,'method':'tools/call','params':{'name':'lumaraw_edit_photo','arguments':{'photo_id':1,'expected_revision':1,'patch':{'exposure':100}}}},
        {'jsonrpc':'2.0','id':6,'method':'tools/call','params':{'name':'lumaraw_status','arguments':{'unknown':1}}},
    ]
    output=subprocess.check_output([sys.executable,'-m','lumaraw.mcp','--catalog',str(root)],input='\n'.join(json.dumps(m) for m in messages)+'\n',text=True)
    rows=[json.loads(x) for x in output.splitlines()]
    assert rows[0]['error']['code']==-32002
    assert rows[1]['result']['protocolVersion']=='2025-11-25'
    assert len(rows[2]['result']['tools'])>=20
    assert rows[3]['result']['isError'] is False
    assert all(r['result']['isError'] for r in rows[4:])
    # CLI reads the exact MCP edit from the shared service; no second catalog.
    assert call(root,'get_photo',{'photo_id':1})['result']['recipe']['exposure']==0.75

def test_mcp_malformed_and_unknown_rpc(tmp_path):
    sink=io.StringIO()
    run(tmp_path,io.StringIO('not json\n[]\n{"jsonrpc":"2.0","id":1,"method":"ping"}\n'),sink)
    rows=[json.loads(x) for x in sink.getvalue().splitlines()]
    assert [r.get('error',{}).get('code') for r in rows]==[-32700,-32600,None]

def test_invalid_edit_preserves_history_and_recipe(service):
    s,_=service
    with pytest.raises(ValueError):s.dispatch('edit_photo',{'photo_id':1,'expected_revision':0,'patch':{'exposure':99}})
    with s.catalog() as c:assert c.db.execute('SELECT count(*) FROM history').fetchone()[0]==0
    assert s.dispatch('get_photo',{'photo_id':1})['revision']==0

def test_cancel_reserved_export_waiting_behind_preview(service,tmp_path):
    s,_=service
    # Holding the slot models an interactive image operation already in flight.
    s.image_lock.acquire()
    try:
        job=enqueue(s,tmp_path/'export')['job_ids'][0]
        s.dispatch('queue_control',{'action':'resume'})
        until=time.monotonic()+3
        while time.monotonic()<until:
            if s.dispatch('get_job',{'job_id':job})['state']=='running':break
            time.sleep(.01)
        assert s.dispatch('get_job',{'job_id':job})['state']=='running'
        s.dispatch('queue_control',{'action':'cancel','job_id':job})
    finally:s.image_lock.release()
    assert wait_jobs(s)['counts']=={'cancelled':1}
    assert not list((tmp_path/'export').glob('*.tif'))

def test_sampled_memory_guard_stops_actual_child(service):
    s,_=service;s.budget=1
    with pytest.raises(RuntimeError,match='Memory|budget'):
        s.dispatch('preview_photo',{'photo_id':1})
    assert s.active is None

def test_individual_job_receipt_survives_page_limit(service,tmp_path):
    s,_=service
    first=enqueue(s,tmp_path/'export','old')['job_ids'][0]
    for i in range(61):enqueue(s,tmp_path/'export',f'new-{i}')
    assert len(s.dispatch('list_jobs')['jobs'])==60
    old=s.dispatch('get_job',{'job_id':first})
    assert old['id']==first and old['recipe']['version']==2

def test_superseded_native_preview_is_skipped_without_cancelling_other_client(service):
    s,_=service;results=[]
    s.image_lock.acquire()
    def preview(generation):
        try:results.append((generation,s.dispatch('preview_photo',{'photo_id':1,'client_id':'native-test','generation':generation})))
        except InterruptedError:results.append((generation,'superseded'))
    old=threading.Thread(target=preview,args=(1,));new=threading.Thread(target=preview,args=(2,))
    try:
        old.start()
        until=time.monotonic()+3
        while s.preview_versions.get('native-test')!=1 and time.monotonic()<until:time.sleep(.01)
        new.start()
        until=time.monotonic()+3
        while s.preview_versions.get('native-test')!=2 and time.monotonic()<until:time.sleep(.01)
    finally:s.image_lock.release()
    old.join(10);new.join(10)
    assert (1,'superseded') in results
    assert any(g==2 and isinstance(r,dict) and r['ok'] for g,r in results)
    assert s.dispatch('preview_photo',{'photo_id':1})['ok']

def test_effective_budget_never_exceeds_available_memory(service,monkeypatch):
    from types import SimpleNamespace
    import lumaraw.service as module
    s,_=service
    monkeypatch.setattr(module.psutil,'virtual_memory',lambda:SimpleNamespace(available=100*1024**2))
    status=s.dispatch('settings')
    assert status['budget_mb']==4096
    assert status['effective_budget_mb']==70
    assert status['limited_by_available_memory'] is True

def test_failed_export_retains_measured_peak(service,tmp_path):
    s,_=service;s.budget=1
    enqueue(s,tmp_path/'exports')
    s.dispatch('queue_control',{'action':'resume'})
    job=wait_jobs(s)['jobs'][0]
    assert job['state']=='failed'
    assert job['peak_mb']>0
    assert 'Memory' in job['error'] or 'budget' in job['error']

def test_backend_setting_persists_and_receipt_identifies_actual_cpu(service,tmp_path):
    s,_=service
    settings=s.dispatch('settings',{'compute_backend':'cpu'})
    assert settings['compute_backend']=='cpu'
    with s.catalog() as c:assert c.setting('compute_backend')=='cpu'
    enqueue(s,tmp_path/'backend-output')
    s.dispatch('queue_control',{'action':'resume'})
    job=wait_jobs(s)['jobs'][0]
    assert job['state']=='done'
    assert job['processing']['backend']=='cpu'
    assert job['processing']['raw_decode_backend']=='LibRaw CPU'
    assert job['processing']['stages']['grade_and_output']['calls']>0
    assert s.dispatch('get_job',{'job_id':job['id']})['processing']==job['processing']
    assert s.dispatch('status')['last_processing']['backend']=='cpu'
    with pytest.raises(Exception):s.dispatch('settings',{'compute_backend':'cuda'})

def test_direct_worker_without_parent_reports_timings(service,tmp_path):
    s,paths=service
    request={'operation':'preview','path':paths[0],'cache':str(tmp_path/'direct-cache'),'budget_mb':2048,'compute_backend':'cpu'}
    p=subprocess.run([sys.executable,'-m','lumaraw.worker'],input=json.dumps(request)+'\n',text=True,capture_output=True,timeout=30)
    result=json.loads(p.stdout)
    assert p.returncode==0 and result['ok'],result
    assert result['processing']['worker_seconds']>0
