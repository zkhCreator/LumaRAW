"""Versioned public command contracts shared by native UI, CLI and MCP.

Inputs: bounded JSON objects. Outputs: JSON schemas and validated domain commands.
No transport, pixels or UI dependencies. IDs refer only to the selected catalog.
Tool annotations describe effects; they never substitute for user authorization.
"""
from .model import LIMITS, Recipe, SYNC_GROUPS
from .organization import COLORS, SORTS, FILTER_SCHEMA

def obj(properties=None, required=()):
    return {'type':'object','properties':properties or {},'required':list(required),'additionalProperties':False}
def integer(lo=0,hi=2**53-1): return {'type':'integer','minimum':lo,'maximum':hi}
def string(maximum=4096): return {'type':'string','minLength':1,'maxLength':maximum}
def array(items,maximum=1000): return {'type':'array','items':items,'maxItems':maximum,'minItems':1}
ID=integer(1); REV=integer(); PATH=string(); BOOL={'type':'boolean'}
OPTIONAL_ID={'anyOf':[ID,{'type':'null'}]}
PATCH={'type':'object','maxProperties':64}
TOOLS={}
def tool(name,description,properties=None,required=(),read=False):
    TOOLS[name]={'name':name,'description':description,'inputSchema':obj(properties,required),
        'annotations':{'readOnlyHint':read,'destructiveHint':False,'idempotentHint':read,'openWorldHint':False}}
