"""Selective metadata presets and atomic additive keyword application.

Inputs: explicitly checked values, immutable preset tokens and bounded captured
photo metadata/rating states. Outputs: shared/local presets and catalog metadata.
Unchecked fields, recipes, original files and queued exports survive. Keywords add
to existing assignments; empty text clears a checked scalar field. Saving presets
never creates vocabulary. Shared storage locks before catalog storage. No pixels,
sidecar writes, native paths, Adobe preset-file execution or implicit conflict retry.
"""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid

from .develop_presets import title
from . import iptc
from .keywords import Keywords
from .keyword_sets import remember, validate_slots
from .organization import COLORS, folded
from .preset_paths import preset_root

BASIC_FIELDS = (
    {'key':'title','label':'Title','group':'IPTC Status','kind':'text','limit':500},
    {'key':'caption','label':'Caption','group':'Basic Info','kind':'multiline','limit':5000},
    {'key':'copyright','label':'Copyright Notice','group':'IPTC Copyright','kind':'text','limit':500},
    {'key':'rating','label':'Rating','group':'Basic Info','kind':'rating','limit':5},
    {'key':'color_label','label':'Color Label','group':'Basic Info','kind':'label','limit':0},
    {'key':'keywords','label':'Keywords (Append)','group':'Keywords','kind':'keywords','limit':4096},
)
FORM_FIELDS = [*BASIC_FIELDS,*[{**field,'key':'iptc.'+key} for key,field in iptc.FIELDS.items()]]
PATCH_SCHEMA = {'type':'object','additionalProperties':False,'minProperties':1,'properties':{
    'title':{'type':'string','maxLength':500},'caption':{'type':'string','maxLength':5000},
    'copyright':{'type':'string','maxLength':500},'rating':{'type':'integer','minimum':0,'maximum':5},
    'color_label':{'enum':list(COLORS)},'iptc':iptc.SCHEMA,
    'keywords':{'type':'array','maxItems':100,'items':{'type':'string','minLength':1,'maxLength':4096}}}}


def validate_patch(patch):
    import jsonschema
    jsonschema.validate(patch,PATCH_SCHEMA)
    iptc.validate(patch.get('iptc',{}))
    for key in ('title','caption','copyright'):
        if key in patch:
            from .export_metadata import text
            text(patch[key])
    # Validate portable slot text without resolving catalog identities or creating
    # tags. Legacy literal labels are resolved at application, under the token.
    result={**patch}
    if 'keywords' in patch:
        result['keywords']=[validate_slots([value]+['']*8)[0] for value in patch['keywords']]
        if any(not value for value in result['keywords']):
            raise ValueError('Preset keywords cannot be blank')
    if not field_count(result):
        raise ValueError('Select at least one metadata field')
    if len(json.dumps(result).encode())>512*1024:
        raise ValueError('Metadata preset exceeds 512 KiB')
    return result


def field_count(patch):
    return len(set(patch)-{'iptc'})+len(patch.get('iptc',{}))


def create_tables(db):
    db.execute('CREATE TABLE metadata_preset_state(id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER NOT NULL)')
    db.execute('INSERT INTO metadata_preset_state VALUES(1,0)')
    db.execute('CREATE TABLE metadata_presets(id TEXT PRIMARY KEY,name TEXT NOT NULL,normalized TEXT NOT NULL UNIQUE,'
               'patch TEXT NOT NULL,field_count INTEGER NOT NULL)')
    db.execute('CREATE INDEX metadata_preset_names ON metadata_presets(normalized,id)')


def migrate(db):
    if db.execute('PRAGMA user_version').fetchone()[0]>=18:
        return
    db.execute('BEGIN IMMEDIATE')
    try:
        create_tables(db)
        db.execute('PRAGMA user_version=18')
        db.commit()
    except BaseException:
        db.rollback()
        raise


