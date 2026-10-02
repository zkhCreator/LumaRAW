"""Single-owner catalog service and bounded disposable-worker supervisor.

Purpose: keep UI and agents on one transactional domain boundary. Each command
opens its own SQLite connection under a short catalog lock. Expensive pixels run
outside that lock, in one child at a time, with sampled RSS and time limits.
Inputs: validated API commands. Outputs: JSON, file-backed previews, durable jobs,
revision-bound shared/catalog export preset workflows, catalog-local Previous
settings and immutable, pageable multi-preset export batches. Same-policy batch
jobs reuse only bounded serialized metadata during the batch write transaction.
Completed preview receipts are checked outside catalog locks without starting an
image worker; source identity, revisions and cancellation still bind each reply.
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
import uuid

import jsonschema
import psutil
from .api import TOOLS
from .catalog import Catalog, walk_images
from .model import Recipe, ExportOptions, LIMITS, PRESETS, SYNC_GROUPS, POINT_CURVE_PRESETS
from . import export_previous, export_batches, export_presets as export_preset_domain
from .organization import Organization
from .collections import Collections
from .virtual_copies import VirtualCopies
from .stacks import Stacks
from .auto_stacks import AutoStacks
from .folders import Folders
from .keywords import Keywords
from .relocations import Relocations, RelocationBusy, identity as relocation_identity, inspect_file
from .source_identity import cached_thumbnail, fingerprint
from .runtime import engine_identity, EngineChangedError
from .folder_sync import FolderSync
from .folder_sync_runner import FolderSyncRunner
from .keyword_exports import KeywordExports
from .batch_export_metadata import BatchExportMetadataCache
from .keyword_details import KeywordDetails
from .previous_import import state as previous_import_state
from .develop_history import DevelopHistory, adjustment_label
from .before_after import BeforeAfter
from .snapshots import Snapshots
from .snapshot_status import revision as snapshot_filter_revision
from . import preview_cache

class ConflictError(ValueError): pass

def executable_args():
    return [sys.executable] if getattr(sys,'frozen',False) else [sys.executable,'-m','lumaraw.bridge']

def unpack(row):
    if row:
        row=dict(row)
        for key in ('history_base_recipe','history_base_label','history_base_created','history_cursor'):
            row.pop(key,None)
        for key in ('recipe','metadata','options','processing','export_metadata','iptc'):
            if key in row and isinstance(row[key],str): row[key]=json.loads(row[key])
    return row

class Service:
    def __init__(self,root,identity=None,presets_root=None):
        self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True)
        self.cache=self.root/'cache';self.cache.mkdir(exist_ok=True)
        self.lock=threading.RLock();self.image_lock=threading.Lock();self.state_lock=threading.RLock()
        self.stopping=threading.Event();self.wake=threading.Event();self.active=None;self.peak=0
        self.cancel_jobs=set();self.preview_versions={};self.upgrading=False
        self.worker_identity=engine_identity()
        self.relocation_lock=threading.Lock()
        self.relocation_cancel={}
        self.folder_sync=FolderSyncRunner(self)
        from .keyword_sets import KeywordSets
        self.keyword_sets=KeywordSets(self,presets_root)
        from .develop_presets import DevelopPresets
        self.develop_presets=DevelopPresets(self,presets_root)
        from .metadata_presets import MetadataPresets
        self.metadata_presets=MetadataPresets(self,presets_root)
        from .export_presets import ExportPresets
        self.export_presets=ExportPresets(self,presets_root)
        from .import_runner import ImportRunner
        from .import_review import ImportReview
        self.import_review=ImportRunner(self)
        self.last_activity=time.monotonic()
        with self.catalog() as c:
            Relocations(c).recover()
            FolderSync(c).recover()
            ImportReview(c).recover()
            handoff=c.setting('clean_handoff')
            clean=(identity is not None and handoff == {'target':identity}
                   and c.job_counts().get('running',0)==0)
            c.recover_jobs()
            # Only a sealed, idle handoff to this exact engine preserves pending
            # work. Crashes and unrelated engines retain explicit recovery.
            with c.db:
                c.db.execute("DELETE FROM settings WHERE key='clean_handoff'")
                if not clean:
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

    @staticmethod
    def export_request_digest(method,params):
        # Preserve enqueue_exports' historical receipt digest byte-for-byte.
        # New Previous requests include their method name to prevent cross-method key reuse.
        payload=params if method=='enqueue_exports' else {'method':method,'args':params}
        return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()

    def export_request_replay(self,c,method,params,digest=None):
        digest=digest or self.export_request_digest(method,params)
        row=c.db.execute('SELECT digest,result FROM requests WHERE key=?',(params['request_key'],)).fetchone()
        if row is None:
            return digest,None
        if row['digest']!=digest:
            raise ValueError('request_key is already used by a different export request')
        return digest,json.loads(row['result'])

    @staticmethod
    def enqueue_export_rows(c,rows,destination,fmt,options):
        return [c.enqueue_one(row,destination,fmt,options) for row in rows]

    def enqueue_export_batch(self,p):
        method='enqueue_export_batch'
        digest=self.export_request_digest(method,p)
        # Receipt replay precedes storage-token validation so an accepted request
        # remains recoverable after a later preset mutation or storage switch.
        with self.catalog() as c:
            digest,replay=self.export_request_replay(c,method,p,digest)
            if replay is not None:return replay

        photo_ids=list(dict.fromkeys(p['photo_ids']))
        targets=p['presets']
        if not 1 <= len(targets) <= export_batches.MAX_PRESET_IDS:
            raise ValueError(f'Select between 1 and {export_batches.MAX_PRESET_IDS} export presets')
        if len({item['preset_id'] for item in targets}) != len(targets):
            raise ValueError('Export preset IDs must be unique')
        if len(photo_ids)*len(targets) > export_batches.MAX_BATCH_JOBS:
            raise ValueError(f'A batch cannot contain more than {export_batches.MAX_BATCH_JOBS} photo/preset jobs')
        parent_requested='parent_destination' in p
        parent_value=p.get('parent_destination')

        # Validate the submitted target shape before acquiring shared/catalog
        # write locks; stored settings and destinations are validated again under
        # the captured preset token below.
        allowed={'preset_id','destination','subfolder','filename_suffix'}
        for item in targets:
            if not isinstance(item,dict) or set(item)-allowed or 'preset_id' not in item:
                raise ValueError('Each batch preset must contain only its ID and optional destination fields')
            if parent_requested:
                if 'destination' in item or 'subfolder' not in item:
                    raise ValueError('Parent-folder batches require a subfolder for each preset and forbid destination overrides')
            elif 'subfolder' in item:
                raise ValueError('Per-preset subfolders are only valid with a parent destination')

        with self.export_presets.transaction() as (shared,c,db,local):
            digest,replay=self.export_request_replay(c,method,p,digest)
            if replay is not None:return replay
            revision=self.export_presets.token(shared,c)
            if revision != p['expected_revision']:
                raise ValueError('Export presets or storage changed; refresh before continuing')

            parent_destination=(export_batches.resolve_directory(parent_value,'parent_destination')
                                if parent_requested else None)
            resolved=[]
            seen_subfolders=set()
            for item in targets:
                row=self.export_presets.row(db,item['preset_id'])
                settings=export_preset_domain.validate_settings(json.loads(row['settings']))
                suffix=export_batches.validate_component(
                    item.get('filename_suffix',row['name']),'filename_suffix',
                    export_batches.MAX_FILENAME_SUFFIX_BYTES)
                if parent_requested:
                    subfolder=export_batches.validate_component(
                        item['subfolder'],'subfolder',export_batches.MAX_SUBFOLDER_BYTES)
                    key=export_batches.component_key(subfolder)
                    if key in seen_subfolders:
                        raise ValueError('Parent export subfolders must be unique after Unicode normalization and case folding')
                    seen_subfolders.add(key)
                    destination=str(export_batches.preflight_child(parent_destination,subfolder))
                else:
                    if 'subfolder' in item:
                        raise ValueError('Per-preset subfolders are only valid with a parent destination')
                    raw_destination=item.get('destination',settings['destination'])
                    if raw_destination is None:
                        raise ValueError(f"Export preset '{row['name']}' has no destination; choose one before batching")
                    destination=export_batches.resolve_directory(raw_destination,'preset destination')
                    subfolder=None
                resolved.append({'preset_id':row['id'],'name':row['name'],'format':settings['format'],
                                 'options':settings['options'],'destination':destination,
                                 'subfolder':subfolder,'filename_suffix':suffix})

            # Snapshot all target rows before the first directory is created.
            rows=[self.require(c,photo_id) for photo_id in photo_ids]
            destinations=list(dict.fromkeys(item['destination'] for item in resolved))
            if parent_requested:
                export_batches.preflight_directory(parent_destination,'parent_destination')
                for item in resolved:
                    export_batches.preflight_child(parent_destination,item['subfolder'])
                if len(destinations)!=len(resolved):
                    raise ValueError('Parent export subfolders resolve to the same destination')
            else:
                for destination in destinations:
                    export_batches.preflight_directory(destination,'preset destination')

            parent_identity=None
            if parent_requested:
                Path(parent_destination).mkdir(parents=True,exist_ok=True)
                parent_identity=export_batches.directory_identity(parent_destination,'parent_destination')
            destination_identities={}
            for destination in destinations:
                Path(destination).mkdir(parents=True,exist_ok=True)
                destination_identities[destination]=export_batches.directory_identity(destination,'batch destination')

            # Recheck identities and canonical containment after mkdir to detect
            # observed path changes before rows are inserted. Filesystem changes
            # cannot be made atomic with the catalog transaction.
            if parent_requested:
                current_parent=export_batches.directory_identity(parent_destination,'parent_destination')
                if current_parent!=parent_identity:
                    raise ValueError('parent_destination changed during batch preflight')
                if str(Path(parent_destination).resolve(strict=True))!=parent_destination:
                    raise ValueError('parent_destination changed through a symbolic link during batch preflight')
            for destination,identity in destination_identities.items():
                current=export_batches.directory_identity(destination,'batch destination')
                if current!=identity:
                    raise ValueError('A batch destination changed during directory creation')
                resolved_path=Path(destination).resolve(strict=True)
                if parent_requested:
                    if resolved_path.parent!=Path(parent_destination).resolve(strict=True):
                        raise ValueError('A batch subfolder escaped its selected parent')
                elif str(resolved_path)!=destination:
                    raise ValueError('A preset destination changed through a symbolic link')

            batch_id=str(uuid.uuid4())
            created=time.time()
            destination_mode='parent' if parent_requested else 'individual'
            c.db.execute('INSERT INTO export_batches(batch_id,created,revision,photo_count,preset_count,queued,'
                          'destination_mode,parent_destination) VALUES(?,?,?,?,?,?,?,?)',
                          (batch_id,created,revision,len(rows),len(resolved),len(rows)*len(resolved),
                           destination_mode,parent_destination))
            metadata_cache=BatchExportMetadataCache(c)
            for order,item in enumerate(resolved):
                c.db.execute('INSERT INTO export_batch_presets(batch_id,preset_order,preset_id,name,format,options,'
                             'destination,subfolder,filename_suffix) VALUES(?,?,?,?,?,?,?,?,?)',
                             (batch_id,order,item['preset_id'],item['name'],item['format'],
                              json.dumps(item['options'],ensure_ascii=False,sort_keys=True,separators=(',',':')),
                              item['destination'],item['subfolder'],item['filename_suffix']))
                options=ExportOptions.parse(item['options'])
                for row in rows:
                    frozen_metadata=metadata_cache.get(row['id'],options)
                    c.enqueue_one(row,item['destination'],item['format'],options,batch_id=batch_id,
                                  preset_name=item['name'],collision_suffix=item['filename_suffix'],
                                  frozen_metadata=frozen_metadata)
            result={'batch_id':batch_id,'queued':len(rows)*len(resolved),
                    'photo_count':len(rows),'preset_count':len(resolved)}
            c.db.execute('INSERT INTO requests VALUES(?,?,?)',
                         (p['request_key'],digest,json.dumps(result)))
        self.wake.set()
        return result

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
        if method=='metadata_schema':
            from .iptc import FIELDS, SCHEMA
            return {'iptc_fields':list(FIELDS.values()),'iptc_schema':SCHEMA}
        if method=='get_import_destinations':
            from .import_destinations import ImportDestinations
            with self.catalog() as c:
                return ImportDestinations(c).get(**p)
        if method in ('get_import_sequence','set_import_sequence'):
            from . import import_sequence
            with self.catalog() as c:
                return import_sequence.state(c.db) if method=='get_import_sequence' else import_sequence.set_state(c,**p)
        if method in ('list_import_presets','get_import_preset','save_import_preset','import_preset_action'):
            from .import_presets import ImportPresets
            with self.catalog() as c:
                domain=ImportPresets(c)
                return {'list_import_presets':domain.list,'get_import_preset':domain.get,
                        'save_import_preset':domain.save,'import_preset_action':domain.action}[method](**p)
        if method in ('get_import_naming','set_import_naming','preview_import_naming','list_filename_templates','get_filename_template','save_filename_template','delete_filename_template'):
            from .import_naming import ImportNaming
            with self.catalog() as c:
                domain=ImportNaming(c)
                return {'get_import_naming':domain.get,'set_import_naming':domain.set,'preview_import_naming':domain.preview,'list_filename_templates':domain.list,
                        'get_filename_template':domain.read,'save_filename_template':domain.save,'delete_filename_template':domain.delete}[method](**p)
        if method in ('list_metadata_presets','get_metadata_preset','save_metadata_preset','metadata_preset_action','apply_metadata_preset'):
            return self.metadata_presets.dispatch(method,p)
        if method in ('list_export_presets','get_export_preset','get_export_presets','save_export_preset','export_preset_action'):
            return self.export_presets.dispatch(method,p)
        if method=='enqueue_export_batch':return self.enqueue_export_batch(p)
        if method=='list_export_batches':
            with self.catalog() as c:return export_batches.list_batches(c.db,**p)
        if method=='get_export_batch':
            with self.catalog() as c:return export_batches.get_batch(c.db,**p)
        if method in ('list_develop_presets','get_develop_preset','save_develop_preset','develop_preset_action','apply_develop_preset'):
            return self.develop_presets.dispatch(method,p)
        if method in ('list_keyword_sets','get_keyword_set','save_keyword_set','keyword_set_action','apply_keyword_set'):
            return self.keyword_sets.dispatch(method,p)
        if method in ('prepare_folder_sync','get_folder_sync','get_folder_sync_metadata','scan_folder_sync','select_folder_sync_items','apply_folder_sync','cancel_folder_sync'):
            return self.folder_sync.dispatch(method,p)
        if method in ('prepare_import','get_import','scan_import','select_import_items','set_import_options','apply_import','cancel_import','preview_import_item','get_import_processing','set_import_processing','resume_import_copy','get_import_copies','set_import_backup','restart_import_with_preset'):
            return self.import_review.dispatch(method,p)
        if method=='status':
            with self.catalog() as c:
                return {'version':'0.4.1','api_version':1,'catalog':str(self.root),'photos':c.count(),'counts':c.job_counts(),'paused':self.paused,'active':self.active,**self.memory_status(),'peak_mb':round(self.peak,1)}
        if method=='recipe_schema':return {'defaults':Recipe().dict(),'limits':LIMITS,'presets':{k:v.dict() for k,v in PRESETS.items()},'groups':SYNC_GROUPS,
            'point_curve_presets':{k:[list(p) for p in v] for k,v in POINT_CURVE_PRESETS.items()}}
        if method in ('import_keywords','export_keywords'):
            from .keyword_exchange import import_file, export_file
            return (import_file if method=='import_keywords' else export_file)(self, **p)
        if method in ('scan_folder_relocation','apply_folder_relocation'):
            return self.run_relocation(method,p)
        if method=='cancel_folder_relocation':
            with self.state_lock:
                if event:=self.relocation_cancel.get(p['plan_id']):event.set()
            with self.catalog() as c:return Relocations(c).terminal(p['plan_id'],'cancelled')
        if method=='cancel_preview':
            with self.state_lock:
                client=p['client_id'];generation=p['generation']
                if generation < self.preview_versions.get(client,-1):
                    return {'cancelled':False,'superseded':True}
                self.preview_versions[client]=generation
                if len(self.preview_versions)>128:self.preview_versions.pop(next(iter(self.preview_versions)))
                cancelled=False
                if (self.active and self.active.get('client_id')==client
                        and self.active.get('generation',-1)<generation
                        and self.active.get('operation') in ('preview','detail','thumbnail')):
                    self.cancelled=True
                    if self.process.poll() is None:self.process.kill();cancelled=True
                return {'cancelled':cancelled,'generation':generation}
        if method=='cached_thumbnails':
            with self.catalog() as c:
                rows=[self.require(c,photo_id) for photo_id in dict.fromkeys(p['photo_ids'])]
            developed=p.get('kind') == 'developed'
            entries=[]
            for row in rows:
                recipe=Recipe.parse(json.loads(row['recipe'])) if developed else None
                if path:=cached_thumbnail(row['path'],self.cache,recipe,row['orientation']):
                    entry={'photo_id':row['id'],'thumbnail':path}
                    if developed:entry.update(revision=row['revision'],kind='developed',source=row['path'])
                    entries.append(entry)
            return {'thumbnails':entries,'worker_spawned':False}
        if method in ('preview_photo','thumbnail','calibrate_camera'):
            if method in ('preview_photo','thumbnail') and p.get('client_id'):
                if 'generation' not in p:raise ValueError('client_id requires generation')
                with self.state_lock:
                    client=p['client_id'];generation=p['generation']
                    if generation<self.preview_versions.get(client,-1):raise InterruptedError('Preview is superseded')
                    self.preview_versions[client]=generation
                    if len(self.preview_versions)>128:self.preview_versions.pop(next(iter(self.preview_versions)))
                    if (self.active and self.active.get('client_id')==client and self.active.get('generation',-1)<generation
                            and self.active.get('operation') in ('preview','detail','thumbnail')):
                        self.cancelled=True
                        if self.process.poll() is None:self.process.kill()
            with self.catalog() as c:
                draft_key='curve_patch' if 'curve_patch' in p else ('mixer_patch' if 'mixer_patch' in p else None)
                row=self.check_revision(c,p['photo_id'],p['expected_revision']) if 'expected_revision' in p else self.require(c,p['photo_id'])
                preview_recipe=json.loads(row['recipe'])
                if draft_key:
                    preview_recipe=Recipe.parse({**preview_recipe,**p[draft_key]}).dict()
                before_state = BeforeAfter(c.db).read(row['id']) if method=='preview_photo' and p.get('include_before',True) else None
            if method=='thumbnail':
                recipe=Recipe.parse(json.loads(row['recipe'])) if p.get('kind') == 'developed' else None
                path=cached_thumbnail(row['path'],self.cache,recipe,row['orientation'])
                if path:
                    return {'thumbnail':path,'photo_id':row['id'],'revision':row['revision'],'kind':p.get('kind','source'),'source':row['path'],
                            'cache_hit':True,'worker_spawned':False}
            request={'operation':{'preview_photo':'preview','thumbnail':'thumbnail','calibrate_camera':'calibrate'}[method],
                     'path':row['path'],'recipe':preview_recipe,'orientation':row['orientation']}
            request.update({k:v for k,v in p.items() if k not in ('photo_id','curve_patch','mixer_patch','expected_revision')})
            if before_state:
                request['before_recipe']=before_state[0].dict()
            source_fingerprint=fingerprint(row['path']) if 'expected_revision' in p else None
            result=None
            if method=='preview_photo':
                cache_key=preview_cache.key(request,self.worker_identity,self.compute_backend)
                result=preview_cache.load(self.cache,cache_key,request,self.compute_backend,
                                          lambda:self.check_preview_current(request),repair_lock=self.image_lock)
                if result is not None and cache_key!=preview_cache.key(request,self.worker_identity,self.compute_backend):
                    raise ValueError('Source or rendering asset changed during preview; reload the photograph')
            if result is None:
                result=self.run_worker(request)
            if method=='preview_photo':
                self.check_preview_current(request)
            if 'expected_revision' in p:
                if fingerprint(row['path']) != source_fingerprint:
                    raise ValueError('Source changed during preview; reload the photograph')
                with self.catalog() as c:self.check_revision(c,p['photo_id'],p['expected_revision'])
            if 'metadata' in result:
                with self.catalog() as c:c.update_metadata(row['id'],result['metadata'])
            return {**result,'photo_id':row['id'],'revision':row['revision'],'source':row['path'],
                    **({'before_label':before_state[1]} if before_state else {}),
                    'curve_draft':'curve_patch' in p,'mixer_draft':'mixer_patch' in p}
        if method=='queue_control':return self.control(p)
        with self.catalog() as c:
            if method in ('orientation_state','orient_photos','undo_orientation'):
                from .orientation import Orientations
                orientations=Orientations(c)
                return {'orientation_state':orientations.state,'orient_photos':orientations.apply,'undo_orientation':orientations.undo}[method](**p)
            if method=='prepare_folder_relocation':return Relocations(c).prepare(**p)
            if method in ('get_keyword_shortcut','set_keyword_shortcut','paint_library'):
                from .library_painter import LibraryPainter
                painter=LibraryPainter(c)
                return {'get_keyword_shortcut':painter.read,'set_keyword_shortcut':painter.save,'paint_library':painter.paint}[method](**p)
            if method=='get_folder_relocation':return Relocations(c).get(**p)
            if method in ('photo_summaries','library_state'):
                state={'stack_revision':Stacks(c).revision(),'folder_revision':Folders(c).revision(),
                       'keyword_revision':Keywords(c).revision(),'previous_import':previous_import_state(c.db),
                       'snapshot_filter_revision':snapshot_filter_revision(c.db)}
                if method=='photo_summaries':state['photos']=c.summaries(p['photo_ids'])
                return state
            if method=='list_keywords':return Keywords(c).list(**p)
            if method=='get_keyword':return Keywords(c).details(**p)
            if method=='save_keyword':return Keywords(c).save(**p)
            if method=='delete_keyword':return Keywords(c).delete(**p)
            if method=='keyword_membership':return Keywords(c).membership(**p)
            if method=='list_folders':return Folders(c).list(**p)
            if method=='get_folder':return Folders(c).details(**p)
            if method=='edit_folder':return Folders(c).edit(**p)
            if method=='set_folder_visibility':return Folders(c).visibility(**p)
            if method=='import_photos':
                def paths():
                    for path in p['paths']:
                        q=Path(path)
                        if q.is_dir() and not q.is_symlink():yield from walk_images(q)
                        else:yield q
                count,skipped=c.import_paths(paths());return {'imported':count,'skipped':skipped,'total':c.count()}
            if method=='list_photos':
                mode=p.get('mode','all');search=p.get('search','');offset=p.get('offset',0)
                filters=p.get('filters');collection=p.get('collection_id')
                stacked=p.get('stacked',True)
                folder=p.get('folder_id');subfolders=p.get('include_subfolders',True)
                total=c.filtered_count(mode,search,filters,collection,stacked,folder,subfolders)
                offset=min(offset,max(0,((total-1)//60)*60))
                return {'photos':c.filtered_page(offset,mode,search,filters,collection,p.get('sort','imported'),p.get('descending',True),stacked,folder,subfolders,match_count=total),'total':total,'offset':offset,'page_size':60,'stack_revision':Stacks(c).revision(),'folder_revision':Folders(c).revision(),'keyword_revision':Keywords(c).revision(),'previous_import':previous_import_state(c.db),'snapshot_filter_revision':snapshot_filter_revision(c.db)}
            if method=='stack_state':return {'revision':Stacks(c).revision()}
            if method=='preview_export_metadata':return KeywordExports(c).preview(**p)
            if method=='stack_photos':return Stacks(c).change(**p)
            if method=='set_stack_visibility':return Stacks(c).visibility(**p)
            if method=='preview_auto_stack':return AutoStacks(c).preview(**p)
            if method=='apply_auto_stack':return AutoStacks(c).apply(**p)
            if method=='refresh_capture_times':return AutoStacks(c).refresh_times(**p)
            if method=='list_collections':return Collections(c).list(**p)
            if method=='set_collection_labels':return Collections(c).set_labels(**p)
            if method=='get_collection':
                store=Collections(c);row=store.get(p['collection_id'])
                return {**row,'ancestors':list(reversed(store.ancestors(row['parent_id'])))}
            if method=='duplicate_collection':return Collections(c).duplicate(**p)
            if method=='collection_state':return Collections(c).state(p.get('photo_ids',()))
            if method=='set_target_collection':return Collections(c).set_target(**p)
            if method=='target_membership':return Collections(c).target_membership(**p)
            if method=='quick_collection':return Collections(c).quick(**p)
            if method=='save_collection':
                if ('collection_id' in p) != ('expected_revision' in p):
                    raise ValueError('Collection updates require collection_id and expected_revision together')
                return Organization(c).save_collection(**p)
            if method=='collection_membership':
                return Organization(c).membership(p['collection_id'],p['expected_revision'],p['photo_ids'],p['action'])
            if method=='delete_collection':
                return Organization(c).delete_collection(p['collection_id'],p['expected_revision'])
            if method=='edit_metadata':
                ids=Organization(c).edit_metadata(p['targets'],p['patch'])
                first=c.photo(ids[0])
                accepted={key:first[key] for key in p['patch'] if key not in ('keywords','keyword_ids','keyword_additions','iptc')}
                if 'iptc' in p['patch']:
                    accepted['iptc']=p['patch']['iptc']
                if any(key in p['patch'] for key in ('keywords','keyword_ids')):
                    accepted.update({key:first[key] for key in ('keywords','keyword_tags','keyword_ids','keyword_count','keywords_deferred')})
                return {'updated':[{'photo_id':photo_id,'metadata_revision':c.db.execute(
                    'SELECT metadata_revision FROM photos WHERE id=?',(photo_id,)).fetchone()[0]} for photo_id in ids], 'patch':accepted}
            if method=='create_virtual_copies':
                if ('collection_id' in p) != ('expected_collection_revision' in p):
                    raise ValueError('Collection ID and revision must be provided together')
                return VirtualCopies(c).create(**p)
            if method=='remove_virtual_copies':return VirtualCopies(c).remove(p['targets'])
            if method=='set_copy_as_master':return unpack(VirtualCopies(c).promote(p))
            if method=='get_photo':return unpack(self.require(c,p['photo_id']))
            if method=='get_photo_keywords':return KeywordDetails(c).photo(**p)
            if method=='keyword_choices':return KeywordDetails(c).choices(**p)
            if method=='list_history':
                page=DevelopHistory(c.db).page(p['photo_id'],p.get('before_id'))
                if page['revision']!=p['expected_revision']:
                    raise ConflictError('Edit conflict: history changed. Read the photo again.')
                return page
            if method=='before_after':
                row=self.check_revision(c,p['photo_id'],p['expected_revision'])
                with c.db:
                    result=BeforeAfter(c.db).apply(row['id'],p['action'],p.get('step_id'),p.get('version_id'),p.get('expected_version_revision'))
                return {**unpack(c.photo(row['id'])),**result,'before_label':BeforeAfter(c.db).read(row['id'])[1]}
            if method in ('redo_photo','select_history','rename_history','clear_history'):
                row=self.check_revision(c,p['photo_id'],p['expected_revision'])
                history=DevelopHistory(c.db)
                with c.db:
                    if method=='redo_photo':history.move(row['id'],redo=True)
                    elif method=='select_history':history.select(row['id'],p['step_id'])
                    elif method=='rename_history':history.rename(row['id'],p['step_id'],p['name'])
                    else:history.clear(row['id'])
                return unpack(c.photo(row['id']))
            if method in ('edit_photo','undo_photo','restore_version','load_recipe'):
                row=self.check_revision(c,p['photo_id'],p['expected_revision'])
                if method=='edit_photo':
                    values=json.loads(row['recipe']);values.update(p['patch']);c.edit(row['id'],Recipe.parse(values),adjustment_label(p['patch']))
                elif method=='undo_photo':c.undo(row['id'])
                elif method=='restore_version':c.restore_version(row['id'],p['version_id'],p.get('expected_version_revision'))
                else:
                    from .library import load_recipe
                    c.edit(row['id'],load_recipe(p['path'],self.root),'Import Recipe Bundle')
                return unpack(c.photo(row['id']))
            if method=='rate_photo':
                self.require(c,p['photo_id'])
                if 'rating' in p:c.rate(p['photo_id'],p['rating'])
                if 'flag' in p:c.flag(p['photo_id'],p['flag'])
                return unpack(c.photo(p['photo_id']))
            if method=='rate_photos':
                fields={key:p[key] for key in ('rating','flag') if key in p}
                if not fields:raise ValueError('Set a rating or pick flag')
                ids=list(dict.fromkeys(p['photo_ids']))
                for photo_id in ids:self.require(c,photo_id)
                with c.db:
                    c.db.executemany('UPDATE photos SET '+','.join(f'{key}=?' for key in fields)+' WHERE id=?',
                                     [(*fields.values(),photo_id) for photo_id in ids])
                return {'updated':[{'photo_id':photo_id,**fields} for photo_id in ids]}
            if method=='get_previous_export':
                return export_previous.state(c.db)
            if method=='enqueue_exports':
                digest,replay=self.export_request_replay(c,method,p)
                if replay is not None:return replay
                options=ExportOptions.parse(p.get('options'))
                photo_ids=list(dict.fromkeys(p['photo_ids']))
                # Match the existing preflight boundary: reject bad selections before
                # creating the user-requested destination directory.
                for photo_id in photo_ids:self.require(c,photo_id)
                dest=Path(p['destination']).expanduser().resolve()
                dest.mkdir(parents=True,exist_ok=True)
                remember=bool(p.get('remember_previous',False))
                saved_settings=(export_previous.canonical_settings(p['format'],options.dict(),str(dest))
                                if remember else None)
                with c.db:
                    c.db.execute('BEGIN IMMEDIATE')
                    digest,replay=self.export_request_replay(c,method,p,digest)
                    if replay is not None:return replay
                    rows=[self.require(c,photo_id) for photo_id in photo_ids]
                    ids=self.enqueue_export_rows(c,rows,dest,p['format'],options)
                    result={'job_ids':ids,'queued':len(ids)}
                    if saved_settings is not None:export_previous.remember(c.db,saved_settings)
                    c.db.execute('INSERT INTO requests VALUES(?,?,?)',(p['request_key'],digest,json.dumps(result)))
                self.wake.set();return result
            if method=='enqueue_previous_exports':
                digest,replay=self.export_request_replay(c,method,p)
                if replay is not None:return replay
                with c.db:
                    c.db.execute('BEGIN IMMEDIATE')
                    digest,replay=self.export_request_replay(c,method,p,digest)
                    if replay is not None:return replay
                    previous=export_previous.state(c.db)
                    if not previous['available']:
                        raise ValueError('No accepted Previous export settings are available')
                    if previous['revision']!=p['expected_revision']:
                        raise ValueError('Previous export settings changed; refresh and try again')
                    settings=previous['settings']
                    options=ExportOptions.parse(settings['options'])
                    photo_ids=list(dict.fromkeys(p['photo_ids']))
                    rows=[self.require(c,photo_id) for photo_id in photo_ids]
                    # Keep this small filesystem side effect within the same write
                    # transaction as the captured settings and recipe snapshots.
                    dest=Path(settings['destination']).expanduser().resolve()
                    dest.mkdir(parents=True,exist_ok=True)
                    ids=self.enqueue_export_rows(c,rows,dest,settings['format'],options)
                    result={'job_ids':ids,'queued':len(ids)}
                    c.db.execute('INSERT INTO requests VALUES(?,?,?)',(p['request_key'],digest,json.dumps(result)))
                self.wake.set();return result
            if method=='get_job':
                row=c.db.execute('SELECT '+c.job_columns()+' FROM jobs WHERE id=?',(p['job_id'],)).fetchone()
                if not row:raise ValueError('Job does not exist')
                return unpack(dict(row))
            if method=='list_jobs':
                return {'jobs':[{k:v for k,v in unpack(j).items() if k!='recipe'} for j in c.jobs(60)],
                        'counts':c.job_counts(),'paused':self.paused,'active':self.active,
                        'previous_export':export_previous.summary(c.db)}
            if method=='save_version':
                return {'saved':True,**c.save_version(p['photo_id'],p['name'],p.get('expected_revision'),p.get('step_id'))}
            if method=='list_versions':
                return Snapshots(c.db).page(**p)
            if method in ('rename_version','update_version','delete_version'):
                with c.db:
                    c.db.execute('BEGIN IMMEDIATE')
                    return getattr(Snapshots(c.db),method.removesuffix('_version'))(**p)
            if method=='sync_photos':
                source=Recipe.parse(json.loads(self.require(c,p['source_id'])['recipe'])).dict();changes=[]
                for target in p['targets']:
                    row=self.check_revision(c,target['photo_id'],target['expected_revision']);values=json.loads(row['recipe'])
                    values.update({k:source[k] for g in p['groups'] for k in SYNC_GROUPS[g]});changes.append((row,Recipe.parse(values)))
                # All validation precedes the transaction; the timeline writer never commits a batch.
                with c.db:
                    for row,recipe in changes:
                        if row['id']==p['source_id']:continue
                        DevelopHistory(c.db).edit(row['id'],recipe,'Batch Sync')
                return {'synced':sum(r['id']!=p['source_id'] for r,_ in changes)}
            if method=='settings':
                if 'select_previous_import' in p:c.set_setting('select_previous_import',p['select_previous_import'])
                if 'budget_mb' in p:self.budget=p['budget_mb'];c.set_setting('budget_mb',self.budget)
                if 'compute_backend' in p:self.compute_backend=p['compute_backend'];c.set_setting('compute_backend',self.compute_backend)
                from .accelerators import availability
                return {**self.memory_status(),'acceleration':availability(),'select_previous_import':c.setting('select_previous_import',True)}
            from . import library
            if method=='index_library':return library.index_library(c)
            if method=='relink_photo':self.require(c,p['photo_id']);c.relink(p['photo_id'],p['path']);return unpack(c.photo(p['photo_id']))
            if method=='backup_catalog':return {'backup':library.backup_catalog(c,p['path'])}
            if method=='restore_catalog':return {'catalog':str(library.restore_catalog(p['path'],p['destination']))}
            if method=='import_asset':return {'asset':library.import_asset(p['path'],self.root,p['kind'])}
            if method=='save_recipe':self.require(c,p['photo_id']);library.save_recipe(p['path'],c.recipe(p['photo_id']));return {'path':p['path']}
        raise ValueError('Operation is not implemented')

    def run_relocation(self, method, params):
        if not self.relocation_lock.acquire(blocking=False):
            raise ValueError('Another folder verification is active; wait for it or cancel it')
        plan_id=params['plan_id'];event=threading.Event();plan=None;image_admitted=False
        with self.state_lock:self.relocation_cancel[plan_id]=event
        cancelled=lambda:event.is_set() or self.stopping.is_set()
        def check_location():
            if cancelled():raise InterruptedError('Folder relocation cancelled')
            if os.path.exists(plan['source']):
                raise ValueError('The original folder is available again; scan its location before relinking')
            if relocation_identity(plan['destination'],directory=True) != json.loads(plan['destination_identity']):
                raise ValueError('The replacement directory changed; choose it and scan again')
        try:
            if method=='scan_folder_relocation':
                with self.catalog() as c:plan,rows=Relocations(c).start_scan(**params)
                check_location()
                checked=[inspect_file(row,cancelled) for row in rows]
                check_location()
                with self.catalog() as c:return Relocations(c).finish_scan(plan_id,plan['revision'],checked)
            with self.catalog() as c:plan=Relocations(c).start_apply(**params)
            check_location();after=0
            while True:
                with self.catalog() as c:rows=Relocations(c).validation_page(plan_id,plan['revision'],after)
                if not rows:break
                for row in rows:
                    if cancelled():raise InterruptedError('Folder relocation cancelled')
                    if relocation_identity(row['destination']) != json.loads(row['fingerprint']):
                        raise ValueError('A proposed file changed after scanning; scan again before relinking')
                after=rows[-1]['source_id']
                with self.catalog() as c:
                    Relocations(c).check(plan_id,plan['revision'],('verifying',))
                    with c.db:c.db.execute('UPDATE folder_relocations SET checked=checked+? WHERE id=?',(len(rows),plan_id))
            check_location()
            image_admitted=self.image_lock.acquire(blocking=False)
            if not image_admitted:raise RelocationBusy('Image processing is active; apply this plan after it finishes')
            with self.catalog() as c:return Relocations(c).apply(plan_id,plan['revision'])
        except RelocationBusy as error:
            with self.catalog() as c:return Relocations(c).defer_apply(plan_id,plan['revision'],str(error))
        except InterruptedError:
            with self.catalog() as c:return Relocations(c).terminal(plan_id,'cancelled')
        except Exception as error:
            if plan is None:raise
            with self.catalog() as c:return Relocations(c).terminal(plan_id,'failed',str(error))
        finally:
            if image_admitted:self.image_lock.release()
            with self.state_lock:self.relocation_cancel.pop(plan_id,None)
            self.relocation_lock.release()

    def check_preview_current(self,request):
        with self.state_lock:
            if self.stopping.is_set():raise InterruptedError('Processing stopped')
            client=request.get('client_id')
            if client and self.preview_versions.get(client)!=request.get('generation'):
                raise InterruptedError('Preview is superseded')

    def run_worker(self,request):
        with self.image_lock:
            if request['operation']=='export':
                with self.catalog() as c:
                    row=c.db.execute('SELECT state FROM jobs WHERE id=?',(request['job_id'],)).fetchone()
                    if row and row[0]=='cancelled':raise InterruptedError('Cancelled')
            memory=self.memory_status();budget=memory['effective_budget_mb']
            request={**request,'cache':str(self.cache),'budget_mb':budget,'parent_pid':os.getpid(),
                     'compute_backend':self.compute_backend,'engine_identity':self.worker_identity}
            payload=json.dumps(request,ensure_ascii=False,allow_nan=False).encode()+b'\n'
            if len(payload)>8*1024*1024:
                raise ValueError('Image worker request exceeds 8 MiB')
            env={**os.environ,'OMP_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'1','VECLIB_MAXIMUM_THREADS':'2'}
            with tempfile.TemporaryFile() as output,tempfile.TemporaryFile() as errors:
                with self.state_lock:
                    if request.get('job_id') in self.cancel_jobs:raise InterruptedError('Cancelled')
                    if request.get('client_id') and self.preview_versions.get(request['client_id'])!=request.get('generation'):raise InterruptedError('Preview is superseded')
                    process=subprocess.Popen(executable_args()+['--worker'],stdin=subprocess.PIPE,stdout=output,stderr=errors,env=env)
                    self.active={'operation':request['operation'],'pid':process.pid,'job_id':request.get('job_id'),'client_id':request.get('client_id'),'generation':request.get('generation')};self.process=process;self.cancelled=False
                peak=0;failure=None;started=time.monotonic()
                try:
                    process.stdin.write(payload);process.stdin.close()
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
                    if result.get('type')=='EngineChangedError':raise EngineChangedError(result['error'])
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
                if self.paused or self.upgrading:continue
                if psutil.virtual_memory().available<384*1024**2:
                    self.paused=True;c.set_setting('paused',True);continue
                job=c.next_job()
            if not job:continue
            try:
                result=self.run_worker({'operation':'export','path':job['source'],'recipe':json.loads(job['recipe']),
                    'destination':job['destination'],'format':job['format'],'job_id':job['id'],'options':json.loads(job['options']),
                    'metadata_snapshot':json.loads(job['metadata_snapshot']),'orientation':job['orientation'],
                    'collision_suffix':job.get('collision_suffix','')})
                with self.catalog() as c:
                    c.finish_job(job['id'],'done',peak_mb=result['peak_mb'],output=result['output'])
                    with c.db:c.db.execute('UPDATE jobs SET processing=? WHERE id=?',(json.dumps(result.get('processing',{})),job['id']))
            except Exception as e:
                state='interrupted' if isinstance(e,EngineChangedError) else 'cancelled' if isinstance(e,InterruptedError) else 'failed'
                with self.catalog() as c:
                    c.finish_job(job['id'],state,str(e),peak_mb=getattr(e,'peak_mb',0))
                    if isinstance(e,EngineChangedError):
                        self.paused=True;c.set_setting('paused',True)
            self.last_activity=time.monotonic()

    def control(self,p):
        action=p['action'];id_=p.get('job_id');batch_id=p.get('batch_id')
        if id_ is not None and batch_id is not None:
            raise ValueError('Choose either one job or one export batch')
        if batch_id is not None and action not in ('cancel','retry','retry_cancelled'):
            raise ValueError('Batch scope supports cancel, retry, or retry_cancelled only')
        with self.catalog() as c:
            if batch_id is not None:
                try:
                    if str(uuid.UUID(batch_id)) != batch_id:raise ValueError
                except (ValueError,TypeError,AttributeError):
                    raise ValueError('batch_id must be a canonical UUID')
                if not c.db.execute('SELECT 1 FROM export_batches WHERE batch_id=?',(batch_id,)).fetchone():
                    raise ValueError('Export batch does not exist')
                states=('pending','running') if action=='cancel' else (('failed','interrupted') if action=='retry' else ('cancelled',))
                placeholders=','.join('?' for _ in states)
                targets=[row[0] for row in c.db.execute(
                    f'SELECT id FROM jobs WHERE batch_id=? AND state IN ({placeholders})',
                    (batch_id,*states))]
                if action=='cancel':
                    with c.db:
                        c.db.execute(f"UPDATE jobs SET state='cancelled' WHERE batch_id=? AND state IN ({placeholders})",
                                     (batch_id,*states))
                    with self.state_lock:
                        self.cancel_jobs.update(targets)
                        if (self.active and self.active['operation']=='export'
                                and self.active.get('job_id') in targets):
                            self.cancelled=True
                            if self.process.poll() is None:self.process.kill()
                else:
                    with self.state_lock:
                        self.cancel_jobs.difference_update(targets)
                    with c.db:
                        c.db.execute(f"UPDATE jobs SET state='pending',error='' WHERE batch_id=? AND state IN ({placeholders})",
                                     (batch_id,*states))
                self.wake.set()
                return {'paused':self.paused,'counts':c.job_counts(),'batch_id':batch_id,
                        'batch_counts':export_batches.batch_counts(c.db,batch_id)}
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
        self.folder_sync.close()
        self.import_review.close()
