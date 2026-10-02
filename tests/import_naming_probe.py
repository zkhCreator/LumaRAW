"""Measure naming preview ranks over generated large SQL import reviews.

Inputs: a new disposable work directory and synthetic staged-row counts. Outputs:
warm/cold connection page timings, SQLite VM work, RSS and frozen rank checks.
No photos/pixels, real source reads, broker IPC or desktop input are measured.
"""
import argparse
import json
from pathlib import Path
import statistics
import threading
import time

import psutil
from lumaraw.catalog import Catalog
from lumaraw.import_naming import ImportNaming,freeze
from lumaraw import filename_templates as names


def seed(c,count):
    with c.db:
        c.db.execute("INSERT INTO import_plans(state,phase,include_subfolders,file_count,selected_count,created) VALUES('ready','files',1,?,?,1)",(count,count))
        c.db.execute("INSERT INTO import_copy_plans(plan_id,destination,destination_identity,organization,subfolder,roots,owner) VALUES(1,'/probe/destination','{}','flat','','[]','probe')")
        c.db.executemany("INSERT INTO import_files(plan_id,path,name,extension,state,selected) VALUES(1,?,?,'jpg','new',1)",
                        ((f'/probe/source/p{i:08}.jpg',f'p{i:08}.jpg') for i in range(count-1,-1,-1)))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--rows',type=int,nargs='+',default=[10000,100000]);args=parser.parse_args()
    args.work.mkdir(parents=True,exist_ok=False);results=[]
    for count in args.rows:
        root=args.work/str(count);c=Catalog(root);seed(c,count);c.close()
        value={**names.defaults(),'enabled':True,'template':names.builtins()[2]['template'],'custom_text':'Batch'}
        c=Catalog(root);domain=ImportNaming(c);samples=[]
        process=psutil.Process();peak=[process.memory_info().rss];stop=threading.Event()
        def sample():
            while not stop.wait(.005):peak[0]=max(peak[0],process.memory_info().rss)
        sampler=threading.Thread(target=sample,daemon=True);sampler.start()
        for offset in (0,count//2,count-60):
            runs=[];vm=[]
            for run in range(6):
                steps=[0]
                def progress():steps[0]+=1000;return 0
                c.db.set_progress_handler(progress,1000);start=time.perf_counter()
                result=domain.preview(1,0,value,offset=offset)
                runs.append((time.perf_counter()-start)*1000);vm.append(steps[0]);c.db.set_progress_handler(None,0)
                assert len(result['items'])==60 and result['items'][0]['index']==offset+1
                assert result['items'][-1]['index']==offset+60
            samples.append({'offset':offset,'first_ms':runs[0],'warm_median_ms':statistics.median(runs[1:]),
                            'warm_max_ms':max(runs[1:]),'vm_steps':vm,'reply_bytes':len(json.dumps(result).encode())})
        start=time.perf_counter()
        with c.db:freeze(c.db,{'id':1,'skip_duplicates':1})
        elapsed=(time.perf_counter()-start)*1000
        assert c.db.execute('SELECT naming_index FROM import_files ORDER BY name LIMIT 1').fetchone()[0]==1
        assert c.db.execute('SELECT max(naming_index) FROM import_files').fetchone()[0]==count
        peak[0]=max(peak[0],process.memory_info().rss);stop.set();sampler.join()
        results.append({'rows':count,'pages':samples,'freeze_ms':elapsed,'sampled_peak_mb':peak[0]/1024**2,'sample_interval_ms':5})
        c.close()
    report={'results':results,'pixel_workers':0,'fixtures':'synthetic SQLite rows only','desktop_ui':'NOT_VERIFIED'}
    (args.work/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))


if __name__=='__main__':main()
