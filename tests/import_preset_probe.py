"""Measure paged import configurations through a packaged native relay.

Inputs: packaged engine and a new work directory. Outputs: first/warm page and
detail timings, response bytes and sampled broker RSS for synthetic preset libraries.
One valid generated import snapshot seeds the rows before measurement. Source/OS
caches are warm; no RAW processing, workers, desktop input or cold-disk claim.
"""
import argparse
import json
from pathlib import Path
import platform
import statistics
import threading
import time

from PIL import Image
import psutil

from lumaraw.catalog import Catalog
from lumaraw.service import Service
from import_copy_probe import Relay, sha


def seed(root, count):
    photo = root/'source.png'
    Image.new('RGB',(16,12),'navy').save(photo)
    catalog = root/'catalog'
    service = Service(catalog,presets_root=root/'presets')
    try:
        plan = service.dispatch('prepare_import',{'paths':[str(photo)]})['plan']
        while plan['state'] == 'planning':
            plan = service.dispatch('scan_import',{'plan_id':plan['id'],'expected_revision':plan['revision']})['plan']
        words = [' | '.join(['Region '+'a'*80,'Location '+'b'*80,f'Subject {i:03} '+'c'*80]) for i in range(100)]
        setting = service.dispatch('set_import_processing',{'plan_id':plan['id'],'expected_revision':plan['revision'],'keywords':words})
        service.dispatch('save_import_preset',{'plan_id':plan['id'],'expected_plan_revision':setting['revision'],'expected_revision':0,'name':'Seed'})
        service.dispatch('cancel_import',{'plan_id':plan['id']})
    finally:
        service.close()
    c = Catalog(catalog)
    try:
        with c.db:
            value = c.db.execute('SELECT value FROM import_presets').fetchone()[0]
            c.db.execute('DELETE FROM import_presets')
            c.db.executemany('INSERT INTO import_presets VALUES(?,?,?,?,?)',
                ((str(i),f'Import {i:05}',f'import {i:05}','add',value) for i in range(count)))
        return len(value.encode())
    finally:
        c.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--engine',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--rows',type=int,nargs='+',default=[100,5000])
    args = parser.parse_args()
    assert all(30 <= n <= 10000 for n in args.rows)
    work = args.work.resolve();work.mkdir(parents=True,exist_ok=False)
    engine = args.engine.resolve();results=[]
    for count in args.rows:
        root = work/str(count);root.mkdir()
        payload_bytes = seed(root,count)
        relay = Relay(engine,root/'catalog',root/'presets')
        stop = threading.Event();peak=[0]
        try:
            connection=relay.call('service_connection',{'action':'status'})
            process=psutil.Process(connection['pid']);peak[0]=process.memory_info().rss
            def sample():
                while not stop.wait(.005):
                    try:peak[0]=max(peak[0],process.memory_info().rss)
                    except psutil.NoSuchProcess:return
            sampler=threading.Thread(target=sample);sampler.start()
            pages=[]
            for offset in (0,count//2,count-30):
                times=[]
                for run in range(31):
                    started=time.perf_counter();page=relay.call('list_import_presets',{'offset':offset})
                    times.append((time.perf_counter()-started)*1000)
                    assert len(page['items'])==30 and page['total']==count
                    assert set(page['items'][0])=={'id','name','mode'}
                warm=times[1:]
                pages.append({'offset':offset,'first_ms':times[0],'median_ms':statistics.median(warm),
                    'p95_ms':sorted(warm)[28],'max_ms':max(warm),'reply_bytes':len(json.dumps(page).encode())})
            times=[]
            for run in range(30):
                started=time.perf_counter()
                detail=relay.call('get_import_preset',{'preset_id':page['items'][0]['id'],'expected_revision':page['revision']})
                times.append((time.perf_counter()-started)*1000)
                assert detail['processing']['keyword_count']==100 and 'value' not in detail
            stop.set();sampler.join()
            results.append({'rows':count,'snapshot_bytes':payload_bytes,'pages':pages,
                'detail':{'median_ms':statistics.median(times),'p95_ms':sorted(times)[28],
                          'max_ms':max(times),'reply_bytes':len(json.dumps(detail).encode())},
                'sampled_broker_peak_mib':peak[0]/1024**2,'sample_interval_ms':5,
                'worker_peak_mib':relay.call('status')['peak_mb']})
        finally:
            stop.set();relay.close()
    report={'results':results,'engine_sha256':sha(engine),'platform':platform.platform(),
            'memory_gib':psutil.virtual_memory().total/1024**3,'backend':'SQLite and packaged IPC; no GPU/image work',
            'cache':'Fresh seeded catalogs, warm source/OS caches; no desktop or app previews',
            'samples':'One first page and 30 warm repetitions per offset; 30 detail reads'}
    (work/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
