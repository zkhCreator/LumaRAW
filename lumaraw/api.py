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
PATCH={'type':'object','maxProperties':64}
TOOLS={}
def tool(name,description,properties=None,required=(),read=False):
    TOOLS[name]={'name':name,'description':description,'inputSchema':obj(properties,required),
        'annotations':{'readOnlyHint':read,'destructiveHint':False,'idempotentHint':read,'openWorldHint':False}}
tool('status','Service version, catalog location, queue and processing state.',read=True)
tool('recipe_schema','Supported recipe ranges, defaults, presets and sync groups.',read=True)
tool('import_photos','Reference explicit local photos or directories; never copy or modify originals.',{'paths':array(PATH)},['paths'])
tool('list_photos','Read at most 60 summaries with SQL filters, collection membership and stable sorting.',{'offset':integer(),'mode':{'enum':['all','stars','keepers','rejects','missing','duplicates']},'search':{'type':'string','maxLength':200},'filters':FILTER_SCHEMA,'collection_id':ID,'sort':{'enum':list(SORTS)},'descending':BOOL},read=True)
tool('list_collections','Read at most 60 regular or smart collections.',{'offset':integer()},read=True)
tool('save_collection','Create or edit a regular/smart collection. Updates require its revision; originals are unchanged.',{'collection_id':ID,'expected_revision':REV,'name':string(120),'kind':{'enum':['regular','smart']},'rules':FILTER_SCHEMA,'match':{'enum':['all','any']}},['name','kind'])
tool('collection_membership','Add/remove photos in a regular collection atomically; never removes originals or catalog photos.',{'collection_id':ID,'expected_revision':REV,'photo_ids':array(ID,60),'action':{'enum':['add','remove']}},['collection_id','expected_revision','photo_ids','action'])
tool('delete_collection','Delete only a collection and its membership; preserve all catalog photos and originals.',{'collection_id':ID,'expected_revision':REV},['collection_id','expected_revision'])
tool('edit_metadata','Atomically update catalog-only descriptive metadata. Keywords replace the current set. Recipe revisions remain unchanged.',{'targets':array(obj({'photo_id':ID,'expected_metadata_revision':REV},['photo_id','expected_metadata_revision']),60),'patch':obj({'title':{'type':'string','maxLength':500},'caption':{'type':'string','maxLength':5000},'copyright':{'type':'string','maxLength':500},'color_label':{'enum':list(COLORS)},'keywords':{'type':'array','items':string(120),'maxItems':100}})},['targets','patch'])
tool('get_photo','Read recipe, metadata and current revision before editing.',{'photo_id':ID},['photo_id'],True)
tool('edit_photo','Merge a partial recipe using expected_revision; stale revisions fail without changes.',{'photo_id':ID,'expected_revision':REV,'patch':PATCH},['photo_id','expected_revision','patch'])
tool('undo_photo','Undo the last edit only if the revision is current.',{'photo_id':ID,'expected_revision':REV},['photo_id','expected_revision'])
tool('rate_photo','Set rating 0–5 and/or pick flag (-1 reject, 0 neutral, 1 pick).',{'photo_id':ID,'rating':integer(0,5),'flag':{'enum':[-1,0,1]}},['photo_id'])
tool('rate_photos','Atomically set ratings and/or pick flags on a bounded selection; leaves recipes and metadata revisions unchanged.',{'photo_ids':array(ID,60),'rating':integer(0,5),'flag':{'enum':[-1,0,1]}},['photo_ids'])
tool('preview_photo','Render an sRGB preview or full-resolution viewport. Set include_before=false to skip baseline processing; max_edge bounds fitted previews only.',{'photo_id':ID,'client_id':string(128),'generation':integer(),'include_before':BOOL,'max_edge':integer(128,1680),'detail':obj({'cx':{'type':'number','minimum':0,'maximum':1},'cy':{'type':'number','minimum':0,'maximum':1},'width':integer(1,2048),'height':integer(1,1536)}),'display':obj({'gamut':BOOL,'proof_path':PATH,'proof_sha':string(64)})},['photo_id'],True)
tool('cancel_preview','Invalidate older preview generations for one client and stop its older running preview. Never cancels exports or another client.',{'client_id':string(128),'generation':integer()},['client_id','generation'])
tool('photo_summaries','Read existing photo summaries for at most 60 IDs without recipe or EXIF payloads.',{'photo_ids':array(ID,60)},['photo_ids'],True)
tool('thumbnail','Create/read a thumbnail for a catalog photo.',{'photo_id':ID},['photo_id'],True)
tool('cached_thumbnails','Read completed thumbnail paths for up to 60 photos without starting image workers. Missing entries are omitted.',{'photo_ids':array(ID,60)},['photo_ids'],True)
tool('enqueue_exports','Durably enqueue immutable recipe snapshots. Reusing request_key with the same arguments returns original jobs; different arguments fail.',{'photo_ids':array(ID),'destination':PATH,'format':{'enum':['tiff16','jpeg']},'options':obj({'space':{'enum':['srgb','adobe','p3','prophoto']},'max_edge':integer(0,16000),'quality':integer(1,100),'output_sharpen':{'type':'number','minimum':0,'maximum':150},'name':string(120),'priority':integer(0,9)}),'request_key':string(128)},['photo_ids','destination','format','request_key'])
tool('get_job','Read a specific durable export receipt, including its recipe snapshot.',{'job_id':ID},['job_id'],True)
tool('list_jobs','Read the latest 60 export jobs and aggregate queue counts.',read=True)
tool('queue_control','Pause after the current export, resume, cancel, or retry failed/interrupted exports. Cancelled exports require explicit retry_cancelled.',{'action':{'enum':['pause','resume','cancel','retry','retry_cancelled']},'job_id':ID},['action'])
tool('save_version','Save a named recipe snapshot.',{'photo_id':ID,'name':string(120)},['photo_id','name'])
tool('list_versions','List up to 100 saved edit versions.',{'photo_id':ID},['photo_id'],True)
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