tool('service_connection','Inspect engine compatibility or explicitly activate this build when the broker is idle. Preserves pending jobs on a clean handoff; never interrupts active work.',{'action':{'enum':['status','activate']}},['action'])
tool('status','Service version, catalog location, queue and processing state.',read=True)
tool('recipe_schema','Supported recipe ranges, defaults, presets and sync groups.',read=True)
tool('import_photos','Reference explicit local photos or directories; never copy or modify originals.',{'paths':array(PATH)},['paths'])
tool('list_photos','Read at most 60 summaries with SQL filters, collection membership and stable sorting.',{'offset':integer(),'mode':{'enum':['all','stars','keepers','rejects','missing','duplicates']},'search':{'type':'string','maxLength':200},'filters':FILTER_SCHEMA,'collection_id':ID,'sort':{'enum':list(SORTS)},'descending':BOOL},read=True)
tool('list_collections','Read at most 60 collections/sets, excluding Quick. Omit parent_id for flat compatibility; null selects roots, an ID selects children.',{'offset':integer(),'parent_id':OPTIONAL_ID},read=True)
TOOLS['list_photos']['inputSchema']['properties']['stacked']=BOOL
TOOLS['list_photos']['inputSchema']['properties'].update(folder_id=ID,include_subfolders=BOOL)
tool('library_state','Read folder and stack structural revisions without photo payloads.',read=True)
KEYWORD_TARGET = obj({'photo_id':ID,'expected_metadata_revision':REV},['photo_id','expected_metadata_revision'])
tool('list_keywords','Read at most 60 keyword roots/children or search names/synonyms. Counts and selection states are direct assignments; keyword photo filters also include descendants.',{'parent_id':OPTIONAL_ID,'offset':integer(),'search':{'type':'string','maxLength':200},'photo_ids':array(ID,60)},read=True)
tool('save_keyword','Create, rename or move a keyword with up to 30 synonyms. Requires the keyword list revision; ancestor paths of assigned photos also invalidate their metadata revisions.',{'name':string(120),'parent_id':OPTIONAL_ID,'keyword_id':ID,'expected_revision':REV,'synonyms':{'type':'array','items':string(120),'maxItems':30}},['name','expected_revision'])
TOOLS['save_keyword']['inputSchema']['properties']['targets']=array(KEYWORD_TARGET,60)
tool('delete_keyword','Delete one keyword subtree and its photo assignments atomically; preserve originals and recipes.',{'keyword_id':ID,'expected_revision':REV},['keyword_id','expected_revision'])
TOOLS['delete_keyword']['annotations']['destructiveHint']=True
tool('keyword_membership','Add/remove a keyword on up to 60 photos without replacing other tags. Requires both keyword list and photo metadata revisions.',{'keyword_id':ID,'expected_revision':REV,'targets':array(KEYWORD_TARGET,60),'action':{'enum':['add','remove']}},['keyword_id','expected_revision','targets','action'])
tool('list_folders','Read at most 60 catalog folder roots or children, with direct/descendant photo counts. Search/favorite/color filters return a flat list; never scan the filesystem tree.',{'parent_id':OPTIONAL_ID,'offset':integer(),'search':{'type':'string','maxLength':200},'favorites':BOOL,'color_label':{'enum':list(COLORS)}},read=True)
tool('get_folder','Read exactly one folder or the folder containing a photo, including ancestors and navigation offsets. No directory writes.',{'folder_id':ID,'photo_id':ID},read=True)
tool('edit_folder','Change catalog-only folder favorite/color label with optimistic metadata revision.',{'folder_id':ID,'expected_revision':REV,'patch':obj({'favorite':BOOL,'color_label':{'enum':list(COLORS)}})},['folder_id','expected_revision','patch'])
tool('set_folder_visibility','Show a root folder parent or hide an empty parent in favor of its children. Changes catalog presentation only; requires the folder tree revision.',{'folder_id':ID,'expected_revision':REV,'action':{'enum':['show_parent','hide_parent']}},['folder_id','expected_revision','action'])
tool('stack_state','Read the current stack revision for optimistic grouping and visibility changes.',read=True)
AUTO_SOURCE={'folder':PATH,'collection_id':ID}
AUTO_TIME={**AUTO_SOURCE,'seconds':{'type':'number','minimum':0,'maximum':3600}}
tool('preview_auto_stack','Preview capture-time groups for exactly one folder or regular/Quick collection, independent of selection and filters. Returns a fingerprint and at most 20 example groups.',AUTO_TIME,['seconds'],True)
tool('apply_auto_stack','Replace stack organization in the previewed source only if its capture times, membership and stacks still match the token. Originals and recipes are unchanged.',{**AUTO_TIME,'token':string(64)},['seconds','token'])
tool('refresh_capture_times','Read only bounded EXIF headers for at most 60 physical sources in one folder or collection. Continue with after_source_id until done; no hashing or pixels.',{**AUTO_SOURCE,'after_source_id':integer()})
tool('set_stack_visibility','Expand/collapse all stacks in the captured source, independent of photo selection or metadata filters. folder includes descendants unless include_subfolders is false; omit source for all folder stacks.',{'collapsed':BOOL,'expected_revision':REV,'collection_id':ID,'folder':PATH},['collapsed','expected_revision'])
TOOLS['set_stack_visibility']['inputSchema']['properties']['include_subfolders']=BOOL
tool('stack_photos','Change source-scoped stacks atomically. Ordered photo_ids define initial order; active_id becomes the new cover. Split moves a selected subset from an expanded stack; singletons become unstacked. Hidden members are never implicitly selected.',{'action':{'enum':['group','split','unstack','remove','expand','collapse','toggle','top','up','down']},'photo_ids':array(ID,60),'expected_revision':REV,'collection_id':ID,'active_id':ID},['action','photo_ids','expected_revision'])
tool('get_collection','Read one collection and its bounded ancestor path.',{'collection_id':ID},['collection_id'],True)
tool('save_collection','Create or edit a regular/smart collection or set; parent_id moves it, null moves to root. Updates require its revision; originals are unchanged.',{'collection_id':ID,'expected_revision':REV,'name':string(120),'kind':{'enum':['regular','smart','set']},'parent_id':OPTIONAL_ID,'photo_ids':array(ID,60),'rules':FILTER_SCHEMA,'match':{'enum':['all','any']}},['name','kind'])
tool('collection_membership','Add/remove photos in a regular or Quick Collection atomically; never removes originals or catalog photos.',{'collection_id':ID,'expected_revision':REV,'photo_ids':array(ID,60),'action':{'enum':['add','remove']}},['collection_id','expected_revision','photo_ids','action'])
tool('delete_collection','Delete a collection or an entire set subtree and its memberships; preserve all photos and originals. Ancestor revisions cover descendant changes.',{'collection_id':ID,'expected_revision':REV},['collection_id','expected_revision'])
tool('duplicate_collection','Atomically duplicate a collection or a subtree of up to 1000 collections, preserving rules and memberships without copying originals.',{'collection_id':ID,'expected_revision':REV,'name':string(120)},['collection_id','expected_revision','name'])
tool('collection_state','Read the durable Quick and target collections; optionally query target membership for a bounded visible page.',{'photo_ids':array(ID,60)},read=True)
tool('set_target_collection','Choose a regular target collection; null resets to Quick. Requires the current state revision.',{'collection_id':OPTIONAL_ID,'expected_revision':REV},['expected_revision'])
tool('target_membership','Add/remove photos only if the captured target and collection revisions still match.',{'collection_id':ID,'expected_state_revision':REV,'expected_revision':REV,'photo_ids':array(ID,60),'action':{'enum':['add','remove']}},['collection_id','expected_state_revision','expected_revision','photo_ids','action'])
tool('quick_collection','Clear Quick or atomically save it as a regular collection, optionally clearing afterward.',{'expected_revision':REV,'action':{'enum':['clear','save']},'name':string(120),'clear_after':BOOL,'parent_id':OPTIONAL_ID},['expected_revision','action'])
tool('edit_metadata','Atomically update catalog-only descriptive metadata. Keywords replace the current set. Recipe revisions remain unchanged.',{'targets':array(obj({'photo_id':ID,'expected_metadata_revision':REV},['photo_id','expected_metadata_revision']),60),'patch':obj({'copy_name':{'type':'string','maxLength':120},'title':{'type':'string','maxLength':500},'caption':{'type':'string','maxLength':5000},'copyright':{'type':'string','maxLength':500},'color_label':{'enum':list(COLORS)},'keywords':{'type':'array','items':string(120),'maxItems':100}})},['targets','patch'])
TOOLS['edit_metadata']['inputSchema']['properties']['patch']['properties']['keywords']['items']=string(4096)
COPY_TARGET={'photo_id':ID,'expected_revision':REV,'expected_metadata_revision':REV}
COPY_REMOVE={**COPY_TARGET,'expected_source_revision':REV}
tool('create_virtual_copies','Atomically create up to 60 independent catalog variants sharing their original files. Optionally add to a captured regular/Quick collection.',{'targets':array(obj(COPY_TARGET,COPY_TARGET),60),'collection_id':ID,'expected_collection_revision':REV},['targets'])
tool('remove_virtual_copies','Remove only virtual copies and their private history/memberships; preserve originals, shared snapshots and queued export snapshots.',{'targets':array(obj(COPY_REMOVE,COPY_REMOVE),60)},['targets'])
TOOLS['remove_virtual_copies']['annotations']['destructiveHint']=True
tool('set_copy_as_master','Promote a virtual copy and demote the old master without changing IDs, recipes, collections or originals.',COPY_REMOVE,COPY_REMOVE)
tool('get_photo','Read recipe, metadata and current revision before editing.',{'photo_id':ID},['photo_id'],True)
tool('edit_photo','Merge a partial recipe using expected_revision; stale revisions fail without changes.',{'photo_id':ID,'expected_revision':REV,'patch':PATCH},['photo_id','expected_revision','patch'])
tool('undo_photo','Undo the last edit only if the revision is current.',{'photo_id':ID,'expected_revision':REV},['photo_id','expected_revision'])
tool('rate_photo','Set rating 0–5 and/or pick flag (-1 reject, 0 neutral, 1 pick).',{'photo_id':ID,'rating':integer(0,5),'flag':{'enum':[-1,0,1]}},['photo_id'])
tool('rate_photos','Atomically set ratings and/or pick flags on a bounded selection; leaves recipes and metadata revisions unchanged.',{'photo_ids':array(ID,60),'rating':integer(0,5),'flag':{'enum':[-1,0,1]}},['photo_ids'])
tool('preview_photo','Render an sRGB preview or full-resolution viewport. Set include_before=false to skip baseline processing; max_edge bounds fitted previews only.',{'photo_id':ID,'client_id':string(128),'generation':integer(),'include_before':BOOL,'max_edge':integer(128,1680),'detail':obj({'cx':{'type':'number','minimum':0,'maximum':1},'cy':{'type':'number','minimum':0,'maximum':1},'width':integer(1,2048),'height':integer(1,1536)}),'display':obj({'gamut':BOOL,'proof_path':PATH,'proof_sha':string(64)})},['photo_id'],True)
tool('cancel_preview','Invalidate older preview generations for one client and stop its older running preview/thumbnail. Never cancels exports or another client.',{'client_id':string(128),'generation':integer()},['client_id','generation'])
tool('photo_summaries','Read existing photo summaries for at most 60 IDs without recipe or EXIF payloads.',{'photo_ids':array(ID,60)},['photo_ids'],True)
tool('thumbnail','Create/read a source thumbnail (default) or a developed recipe-aware 320-pixel thumbnail.',{'photo_id':ID,'kind':{'enum':['source','developed']},'client_id':string(128),'generation':integer()},['photo_id'],True)
tool('cached_thumbnails','Read completed source (default) or developed thumbnail paths for up to 60 photos without image workers. Developed entries include recipe revisions.',{'photo_ids':array(ID,60),'kind':{'enum':['source','developed']}},['photo_ids'],True)
tool('enqueue_exports','Durably enqueue immutable recipe snapshots. Reusing request_key with the same arguments returns original jobs; different arguments fail.',{'photo_ids':array(ID),'destination':PATH,'format':{'enum':['tiff16','jpeg']},'options':obj({'space':{'enum':['srgb','adobe','p3','prophoto']},'max_edge':integer(0,16000),'quality':integer(1,100),'output_sharpen':{'type':'number','minimum':0,'maximum':150},'name':string(120),'priority':integer(0,9)}),'request_key':string(128)},['photo_ids','destination','format','request_key'])
tool('get_job','Read a specific durable export receipt, including its recipe snapshot.',{'job_id':ID},['job_id'],True)
tool('list_jobs','Read the latest 60 export jobs and aggregate queue counts.',read=True)
tool('queue_control','Pause after the current export, resume, cancel, or retry failed/interrupted exports. Cancelled exports require explicit retry_cancelled.',{'action':{'enum':['pause','resume','cancel','retry','retry_cancelled']},'job_id':ID},['action'])
tool('save_version','Save a named recipe snapshot shared by all variants of this source.',{'photo_id':ID,'name':string(120)},['photo_id','name'])
tool('list_versions','List up to 100 named snapshots shared by this photo family.',{'photo_id':ID},['photo_id'],True)
tool('restore_version','Restore a version with conflict detection and undo history.',{'photo_id':ID,'version_id':ID,'expected_revision':REV},['photo_id','version_id','expected_revision'])
tool('sync_photos','Copy selected parameter groups atomically; every target requires its current revision.',{'source_id':ID,'targets':array(obj({'photo_id':ID,'expected_revision':REV},['photo_id','expected_revision']),60),'groups':array({'enum':list(SYNC_GROUPS)},10)},['source_id','targets','groups'])
tool('index_library','Hash originals read-only, detect duplicates, missing files and EXIF bursts.')
tool('relink_photo','Relink a missing original; checks a known content fingerprint.',{'photo_id':ID,'path':PATH},['photo_id','path'])
tool('backup_catalog','Write a new SQLite backup and asset directory; never overwrite.',{'path':PATH},['path'])
tool('restore_catalog','Restore a backup to a new empty catalog directory; exports remain interrupted.',{'path':PATH,'destination':PATH},['path','destination'])
tool('import_asset','Validate a LUT, ICC proof profile, or camera calibration profile.',{'path':PATH,'kind':{'enum':['lut','icc','profile']}},['path','kind'])
tool('save_recipe','Save a portable recipe bundle to a new file.',{'photo_id':ID,'path':PATH},['photo_id','path'])
tool('load_recipe','Load a recipe bundle with conflict detection.',{'photo_id':ID,'path':PATH,'expected_revision':REV},['photo_id','path','expected_revision'])
RECT={'type':'array','items':{'type':'number','minimum':0,'maximum':1},'minItems':4,'maxItems':4}
tool('calibrate_camera','Fit a camera-bound 24-patch profile against an explicit reference. Result is not independent Nikon accuracy evidence.',{'photo_id':ID,'reference':PATH,'source_rect':RECT,'reference_rect':RECT,'name':string(120),'lighting':string(256)},['photo_id','reference','source_rect','reference_rect','name','lighting'])
tool('settings','Read or update memory budget and compute backend: auto (Metal with CPU fallback), cpu, or metal (GPU failures reported). Includes last processing timings.',{'budget_mb':integer(256,32768),'compute_backend':{'enum':['auto','cpu','metal']}})
