"""Measure durable folder sync over a large metadata catalog and bounded scans.

Inputs: new work directory and catalog row count. Outputs: timings, concurrent
browse waits and RSS. Synthetic originals are absent except one empty placeholder;
10% additional empty .png files exercise discovery/import without pixel decoding.
These are metadata/SQLite/stat results, not valid-image, RAW or desktop benchmarks.
"""
import argparse
import json
from pathlib import Path
import platform
import resource
import threading
import time

import psutil

from relocation_probe import summary
from lumaraw.model import Recipe
from lumaraw.service import Service
from lumaraw.folder_sync import FolderSync


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--rows',type=int,default=10000)
    args=parser.parse_args()
    if not 120<=args.rows<=1000000:raise SystemExit('Row count outside probe bounds')
    root=args.work.resolve()
    if root.exists():raise SystemExit('Choose a new work directory')
    pictures=root/'Photos';pictures.mkdir(parents=True)
    (pictures/'existing.png').touch()
    new=pictures/'New';new.mkdir()
    new_count=args.rows//10
    for index in range(new_count):(new/f'{index:08}.png').touch()
    service=Service(root/'catalog')
    stop=threading.Event();reads=[];errors=[];thread=None
    def reader():
        while not stop.wait(.02):
            started=time.perf_counter()
            try:
                result=service.dispatch('list_photos',{'stacked':False})
                assert result['total'] in (args.rows,new_count+1) and len(result['photos'])<=60
                reads.append((time.perf_counter()-started)*1000)
            except Exception as error:errors.append(str(error));return
    try:
        service.dispatch('queue_control',{'action':'pause'})
        started=time.perf_counter()
        with service.catalog() as catalog,catalog.db:
            recipe=json.dumps(Recipe().dict())
            catalog.db.executemany('INSERT INTO photos(path,name,bytes,mtime,recipe,created) VALUES(?,?,0,0,?,0)',
                ((str(pictures/'existing.png') if i==0 else str(pictures/f'shoot-{i%1000:04}'/f'{i:08}.png'),f'{i:08}.png',recipe)
                 for i in range(args.rows)))
        setup_ms=(time.perf_counter()-started)*1000
        folder=service.dispatch('get_folder',{'photo_id':1})
        report={'platform':platform.platform(),'machine':platform.machine(),'memory_gb':round(psutil.virtual_memory().total/1024**3,1),
                'catalog_originals':args.rows,'missing_originals':args.rows-1,'new_files':new_count,
                'scope':'In-process service/SQL and filesystem stat; empty synthetic files, no hashes, pixels, IPC or UI',
                'cache':'Warm catalog and recently created directory entries','synthetic_insert_ms':round(setup_ms,3)}
        thread=threading.Thread(target=reader);thread.start()
        started=time.perf_counter()
        plan=service.dispatch('prepare_folder_sync',{'folder_id':folder['id'],'expected_revision':folder['folder_revision'],'scan_metadata':False})['plan']
        report['prepare_ms']=round((time.perf_counter()-started)*1000,3)
        pages=[];started=time.perf_counter()
        while plan['state']=='planning':
            start=time.perf_counter()
            result=service.dispatch('scan_folder_sync',{'plan_id':plan['id'],'expected_revision':plan['revision']})
            plan=result['plan'];assert len(result['items'])<=60
            pages.append((time.perf_counter()-start)*1000)
        assert plan['state']=='ready',plan
        assert plan['counts']['new']==new_count and plan['counts']['missing']==args.rows-1
        report['scan_total_ms']=round((time.perf_counter()-started)*1000,3);report['scan_request']=summary(pages)
        original=FolderSync.apply;commit=[]
        def timed(self,*params):
            started=time.perf_counter()
            try:return original(self,*params)
            finally:commit.append((time.perf_counter()-started)*1000)
        FolderSync.apply=timed
        started=time.perf_counter()
        try:
            plan=service.dispatch('apply_folder_sync',{'plan_id':plan['id'],'expected_revision':plan['revision'],
                'remove_missing':True,'read_metadata':False})['plan']
        finally:FolderSync.apply=original
        report['apply_total_ms']=round((time.perf_counter()-started)*1000,3);report['atomic_commit_ms']=round(commit[0],3)
        assert plan['state']=='applied',plan
        assert plan['imported']==new_count and plan['removed']==args.rows-1
        stop.set();thread.join();thread=None
        assert not errors,errors
        report['concurrent_browse']=summary(reads)
        with service.catalog() as catalog:
            assert catalog.db.execute('SELECT count(*) FROM photos').fetchone()[0]==new_count+1
            assert catalog.db.execute('SELECT total_count FROM catalog_folders WHERE id=?',(folder['id'],)).fetchone()[0]==new_count+1
            assert catalog.db.execute('SELECT count(*) FROM folder_sync_files').fetchone()[0]==0
            assert catalog.db.execute('SELECT enabled FROM folder_maintenance').fetchone()[0]==1
        report['peak_rss_mb']=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024**2 if platform.system()=='Darwin' else 1024),2)
        report['worker_peak_mb']=service.peak
        (root/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    finally:
        stop.set()
        if thread:thread.join()
        service.close()


if __name__=='__main__':main()
