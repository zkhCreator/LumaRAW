"""Measure dictionary parsing, transactional import and streamed file export.

Inputs: a new work directory and synthetic tag count. Outputs: timings, file sizes,
RSS and catalog counts. Input has one synonym per leaf and a shared parent. The
generated file is warm in the OS cache; the first catalog is new. No photos, pixels,
network volumes, IPC or desktop responsiveness are included.
"""
import argparse
import json
from pathlib import Path
import platform
import resource
import time

import psutil

from lumaraw.keyword_exchange import read_document
from lumaraw.service import Service
from library_probe import measure


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--tags',type=int,default=10000)
    args=parser.parse_args()
    if not 1000<=args.tags<=500000:raise SystemExit('Counts outside probe bounds')
    root=args.work.resolve()
    if root.exists():raise SystemExit('Choose a new work directory')
    root.mkdir(parents=True)
    source=root/'input.txt'
    with source.open('w',encoding='utf-8') as stream:
        stream.write('[Places]\n')
        for i in range(args.tags):stream.write(f'\tPlace {i:06} 海岸\n\t\t{{Alias {i:06}}}\n')
    s=Service(root/'catalog')
    try:
        report={'platform':platform.platform(),'machine':platform.machine(),
            'memory_gb':round(psutil.virtual_memory().total/1024**3,1),'tags':args.tags+1,
            'synonyms':args.tags,'input_bytes':source.stat().st_size,
            'scope':'Service/SQLite and local files; no photographs, IPC or UI',
            'cache':'Generated input warm in OS cache; first catalog new'}
        started=time.perf_counter()
        with read_document(source) as (document,_,_):
            report['parse_ms']=round((time.perf_counter()-started)*1000,3)
            started=time.perf_counter()
            with s.catalog() as c:result=document.apply(c,0)
            report['initial_apply_ms']=round((time.perf_counter()-started)*1000,3)
        assert result['created']==args.tags+1
        request={'path':str(source),'expected_revision':result['keyword_revision']}
        report['repeat_import']=measure(lambda:s.dispatch('import_keywords',request),3)
        for format in ('text','csv'):
            counter=0
            def export():
                nonlocal counter
                counter+=1
                output=root/f'output-{counter}.{"csv" if format=="csv" else "txt"}'
                receipt=s.dispatch('export_keywords',{'path':str(output),'format':format,'expected_revision':result['keyword_revision']})
                assert receipt['keywords']==args.tags+1 and receipt['synonyms']==args.tags
                return receipt
            first=export()
            report[f'export_{format}']=measure(export,3)
            report[f'export_{format}']['bytes']=first['bytes']
        report['peak_rss_mb']=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024**2 if platform.system()=='Darwin' else 1024),2)
        report['worker_peak_mb']=s.peak
        assert s.peak==0
        (root/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    finally:s.close()


if __name__=='__main__':main()
