"""Reproducible synthetic catalog and thumbnail throughput measurements.

Inputs: a new explicit work directory, row/sample counts. Outputs: JSON timings
and generated fixtures in that directory. No user photos, no benchmark pass/fail
thresholds. Query tests use synthetic rows; thumbnail timings use actual workers.
The warm-worker baseline replays the previous per-thumbnail worker path explicitly.
"""
import argparse
import json
import platform
from pathlib import Path
import statistics
import time

from PIL import Image
import psutil

from lumaraw.model import Recipe
from lumaraw.service import Service


def measure(operation, samples):
    values=[]
    for _ in range(samples):
        started=time.perf_counter()
        operation()
        values.append((time.perf_counter()-started)*1000)
    ordered=sorted(values)
    return {'samples':samples,'median_ms':round(statistics.median(values),3),
            'p95_ms':round(ordered[min(len(ordered)-1,int(len(ordered)*.95))],3)}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--rows',type=int,default=10000)
    parser.add_argument('--samples',type=int,default=30)
    parser.add_argument('--thumbnails',type=int,default=12)
    args=parser.parse_args()
    if not 1 <= args.rows <= 1000000 or not 1 <= args.samples <= 1000 or not 1 <= args.thumbnails <= 60:
        raise SystemExit('Counts are outside probe bounds')
    work=args.work.resolve()
    if work.exists():
        raise SystemExit('Choose a new work directory')
    work.mkdir(parents=True)
    service=Service(work/'catalog')
    try:
        service.dispatch('queue_control',{'action':'pause'})
        service.dispatch('settings',{'compute_backend':'cpu'})
        paths=[]
        for index in range(args.thumbnails):
            path=work/f'sample-{index}.png'
            Image.new('RGB',(600,400),(index*3,110,160)).save(path)
            paths.append(str(path))
        service.dispatch('import_photos',{'paths':paths})
        with service.catalog() as catalog:
            payload=json.dumps(Recipe().dict())
            catalog.db.executemany('INSERT INTO photos(path,name,bytes,mtime,recipe,created,rating,color_label) '
                'VALUES(?,?,?,?,?,?,?,?)',((str(work/'synthetic'/f'{i}.png'),f'catalog-{i:08d}.png',0,0,payload,0,i%6,
                'red' if i%4 == 0 else 'none') for i in range(max(0,args.rows-args.thumbnails))))
            catalog.db.commit()
        smart=service.dispatch('save_collection',{'name':'Best red','kind':'smart',
            'rules':{'rating_min':4,'color_label':'red'}})
        report={'platform':platform.platform(),'machine':platform.machine(),
                'memory_gb':round(psutil.virtual_memory().total/1024**3,1),'catalog_rows':max(args.rows,args.thumbnails),
                'thumbnail_count':args.thumbnails,'thumbnail_source_dimensions':[600,400],
                'scope':'Synthetic catalog, CPU thumbnail workers; not RAW processing or desktop latency'}
        report['smart_collection_matches']=service.dispatch('list_photos',{'collection_id':smart['id']})['total']
        for name,params in (
            ('default_page',{}),('name_sort',{'sort':'name','descending':False}),
            ('rating_filter',{'filters':{'rating_min':4}}),
            ('smart_collection',{'collection_id':smart['id']}),('literal_text_search',{'search':'catalog-00005'}),
        ):
            report[name]=measure(lambda params=params:service.dispatch('list_photos',params),args.samples)
        photo_ids=list(range(1,args.thumbnails+1))
        report['cold_thumbnail_page']=measure(lambda:[service.dispatch('thumbnail',{'photo_id':i}) for i in photo_ids],1)
        report['warm_worker_page_baseline']=measure(lambda:[service.run_worker({
            'operation':'thumbnail','path':path,'recipe':Recipe().dict()}) for path in paths],3)
        report['warm_cached_page']=measure(lambda:service.dispatch('cached_thumbnails',{'photo_ids':photo_ids}),args.samples)
        report['broker_rss_mb']=round(psutil.Process().memory_info().rss/1024**2,2)
        report['sampled_worker_peak_mb']=round(service.peak,2)
        (work/'report.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))
    finally:
        service.close()


if __name__ == '__main__':
    main()
