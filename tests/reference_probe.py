"""Measure revision-bound Reference/Active previews through a packaged broker.

Inputs: an explicit read-only RAW fixture, engine and new work directory. Outputs:
sequential CPU/Metal cold-application/warm-cache fit/detail latency and sampled
worker RSS, with pixel comparisons. CLI/IPC is included, native display excluded.
No OS-cache reset, camera-color accuracy or Adobe equivalence is claimed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import time

import numpy as np
from PIL import Image


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--engine',required=True,type=Path)
    parser.add_argument('--fixture',required=True,type=Path)
    parser.add_argument('--work',required=True,type=Path)
    args=parser.parse_args();args.work.mkdir(parents=True,exist_ok=False)
    root=args.work.resolve();engine=args.engine.resolve();fixture=args.fixture.resolve()
    original=hashlib.sha256(fixture.read_bytes()).hexdigest()
    records=[];images={}
    for backend in ('cpu','metal'):
        catalog=root/backend
        def call(method,params=None):
            start=time.perf_counter()
            result=subprocess.run([str(engine),'--catalog',str(catalog),method],
                input=json.dumps(params or {}),text=True,capture_output=True,timeout=180,
                env={**os.environ,'LUMARAW_PRESETS_ROOT':str(root/'presets'/backend)})
            reply=json.loads(result.stdout)
            if result.returncode or not reply.get('ok'):raise RuntimeError(reply)
            return reply['result'],(time.perf_counter()-start)*1000
        call('queue_control',{'action':'pause'})
        call('settings',{'compute_backend':backend})
        call('import_photos',{'paths':[str(fixture)]})
        p,_=call('get_photo',{'photo_id':1})
        copied,_=call('create_virtual_copies',{'targets':[{'photo_id':1,'expected_revision':p['revision'],'expected_metadata_revision':p['metadata_revision']}]})
        active=copied['photos'][0]['id']
        call('edit_photo',{'photo_id':active,'expected_revision':0,'patch':{'exposure':.35,'shadows':20,'blue_hue':-9}})
        cases=[('reference-cold-fit',1,0,False),('active-fit',active,1,False),
               ('reference-warm-fit',1,0,False),('reference-cold-detail',1,0,True),
               ('reference-warm-detail',1,0,True),('active-detail',active,1,True)]
        for name,id_,revision,detail in cases:
            params={'photo_id':id_,'expected_revision':revision,'include_before':False}
            if detail:params['detail']={'cx':.6,'cy':.4,'width':800,'height':600}
            else:params['max_edge']=1680
            result,elapsed=call('preview_photo',params)
            assert 'before' not in result and result['revision']==revision
            processing=result['processing']
            if backend=='metal':assert processing['metal_grade_tiles']>0
            path=root/f'{backend}-{name}.png';shutil.copy2(result['preview'],path)
            with Image.open(path) as image:
                assert image.info.get('icc_profile');images[(backend,name)]=np.array(image)
            records.append({'backend':backend,'case':name,'wall_ms':round(elapsed,3),
                'worker_peak_mib':result['peak_mb'],'width':result['width'],'height':result['height'],
                'roi':result['roi'],'processing':processing})
        before=images[(backend,'reference-cold-fit')]
        assert np.array_equal(before,images[(backend,'reference-warm-fit')])
        assert np.array_equal(images[(backend,'reference-cold-detail')],images[(backend,'reference-warm-detail')])
        assert not np.array_equal(before,images[(backend,'active-fit')])
    differences={}
    for _,name in images:
        if name in differences:continue
        error=np.abs(images[('cpu',name)].astype(np.int16)-images[('metal',name)].astype(np.int16))
        differences[name]={'max_code':int(error.max()),'mean_code':float(error.mean())}
        assert error.max()<=1
    assert hashlib.sha256(fixture.read_bytes()).hexdigest()==original
    report={'system':platform.platform(),'fixture_sha256':original,'fixture_bytes':fixture.stat().st_size,
            'scope':'Single sequential samples; CLI/IPC included, native UI and cold OS cache excluded',
            'runs':records,'cpu_metal_differences':differences,'original_unchanged':True}
    (root/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))


if __name__=='__main__':main()
