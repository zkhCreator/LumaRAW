"""Measure independent orientation using sequential packaged image workers.

Inputs: one explicit read-only RAW, packaged engine and new work directory.
Outputs: full-resolution TIFF parity, actual Metal dispatch, wall time and sampled
worker RSS. A priming export warms the linear cache for each recipe; timed runs
include process startup and encoding. No OS-cache, camera-color or UI claims.
"""
import argparse
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import threading
import time

import numpy as np
import psutil
import tifffile

from acceleration_probe import digest


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--engine',type=Path,required=True)
    parser.add_argument('--fixture',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=3)
    args=parser.parse_args()
    if not 1<=args.samples<=30:
        raise SystemExit('Choose 1 to 30 samples')
    root=args.work.resolve()
    root.mkdir()
    engine=args.engine.resolve()
    source=args.fixture.resolve()
    original=digest(source)
    runs=[]
    recipes={'neutral':{},'masked':{'exposure':0.3,'crop_box':[.07,.09,.93,.94],
        'straighten':2,'sharpen':25,'luma_noise':10,'chroma_noise':8,
        'masks':[{'kind':'radial','x':.23,'y':.63,'radius':.18,'exposure':1.1},
                 {'kind':'linear','x':.1,'y':.1,'x2':.9,'y2':.7,'exposure':-.7}]}}

    def run(label,recipe,orientation,prime=False):
        destination=root/f'output-{len(runs):03}'
        destination.mkdir()
        request={'operation':'export','path':str(source),'recipe':recipe,
            'orientation':orientation,'cache':str(root/'cache'),
            'budget_mb':4096,'compute_backend':'metal','destination':str(destination),
            'format':'tiff16','job_id':len(runs)+1,'options':{'space':'prophoto','max_edge':0}}
        start=time.perf_counter()
        process=subprocess.Popen([str(engine),'--worker'],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            env={**os.environ,'OMP_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'1','VECLIB_MAXIMUM_THREADS':'2'})
        peak=[0.]
        done=threading.Event()
        def monitor():
            while not done.wait(.02):
                try:
                    peak[0]=max(peak[0],psutil.Process(process.pid).memory_info().rss/1024**2)
                except psutil.NoSuchProcess:
                    break
        thread=threading.Thread(target=monitor)
        thread.start()
        try:
            stdout,stderr=process.communicate(json.dumps(request).encode()+b'\n',timeout=300)
        finally:
            if process.poll() is None:
                process.kill();process.wait()
            done.set();thread.join()
        elapsed=time.perf_counter()-start
        result=json.loads(stdout)
        assert process.returncode==0 and result['ok'],(result,stderr.decode())
        processing=result['processing']
        assert processing['metal_grade_tiles']+processing['metal_output_tiles']>0,result
        item={'recipe':label,'orientation':orientation,'priming':prime,
            'wall_seconds':round(elapsed,6),'peak_worker_rss_mb':round(peak[0],2),
            'processing':processing,'output':result['output']}
        runs.append(item)
        return item

    comparisons=[]
    for label,recipe in recipes.items():
        run(label,recipe,0,True)
        for index in range(args.samples):
            pair={value:run(label,recipe,value) for value in ((0,1) if index%2==0 else (1,0))}
            canonical=tifffile.imread(pair[0]['output'])
            rotated=tifffile.imread(pair[1]['output'])
            expected=np.rot90(canonical,-1)
            assert rotated.shape==expected.shape
            difference=np.abs(rotated.astype(np.int32)-expected.astype(np.int32))
            comparisons.append({'recipe':label,'sample':index,'canonical_dimensions':list(canonical.shape),
                'rotated_dimensions':list(rotated.shape),'max_code_difference':int(difference.max()),
                'mean_code_difference':float(difference.mean())})
            assert difference.max()<=1,comparisons[-1]
            del canonical,rotated,expected,difference
    summary=[]
    for label in recipes:
        for orientation in (0,1):
            items=[r for r in runs if r['recipe']==label and r['orientation']==orientation and not r['priming']]
            summary.append({'recipe':label,'orientation':orientation,'samples':len(items),
                'median_seconds':round(statistics.median(r['wall_seconds'] for r in items),6),
                'max_worker_rss_mb':max(r['peak_worker_rss_mb'] for r in items)})
    assert digest(source)==original
    report={'engine_sha256':digest(engine),'source_sha256':original,'original_unchanged':True,
        'platform':platform.platform(),'machine':platform.machine(),
        'memory_gb':round(psutil.virtual_memory().total/1024**3,1),'recipes':recipes,
        'scope':'Sequential warm linear-cache workers; startup and full TIFF encoding included; RSS sampled every 20 ms',
        'summary':summary,'pixel_parity':comparisons,'runs':runs}
    (root/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
