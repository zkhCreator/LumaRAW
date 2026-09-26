"""Exercise the packaged broker/worker with explicit read-only RAW fixtures.

Outputs go only to a new dedicated work directory. Repeated D3S/D4 plus optional
synthetic high-pixel DNG test process isolation, queue receipts and source hashes;
these repetitions do not form a camera compatibility or Nikon colorimetry suite.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import threading
import time
import psutil
import tifffile
from lumaraw.bridge import call, endpoint
from multiprocessing.connection import Client

def digest(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        while chunk:=f.read(1024*1024):h.update(chunk)
    return h.hexdigest()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--engine',required=True,type=Path);parser.add_argument('--work',required=True,type=Path);parser.add_argument('--count',type=int,default=60);parser.add_argument('--max-edge',type=int,default=1024);parser.add_argument('fixtures',nargs='+',type=Path);parser.add_argument('--require-metal',action='store_true');a=parser.parse_args()
    if a.work.exists():raise SystemExit('Choose a new probe directory')
    a.work.mkdir(parents=True);root=a.work/'catalog';root.mkdir();engine=a.engine.resolve()
    before={str(p.resolve()):digest(p) for p in a.fixtures};log=(a.work/'broker.log').open('w')
    broker=subprocess.Popen([str(engine),'--broker','--catalog',str(root.resolve())],stdout=log,stderr=log)
    address,family=endpoint(root)
    try:
        for _ in range(200):
            if broker.poll() is not None:raise RuntimeError('Packaged broker failed')
            try:
                with Client(address,family=family):pass
                break
            except OSError:time.sleep(.05)
        def rpc(method,p=None):
            assert broker.poll() is None
            r=call(root,method,p or {});assert r['ok'],r
            return r['result']
        if a.require_metal:rpc('settings',{'compute_backend':'metal'})
        rpc('queue_control',{'action':'pause'})
        rpc('import_photos',{'paths':list(before)})
        job_ids=[]
        for i in range(a.count):
            id_=i%len(a.fixtures)+1
            photo=rpc('get_photo',{'photo_id':id_})
            rpc('edit_photo',{'photo_id':id_,'expected_revision':photo['revision'],'patch':{'temperature':i%5,'exposure':(i%4)*.1,'sharpen':20}})
            result=rpc('enqueue_exports',{'photo_ids':[id_],'destination':str((a.work/'exports').resolve()),'format':'tiff16' if i%2==0 else 'jpeg','options':{'max_edge':a.max_edge,'space':['srgb','p3','adobe','prophoto'][i%4]},'request_key':f'packaged-batch-{i}'})
            job_ids.extend(result['job_ids'])
        samples=[];child_counts=[];done=threading.Event()
        def sample():
            proc=psutil.Process(broker.pid)
            while not done.wait(.05):
                try:samples.append(proc.memory_info().rss/1024**2);child_counts.append(len(proc.children()))
                except psutil.NoSuchProcess:break
        monitor=threading.Thread(target=sample,daemon=True);monitor.start()
        start=time.monotonic();rpc('queue_control',{'action':'resume'})
        until=start+600
        while time.monotonic()<until:
            jobs=rpc('list_jobs')
            if not jobs['counts'].get('pending',0) and not jobs['counts'].get('running',0):break
            time.sleep(.3)
        done.set();monitor.join()
        receipts=[rpc('get_job',{'job_id':id_}) for id_ in job_ids]
        for job in receipts:
            if job['state']!='done':continue
            if a.require_metal:assert job['processing']['metal_grade_tiles']+job['processing']['metal_output_tiles']>0,job
            path=Path(job['output']);assert path.is_file()
            if job['format']=='tiff16':
                with tifffile.TiffFile(path) as tif:
                    assert tif.pages[0].dtype.name=='uint16'
                    assert 34675 in tif.pages[0].tags
        after={p:digest(p) for p in before}
        assert before==after
        assert max(child_counts)<=1,child_counts
        report={'engine':str(engine),'engine_sha256':digest(engine),'jobs':len(receipts),'output_max_edge':a.max_edge,'elapsed_seconds':round(time.monotonic()-start,2),
            'fixtures':[{'name':Path(p).name,'sha256':sha,'synthetic':Path(p).suffix.lower()=='.dng'} for p,sha in before.items()],
            'all_done':all(j['state']=='done' for j in receipts),'original_hashes_unchanged':True,'maximum_image_children':max(child_counts),
            'service_rss_first_mb':round(samples[0],2),'service_rss_final_mb':round(samples[-1],2),'service_rss_peak_mb':round(max(samples),2),
            'worker_peak_mb':max(j['peak_mb'] for j in receipts),'remaining_partials':[p.name for p in (a.work/'exports').glob('.lumaraw-*')],
            'receipts':[{k:j[k] for k in ('id','state','error','peak_mb','format','output','processing')} for j in receipts]}
        (a.work/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='receipts'},indent=2))
        assert report['all_done'], 'Some jobs failed; inspect report.json'
    finally:
        broker.terminate()
        try:broker.wait(timeout=5)
        except subprocess.TimeoutExpired:broker.kill();broker.wait()
        log.close()
if __name__=='__main__':main()
