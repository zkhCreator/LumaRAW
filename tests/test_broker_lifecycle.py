"""Real-process engine handoff, single ownership and conservative crash recovery.

Inputs: isolated catalogs, generated photos and explicitly tagged test brokers.
Outputs: identity/queue receipts and assertions that rejected commands did not run.
Only test-owned processes are terminated in cleanup; no desktop/user broker access.
"""
from concurrent.futures import ThreadPoolExecutor
import json
from multiprocessing.connection import Client, Listener
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time

from PIL import Image
import psutil
import pytest

from lumaraw import bridge
from lumaraw.broker_lifecycle import BrokerLifecycle, ServiceConnectionError, owner_lock
from lumaraw.catalog import Catalog
from lumaraw.runtime import engine_identity, source_digest
from lumaraw.service import Service


def raw(root, method, params=None, identity=None):
    address,family=bridge.endpoint(root)
    with Client(address,family=family) as conn:
        return bridge.exchange(conn,{'method':method,'params':params or {},'engine':identity},timeout=20)


@pytest.fixture
def brokers(tmp_path):
    processes=[];roots=[]
    def launch(identity, block=False, root=None):
        root=root or tmp_path/f'catalog-{len(processes)}'
        script='''import json,sys,time
from pathlib import Path
from lumaraw import bridge,broker_lifecycle
from lumaraw.service import Service
identity=json.loads(sys.argv[1]);root=Path(sys.argv[2])
bridge.engine_identity=lambda:identity
broker_lifecycle.engine_identity=lambda:identity
if sys.argv[3]=='block':
    original=Service.run_worker
    def held(self,request):
        (root/'entered').write_text('ready')
        until=time.monotonic()+15
        while not (root/'release').exists() and time.monotonic()<until:time.sleep(.01)
        return original(self,request)
    Service.run_worker=held
bridge.serve(root)
'''
        process=subprocess.Popen([sys.executable,'-c',script,json.dumps(identity),str(root),'block' if block else 'normal'],
                                 stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        processes.append(process);roots.append(root)
        until=time.monotonic()+8
        while time.monotonic()<until:
            if process.poll() is not None:
                raise AssertionError(process.stderr.read().decode())
            try:
                if raw(root,'__broker_info__')['result']['engine']==identity:return root,process
            except (OSError,EOFError):pass
            time.sleep(.03)
        raise AssertionError('Test broker did not start')
    yield launch
    for root in roots:
        try:
            info=raw(root,'__broker_info__')['result']
            pid=info['pid'];process=psutil.Process(pid)
            # PID is freshly read from this fixture's private endpoint. Verify
            # the exact fixture catalog is also in its command before cleanup.
            if str(root) in process.cmdline():process.terminate();process.wait(timeout=5)
        except (OSError,EOFError,KeyError,psutil.Error):pass
    for process in processes:
        if process.poll() is None:process.terminate()
        process.wait(timeout=5);process.stderr.close()


def prepare(root, identity, tmp_path):
    path=tmp_path/'photo.png';Image.new('RGB',(80,60),(70,90,110)).save(path)
    assert raw(root,'queue_control',{'action':'pause'},identity)['ok']
    assert raw(root,'import_photos',{'paths':[str(path)]},identity)['ok']
    params={'photo_ids':[1],'destination':str(tmp_path/'exports'),'format':'jpeg','request_key':'durable'}
    job=raw(root,'enqueue_exports',params,identity)['result']['job_ids'][0]
    return path,job,params


def test_same_generation_requires_explicit_switch_preserving_pending_jobs(brokers,tmp_path):
    current=engine_identity();old={**current,'digest':'f'*64}
    root,process=brokers(old)
    _,job,params=prepare(root,old,tmp_path)
    with pytest.raises(ServiceConnectionError,match='Another build'):
        bridge.call(root,'edit_photo',{'photo_id':1,'expected_revision':0,'patch':{'exposure':2}})
    assert raw(root,'get_photo',{'photo_id':1},old)['result']['revision']==0
    switched=bridge.call(root,'service_connection',{'action':'activate'})
    assert switched['ok'] and switched['result']['engine']==current
    process.wait(timeout=5)
    queued=bridge.call(root,'get_job',{'job_id':job})['result']
    assert queued['state']=='pending' and queued['recipe']['exposure']==0
    assert bridge.call(root,'list_jobs')['result']['paused'] is True
    assert bridge.call(root,'enqueue_exports',params)['result']['job_ids']==[job]
    with pytest.raises(ServiceConnectionError,match='Connect with This Version'):
        # An old same-generation client cannot seize the newly pinned catalog.
        from lumaraw.broker_lifecycle import allow_start
        allow_start(root,old)


def test_new_generation_handoffs_automatically_and_old_writes_are_rejected(brokers,tmp_path):
    current=engine_identity();old={**current,'generation':current['generation']-1,'digest':'e'*64}
    root,process=brokers(old)
    path,job,_=prepare(root,old,tmp_path)
    result=bridge.call(root,'get_photo',{'photo_id':1})
    assert result['ok'] and result['result']['path']==str(path)
    process.wait(timeout=5)
    assert bridge.call(root,'get_job',{'job_id':job})['result']['state']=='pending'
    rejected=raw(root,'rate_photo',{'photo_id':1,'rating':5},old)
    legacy=raw(root,'rate_photo',{'photo_id':1,'rating':5})
    assert not rejected['ok'] and not legacy['ok']
    assert bridge.call(root,'get_photo',{'photo_id':1})['result']['rating']==0


def test_newer_engine_is_not_downgraded_even_by_explicit_activation(brokers):
    newer={**engine_identity(),'generation':engine_identity()['generation']+1,'digest':'d'*64}
    root,process=brokers(newer)
    for method,params in [('status',{}),('service_connection',{'action':'activate'})]:
        with pytest.raises(ServiceConnectionError,match='newer'):
            bridge.call(root,method,params)
    assert process.poll() is None
    assert bridge.call(root,'service_connection',{'action':'status'})['result']['compatible'] is False


def test_busy_preview_is_not_interrupted_by_handoff(brokers,tmp_path):
    old={**engine_identity(),'generation':engine_identity()['generation']-1,'digest':'c'*64}
    root,process=brokers(old,block=True)
    prepare(root,old,tmp_path)
    with ThreadPoolExecutor(max_workers=1) as pool:
        task=pool.submit(raw,root,'preview_photo',{'photo_id':1},old)
        until=time.monotonic()+5
        while not (root/'entered').exists() and time.monotonic()<until:time.sleep(.01)
        assert (root/'entered').exists() and process.poll() is None
        rejected=bridge.call(root,'status')
        assert not rejected['ok'] and 'busy' in rejected['error']
        assert process.poll() is None
        (root/'release').write_text('continue')
        assert task.result(timeout=20)['ok']
    assert bridge.call(root,'status')['ok']
    process.wait(timeout=5)


def test_second_broker_cannot_replace_live_endpoint(brokers):
    root,process=brokers(engine_identity())
    duplicate=subprocess.run([sys.executable,'-m','lumaraw.bridge','--broker','--catalog',str(root)],
                             capture_output=True,timeout=8)
    assert duplicate.returncode!=0 and process.poll() is None
    assert raw(root,'__broker_info__')['result']['pid']==process.pid


def test_running_export_blocks_switch_without_cancelling_or_resubmitting(brokers,tmp_path):
    old={**engine_identity(),'generation':engine_identity()['generation']-1,'digest':'b'*64}
    root,process=brokers(old,block=True)
    _,job,_=prepare(root,old,tmp_path)
    raw(root,'queue_control',{'action':'resume'},old)
    until=time.monotonic()+5
    while not (root/'entered').exists() and time.monotonic()<until:time.sleep(.01)
    assert (root/'entered').exists()
    rejected=bridge.call(root,'service_connection',{'action':'activate'})
    assert not rejected['ok'] and 'being processed' in rejected['error']
    assert raw(root,'get_job',{'job_id':job},old)['result']['state']=='running'
    (root/'release').write_text('continue')
    until=time.monotonic()+15
    while time.monotonic()<until:
        row=raw(root,'get_job',{'job_id':job},old)['result']
        if row['state'] in ('done','failed'):break
        time.sleep(.03)
    assert row['state']=='done' and Path(row['output']).is_file()
    assert bridge.call(root,'status')['ok']
    process.wait(timeout=5)
    jobs=bridge.call(root,'list_jobs')['result']['jobs']
    assert len(jobs)==1 and jobs[0]['state']=='done'


def test_lost_handoff_reply_does_not_strand_the_broker(brokers,tmp_path):
    current=engine_identity();old={**current,'digest':'a'*64}
    root,process=brokers(old)
    _,job,_=prepare(root,old,tmp_path)
    address,family=bridge.endpoint(root)
    with Client(address,family=family) as conn:
        conn.send_bytes(json.dumps({'method':'__broker_handoff__','expected':old,'target':current,'explicit':True}).encode())
        # Intentionally abandon the response; retirement must still finish.
    process.wait(timeout=5)
    assert bridge.call(root,'get_job',{'job_id':job})['result']['state']=='pending'


def test_legacy_preflight_never_sends_requested_mutation(tmp_path):
    root=tmp_path/'legacy';root.mkdir();address,family=bridge.endpoint(root)
    listener=Listener(address,family=family);seen=[]
    def answer():
        with listener.accept() as conn:
            request=json.loads(conn.recv_bytes());seen.append(request)
            conn.send_bytes(json.dumps({'ok':False,'error':'Unknown operation'}).encode())
    thread=threading.Thread(target=answer);thread.start()
    try:
        with pytest.raises(ServiceConnectionError,match='older background service'):
            bridge.call(root,'edit_photo',{'photo_id':1,'expected_revision':0,'patch':{'exposure':2}})
    finally:
        thread.join(timeout=3);listener.close()
    assert [r['method'] for r in seen]==['__broker_info__']


def test_uncertain_command_response_is_never_retried(tmp_path):
    root=tmp_path/'uncertain';root.mkdir();address,family=bridge.endpoint(root)
    listener=Listener(address,family=family);seen=[]
    def answer():
        with listener.accept() as conn:
            seen.append(json.loads(conn.recv_bytes())['method'])
            conn.send_bytes(json.dumps({'ok':True,'result':{'engine':engine_identity(),'retiring':False}}).encode())
        with listener.accept() as conn:
            seen.append(json.loads(conn.recv_bytes())['method'])
            # Models a committed command whose result was lost in transport.
    thread=threading.Thread(target=answer);thread.start()
    try:
        with pytest.raises(EOFError):
            bridge.call(root,'rate_photo',{'photo_id':1,'rating':5})
    finally:
        thread.join(timeout=3);listener.close()
    assert seen==['__broker_info__','rate_photo']


def test_clean_receipt_is_exact_and_consumed_once(tmp_path):
    identity=engine_identity();root=tmp_path/'catalog'
    service=Service(root)
    try:
        service.dispatch('queue_control',{'action':'pause'})
        path=tmp_path/'p.png';Image.new('RGB',(4,4)).save(path)
        service.dispatch('import_photos',{'paths':[str(path)]})
        service.dispatch('enqueue_exports',{'photo_ids':[1],'destination':str(tmp_path/'out'),'format':'jpeg','request_key':'clean'})
        with service.catalog() as c:c.set_setting('clean_handoff',{'target':identity})
    finally:service.close()
    resumed=Service(root,identity=identity)
    assert resumed.dispatch('list_jobs')['jobs'][0]['state']=='pending'
    resumed.close()
    cold=Service(root,identity=identity)
    assert cold.dispatch('list_jobs')['jobs'][0]['state']=='interrupted'
    cold.close()


def test_future_catalog_is_rejected_before_writes(tmp_path):
    root=tmp_path/'catalog';c=Catalog(root)
    c.db.execute('PRAGMA user_version=999');c.db.commit();c.close()
    before=(root/'catalog.sqlite').read_bytes()
    with pytest.raises(ValueError,match='newer LumaRAW'):
        Catalog(root)
    assert (root/'catalog.sqlite').read_bytes()==before


def test_replaced_worker_engine_pauses_queue_before_opening_photos(tmp_path):
    s=Service(tmp_path/'catalog')
    try:
        s.dispatch('queue_control',{'action':'pause'})
        path=tmp_path/'p.png';Image.new('RGB',(8,6)).save(path)
        s.dispatch('import_photos',{'paths':[str(path)]})
        for key in ('one','two'):
            s.dispatch('enqueue_exports',{'photo_ids':[1],'destination':str(tmp_path/'out'),
                'format':'jpeg','request_key':key})
        s.worker_identity={**engine_identity(),'digest':'9'*64}
        s.dispatch('queue_control',{'action':'resume'})
        until=time.monotonic()+8
        while time.monotonic()<until:
            result=s.dispatch('list_jobs')
            if result['paused']:break
            time.sleep(.02)
        assert result['paused'] and result['counts']=={'interrupted':1,'pending':1}
        assert not list((tmp_path/'out').iterdir())
        assert not list(s.cache.iterdir())
        assert 'No pixels were processed' in result['jobs'][1]['error']
    finally:s.close()


def test_source_identity_covers_code_and_dependencies_without_local_paths(tmp_path):
    (tmp_path/'lumaraw').mkdir();(tmp_path/'metal').mkdir()
    code=tmp_path/'lumaraw'/'file.py';code.write_text('VALUE=1')
    one=source_digest(tmp_path);code.write_text('VALUE=2');two=source_digest(tmp_path)
    (tmp_path/'uv.lock').write_text('dependency update')
    assert one!=two!=source_digest(tmp_path)
