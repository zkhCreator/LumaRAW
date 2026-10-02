"""Measure packaged Copy throughput and concurrent control-command responsiveness.

Inputs: explicit read-only RAW, packaged engine and a fresh disposable work root.
Outputs: three new-catalog transfer timings, sampled broker RSS, warm control
latencies and exact copied bytes. Source clones are generated before measurement.
No cold OS cache, desktop frame-rate or camera-rendering equivalence is claimed.
An optional second-copy run verifies both independently journaled destinations.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import select
import shutil
import subprocess
import threading
import time

import psutil
import rawpy


def sha(path):
    result=hashlib.sha256()
    with Path(path).open('rb') as stream:
        while block:=stream.read(1024*1024):result.update(block)
    return result.hexdigest()


class Relay:
    def __init__(self,engine,catalog,presets):
        self.number=0
        self.process=subprocess.Popen([str(engine),'--catalog',str(catalog),'--native-client'],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            env={**os.environ,'LUMARAW_PRESETS_ROOT':str(presets)})

    def call(self,method,params=None):
        self.number+=1
        self.process.stdin.write(json.dumps({'id':self.number,'method':method,'params':params or {}}).encode()+b'\n')
        self.process.stdin.flush()
        if not select.select([self.process.stdout],[],[],180)[0]:raise TimeoutError(method)
        result=json.loads(self.process.stdout.readline(1024*1024+1))
        assert result['id']==self.number and result['ok'],result
        return result['result']

    def close(self):
        self.process.stdin.close();self.process.wait(timeout=30);self.process.stdout.close()


def main():
    parser=argparse.ArgumentParser()
    for name in ('engine','fixture','work'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--files',type=int,default=24)
    parser.add_argument('--second-copy',action='store_true')
    args=parser.parse_args();assert 2<=args.files<=256
    root=args.work.resolve();root.mkdir(parents=True,exist_ok=False)
    engine=args.engine.resolve();fixture=args.fixture.resolve();original=sha(fixture)
    with rawpy.imread(str(fixture)) as raw:dimensions=[raw.sizes.width,raw.sizes.height]
    source=root/'source';source.mkdir()
    for index in range(args.files):shutil.copyfile(fixture,source/(f'{index:04}'+fixture.suffix))
    results=[]
    for index in range(3):
        destination=root/f'output-{index}';destination.mkdir()
        backup=root/f'backup-{index}'
        if args.second_copy:backup.mkdir()
        catalog=root/f'catalog-{index}'
        writer=Relay(engine,catalog,root/'presets');control=Relay(engine,catalog,root/'presets')
        stop=threading.Event();samples=[];peak=[0];outcome={};errors=[]
        try:
            writer.call('queue_control',{'action':'pause'})
            connection=control.call('service_connection',{'action':'status'});broker=psutil.Process(connection['pid'])
            options={'paths':[str(source)],'mode':'copy','destination':str(destination)}
            if args.second_copy:options['second_copy_destination']=str(backup)
            plan=writer.call('prepare_import',options)['plan']
            started=time.perf_counter()
            while plan['state']=='planning':plan=writer.call('scan_import',{'plan_id':plan['id'],'expected_revision':plan['revision']})['plan']
            scan_ms=(time.perf_counter()-started)*1000
            assert plan['state']=='ready' and plan['selected_count']==args.files
            def sample():
                while not stop.wait(.005):
                    try:peak[0]=max(peak[0],broker.memory_info().rss/1024**2)
                    except psutil.NoSuchProcess:return
            def copy():
                try:outcome.update(writer.call('apply_import',{'plan_id':plan['id'],'expected_revision':plan['revision']}))
                except BaseException as error:errors.append(str(error))
            sampler=threading.Thread(target=sample);sampler.start()
            thread=threading.Thread(target=copy);started=time.perf_counter();thread.start()
            while thread.is_alive():
                begin=time.perf_counter();control.call('status');samples.append((time.perf_counter()-begin)*1000)
                thread.join(.01)
            elapsed=time.perf_counter()-started;stop.set();sampler.join()
            assert not errors,errors
            assert outcome['plan']['state']=='applied' and outcome['plan']['imported']==args.files,outcome
            assert all(sha(path)==original for path in destination.iterdir())
            assert not list(destination.glob('*.part'))
            if args.second_copy:
                backup_files=[p for p in backup.rglob('*') if p.is_file()]
                assert len(backup_files)==args.files and all(sha(path)==original for path in backup_files)
                assert outcome['plan']['copy']['backup']['copied']==args.files
                assert not list(backup.rglob('*.part'))
            ordered=sorted(samples);total=args.files*fixture.stat().st_size*(2 if args.second_copy else 1)
            results.append({'round':index+1,'scan_ms':round(scan_ms,3),'apply_ms':round(elapsed*1000,3),
                'throughput_mib_s':round(total/1024**2/elapsed,2),'broker_peak_mib':round(peak[0],2),
                'control_samples':len(samples),'control_median_ms':round(ordered[len(ordered)//2],3),
                'control_p95_ms':round(ordered[int((len(ordered)-1)*.95)],3),'control_max_ms':round(max(ordered),3),
                'worker_peak_mib':control.call('status')['peak_mb'],'bytes':total,'exact_copies':True})
        finally:
            stop.set();writer.close();control.close()
    assert sha(fixture)==original
    report={'platform':platform.platform(),'memory_gib':round(psutil.virtual_memory().total/1024**3,1),
        'engine_sha256':sha(engine),'fixture_sha256':original,'dimensions':dimensions,'files':args.files,'second_copy':args.second_copy,
        'backend':'filesystem streaming and SHA-256; no image workers or GPU',
        'cache':'Fresh catalog/destination each round; sources and OS caches warm; no app previews',
        'scope':'Copy application includes IPC, preflight, fsync, checksum verification and atomic catalog application; excludes source generation and desktop rendering',
        'results':results,'original_unchanged':True}
    (root/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
