"""Single-owner catalog service and bounded disposable-worker supervisor.

Purpose: keep UI and agents on one transactional domain boundary. Each command
opens its own SQLite connection under a short catalog lock. Expensive pixels run
outside that lock, in one child at a time, with sampled RSS and time limits.
Inputs: validated API commands. Outputs: JSON, file-backed previews, durable jobs.
No GUI, HTTP listener, telemetry or original-file writes. Interrupted exports are
never automatically replayed. Optimistic revisions prevent lost recipe updates.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

import jsonschema
import psutil
from .api import TOOLS
from .catalog import Catalog, walk_images
from .model import Recipe, ExportOptions, LIMITS, PRESETS, SYNC_GROUPS

class ConflictError(ValueError): pass

def executable_args():
    return [sys.executable] if getattr(sys,'frozen',False) else [sys.executable,'-m','lumaraw.bridge']

def unpack(row):
    if row:
        row=dict(row)
        for key in ('recipe','metadata','options','processing'):
            if key in row and isinstance(row[key],str): row[key]=json.loads(row[key])
    return row

class Service:
    def __init__(self,root):
        self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True)
        self.cache=self.root/'cache';self.cache.mkdir(exist_ok=True)
        self.lock=threading.RLock();self.image_lock=threading.Lock();self.state_lock=threading.RLock()
        self.stopping=threading.Event();self.wake=threading.Event();self.active=None;self.peak=0
        self.cancel_jobs=set();self.preview_versions={}
        self.last_activity=time.monotonic()
        with self.catalog() as c:
            c.recover_jobs()
            # A broker restart also leaves unstarted exports for explicit review.
            with c.db:
                c.db.execute("UPDATE jobs SET state='interrupted',error='Service restarted; check output before retrying' WHERE state='pending'")
                c.db.execute('CREATE TABLE IF NOT EXISTS requests(key TEXT PRIMARY KEY,digest TEXT NOT NULL,result TEXT NOT NULL)')
            self.paused=c.setting('paused',False)
            self.budget=c.setting('budget_mb',4096)
            self.compute_backend=c.setting('compute_backend','auto')
            if 'processing' not in {r[1] for r in c.db.execute('PRAGMA table_info(jobs)')}:
                c.db.execute("ALTER TABLE jobs ADD COLUMN processing TEXT NOT NULL DEFAULT '{}'");c.db.commit()
        self.last_processing={}
        self.thread=threading.Thread(target=self.queue_loop,daemon=True);self.thread.start()

    @contextmanager
    def catalog(self):
        with self.lock:
            c=Catalog(self.root)
            try: yield c
            finally:c.close()

    def require(self,c,id_):
        row=c.photo(id_)
        if not row:raise ValueError('Photo does not exist')
        return row

    def check_revision(self,c,id_,revision):
        row=self.require(c,id_)
        if row['revision']!=revision:
            raise ConflictError(f"Edit conflict: current revision {row['revision']}, requested revision {revision}. Read the photo again.")
        return row

    def memory_status(self):
        """Keep the user's cap distinct from the currently affordable cap."""
        available=psutil.virtual_memory().available / 1024**2
        effective=max(1,min(self.budget,int(available*.7)))
        return {'budget_mb':self.budget,'available_mb':round(available,1),
                'effective_budget_mb':effective,'limited_by_available_memory':effective<self.budget,'compute_backend':self.compute_backend,'last_processing':self.last_processing}

    def dispatch(self,method,p=None):
        self.last_activity=time.monotonic();p={} if p is None else p
        if method not in TOOLS: raise ValueError('Unknown operation: '+method)
        jsonschema.validate(p,TOOLS[method]['inputSchema'])
        if method=='status':
            with self.catalog() as c:
                return {'version':'0.4.1','api_version':1,'catalog':str(self.root),'photos':c.count(),'counts':c.job_counts(),'paused':self.paused,'active':self.active,**self.memory_status(),'peak_mb':round(self.peak,1)}
        if method=='recipe_schema':return {'defaults':Recipe().dict(),'limits':LIMITS,'presets':{k:v.dict() for k,v in PRESETS.items()},'groups':SYNC_GROUPS}
        if method in ('preview_photo','thumbnail','calibrate_camera'):
            if method=='preview_photo' and p.get('client_id'):
                if 'generation' not in p:raise ValueError('client_id requires generation')
                with self.state_lock:
                    client=p['client_id'];generation=p['generation']
                    if generation<self.preview_versions.get(client,-1):raise InterruptedError('Preview is superseded')
                    self.preview_versions[client]=generation
                    if len(self.preview_versions)>128:self.preview_versions.pop(next(iter(self.preview_versions)))
                    if self.active and self.active.get('client_id')==client and self.active.get('generation',-1)<generation:
                        self.cancelled=True
                        if self.process.poll() is None:self.process.kill()
            with self.catalog() as c:row=self.require(c,p['photo_id'])
            request={'operation':{'preview_photo':'preview','thumbnail':'thumbnail','calibrate_camera':'calibrate'}[method],
                     'path':row['path'],'recipe':json.loads(row['recipe'])}
            request.update({k:v for k,v in p.items() if k!='photo_id'})
            result=self.run_worker(request)
            if 'metadata' in result:
                with self.catalog() as c:c.update_metadata(row['id'],result['metadata'])
            return {**result,'photo_id':row['id'],'revision':row['revision']}
        if method=='queue_control':return self.control(p)
        with self.catalog() as c:
            if method=='import_photos':
                def paths():
                    for path in p['paths']:
                        q=Path(path)
                        if q.is_dir() and not q.is_symlink():yield from walk_images(q)
                        else:yield q
                count,skipped=c.import_paths(paths());return {'imported':count,'skipped':skipped,'total':c.count()}
            if method=='list_photos':
                mode=p.get('mode','all');search=p.get('search','');offset=p.get('offset',0)
                return {'photos':[{k:v for k,v in unpack(x).items() if k not in ('recipe','metadata')} for x in c.filtered_page(offset,mode,search)],'total':c.filtered_count(mode,search),'offset':offset,'page_size':60}
            if method=='get_photo':return unpack(self.require(c,p['photo_id']))
            if method in ('edit_photo','undo_photo','restore_version','load_recipe'):
                row=self.check_revision(c,p['photo_id'],p['expected_revision'])
                if method=='edit_photo':
                    values=json.loads(row['recipe']);values.update(p['patch']);c.edit(row['id'],Recipe.parse(values),'App / Agent Adjustments')
                elif method=='undo_photo':c.undo(row['id'])
                elif method=='restore_version':c.restore_version(row['id'],p['version_id'])
                else:
                    from .library import load_recipe
                    c.edit(row['id'],load_recipe(p['path'],self.root),'Import Recipe Bundle')
                return unpack(c.photo(row['id']))
            if method=='rate_photo':
                self.require(c,p['photo_id'])
                if 'rating' in p:c.rate(p['photo_id'],p['rating'])
                if 'flag' in p:c.flag(p['photo_id'],p['flag'])
                return unpack(c.photo(p['photo_id']))
            if method=='enqueue_exports':
                digest=hashlib.sha256(json.dumps(p,sort_keys=True).encode()).hexdigest()
                previous=c.db.execute('SELECT digest,result FROM requests WHERE key=?',(p['request_key'],)).fetchone()
                if previous:
                    if previous[0]!=digest:raise ValueError('request_key is already used by a different export request')
                    return json.loads(previous[1])
                options=ExportOptions.parse(p.get('options'));rows=[self.require(c,i) for i in dict.fromkeys(p['photo_ids'])]
                dest=Path(p['destination']).expanduser().resolve();dest.mkdir(parents=True,exist_ok=True)
                ids=[]
                with c.db:
                    for row in rows:
                        cur=c.db.execute('INSERT INTO jobs(photo_id,source,recipe,destination,format,created,options,priority) VALUES(?,?,?,?,?,?,?,?)',
                            (row['id'],row['path'],row['recipe'],str(dest),p['format'],time.time(),json.dumps(options.dict()),options.priority));ids.append(cur.lastrowid)
                    result={'job_ids':ids,'queued':len(ids)}
                    c.db.execute('INSERT INTO requests VALUES(?,?,?)',(p['request_key'],digest,json.dumps(result)))
                self.wake.set();return result
            if method=='get_job':
                row=c.db.execute('SELECT * FROM jobs WHERE id=?',(p['job_id'],)).fetchone()
                if not row:raise ValueError('Job does not exist')
                return unpack(dict(row))
            if method=='list_jobs':return {'jobs':[{k:v for k,v in unpack(j).items() if k!='recipe'} for j in c.jobs(60)],'counts':c.job_counts(),'paused':self.paused,'active':self.active}
            if method=='save_version':self.require(c,p['photo_id']);c.save_version(p['photo_id'],p['name']);return {'saved':True}
            if method=='list_versions':
                self.require(c,p['photo_id']);return {'versions':[unpack(dict(r)) for r in c.db.execute('SELECT id,photo_id,name,created FROM versions WHERE photo_id=? ORDER BY id DESC LIMIT 100',(p['photo_id'],))]}
            if method=='sync_photos':
                source=json.loads(self.require(c,p['source_id'])['recipe']);changes=[]
                for target in p['targets']:
                    row=self.check_revision(c,target['photo_id'],target['expected_revision']);values=json.loads(row['recipe'])
                    values.update({k:source[k] for g in p['groups'] for k in SYNC_GROUPS[g]});changes.append((row,Recipe.parse(values)))
                # All validation precedes the transaction. Catalog.edit commits, so write this group atomically here.
                with c.db:
                    for row,recipe in changes:
                        if row['id']==p['source_id']:continue
                        c.db.execute('INSERT INTO history(photo_id,recipe,label,created) VALUES(?,?,?,?)',(row['id'],row['recipe'],'Batch Sync',time.time()))
                        c.db.execute('UPDATE photos SET recipe=?,revision=revision+1 WHERE id=?',(json.dumps(recipe.dict()),row['id']))
                        c.db.execute('DELETE FROM history WHERE photo_id=? AND id NOT IN (SELECT id FROM history WHERE photo_id=? ORDER BY id DESC LIMIT 50)',(row['id'],row['id']))
                return {'synced':sum(r['id']!=p['source_id'] for r,_ in changes)}
            if method=='settings':
                if 'budget_mb' in p:self.budget=p['budget_mb'];c.set_setting('budget_mb',self.budget)
                if 'compute_backend' in p:self.compute_backend=p['compute_backend'];c.set_setting('compute_backend',self.compute_backend)
                from .accelerators import availability
                return {**self.memory_status(),'acceleration':availability()}
            from . import library
            if method=='index_library':return library.index_library(c)
            if method=='relink_photo':self.require(c,p['photo_id']);c.relink(p['photo_id'],p['path']);return unpack(c.photo(p['photo_id']))
            if method=='backup_catalog':return {'backup':library.backup_catalog(c,p['path'])}
            if method=='restore_catalog':return {'catalog':str(library.restore_catalog(p['path'],p['destination']))}
            if method=='import_asset':return {'asset':library.import_asset(p['path'],self.root,p['kind'])}
            if method=='save_recipe':self.require(c,p['photo_id']);library.save_recipe(p['path'],c.recipe(p['photo_id']));return {'path':p['path']}
        raise ValueError('Operation is not implemented')

    def run_worker(self,request):
        with self.image_lock:
            if request['operation']=='export':
                with self.catalog() as c:
                    row=c.db.execute('SELECT state FROM jobs WHERE id=?',(request['job_id'],)).fetchone()
                    if row and row[0]=='cancelled':raise InterruptedError('Cancelled')
            memory=self.memory_status();budget=memory['effective_budget_mb']
            request={**request,'cache':str(self.cache),'budget_mb':budget,'parent_pid':os.getpid(),'compute_backend':self.compute_backend}
            env={**os.environ,'OMP_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'1','VECLIB_MAXIMUM_THREADS':'2'}
            with tempfile.TemporaryFile() as output,tempfile.TemporaryFile() as errors:
                with self.state_lock:
                    if request.get('job_id') in self.cancel_jobs:raise InterruptedError('Cancelled')
                    if request.get('client_id') and self.preview_versions.get(request['client_id'])!=request.get('generation'):raise InterruptedError('Preview is superseded')
                    process=subprocess.Popen(executable_args()+['--worker'],stdin=subprocess.PIPE,stdout=output,stderr=errors,env=env)
                    self.active={'operation':request['operation'],'pid':process.pid,'job_id':request.get('job_id'),'client_id':request.get('client_id'),'generation':request.get('generation')};self.process=process;self.cancelled=False
                peak=0;failure=None;started=time.monotonic()
                try:
                    process.stdin.write(json.dumps(request,allow_nan=False).encode()+b'\n');process.stdin.close()
                    while process.poll() is None:
                        try:
                            peak=max(peak,psutil.Process(process.pid).memory_info().rss/1024**2)
                            if peak>budget:failure=f'Memory exceeded the {budget} MB budget';process.kill()
                        except psutil.NoSuchProcess:pass
                        if self.stopping.is_set() or time.monotonic()-started>300:
                            failure='Processing stopped or exceeded 5 minutes';process.kill()
                        time.sleep(.05)
                    output.seek(0);raw=output.read(1024*1024)
                    result=json.loads(raw) if raw else {}
                    # A completed atomic publication wins over a late cancellation.
                    if result.get('ok'):
                        if result.get('processing'):self.last_processing=result['processing']
                        return {**result,'peak_mb':round(peak,1)}
                    if self.cancelled:raise InterruptedError('Cancelled; check the destination for any completed output')
                    message=failure or result.get('error','Image worker exited without a result')
                    if memory['limited_by_available_memory'] and (failure or result.get('type')=='MemoryError'):
                        message+=f" Configured budget: {memory['budget_mb']} MB; available memory: {memory['available_mb']} MB. This job is capped at 70% of available memory; increasing the setting cannot exceed this cap."
                    raise RuntimeError(message)
                except Exception as error:
                    # Preserve observed failure peaks instead of reporting an artificial zero.
                    error.peak_mb=round(peak,1)
                    raise
                finally:
                    if process.poll() is None:process.kill();process.wait()
                    self.peak=max(self.peak,peak)
                    with self.state_lock:self.active=None;self.process=None
                    if request['operation']=='export':
                        for suffix in ('part','pixels'):
                            for path in Path(request['destination']).glob(f".lumaraw-{request['job_id']}-*.{suffix}"):path.unlink(missing_ok=True)

    def queue_loop(self):
        while not self.stopping.is_set():
            self.wake.wait(.2);self.wake.clear()
            with self.catalog() as c:
                if self.paused:continue
                if psutil.virtual_memory().available<384*1024**2:
                    self.paused=True;c.set_setting('paused',True);continue
                job=c.next_job()
            if not job:continue
            try:
                result=self.run_worker({'operation':'export','path':job['source'],'recipe':json.loads(job['recipe']),
                    'destination':job['destination'],'format':job['format'],'job_id':job['id'],'options':json.loads(job['options'])})
                with self.catalog() as c:
                    c.finish_job(job['id'],'done',peak_mb=result['peak_mb'],output=result['output'])
                    with c.db:c.db.execute('UPDATE jobs SET processing=? WHERE id=?',(json.dumps(result.get('processing',{})),job['id']))
            except Exception as e:
                state='cancelled' if isinstance(e,InterruptedError) else 'failed'
                with self.catalog() as c:c.finish_job(job['id'],state,str(e),peak_mb=getattr(e,'peak_mb',0))
            self.last_activity=time.monotonic()

    def control(self,p):
        action=p['action'];id_=p.get('job_id')
        with self.catalog() as c:
            if action in ('pause','resume'):
                self.paused=action=='pause';c.set_setting('paused',self.paused)
            elif action=='cancel':
                cancelled_ids=[r[0] for r in c.db.execute("SELECT id FROM jobs WHERE state IN ('pending','running')"+(' AND id=?' if id_ else ''),(id_,) if id_ else ())]
                with c.db:
                    c.db.execute("UPDATE jobs SET state='cancelled' WHERE state IN ('pending','running')"+(' AND id=?' if id_ else ''),(id_,) if id_ else ())
                with self.state_lock:
                    self.cancel_jobs.update(cancelled_ids)
                    if self.active and self.active['operation']=='export' and (not id_ or self.active['job_id']==id_):
                        self.cancelled=True
                        if self.process.poll() is None:self.process.kill()
            elif action in ('retry','retry_cancelled'):
                with self.state_lock:
                    if id_:self.cancel_jobs.discard(id_)
                    else:self.cancel_jobs.clear()
                states="('failed','interrupted')" if action=='retry' else "('cancelled')"
                with c.db:c.db.execute(f"UPDATE jobs SET state='pending',error='' WHERE state IN {states}"+(' AND id=?' if id_ else ''),(id_,) if id_ else ())
            self.wake.set()
            return {'paused':self.paused,'counts':c.job_counts()}

    def close(self):
        self.stopping.set();self.wake.set();self.thread.join(timeout=6)
