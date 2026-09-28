"""Measure bounded missing-folder planning, scanning and atomic catalog remapping.

Inputs: an explicit new work directory and synthetic row count. Outputs: timings,
concurrent browse latency and RSS; the replacement directory exists but photos do
not. Measures worst-case missing issue pages, not hash throughput, RAW processing,
IPC or desktop interaction. Uses production triggers and service commands.
"""
import argparse
import json
from pathlib import Path
import platform
import resource
import statistics
import threading
import time

import psutil

from lumaraw.model import Recipe
from lumaraw.service import Service


def summary(values):
    ordered = sorted(values)
    return {'samples':len(values), 'median_ms':round(statistics.median(values),3),
            'p95_ms':round(ordered[min(len(ordered)-1,int(len(ordered)*.95))],3),
            'max_ms':round(max(values),3)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--rows',type=int,default=10000)
    args = parser.parse_args()
    if not 120 <= args.rows <= 1000000:
        raise SystemExit('Row count outside probe bounds')
    root = args.work.resolve()
    if root.exists():raise SystemExit('Choose a new work directory')
    root.mkdir(parents=True);destination=root/'Located';destination.mkdir()
    service = Service(root/'catalog')
    done = threading.Event();browse=[];browse_errors=[]
    def reader():
        while not done.wait(.02):
            started = time.perf_counter()
            try:
                result = service.dispatch('list_photos',{'stacked':False})
                assert len(result['photos']) <= 60 and result['total'] == args.rows
                browse.append((time.perf_counter()-started)*1000)
            except Exception as error:
                browse_errors.append(str(error));return
    thread = None
    try:
        service.dispatch('queue_control',{'action':'pause'})
        started = time.perf_counter()
        with service.catalog() as catalog,catalog.db:
            recipe=json.dumps(Recipe().dict())
            catalog.db.executemany('INSERT INTO photos(path,name,bytes,mtime,recipe,created) VALUES(?,?,0,0,?,0)',
                ((str(root/'Missing'/f'shoot-{i%1000:04}'/f'{i:08}.png'),f'{i:08}.png',recipe) for i in range(args.rows)))
        insertion = (time.perf_counter()-started)*1000
        leaf = service.dispatch('get_folder',{'photo_id':1})
        with service.catalog() as catalog:
            folder_id=catalog.db.execute('SELECT id FROM catalog_folders WHERE path=?',(leaf['parent_path'],)).fetchone()[0]
        report={'platform':platform.platform(),'machine':platform.machine(),'memory_gb':round(psutil.virtual_memory().total/1024**3,1),
                'photos':args.rows,'folders':1001,'scope':'In-process service/SQL and missing-file stat; no hash/RAW/IPC/UI',
                'cache':'Warm catalog; first pass over missing paths','synthetic_insert_ms':round(insertion,3)}
        thread=threading.Thread(target=reader);thread.start()
        started=time.perf_counter()
        plan=service.dispatch('prepare_folder_relocation',{'folder_id':folder_id,'destination':str(destination),
            'expected_revision':service.dispatch('library_state')['folder_revision']})['plan']
        report['prepare_ms']=round((time.perf_counter()-started)*1000,3)
        pages=[];started=time.perf_counter()
        while plan['state']=='planning':
            page_start=time.perf_counter()
            result=service.dispatch('scan_folder_relocation',{'plan_id':plan['id'],'expected_revision':plan['revision']})
            plan=result['plan'];assert len(result['items'])<=60
            pages.append((time.perf_counter()-page_start)*1000)
        report['scan_total_ms']=round((time.perf_counter()-started)*1000,3);report['scan_page']=summary(pages)
        assert plan['scanned']==args.rows and plan['missing']==args.rows and plan['conflicts']==0
        # Separate commit cost from stat validation while keeping the real apply
        # service path and admission/revision checks intact.
        from lumaraw.relocations import Relocations
        original_apply=Relocations.apply;commit=[]
        def timed_apply(self,*params):
            started=time.perf_counter()
            try:return original_apply(self,*params)
            finally:commit.append((time.perf_counter()-started)*1000)
        Relocations.apply=timed_apply
        started=time.perf_counter()
        try:result=service.dispatch('apply_folder_relocation',{'plan_id':plan['id'],'expected_revision':plan['revision']})['plan']
        finally:Relocations.apply=original_apply
        report['apply_total_ms']=round((time.perf_counter()-started)*1000,3);report['atomic_commit_ms']=round(commit[0],3)
        assert result['state']=='applied' and result['checked']==args.rows
        done.set();thread.join();thread=None
        assert not browse_errors,browse_errors
        report['concurrent_browse']=summary(browse)
        with service.catalog() as catalog:
            assert catalog.db.execute('SELECT count(*) FROM photos WHERE missing=1 AND path LIKE ?', (str(destination)+'/%',)).fetchone()[0]==args.rows
            assert catalog.db.execute('SELECT total_count FROM catalog_folders WHERE id=?',(result['result_folder_id'],)).fetchone()[0]==args.rows
            assert catalog.db.execute('SELECT count(*) FROM relocation_files').fetchone()[0]==0
        report['peak_rss_mb']=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024**2 if platform.system()=='Darwin' else 1024),2)
        report['worker_peak_mb']=service.peak
        (root/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    finally:
        done.set()
        if thread:thread.join()
        service.close()


if __name__=='__main__':main()