class MetadataPresets:
    def __init__(self,service,root=None):
        self.service=service
        self.root=(Path(root) if root is not None else preset_root())/'metadata'

    @contextmanager
    def transaction(self):
        self.root.mkdir(parents=True,exist_ok=True)
        shared=sqlite3.connect(self.root/'presets.sqlite',timeout=5)
        shared.row_factory=sqlite3.Row
        try:
            shared.execute('BEGIN IMMEDIATE')
            version=shared.execute('PRAGMA user_version').fetchone()[0]
            if version>1:
                raise ValueError('Metadata presets were created by a newer engine')
            if version==0:
                create_tables(shared)
                shared.execute('CREATE TABLE metadata_storage(id INTEGER PRIMARY KEY CHECK(id=1),catalog INTEGER NOT NULL)')
                shared.execute('INSERT INTO metadata_storage VALUES(1,0)')
                shared.execute('PRAGMA user_version=1')
            with self.service.catalog() as catalog,catalog.db:
                catalog.db.execute('BEGIN IMMEDIATE')
                local=bool(shared.execute('SELECT catalog FROM metadata_storage').fetchone()[0])
                yield shared,catalog,catalog.db if local else shared,local
            shared.commit()
        except BaseException:
            shared.rollback()
            raise
        finally:
            shared.close()

    def token(self,shared,catalog):
        state=[str(catalog.root),shared.execute('SELECT revision FROM metadata_preset_state').fetchone()[0],
               catalog.db.execute('SELECT revision FROM metadata_preset_state').fetchone()[0],
               shared.execute('SELECT catalog FROM metadata_storage').fetchone()[0],Keywords(catalog).revision()]
        return hashlib.sha256(json.dumps(state).encode()).hexdigest()

    def page(self,shared,catalog,db,local,params):
        query=folded(params.get('search',''))
        total=db.execute('SELECT COUNT(*) FROM metadata_presets WHERE instr(normalized,?)>0',(query,)).fetchone()[0]
        offset=min(params.get('offset',0),max(0,(total-1)//30*30))
        rows=[dict(row) for row in db.execute('SELECT id,name,field_count FROM metadata_presets '
              'WHERE instr(normalized,?)>0 ORDER BY normalized,id LIMIT 30 OFFSET ?',(query,offset))]
        return {'presets':rows,'total':total,'offset':offset,'page_size':30,'fields':FORM_FIELDS,
                'revision':self.token(shared,catalog),'store_with_catalog':local}

    def row(self,db,id_):
        row=db.execute('SELECT * FROM metadata_presets WHERE id=?',(id_,)).fetchone()
        if row is None:
            raise ValueError('Metadata preset does not exist')
        return dict(row)

    @staticmethod
    def bump(db):
        db.execute('UPDATE metadata_preset_state SET revision=revision+1')

    def save(self,db,params):
        patch=validate_patch(params['patch'])
        name=title(params['name'])
        id_=params.get('preset_id')
        if id_:
            self.row(db,id_)
        duplicate=db.execute('SELECT id FROM metadata_presets WHERE normalized=? AND id!=?',(folded(name),id_ or '')).fetchone()
        if duplicate:
            raise ValueError('Metadata preset name already exists; choose another name')
        id_=id_ or str(uuid.uuid4())
        db.execute('INSERT INTO metadata_presets VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET '
                   'name=excluded.name,normalized=excluded.normalized,patch=excluded.patch,field_count=excluded.field_count',
                   (id_,name,folded(name),json.dumps(patch,ensure_ascii=False),field_count(patch)))
        self.bump(db)
        return id_

    @staticmethod
    def apply(catalog,patch,targets,keyword_ids=None):
        tags=Keywords(catalog)
        ids=tags.check_targets(targets)
        if not 1<=len(ids)<=60:
            raise ValueError('Choose between one and sixty photos')
        columns=set(patch)-{'keywords','iptc'}
        # Resolve at the captured vocabulary revision, then validate every target
        # before writing any photo. Newly created vocabulary rolls back on failure.
        # Import resolves its captured additions once for the whole transaction.
        additions=(list(dict.fromkeys(tags.resolve(value) for value in patch.get('keywords',[])))
                   if keyword_ids is None else keyword_ids)
        changes=[]
        # One bounded batch can contain repeated large IPTC values. Validate each
        # distinct merged value once, retaining at most sixty exact JSON keys.
        # Scalar-only presets never parse unrelated descriptive JSON.
        merged_iptc={}
        projection='id,title,caption,copyright,rating,color_label'+(',iptc' if patch.get('iptc') else '')
        for target in targets:
            row=catalog.db.execute('SELECT '+projection+' FROM photos WHERE id=?',
                                   (target['photo_id'],)).fetchone()
            if 'rating' in patch and target.get('expected_rating')!=row['rating']:
                raise ValueError('Rating conflict; refresh the photos before applying')
            fields={key:patch[key] for key in columns if patch[key]!=row[key]}
            if patch.get('iptc'):
                raw=row['iptc']
                if raw not in merged_iptc:
                    current=json.loads(raw)
                    merged=iptc.validate({**current,**patch['iptc']})
                    merged_iptc[raw]=json.dumps(merged,ensure_ascii=False) if merged!=current else None
                if merged_iptc[raw] is not None:
                    fields['iptc']=merged_iptc[raw]
            existing={r[0] for r in catalog.db.execute('SELECT keyword_id FROM keyword_photos WHERE photo_id=?',(row['id'],))} if additions else set()
            if len(existing|set(additions))>100:
                raise ValueError('A photo cannot have more than 100 directly assigned keywords')
            new=[id_ for id_ in additions if id_ not in existing]
            changes.append((row['id'],fields,new))
        updated=[]
        used=[]
        for photo_id,fields,new in changes:
            if not fields and not new:
                continue
            if fields:
                catalog.db.execute('UPDATE photos SET '+','.join(key+'=?' for key in fields)+' WHERE id=?',[*fields.values(),photo_id])
            catalog.db.executemany('INSERT INTO keyword_photos VALUES(?,?)',((photo_id,id_) for id_ in new))
            catalog.db.execute('UPDATE photos SET metadata_revision=metadata_revision+1 WHERE id=?',(photo_id,))
            updated.append(photo_id)
            used.extend(new)
        remember(catalog.db,used)
        return updated

    def dispatch(self,method,params):
        with self.transaction() as (shared,catalog,db,local):
            if method!='list_metadata_presets' and params['expected_revision']!=self.token(shared,catalog):
                raise ValueError('Metadata presets, storage or keywords changed; refresh before continuing')
            result={}
            if method=='get_metadata_preset':
                row=self.row(db,params['preset_id'])
                row['patch']=json.loads(row['patch'])
                return {'preset':row,'fields':FORM_FIELDS,'revision':self.token(shared,catalog)}
            if method=='save_metadata_preset':
                result['preset_id']=self.save(db,params)
            elif method=='metadata_preset_action':
                action=params['action']
                allowed={'storage':{'store_with_catalog'},'delete':{'preset_id'},'rename':{'preset_id','name'},'duplicate':{'preset_id','name'}}
                if set(params)-{'action','expected_revision'}!=allowed[action]:
                    raise ValueError('Provide exactly the fields required for this metadata preset action')
                if action=='storage':
                    shared.execute('UPDATE metadata_storage SET catalog=?',(int(params['store_with_catalog']),))
                    self.bump(shared)
                    local=params['store_with_catalog'];db=catalog.db if local else shared
                else:
                    row=self.row(db,params['preset_id'])
                    if action=='delete':
                        db.execute('DELETE FROM metadata_presets WHERE id=?',(row['id'],))
                        self.bump(db)
                    else:
                        result['preset_id']=self.save(db,{'preset_id':row['id'] if action=='rename' else None,
                            'name':params['name'],'patch':json.loads(row['patch'])})
            elif method=='apply_metadata_preset':
                row=self.row(db,params['preset_id'])
                result={'updated':self.apply(catalog,validate_patch(json.loads(row['patch'])),params['targets']),
                        'targeted':len(params['targets']),'preset_id':row['id'],'preset_name':row['name']}
            return {**self.page(shared,catalog,db,local,params if method=='list_metadata_presets' else {}),**result}
