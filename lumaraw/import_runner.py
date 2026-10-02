"""Responsive filesystem/preview orchestration for durable import reviews.

Inputs: explicit paths, plan/item revisions, viewport requests and cancellation
generations. Outputs: bounded scan pages, fitted or 1:1 file-backed previews and
catalog-only import receipts. File and sidecar I/O runs outside catalog locks.
Completed previews use the shared integrity-checked cache; misses use the bounded
image worker. One directory iterator survives pages; restart replays into unique
staging rows. Copy I/O is delegated to its journalled adapter; this module never
writes originals or replays an uncertain application.
"""
import json
import math
from pathlib import Path
import threading

from .folder_sync_io import DirectoryReader,directory_identity,inspect_file
from .import_review import ImportReview,ACTIVE
from .model import IMAGE_EXTENSIONS
from .relocations import identity
from . import import_processing


def sources(paths):
    result=[]
    for value in paths:
        path=Path(value).expanduser()
        if path.is_symlink():raise ValueError('Choose original files or real folders, not symbolic links')
        path=path.resolve(strict=True)
        if len(str(path).encode())>4096:raise ValueError('Import paths exceed the supported filesystem path length')
        directory=path.is_dir()
        if not directory and path.suffix.lower() not in IMAGE_EXTENSIONS:
            raise ValueError('Choose a supported photograph or folder')
        fingerprint=directory_identity(path) if directory else identity(path)
        if fingerprint is None:raise ValueError('An import source is no longer available')
        result.append({'path':str(path),'directory':directory,'fingerprint':fingerprint})
    return result


