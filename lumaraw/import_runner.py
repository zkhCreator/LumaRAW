"""Responsive filesystem/preview orchestration for durable Add import reviews.

Inputs: explicit paths, plan/item revisions and cancellation generations. Outputs:
bounded scan pages, file-backed previews and catalog-only import receipts. File
and sidecar I/O runs outside catalog locks. One directory iterator survives pages;
restart replays into unique staging rows. Never copies, moves or writes originals.
"""
import json
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
        if method=='get_import_processing':
            return import_processing.ImportProcessing(self.service).get(**params)
        if method=='set_import_processing':
            return import_processing.ImportProcessing(self.service).set(**params)
        if method=='prepare_import':
            captured=sources(params['paths'])
            if any(Path(item['path'])==self.service.root or self.service.root in Path(item['path']).parents for item in captured):
                raise ValueError('The active catalog and its generated cache are not import sources')
            with self.service.catalog() as catalog:
                return ImportReview(catalog).prepare(captured,params.get('include_subfolders',True),params.get('skip_duplicates',True))
        if method in ('get_import','select_import_items','set_import_options'):
            with self.service.catalog() as catalog:
                domain=ImportReview(catalog)
                return {'get_import':domain.get,'select_import_items':domain.select,'set_import_options':domain.options}[method](**params)
        if method=='preview_import_item':return self.preview(**params)
        if method=='cancel_import':
            with self.state_lock:
                if event:=self.events.get(params['plan_id']):event.set()
            with self.service.catalog() as catalog:
                result=ImportReview(catalog).terminal(params['plan_id'],'cancelled')
            if self.lock.acquire(blocking=False):
                try:
                    if self.reader_plan==params['plan_id']:self.reader.close();self.reader_plan=None
                finally:self.lock.release()
            return result
        return self.run(method,params)

    def preview(self,plan_id,item_id,expected_revision,client_id,generation,detail=False):
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
        path=None if detail else cached_thumbnail(row['path'],self.service.cache,recipe=recipe)
        if path:result={'thumbnail':path,'cache_hit':True,'worker_spawned':False}
        else:
            result=self.service.run_worker({'operation':'preview' if detail else 'thumbnail','path':row['path'],
                'recipe':patch,'kind':'developed' if patch else 'source','max_edge':1600,
                'include_before':False,'client_id':client_id,'generation':generation})
        if identity(row['path'])!=expected:raise ValueError('The import source changed during preview')
        with self.service.catalog() as catalog:
            ImportReview(catalog).item(plan_id,item_id,expected_revision)
        return {**result,'plan_id':plan_id,'item_id':item_id,'revision':expected_revision,'source':row['path']}

    def run(self,method,params):
        if not self.lock.acquire(blocking=False):raise ValueError('Another import scan or application is active')
        plan_id=params['plan_id'];event=threading.Event();plan=None
        with self.state_lock:self.events[plan_id]=event
        def cancelled():return event.is_set() or self.service.stopping.is_set()
        try:
            if method=='scan_import':
                with self.service.catalog() as catalog:plan,rows=ImportReview(catalog).start_scan(**params)
                if plan['phase']=='directories':
                    if self.reader_plan!=plan_id:self.reader.close();self.reader_plan=plan_id
                    directory=rows[0]
                    result=self.reader.read(directory['path'],json.loads(directory['fingerprint']),cancelled)
                    result['directories']=[entry for entry in result['directories'] if Path(entry[0])!=self.service.root]
                    with self.service.catalog() as catalog:
                        return ImportReview(catalog).finish_directory(plan_id,plan['revision'],directory,result)
                observations=[(row,inspect_file({**row,'source_id':0},True,cancelled)) for row in rows]
                with self.service.catalog() as catalog:
                    return ImportReview(catalog).finish_files(plan_id,plan['revision'],observations)
            with self.service.catalog() as catalog:plan=ImportReview(catalog).start_apply(**params)
            with self.service.catalog() as catalog:processing=import_processing.settings(catalog,plan_id)
            import_processing.verify_asset(processing)
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
                    if kind=='files':
                        with self.service.catalog() as catalog:
                            ImportReview(catalog).check(plan_id,plan['revision'],('verifying',))
                            with catalog.db:catalog.db.execute('UPDATE import_plans SET checked=checked+? WHERE id=?',(len(rows),plan_id))
            with self.service.catalog() as catalog:return ImportReview(catalog).apply(plan_id,plan['revision'],cancelled)
        except InterruptedError:
            with self.service.catalog() as catalog:return ImportReview(catalog).terminal(plan_id,'cancelled')
        except Exception as error:
            if plan is None:raise
            with self.service.catalog() as catalog:return ImportReview(catalog).terminal(plan_id,'failed',str(error))
        finally:
            with self.state_lock:self.events.pop(plan_id,None)
            try:
                if plan is not None:
                    with self.service.catalog() as catalog:current=ImportReview(catalog).row(plan_id)
                    if current['state'] not in ACTIVE or current['phase']!='directories':self.reader.close();self.reader_plan=None
            finally:self.lock.release()

    def close(self):
        if self.lock.acquire(blocking=False):
            try:self.reader.close();self.reader_plan=None
            finally:self.lock.release()
