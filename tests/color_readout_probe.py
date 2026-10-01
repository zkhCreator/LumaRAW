"""Compare bounded RGB/Lab readouts with ordinary previews on a packaged engine.

Inputs: explicit read-only RAW, engine and fresh work directory. Outputs: cold
application/warm-map timings, sampled worker/broker peak RSS, numerical/display parity.
Uses the native persistent relay. No cold-OS-cache, desktop or Adobe parity claim.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import select
import subprocess
import threading
import time

import numpy as np
import psutil
from PIL import Image


def main():
    parser=argparse.ArgumentParser()
    for name in ('engine','fixture','work'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();args.work.mkdir(parents=True,exist_ok=False)
    root=args.work.resolve();fixture=args.fixture.resolve()
    digest=hashlib.sha256(fixture.read_bytes()).hexdigest()
    runs=[];maps={};display={}
    for backend in ('cpu','metal'):
        relay=subprocess.Popen([str(args.engine.resolve()),'--catalog',str(root/backend),'--native-client'],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            env={**os.environ,'LUMARAW_PRESETS_ROOT':str(root/'presets'/backend)})
        counter=0
        broker=None;active_peak=[0.];last_broker_peak=0.
        stop=threading.Event();sampler=None
        def sample_broker():
            while not stop.wait(.005):
                target=active_peak
                try:target[0]=max(target[0],broker.memory_info().rss/1024**2)
                except psutil.NoSuchProcess:return
        def call(method,params=None):
            nonlocal counter,active_peak,last_broker_peak
            active_peak=[broker.memory_info().rss/1024**2 if broker else 0.]
            counter+=1;start=time.perf_counter()
            relay.stdin.write(json.dumps({'id':counter,'method':method,'params':params or {}}).encode()+b'\n')
            relay.stdin.flush()
            assert select.select([relay.stdout],[],[],180)[0],'Native relay timed out'
            envelope=json.loads(relay.stdout.readline(1024*1024+1))
            assert envelope.get('ok') and envelope['id']==counter,envelope
            last_broker_peak=round(active_peak[0],1)
            return envelope['result'],(time.perf_counter()-start)*1000
        try:
            call('queue_control',{'action':'pause'});call('settings',{'compute_backend':backend})
            connection,_=call('service_connection',{'action':'status'})
            broker=psutil.Process(connection['pid'])
            sampler=threading.Thread(target=sample_broker,daemon=True);sampler.start()
            call('import_photos',{'paths':[str(fixture)]})
            call('edit_photo',{'photo_id':1,'expected_revision':0,'patch':{'exposure':.35,'shadows':20,'blue_hue':-9}})
            for detail in (False,True):
                mode='detail' if detail else 'fit'
                geometry={'detail':{'cx':.6,'cy':.4,'width':800,'height':600}} if detail else {'max_edge':1680}
                for name,enabled in [('baseline-first',False),('readouts-first',True),('readouts-warm',True),('baseline-warm',False)]:
                    result,elapsed=call('preview_photo',{'photo_id':1,'expected_revision':1,
                        'include_before':True,'include_color_readouts':enabled,**geometry})
                    case=mode+'-'+name
                    with Image.open(result['preview']) as image:
                        assert image.info.get('icc_profile')
                        pixels=np.asarray(image).copy()
                        image.save(root/(backend+'-'+case+'.png'),icc_profile=image.info['icc_profile'])
                    baseline=display.setdefault((backend,mode),pixels)
                    error=int(np.abs(baseline.astype(np.int16)-pixels.astype(np.int16)).max())
                    assert error<=1
                    if result.get('preview_cache_hit'):
                        assert result['worker_spawned'] is False
                        assert result['processing']['backend']=='cache'
                        assert result['processing']['metal_grade_tiles']==result['processing']['cpu_tiles']==0
                    elif backend=='metal':assert result['processing']['metal_grade_tiles']>0
                    record={'backend':backend,'case':case,'wall_ms':round(elapsed,3),
                        'worker_peak_mib':result['peak_mb'],'width':result['width'],'height':result['height'],
                        'broker_peak_mib':last_broker_peak,
                        'roi':result['roi'],'processing':result['processing'],'display_max_code_difference':error,
                        'preview_cache_hit':result.get('preview_cache_hit',False),
                        'worker_spawned':result.get('worker_spawned',True)}
                    if enabled:
                        for key in ('color_readouts','before_color_readouts'):
                            receipt=result[key];data=Path(receipt['path']).read_bytes()
                            array=np.frombuffer(data[16:],'<f4').reshape(receipt['height'],receipt['width'],6).copy()
                            assert np.isfinite(array).all()
                            previous=maps.setdefault((backend,mode,key),array)
                            np.testing.assert_array_equal(previous,array)
                            record[key+'_cache_hit']=receipt['cache_hit']
                            if name=='readouts-warm':assert receipt['cache_hit']
                        record['image_dimensions']=[result['image_width'],result['image_height']]
                    runs.append(record)
        finally:
            stop.set()
            if sampler:sampler.join(timeout=2)
            relay.stdin.close();relay.wait(timeout=30);relay.stdout.close()
    differences={}
    for _,mode,key in maps:
        case=mode+'-'+key
        if case in differences:continue
        delta=np.abs(maps[('cpu',mode,key)]-maps[('metal',mode,key)])
        maximum=delta.reshape(-1,6).max(axis=0)
        assert maximum.max()<=.01
        differences[case]={'maximum_by_channel':maximum.tolist(),'mean':float(delta.mean())}
    assert hashlib.sha256(fixture.read_bytes()).hexdigest()==digest
    report={'system':platform.platform(),'fixture_sha256':digest,'fixture_bytes':fixture.stat().st_size,
        'scope':'Sequential single samples, persistent negotiated IPC; cold application caches, not cold OS cache or desktop latency. Broker RSS sampled every 5 ms, separately from worker RSS; neither is whole-app peak memory.',
        'runs':runs,'cpu_metal_readout_differences':differences,'original_unchanged':True}
    (root/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