class ImportRunner:
    def __init__(self,service):
        self.service=service
        self.lock=threading.Lock();self.state_lock=threading.Lock();self.events={}
        self.reader=DirectoryReader();self.reader_plan=None

    def dispatch(self,method,params):
        if method=='set_import_backup':
            from .import_backup import set_backup
            return set_backup(self.service,**params)
        if method=='get_import_processing':
            return import_processing.ImportProcessing(self.service).get(**params)
        if method=='set_import_processing':
            return import_processing.ImportProcessing(self.service).set(**params)
        if method in ('prepare_import','restart_import_with_preset'):
            from .import_presets import prepare
            if method=='prepare_import':return prepare(self.service,params)
            return prepare(self.service,{'preset':params['preset']},replace={key:params[key] for key in ('plan_id','expected_revision')})
        if method=='get_import_copies':
            from .import_copy import ImportCopy
            with self.service.catalog() as catalog:return ImportCopy(catalog).receipt(**params)
        if method in ('get_import','select_import_items','set_import_options'):
            with self.service.catalog() as catalog:
                domain=ImportReview(catalog)
                return {'get_import':domain.get,'select_import_items':domain.select,'set_import_options':domain.options}[method](**params)
        if method=='preview_import_item':return self.preview(**params)
        if method=='cancel_import':
            from .import_copy import settings,COPY_PHASES
            with self.service.catalog() as catalog:
                copy=settings(catalog.db,params['plan_id'])
                current=ImportReview(catalog).row(params['plan_id'])
            with self.state_lock:
                event=self.events.get(params['plan_id'])
                if event:event.set()
            if copy and event:
                with self.service.catalog() as catalog:return ImportReview(catalog).get(params['plan_id'])
            if copy and current['phase'] in COPY_PHASES:
                if not self.lock.acquire(blocking=False):raise ValueError('Wait for the active Copy operation to stop')
                try:
                    from .import_copy_runner import CopyRunner
                    return CopyRunner(self.service).cancel(params['plan_id'])
                finally:self.lock.release()
            with self.service.catalog() as catalog:
                result=ImportReview(catalog).terminal(params['plan_id'],'cancelled')
            if self.lock.acquire(blocking=False):
                try:
                    if self.reader_plan==params['plan_id']:self.reader.close();self.reader_plan=None
                finally:self.lock.release()
            return result
        return self.run(method,params)

    def preview(self,plan_id,item_id,expected_revision,client_id,generation,detail=False,viewport=None):
        if type(detail) is not bool:raise ValueError('detail must be an explicit boolean')
        if viewport is not None:
            if detail is not True:raise ValueError('A 1:1 viewport requires explicit detail=true')
            if not isinstance(viewport,dict) or set(viewport)!={'cx','cy','width','height'}:
                raise ValueError('A 1:1 viewport requires cx, cy, width and height')
            for key in ('cx','cy'):
                value=viewport[key]
                if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=1:
                    raise ValueError('Viewport center coordinates must be between 0 and 1')
            for key,maximum in (('width',2048),('height',1536)):
                value=viewport[key]
                if type(value) is not int or not 1<=value<=maximum:
                    raise ValueError(f'Viewport {key} must be between 1 and {maximum}')
        admitted=self.service.dispatch('cancel_preview',{'client_id':client_id,'generation':generation})
        if admitted.get('superseded'):raise InterruptedError('Preview is superseded')
        with self.service.catalog() as catalog:
            row=ImportReview(catalog).item(plan_id,item_id,expected_revision)
            patch=import_processing.develop_patch(catalog,plan_id)
        import_processing.check_camera(patch,json.loads(row['clock']).get('camera',''))
        if row['state'] in ('pending','error'):raise ValueError('Finish scanning this item before previewing')
        expected=json.loads(row['fingerprints']).get(row['path'])
        if expected is None or identity(row['path'])!=expected:
            raise ValueError('The import source changed; create a fresh review')
        from .source_identity import cached_thumbnail
        from .model import Recipe
        recipe=Recipe.parse(patch) if patch else None
        result=None
        if not detail:
            path=cached_thumbnail(row['path'],self.service.cache,recipe=recipe)
            if path:result={'thumbnail':path,'cache_hit':True,'worker_spawned':False}
        request={'operation':'preview' if detail else 'thumbnail','path':row['path'],
            'recipe':patch,'kind':'developed' if patch else 'source',
            'max_edge':1600,'include_before':False,'client_id':client_id,'generation':generation}
        if detail:
            if viewport is not None:
                request.pop('max_edge')
                request['detail']=dict(viewport)
            from . import preview_cache
            backend=self.service.compute_backend
            cache_key=preview_cache.key(request,self.service.worker_identity,backend)
            result=preview_cache.load(self.service.cache,cache_key,request,backend,
                lambda:self.service.check_preview_current(request),repair_lock=self.service.image_lock)
            if result is not None and cache_key!=preview_cache.key(request,self.service.worker_identity,self.service.compute_backend):
                raise ValueError('Source or rendering asset changed during preview; reload the photograph')
        if result is None:result=self.service.run_worker(request)
        self.service.check_preview_current(request)
        if identity(row['path'])!=expected:raise ValueError('The import source changed during preview')
        with self.service.catalog() as catalog:
            ImportReview(catalog).item(plan_id,item_id,expected_revision)
        self.service.check_preview_current(request)
        return {**result,'plan_id':plan_id,'item_id':item_id,'revision':expected_revision,'source':row['path']}

    def run(self,method,params):
        if not self.lock.acquire(blocking=False):raise ValueError('Another import scan or application is active')
        plan_id=params['plan_id'];event=threading.Event();plan=None;copy=None
        with self.state_lock:self.events[plan_id]=event
        def cancelled():return event.is_set() or self.service.stopping.is_set()
        try:
            from .import_copy import settings
            from .import_copy_runner import CopyRunner
            with self.service.catalog() as catalog:copy=settings(catalog.db,plan_id)
            if method=='scan_import':
                with self.service.catalog() as catalog:plan,rows=ImportReview(catalog).start_scan(**params)
                if plan['phase']=='directories':
                    if self.reader_plan!=plan_id:self.reader.close();self.reader_plan=plan_id
                    directory=rows[0]
                    result=self.reader.read(directory['path'],json.loads(directory['fingerprint']),cancelled)
                    if cancelled():raise InterruptedError('Import cancelled')
                    result['directories']=[entry for entry in result['directories'] if Path(entry[0])!=self.service.root]
                    with self.service.catalog() as catalog:
                        return ImportReview(catalog).finish_directory(plan_id,plan['revision'],directory,result)
                observations=[(row,inspect_file({**row,'source_id':0},True,cancelled,include_date=True) if copy else
                                   inspect_file({**row,'source_id':0},True,cancelled)) for row in rows]
                if cancelled():raise InterruptedError('Import cancelled')
                with self.service.catalog() as catalog:
                    return ImportReview(catalog).finish_files(plan_id,plan['revision'],observations)
            if method=='resume_import_copy':plan=CopyRunner(self.service).resume(**params)
            else:
                with self.service.catalog() as catalog:plan=ImportReview(catalog).start_apply(**params)
            with self.service.catalog() as catalog:processing=import_processing.settings(catalog,plan_id)
            import_processing.verify_asset(processing)
            self.verify_sources(plan,cancelled)
            if copy:return CopyRunner(self.service).execute(plan,cancelled,self.verify_sources)
            with self.service.catalog() as catalog:return ImportReview(catalog).apply(plan_id,plan['revision'],cancelled)
        except InterruptedError:
            if copy and plan and method!='scan_import':
                if self.service.stopping.is_set():return CopyRunner(self.service).interrupt(plan_id,'Copy interrupted by service shutdown.')
                return CopyRunner(self.service).cancel(plan_id)
            with self.service.catalog() as catalog:return ImportReview(catalog).terminal(plan_id,'cancelled')
        except Exception as error:
            if plan is None:raise
            if copy and method!='scan_import':return CopyRunner(self.service).interrupt(plan_id,error)
            with self.service.catalog() as catalog:return ImportReview(catalog).terminal(plan_id,'failed',str(error))
        finally:
            with self.state_lock:self.events.pop(plan_id,None)
            try:
                if plan is not None:
                    with self.service.catalog() as catalog:current=ImportReview(catalog).row(plan_id)
                    if current['state'] not in ACTIVE or current['phase']!='directories':self.reader.close();self.reader_plan=None
            finally:self.lock.release()

    def verify_sources(self,plan,cancelled,count=True):
        plan_id=plan['id']
        for kind in ('directories','files'):
            after=0
            while True:
                with self.service.catalog() as catalog:rows=ImportReview(catalog).pages(plan_id,plan['revision'],kind,after)
                if not rows:break
                for row in rows:
                    if cancelled():raise InterruptedError('Import cancelled')
                    if kind=='directories':
                        if directory_identity(row['path'])!=json.loads(row['fingerprint']):
                            raise ValueError('Import folder contents changed; create a fresh review')
                    else:
                        if Path(row['path']).resolve()!=Path(row['path']):
                            raise ValueError('An import source now traverses a symbolic link')
                        if any(identity(path)!=expected for path,expected in json.loads(row['fingerprints']).items()):
                            raise ValueError('An original or sidecar changed; create a fresh review')
                after=rows[-1]['id']
                if kind=='files' and count:
                    with self.service.catalog() as catalog:
                        ImportReview(catalog).check(plan_id,plan['revision'],('verifying',))
                        with catalog.db:catalog.db.execute('UPDATE import_plans SET checked=checked+? WHERE id=?',(len(rows),plan_id))

    def close(self):
        if self.lock.acquire(blocking=False):
            try:self.reader.close();self.reader_plan=None
            finally:self.lock.release()
