"""Cold recovery evidence for a killed packaged broker, with unknown publication.

Only uses a new disposable catalog and caller-supplied read-only RAW. Killing the
broker is intentional; the output effect is conservatively recorded as unknown.
No recovered export is replayed, and no potentially published output is deleted.
"""
import argparse
import json
from multiprocessing.connection import Client
from pathlib import Path
import subprocess
import time
import psutil
from lumaraw.bridge import endpoint,call

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--engine',required=True);parser.add_argument('--work',type=Path,required=True);parser.add_argument('--fixture',required=True);a=parser.parse_args()
    if a.work.exists():raise SystemExit('Choose a new directory')
    a.work.mkdir(parents=True);root=a.work/'catalog';root.mkdir();address,family=endpoint(root)
    def start():
        process=subprocess.Popen([a.engine,'--broker','--catalog',str(root.resolve())],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(150):
            if process.poll() is not None:raise RuntimeError('Broker exited')
            try:
                with Client(address,family=family):pass
                return process
            except OSError:time.sleep(.05)
        raise TimeoutError('Broker startup')
    broker=start();worker=None
    try:
        def rpc(method,p=None):
            response=call(root,method,p or {});assert response['ok'],response;return response['result']
        rpc('import_photos',{'paths':[a.fixture]})
        rpc('edit_photo',{'photo_id':1,'expected_revision':0,'patch':{'temperature':37,'luma_noise':90,'sharpen':100}})
        job=rpc('enqueue_exports',{'photo_ids':[1],'destination':str((a.work/'export').resolve()),'format':'tiff16','request_key':'crash-once'})['job_ids'][0]
        for _ in range(150):
            status=rpc('status')
            if status['active'] and status['active']['operation']=='export':
                worker=psutil.Process(status['active']['pid']);break
            time.sleep(.02)
        assert worker is not None
        receipt_before=rpc('get_job',{'job_id':job});assert receipt_before['state']=='running'
        broker.kill();broker.wait();exit_code=broker.returncode
        for _ in range(100):
            if not worker.is_running() or worker.status()==psutil.STATUS_ZOMBIE:break
            time.sleep(.05)
        worker_stopped=not worker.is_running() or worker.status()==psutil.STATUS_ZOMBIE
        assert worker_stopped
        broker=start();receipt_after=rpc('get_job',{'job_id':job})
        time.sleep(1)
        cold=rpc('get_job',{'job_id':job})
        assert receipt_after['state']==cold['state']=='interrupted'
        assert rpc('status')['active'] is None
        result={'ok':True,'broker_exit_code':exit_code,'termination':'SIGKILL','unknown_effect':True,'before_state':receipt_before['state'],
            'recovered_state':cold['state'],'cold_no_replay':True,'orphan_worker_stopped':worker_stopped,
            'published_files_observed':[p.name for p in (a.work/'export').glob('*.tif')],
            'note':'No retry requested; publication uncertainty preserved.'}
        (a.work/'report.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
    finally:
        if broker.poll() is None:broker.terminate();broker.wait(timeout=5)
if __name__=='__main__':main()
