"""Measure bounded Add review pages and import transaction scaling.

Inputs: a new directory, synthetic catalog/candidate counts and sixty small files.
Outputs: warm service/SQL samples, a real sixty-file apply and one synthetic bulk
transaction measurement. Synthetic bulk excludes filesystem verification; setup,
image decoding, IPC and UI are excluded everywhere. No personal files or thresholds.
Optional processing captures two preset snapshots and three keyword additions;
large IPTC tests paging independence and atomic application cost, not pixel speed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import resource

from PIL import Image
import psutil

from library_probe import measure
from lumaraw.import_review import ImportReview
from lumaraw.model import Recipe
from lumaraw.service import Service


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--work',type=Path,required=True)
    p.add_argument('--photos',type=int,default=10000)
    p.add_argument('--candidates',type=int,default=10000)
    p.add_argument('--samples',type=int,default=30)
    p.add_argument('--processing',action='store_true')
    args=p.parse_args()
    if not 60<=args.photos<=1000000 or not 60<=args.candidates<=1000000 or not 1<=args.samples<=1000:
        raise SystemExit('Counts outside probe bounds')
    root=args.work.resolve();root.mkdir()
    paths=[]
    for i in range(60):
        path=root/f'A{i:03}.png';Image.new('RGB',(8,8),'navy').save(path);paths.append(path)
    fingerprints=[hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
    s=Service(root/'catalog',presets_root=root/'presets')
    try:
        s.dispatch('queue_control',{'action':'pause'})
        with s.catalog() as c,c.db:
            recipe=json.dumps(Recipe().dict())
            c.db.executemany('INSERT INTO photos(path,name,bytes,mtime,recipe,created) VALUES(?,?,0,0,?,0)',
                ((str(root/'existing'/f'{i}.png'),f'{i:08}.png',recipe) for i in range(args.photos)))
        plan=s.dispatch('prepare_import',{'paths':list(map(str,paths))})['plan']
        def scan():return s.dispatch('scan_import',{'plan_id':plan['id'],'expected_revision':plan['revision']})
        report={'platform':platform.platform(),'machine':platform.machine(),'memory_gb':round(psutil.virtual_memory().total/1024**3,1),
                'existing_photos':args.photos,'review_candidates':args.candidates,'real_files':60,'dimensions':[8,8],
                'cache':'Warm SQLite; generated JPEG/RAW decoding excluded',
                'scope':'In-process service/SQL, excluding setup, IPC and UI; synthetic bulk additionally excludes file verification'}
        report['scan_sixty_files']=measure(scan,1)
        plan=s.dispatch('get_import')['plan'];assert plan['state']=='ready'
        captured_processing=None
        if args.processing:
            iptc={'headline':'界'*500,'alt_text':'界'*5000,'extended_description':'界'*5000}
            report['iptc_utf8_bytes']=len(json.dumps(iptc,ensure_ascii=False).encode())
            report['processing']='Exposure/contrast; title/rating/large IPTC; three captured keyword paths'
            with s.develop_presets.transaction() as (_,_,db,_):
                db.execute("INSERT INTO develop_presets VALUES('probe','Probe','probe','user',?,2,0,0)",
                           (json.dumps({'exposure':1,'contrast':12}),))
                s.develop_presets.bump(db)
            metadata=s.dispatch('save_metadata_preset',{'name':'Import probe','patch':{'title':'Imported','rating':4,'iptc':iptc,
                'keywords':['Imported | Batch','Project | Album']},'expected_revision':s.dispatch('list_metadata_presets')['revision']})
            s.dispatch('set_import_processing',{'plan_id':plan['id'],'expected_revision':plan['revision'],
                'develop_preset':{'preset_id':'probe','expected_revision':s.dispatch('list_develop_presets')['revision']},
                'metadata_preset':{'preset_id':metadata['preset_id'],'expected_revision':metadata['revision']},'keywords':['Reviewed']})
            with s.catalog() as c:
                captured_processing=dict(c.db.execute('SELECT * FROM import_processing WHERE plan_id=?',(plan['id'],)).fetchone())
        with s.catalog() as c,c.db:
            c.db.executemany('INSERT INTO import_files(plan_id,path,name,extension,state,selected,bytes) VALUES(?,?,?,\'.png\',\'new\',0,1)',
                ((plan['id'],str(root/'synthetic'/f'{i:08}.png'),f'Z{i:08}.png') for i in range(args.candidates-60)))
            c.db.execute('UPDATE import_plans SET file_count=?,counts=? WHERE id=?',
                         (args.candidates,json.dumps({'new':args.candidates}),plan['id']))
        for name,params in [('first_page',{}),('last_page',{'offset':args.candidates}),
                            ('checked_page',{'kind':'selected'}),('capture_sort',{'sort':'captured'}),('type_sort',{'sort':'type'})]:
            result=s.dispatch('get_import',params)
            report[name]=measure(lambda params=params:s.dispatch('get_import',params),args.samples)
            report[name]['response_bytes']=len(json.dumps(result).encode())
            assert len(result['items'])<=60
        def apply():
            state=s.dispatch('get_import')['plan']
            return s.dispatch('apply_import',{'plan_id':state['id'],'expected_revision':state['revision']})
        report['apply_sixty_real_files']=measure(apply,1)
        assert s.dispatch('get_import')['plan']['imported']==60 and s.dispatch('status')['photos']==args.photos+60
        # Isolate final SQL lock duration at scale, using explicitly synthetic
        # rows already staged as verified. This is not a real filesystem import.
        with s.catalog() as c:
            domain=ImportReview(c)
            bulk=domain.prepare([])['plan']
            with c.db:
                c.db.executemany("INSERT INTO import_files(plan_id,path,name,extension,state,bytes,clock) VALUES(?,?,?,'.png','new',1,'{}')",
                    ((bulk['id'],str(root/'bulk'/f'{i:08}.png'),f'{i:08}.png') for i in range(args.candidates)))
                c.db.execute("UPDATE import_plans SET state='verifying',phase='files',file_count=?,selected_count=?,counts=? WHERE id=?",
                             (args.candidates,args.candidates,json.dumps({'new':args.candidates}),bulk['id']))
                if captured_processing:
                    values={**captured_processing,'plan_id':bulk['id']}
                    c.db.execute('INSERT INTO import_processing('+','.join(values)+') VALUES('+','.join('?' for _ in values)+')',list(values.values()))
            report['synthetic_bulk_transaction']=measure(lambda:domain.apply(bulk['id'],bulk['revision']),1)
            assert domain.row(bulk['id'])['imported']==args.candidates
            assert c.db.execute('SELECT count(*) FROM photos').fetchone()[0]==args.photos+60+args.candidates
            assert c.db.execute('SELECT count(*) FROM history').fetchone()[0]==0
            assert c.db.execute('SELECT count(*) FROM import_files').fetchone()[0]==0
            assert c.db.execute('SELECT enabled FROM folder_maintenance').fetchone()[0]==1
            assert c.db.execute('SELECT sum(direct_count) FROM catalog_folders').fetchone()[0]==args.photos+60+args.candidates
            if args.processing:
                assert c.db.execute("SELECT count(*) FROM photos WHERE title='Imported' AND rating=4 AND json_extract(recipe,'$.exposure')=1").fetchone()[0]==args.candidates+60
                assert c.db.execute('SELECT count(*) FROM keyword_photos').fetchone()[0]==(args.candidates+60)*3
                assert c.db.execute('SELECT count(*) FROM import_processing').fetchone()[0]==0
        assert fingerprints==[hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
        report['peak_rss_mb']=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024**2 if platform.system()=='Darwin' else 1024),2)
        report['worker_peak_mb']=s.peak;assert s.peak==0
        (root/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    finally:s.close()


if __name__=='__main__':main()
