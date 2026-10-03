"""Measure Presence on an explicit read-only source with isolated generated output.

Inputs: photograph, fresh work directory and CPU/Metal policy. Outputs: per-case
cold/warm worker timings, sampled RSS, dimensions, hashes and processing reports.
Cold means a new LumaRAW cache, not a flushed OS cache. Preview/viewport/export
use the actual supervised worker; this is not native interaction, camera accuracy
or Adobe comparison evidence. No personal catalog, original writes or publication.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from lumaraw.model import Recipe
from lumaraw.runtime import engine_identity, raw_backend
from lumaraw.service import Service


def sha256(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--compute',choices=('cpu','metal'),default='cpu')
    args=parser.parse_args()
    source=args.source.resolve(strict=True);work=args.work.resolve()
    if work.exists() or source==work or work in source.parents:
        parser.error('Choose a new work directory separate from the source')
    before=sha256(source);work.mkdir(parents=True)
    samples=[]
    for mode in ('fit','detail','export'):
        for name,patch in (('baseline',{}),('presence',{'texture':45,'clarity':30,'dehaze':35})):
            case=work/(mode+'-'+name)
            service=Service(case/'catalog',presets_root=case/'presets')
            service.dispatch('queue_control',{'action':'pause'})
            service.compute_backend=args.compute
            try:
                service.dispatch('import_photos',{'paths':[str(source)]})
                for iteration in range(2):
                    row=service.dispatch('get_photo',{'photo_id':1})
                    recipe=Recipe(**patch,exposure=iteration*.05)
                    row=service.dispatch('edit_photo',{'photo_id':1,'expected_revision':row['revision'],
                                                      'patch':recipe.dict()})
                    started=time.perf_counter()
                    if mode=='export':
                        destination=case/'exports';destination.mkdir(exist_ok=True)
                        result=service.run_worker({'operation':'export','path':str(source),'recipe':recipe.dict(),
                            'destination':str(destination),'format':'tiff16','job_id':iteration+1,'cache':str(service.cache)})
                        artifact=result['output']
                    else:
                        options={'photo_id':1,'expected_revision':row['revision'],'include_before':False}
                        if mode=='detail':
                            options['detail']={'cx':.5,'cy':.5,'width':1024,'height':768}
                        else:
                            options['max_edge']=1680
                        result=service.dispatch('preview_photo',options)
                        assert result.get('worker_spawned'), 'A worker measurement reused completed output'
                        artifact=result['preview']
                    elapsed=time.perf_counter()-started
                    processing=result['processing']
                    if args.compute=='metal':
                        assert processing['metal_grade_tiles']+processing['metal_output_tiles']>0
                    sample={'mode':mode,'case':name,'cache':'cold-engine-cache' if iteration==0 else 'warm-linear-cache-new-recipe',
                        'recipe':recipe.dict(),'wall_seconds':round(elapsed,6),'peak_mb':result['peak_mb'],
                        'dimensions':[result.get('width'),result.get('height')],
                        'artifact':str(Path(artifact).relative_to(work)),'artifact_sha256':sha256(Path(artifact)),
                        'processing':processing}
                    samples.append(sample)
                    if mode!='export':
                        started=time.perf_counter();cached=service.dispatch('preview_photo',options)
                        assert cached['preview_cache_hit'] and not cached['worker_spawned']
                        sample['completed_hit_seconds']=round(time.perf_counter()-started,6)
            finally:
                service.close()
    after=sha256(source)
    assert before==after,'The source bytes changed during the probe'
    report={'ok':True,'scope':'Supervised processing; no native interaction or Adobe comparison',
        'platform':platform.platform(),'engine':engine_identity(),'raw_backend':raw_backend(),
        'fixture':{'name':source.name,'sha256':before,'bytes':source.stat().st_size},
        'original_unchanged':True,'os_cache':'Not flushed','samples':samples}
    (work/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({'ok':True,'samples':len(samples),'original_unchanged':True}))


if __name__=='__main__':
    main()
