"""Verify packaged missing-folder reconnection and full-size RAW export continuity.

Inputs: explicit engine and read-only RAW fixture, plus a new work directory.
Outputs: a private copy of that fixture, relocated catalog, two export receipts and
JSON evidence. Only the generated copy is moved. The user fixture is hashed before
and after; no desktop automation or camera/color equivalence claim is made.
"""
import argparse
import json
from multiprocessing.connection import Client
from pathlib import Path
import shutil
import subprocess
import time

from PIL import Image
import tifffile

from bundle_probe import digest
from lumaraw.bridge import call, endpoint


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--engine',type=Path,required=True)
    parser.add_argument('--fixture',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True)
    args=parser.parse_args()
    root=args.work.resolve();fixture=args.fixture.resolve(strict=True)
    if root.exists():raise SystemExit('Choose a new work directory')
    before=digest(fixture);root.mkdir(parents=True)
    original=root/'Originals';original.mkdir();shutil.copy2(fixture,original/fixture.name)
    destination=root/'Located';catalog=root/'catalog'
    log=(root/'broker.log').open('w')
    broker=subprocess.Popen([str(args.engine.resolve()),'--broker','--catalog',str(catalog)],stdout=log,stderr=log)
    try:
        address,family=endpoint(catalog)
        for _ in range(200):
            if broker.poll() is not None:raise RuntimeError('Packaged broker failed')
            try:
                with Client(address,family=family):pass
                break
            except OSError:time.sleep(.05)
        else:raise RuntimeError('Packaged broker did not become ready')
        def rpc(method,params=None):
            response=call(catalog,method,params or {})
            assert response['ok'],response
            return response['result']
        rpc('queue_control',{'action':'pause'});rpc('settings',{'compute_backend':'metal'})
        rpc('import_photos',{'paths':[str(original/fixture.name)]});rpc('index_library')
        photo=rpc('get_photo',{'photo_id':1})
        copy=rpc('create_virtual_copies',{'targets':[{'photo_id':1,'expected_revision':photo['revision'],
            'expected_metadata_revision':photo['metadata_revision']}]})['photos'][0]
        rpc('edit_photo',{'photo_id':copy['id'],'expected_revision':copy['revision'],'patch':{'exposure':1.0}})
        jobs=[]
        for photo_id,fmt in ((1,'tiff16'),(copy['id'],'jpeg')):
            jobs.extend(rpc('enqueue_exports',{'photo_ids':[photo_id],'destination':str(root/'exports'),'format':fmt,
                'options':{'max_edge':0},'request_key':f'relocation-{fmt}'})['job_ids'])
        frozen=[rpc('get_job',{'job_id':id_}) for id_ in jobs]
        folder=rpc('get_folder',{'photo_id':1});original.rename(destination)
        plan=rpc('prepare_folder_relocation',{'folder_id':folder['id'],'destination':str(destination),
            'expected_revision':rpc('library_state')['folder_revision']})['plan']
        started=time.perf_counter()
        plan=rpc('scan_folder_relocation',{'plan_id':plan['id'],'expected_revision':plan['revision']})['plan']
        scan_ms=(time.perf_counter()-started)*1000
        assert plan['verified']==1 and plan['photo_count']==2 and plan['unverified']==0
        plan=rpc('apply_folder_relocation',{'plan_id':plan['id'],'expected_revision':plan['revision']})['plan']
        assert plan['state']=='applied'
        for id_,snapshot in zip(jobs,frozen):
            current=rpc('get_job',{'job_id':id_})
            for key in ('recipe','options','destination','format'):assert current[key]==snapshot[key]
            assert current['source']==str(destination/fixture.name)
        started=time.perf_counter();rpc('queue_control',{'action':'resume'})
        deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            receipts=[rpc('get_job',{'job_id':id_}) for id_ in jobs]
            if all(row['state'] in ('done','failed','interrupted','cancelled') for row in receipts):break
            time.sleep(.1)
        assert all(row['state']=='done' for row in receipts),receipts
        dimensions=[]
        for row in receipts:
            assert row['processing']['metal_grade_tiles']+row['processing']['metal_output_tiles']>0
            with Image.open(row['output']) as image:
                dimensions.append(list(image.size));assert image.info.get('icc_profile')
            if row['format']=='tiff16':
                with tifffile.TiffFile(row['output']) as image:assert image.pages[0].dtype.name=='uint16'
        assert dimensions[0]==dimensions[1] and min(dimensions[0])>1024
        assert digest(fixture)==before==digest(destination/fixture.name)
        report={'ok':True,'fixture':fixture.name,'fixture_sha256':before,'fixture_bytes':fixture.stat().st_size,
            'source_and_copy_unchanged':True,'scan_hash_ms':round(scan_ms,3),'physical_originals':1,'catalog_variants':2,
            'full_size_dimensions':dimensions,'output_formats':['tiff16','jpeg'],'frozen_jobs_preserved':True,
            'two_exports_seconds':round(time.perf_counter()-started,3),
            'cache':'Cold pixel cache; the second variant can reuse decoded source cache. Hash reads are warm after copying/indexing.',
            'worker_peak_mb':max(row['peak_mb'] for row in receipts),'receipts':receipts}
        (root/'report.json').write_text(json.dumps(report,indent=2))
        print(json.dumps({key:value for key,value in report.items() if key!='receipts'},indent=2))
    finally:
        broker.terminate()
        try:broker.wait(timeout=5)
        except subprocess.TimeoutExpired:broker.kill();broker.wait()
        log.close()


if __name__=='__main__':main()
