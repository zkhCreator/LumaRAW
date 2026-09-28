"""Measure whole comparison/Survey preview requests with synthetic photographs.

Inputs: a new work directory, backend and bounded sample count. Outputs: generated
1600x1067 raster, disposable catalog and JSON receipt. Timings include worker
startup/encoding but not native UI/IPC. Warm-decode samples have unique recipes
so final-preview caches cannot conceal processing. No camera-speed claim.
"""
import argparse
import json
from pathlib import Path
import platform
import statistics
import time

import numpy as np
from PIL import Image
import psutil

from lumaraw.service import Service


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=5)
    parser.add_argument('--backend',choices=('cpu','metal'),default='cpu')
    args=parser.parse_args()
    if not 1 <= args.samples <= 100: raise SystemExit('Sample count must be 1–100')
    work=args.work.resolve()
    if work.exists(): raise SystemExit('Choose a new work directory')
    work.mkdir(parents=True)
    x=np.linspace(0,255,1600,dtype=np.uint8)[None,:]
    y=np.linspace(0,255,1067,dtype=np.uint8)[:,None]
    path=work/'synthetic.png'
    Image.fromarray(np.stack(np.broadcast_arrays(x,y,x//2+y//2),axis=-1)).save(path)
    service=Service(work/'catalog')
    try:
        service.dispatch('queue_control',{'action':'pause'})
        service.dispatch('settings',{'compute_backend':args.backend})
        service.dispatch('import_photos',{'paths':[str(path)]})
        report={'platform':platform.platform(),'machine':platform.machine(),
                'memory_gb':round(psutil.virtual_memory().total/1024**3,1),
                'source_dimensions':[1600,1067],'backend':args.backend,
                'scope':'In-process service and disposable worker; excludes UI/IPC; synthetic raster, not RAW'}
        start=time.perf_counter()
        cold=service.dispatch('preview_photo',{'photo_id':1})
        report['cold_decode_default']={'samples':1,'elapsed_ms':round((time.perf_counter()-start)*1000,2),
                                       'processing':cold.get('processing',{})}
        revision=0
        for name,params in (('with_baseline',{}),('compare',{'include_before':False}),
                            ('survey',{'include_before':False,'max_edge':512})):
            elapsed=[];processing=[]
            for index in range(args.samples):
                result=service.dispatch('edit_photo',{'photo_id':1,'expected_revision':revision,
                    'patch':{'exposure':.1+(index+1)/100}})
                revision=result['revision']
                start=time.perf_counter()
                preview=service.dispatch('preview_photo',{'photo_id':1,**params})
                elapsed.append((time.perf_counter()-start)*1000)
                processing.append(preview.get('processing',{}))
            ordered=sorted(elapsed)
            report[name]={'samples':args.samples,'cache':'warm linear source, uncached final recipe/output',
                          'dimensions':[preview['width'],preview['height']],
                          'median_ms':round(statistics.median(elapsed),2),
                          'p95_ms':round(ordered[min(len(ordered)-1,int(len(ordered)*.95))],2),
                          'processing':processing}
        report['broker_rss_mb']=round(psutil.Process().memory_info().rss/1024**2,2)
        report['sampled_worker_peak_mb']=round(service.peak,2)
        (work/'report.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))
    finally:
        service.close()


if __name__ == '__main__':
    main()
