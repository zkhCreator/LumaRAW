"""Service orchestration for responsive, recoverable folder synchronization.

Inputs: validated commands and the owning service's locks/cancellation lifecycle.
Outputs: durable plan receipts; bounded filesystem work occurs outside catalog
locks. A single directory iterator and one scan/apply run are admitted at a time.
No background auto-apply, original writes, image decoding or uncertain retries.
"""
import json
import threading

from .folder_sync import FolderSync, ACTIVE
from .folder_sync_io import DirectoryReader, directory_identity, inspect_file
from .folders import Folders
from .relocations import RelocationBusy, identity


class FolderSyncRunner:
    def __init__(self,service):
        self.service = service
        self.lock = threading.Lock()
        self.state_lock = threading.Lock()
        self.events = {}
        self.reader = DirectoryReader()
        self.reader_plan = None

    def cancelled(self,event):
        return event.is_set() or self.service.stopping.is_set()

    def dispatch(self,method,params):
        if method == 'prepare_folder_sync':
            with self.service.catalog() as catalog:
                folder = Folders(catalog).get(params['folder_id'])
            fingerprint = directory_identity(folder['path'])
            with self.service.catalog() as catalog:
                return FolderSync(catalog).prepare(**params,fingerprint=fingerprint)
        if method in ('get_folder_sync','get_folder_sync_metadata','select_folder_sync_items'):
            with self.service.catalog() as catalog:
                domain = FolderSync(catalog)
                if method == 'get_folder_sync_metadata':
                    return domain.metadata(**params)
                return domain.get(**params) if method == 'get_folder_sync' else domain.select(**params)
        if method == 'cancel_folder_sync':
            with self.state_lock:
                if event := self.events.get(params['plan_id']):
                    event.set()
            with self.service.catalog() as catalog:
                result = FolderSync(catalog).terminal(params['plan_id'],'cancelled')
            if self.lock.acquire(blocking=False):
                try:
                    if self.reader_plan == params['plan_id']:
                        self.reader.close();self.reader_plan = None
                finally:
                    self.lock.release()
            return result
        return self.run(method,params)

    def run(self,method,params):
        if not self.lock.acquire(blocking=False):
            raise ValueError('Another folder scan or synchronization is active')
        plan_id = params['plan_id'];event = threading.Event();plan = None;admitted = False
        with self.state_lock:
            self.events[plan_id] = event
        cancelled = lambda:self.cancelled(event)
        def check_root():
            if cancelled():
                raise InterruptedError('Folder synchronization cancelled')
            if directory_identity(plan['path']) != json.loads(plan['fingerprint']):
                raise ValueError('The synchronized root changed; create a fresh plan')
        try:
            if method == 'scan_folder_sync':
                with self.service.catalog() as catalog:
                    plan,rows = FolderSync(catalog).start_scan(**params)
                check_root()
                if plan['phase'] == 'directories':
                    if self.reader_plan != plan_id:
                        self.reader.close();self.reader_plan = plan_id
                    directory = rows[0]
                    result = self.reader.read(directory['path'],json.loads(directory['fingerprint']),cancelled)
                    check_root()
                    with self.service.catalog() as catalog:
                        return FolderSync(catalog).finish_directory(plan_id,plan['revision'],directory,result)
                observations = [(row,inspect_file(row,bool(plan['scan_metadata']),cancelled)) for row in rows]
                check_root()
                with self.service.catalog() as catalog:
                    return FolderSync(catalog).finish_files(plan_id,plan['revision'],observations)
            with self.service.catalog() as catalog:
                plan = FolderSync(catalog).start_apply(plan_id,params['expected_revision'],params.get('read_metadata',True))
            check_root()
            for kind in ('directories','files'):
                after = 0
                while True:
                    with self.service.catalog() as catalog:
                        rows = FolderSync(catalog).validation_page(plan_id,plan['revision'],kind,after)
                    if not rows:
                        break
                    for row in rows:
                        if cancelled():
                            raise InterruptedError('Folder synchronization cancelled')
                        if kind == 'directories':
                            if directory_identity(row['path']) != json.loads(row['fingerprint']):
                                raise ValueError('Directory contents changed after scanning; scan again')
                        elif any(identity(path) != expected for path,expected in json.loads(row['fingerprints']).items()):
                            raise ValueError('A photo or sidecar changed after scanning; scan again')
                    after = rows[-1]['id']
                    if kind == 'files':
                        with self.service.catalog() as catalog:
                            FolderSync(catalog).check(plan_id,plan['revision'],('verifying',))
                            with catalog.db:
                                catalog.db.execute('UPDATE folder_sync_plans SET checked=checked+? WHERE id=?',(len(rows),plan_id))
            check_root()
            admitted = self.service.image_lock.acquire(blocking=False)
            if not admitted:
                raise RelocationBusy('Image processing is active; synchronize after it finishes')
            with self.service.catalog() as catalog:
                return FolderSync(catalog).apply(plan_id,plan['revision'],params.get('import_new',True),
                                                params.get('remove_missing',False),params.get('read_metadata',True))
        except RelocationBusy as error:
            with self.service.catalog() as catalog:
                return FolderSync(catalog).defer_apply(plan_id,plan['revision'],str(error))
        except InterruptedError:
            with self.service.catalog() as catalog:
                return FolderSync(catalog).terminal(plan_id,'cancelled')
        except Exception as error:
            if plan is None:
                raise
            with self.service.catalog() as catalog:
                return FolderSync(catalog).terminal(plan_id,'failed',str(error))
        finally:
            if admitted:
                self.service.image_lock.release()
            with self.state_lock:
                self.events.pop(plan_id,None)
            try:
                if plan is not None:
                    with self.service.catalog() as catalog:
                        current = FolderSync(catalog).row(plan_id)
                        if current['state'] not in ACTIVE or current['phase'] != 'directories':
                            self.reader.close();self.reader_plan = None
            finally:
                self.lock.release()

    def close(self):
        if self.lock.acquire(blocking=False):
            try:
                self.reader.close();self.reader_plan = None
            finally:
                self.lock.release()
