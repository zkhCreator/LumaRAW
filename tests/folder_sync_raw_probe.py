"""Verify packaged folder discovery, XMP reads and full-size RAW export continuity.

Inputs: explicit engine and read-only RAW fixture, plus a new work directory.
Outputs: catalog references discovered by synchronization, full-size export
receipts and source-hash evidence. Only generated copies/sidecars are changed.
Times are integration diagnostics; no camera accuracy or desktop claim is made.
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
from lumaraw.bridge import call,endpoint


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--engine',type=Path,required=True)
    parser.add_argument('--fixture',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True)
    args=parser.parse_args()
    root=args.work.resolve();fixture=args.fixture.resolve(strict=True)
    if root.exists():raise SystemExit('Choose a new work directory')
    before=digest(fixture);root.mkdir(parents=True)
    originals=root/'Originals';originals.mkdir()
    seed=originals/'seed.png';Image.new('RGB',(16,12)).save(seed)
    catalog=root/'catalog';log=(root/'broker.log').open('w')
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
        def sync(folder):
            plan=rpc('prepare_folder_sync',{'folder_id':folder['id'],
                'expected_revision':rpc('library_state')['folder_revision'],'scan_metadata':True})['plan']
            while plan['state']=='planning':
                result=rpc('scan_folder_sync',{'plan_id':plan['id'],'expected_revision':plan['revision']})
                plan=result['plan']
            assert plan['state']=='ready' and plan['counts'].get('error',0)==0,plan
            receipt=rpc('apply_folder_sync',{'plan_id':plan['id'],'expected_revision':plan['revision']})['plan']
            assert receipt['state']=='applied',receipt
            return result,receipt
        rpc('queue_control',{'action':'pause'});rpc('settings',{'compute_backend':'metal'})
        rpc('import_photos',{'paths':[str(seed)]})
        folder=rpc('get_folder',{'photo_id':1})
        source=originals/fixture.name;shutil.copy2(fixture,source)
        sidecar=source.with_suffix('.xmp')
        sidecar.write_text('<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
            '<rdf:Description xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:xmp="http://ns.adobe.com/xap/1.0/" '
            'xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/" xmp:Rating="4" crs:Exposure2012="2.0">'
            '<dc:title>Raw discovery</dc:title></rdf:Description></rdf:RDF>')
        started=time.perf_counter();review,receipt=sync(folder)
        sync_ms=(time.perf_counter()-started)*1000
        assert receipt['imported']==1
        item=next(item for item in review['items'] if item['path']==str(source))
        assert item['notes'] and item['clock']['camera']
        master=next(p for p in rpc('list_photos',{'stacked':False})['photos'] if p['path']==str(source))
        master=rpc('get_photo',{'photo_id':master['id']})
        assert master['title']=='Raw discovery' and master['rating']==4 and master['recipe']['exposure']==0
        copy=rpc('create_virtual_copies',{'targets':[{'photo_id':master['id'],
            'expected_revision':master['revision'],'expected_metadata_revision':master['metadata_revision']}]})['photos'][0]
        rpc('edit_photo',{'photo_id':copy['id'],'expected_revision':copy['revision'],'patch':{'exposure':1.0}})
        jobs=[]
        for photo_id,fmt in ((master['id'],'tiff16'),(copy['id'],'jpeg')):
            jobs+=rpc('enqueue_exports',{'photo_ids':[photo_id],'destination':str(root/'exports'),'format':fmt,
                'options':{'max_edge':0},'request_key':f'folder-sync-{fmt}'})['job_ids']
        frozen=[rpc('get_job',{'job_id':id_}) for id_ in jobs]
        sidecar.write_text(sidecar.read_text().replace('Raw discovery','After queue'))
        _,updated=sync(folder)
        assert updated['modified']==1
        assert rpc('get_photo',{'photo_id':copy['id']})['title']=='Raw discovery'
        assert [rpc('get_job',{'job_id':id_}) for id_ in jobs]==frozen
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
        assert digest(fixture)==before==digest(source)
        report={'ok':True,'fixture':fixture.name,'fixture_sha256':before,'fixture_bytes':fixture.stat().st_size,
            'source_and_copy_unchanged':True,'discovery_sync_ms':round(sync_ms,3),'camera':master['camera'],
            'unsupported_develop_reported':True,'copy_metadata_independent':True,'frozen_jobs_preserved':True,
            'full_size_dimensions':dimensions,'output_formats':['tiff16','jpeg'],
            'two_exports_seconds':round(time.perf_counter()-started,3),
            'cache':'Warm metadata after copying; cold pixel cache; second variant can reuse decoded source.',
            'worker_peak_mb':max(row['peak_mb'] for row in receipts),'receipts':receipts}
        (root/'report.json').write_text(json.dumps(report,indent=2))
        print(json.dumps({key:value for key,value in report.items() if key!='receipts'},indent=2))
    finally:
        broker.terminate()
        try:broker.wait(timeout=5)
        except subprocess.TimeoutExpired:broker.kill();broker.wait()
        log.close()


if __name__=='__main__':main()

