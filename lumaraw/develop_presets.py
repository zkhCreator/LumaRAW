"""Partial Develop presets, bounded library pages and atomic photo application.

Inputs: selected recipe fields, captured preset/photo revisions and explicit
management actions. Outputs: shared or catalog-local presets and ordinary Develop
history. Unchecked fields, metadata, catalog orientation and queued jobs survive.
Shared storage locks precede catalog locks. LUT bytes stage outside either lock,
then all captured state is revalidated before mutation. No pixels, Adobe parameter
translation, inferred adjustments or platform directory conventions live here.
Presence is a separately selectable group; legacy preset patches remain partial.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unicodedata
import uuid

from .model import Recipe, PRESETS, SYNC_GROUPS
from .organization import folded
from .preset_paths import preset_root
from .develop_history import DevelopHistory

FIELDS = tuple(k for k in Recipe().dict() if k != 'version')
BASIC_FIELDS = ('exposure','temperature','tint','contrast','highlights','shadows','whites','blacks',
                'saturation','vibrance','texture','clarity','dehaze','curve_shadows','curve_midtones','curve_lights',
                'red_hue','red_sat','orange_hue','orange_sat','green_hue','green_sat',
                'blue_hue','blue_sat','monochrome')
PAGE = 30
PATCH_BYTES = 256 * 1024
LUT_BYTES = 32 * 1024 * 1024


def create_tables(db):
    db.execute('CREATE TABLE develop_preset_state(id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL)')
    db.execute('INSERT INTO develop_preset_state VALUES(1,0)')
    db.execute('CREATE TABLE develop_preset_groups(id TEXT PRIMARY KEY, name TEXT NOT NULL, '
               'normalized TEXT NOT NULL UNIQUE, visible INTEGER NOT NULL, builtin INTEGER NOT NULL)')
    db.execute('CREATE TABLE develop_presets(id TEXT PRIMARY KEY, name TEXT NOT NULL, normalized TEXT NOT NULL, '
               'group_id TEXT NOT NULL, patch TEXT NOT NULL, field_count INTEGER NOT NULL, '
               'favorite INTEGER NOT NULL, builtin INTEGER NOT NULL)')
    db.execute('CREATE INDEX develop_preset_group ON develop_presets(group_id,normalized,id)')
    db.execute('CREATE INDEX develop_preset_favorite ON develop_presets(favorite,normalized,id)')
    db.executemany('INSERT INTO develop_preset_groups VALUES(?,?,?,?,?)',
                   [('builtin','LumaRAW','lumaraw',1,1),('user','User Presets','user presets',1,0)])
    for index,(name,recipe) in enumerate(PRESETS.items()):
        patch={key:recipe.dict()[key] for key in BASIC_FIELDS}
        db.execute('INSERT INTO develop_presets VALUES(?,?,?,?,?,?,0,1)',
                   (f'builtin-{index}',name,folded(name),'builtin',json.dumps(patch),len(patch)))


def migrate(db):
    if db.execute('PRAGMA user_version').fetchone()[0] >= 16:
        return
    db.execute('BEGIN IMMEDIATE')
    try:
        create_tables(db)
        db.execute('PRAGMA user_version=16')
        db.commit()
    except BaseException:
        db.rollback()
        raise


def title(value):
    value=unicodedata.normalize('NFC',value.strip())
    if not value or len(value)>120 or any(ord(c)<32 for c in value):
        raise ValueError('Preset and group names must be 1–120 characters on one line')
    return value


def validate_patch(patch):
    if not isinstance(patch,dict) or not patch or set(patch)-set(FIELDS):
        raise ValueError('Select at least one supported Develop setting')
    Recipe.parse(patch)
    if len(json.dumps(patch,ensure_ascii=False).encode())>PATCH_BYTES:
        raise ValueError('Preset settings exceed the 256 KiB limit')
    return patch


def read_lut(path, destination=None):
    digest=hashlib.sha256()
    total=0
    with Path(path).open('rb') as source:
        before=os.fstat(source.fileno())
        if before.st_size>LUT_BYTES:
            raise ValueError('Preset LUT exceeds 32 MiB')
        while block:=source.read(1024*1024):
            total+=len(block)
            if total>LUT_BYTES:
                raise ValueError('Preset LUT exceeds 32 MiB')
            digest.update(block)
            if destination is not None:
                destination.write(block)
        after=os.fstat(source.fileno())
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns) or total!=before.st_size:
        raise ValueError('Preset LUT changed while reading')
    return digest.hexdigest()


def stage_lut(patch, root):
    """Copy immutable LUT assets outside SQL locks; never overwrite an existing file."""
    patch=json.loads(json.dumps(patch))
    if not patch.get('lut'):
        return patch
    lut=patch['lut']
    folder=Path(root)/'assets'
    folder.mkdir(parents=True,exist_ok=True)
    target=folder/(lut['sha256']+'.cube')
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(prefix='.preset-',dir=folder,delete=False) as output:
            temporary=Path(output.name)
            if read_lut(lut['path'],output)!=lut['sha256']:
                raise ValueError('Preset LUT checksum changed; import the asset again')
        try:
            os.link(temporary,target)
        except FileExistsError:
            if target.is_symlink() or read_lut(target)!=lut['sha256']:
                raise ValueError('Stored preset LUT failed checksum verification')
        patch['lut']={**lut,'path':str(target)}
        return patch
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class DevelopPresets:
    def __init__(self, service, root=None):
        self.service=service
        self.root=(Path(root) if root is not None else preset_root())/'develop'

    @contextmanager
    def transaction(self):
        self.root.mkdir(parents=True,exist_ok=True)
        shared=sqlite3.connect(self.root/'presets.sqlite',timeout=5)
        shared.row_factory=sqlite3.Row
        try:
            shared.execute('BEGIN IMMEDIATE')
            version=shared.execute('PRAGMA user_version').fetchone()[0]
            if version>1:
                raise ValueError('Develop preset storage was created by a newer engine')
            if version==0:
                create_tables(shared)
                shared.execute('CREATE TABLE develop_storage(id INTEGER PRIMARY KEY CHECK(id=1), catalog INTEGER NOT NULL)')
                shared.execute('INSERT INTO develop_storage VALUES(1,0)')
                shared.execute('PRAGMA user_version=1')
            with self.service.catalog() as catalog, catalog.db:
                catalog.db.execute('BEGIN IMMEDIATE')
                local=bool(shared.execute('SELECT catalog FROM develop_storage').fetchone()[0])
                yield shared,catalog,catalog.db if local else shared,local
            shared.commit()
        except BaseException:
            shared.rollback()
            raise
        finally:
            shared.close()

    def token(self, shared, catalog):
        values=[str(self.service.root),shared.execute('SELECT revision FROM develop_preset_state').fetchone()[0],
                catalog.db.execute('SELECT revision FROM develop_preset_state').fetchone()[0],
                shared.execute('SELECT catalog FROM develop_storage').fetchone()[0]]
        return hashlib.sha256(json.dumps(values).encode()).hexdigest()

    def check(self, shared, catalog, params):
        if params['expected_revision']!=self.token(shared,catalog):
            raise ValueError('Develop presets or storage changed; refresh before continuing')

    def row(self, db, id_):
        row=db.execute('SELECT p.*,g.name AS group_name,g.visible FROM develop_presets p '
                       'JOIN develop_preset_groups g ON g.id=p.group_id WHERE p.id=?',(id_,)).fetchone()
        if row is None:
            raise ValueError('Develop preset does not exist')
        return dict(row)

    def page(self, shared, catalog, db, local, params):
        clauses,values=[],[]
        if not params.get('include_hidden',False):
            clauses.append('g.visible=1')
        if params.get('favorites',False):
            clauses.append('p.favorite=1')
        if group:=params.get('group_id'):
            clauses.append('p.group_id=?');values.append(group)
        if query:=params.get('search',''):
            clauses.append('(instr(p.normalized,?)>0 OR instr(g.normalized,?)>0)')
            values.extend([folded(query)]*2)
        where=' WHERE '+' AND '.join(clauses) if clauses else ''
        source=' FROM develop_presets p JOIN develop_preset_groups g ON g.id=p.group_id'
        total=db.execute('SELECT COUNT(*)'+source+where,values).fetchone()[0]
        offset=min(params.get('offset',0),max(0,(total-1)//PAGE*PAGE))
        rows=[dict(row) for row in db.execute('SELECT p.id,p.name,p.group_id,p.field_count,p.favorite,p.builtin,'
            'g.name AS group_name,g.visible'+source+where+' ORDER BY g.normalized,p.normalized,p.id LIMIT ? OFFSET ?',
            [*values,PAGE,offset])]
        group_total=db.execute('SELECT COUNT(*) FROM develop_preset_groups').fetchone()[0]
        group_offset=min(params.get('group_offset',0),max(0,(group_total-1)//PAGE*PAGE))
        groups=[dict(row) for row in db.execute('SELECT id,name,visible,builtin FROM develop_preset_groups '
            'ORDER BY normalized,id LIMIT ? OFFSET ?',(PAGE,group_offset))]
        return {'presets':rows,'groups':groups,'total':total,'offset':offset,'page_size':PAGE,
                'group_total':group_total,'group_offset':group_offset,'revision':self.token(shared,catalog),
                'store_with_catalog':local,'fields':list(FIELDS),'field_groups':SYNC_GROUPS}

    def selected_patch(self, catalog, params):
        fields=params['fields']
        if not fields or len(set(fields))!=len(fields) or set(fields)-set(FIELDS):
            raise ValueError('Select distinct supported Develop settings')
        row=catalog.db.execute('SELECT recipe,revision FROM photos WHERE id=?',(params['photo_id'],)).fetchone()
        if row is None:
            raise ValueError('Source photo does not exist')
        if row['revision']!=params['expected_photo_revision']:
            raise ValueError('Source photo changed; reopen the preset editor')
        recipe=Recipe.parse(json.loads(row['recipe'])).dict()
        return validate_patch({key:recipe[key] for key in fields})

    def targets(self, catalog, params, patch):
        targets=params['targets']
        if not 1<=len(targets)<=60 or len({t['photo_id'] for t in targets})!=len(targets):
            raise ValueError('Choose between 1 and 60 distinct photos')
        changes=[]
        for target in targets:
            row=catalog.db.execute('SELECT id,recipe,revision,camera FROM photos WHERE id=?',(target['photo_id'],)).fetchone()
            if row is None:
                raise ValueError('Target photo does not exist')
            if row['revision']!=target['expected_revision']:
                raise ValueError('Preset application conflict; refresh the photos')
            recipe=Recipe.parse({**json.loads(row['recipe']),**patch})
            if profile:=patch.get('camera_profile'):
                if not row['camera'] or profile['camera']!=row['camera']:
                    raise ValueError('Preset camera profile is incompatible with a selected photo')
            changes.append((row,recipe.dict()))
        return changes

    def dispatch(self, method, params):
        # Asset I/O happens between two validation passes. Neither a changed
        # library/scope nor a changed source/target can commit after staging.
        staged=None
        if method in ('save_develop_preset','apply_develop_preset'):
            with self.transaction() as (shared,catalog,db,local):
                self.check(shared,catalog,params)
                if method=='save_develop_preset':
                    staged=self.selected_patch(catalog,params)
                    if params.get('preset_id') and self.row(db,params['preset_id'])['builtin']:
                        raise ValueError('Built-in presets cannot be overwritten')
                    destination=catalog.root if local else self.root
                else:
                    staged=validate_patch(json.loads(self.row(db,params['preset_id'])['patch']))
                    self.targets(catalog,params,staged)
                    destination=catalog.root
            staged=stage_lut(staged,destination)
        with self.transaction() as (shared,catalog,db,local):
            if method!='list_develop_presets':
                self.check(shared,catalog,params)
            if method=='get_develop_preset':
                row=self.row(db,params['preset_id'])
                row['patch']=json.loads(row['patch'])
                return {'preset':row,'revision':self.token(shared,catalog),'store_with_catalog':local}
            if method=='save_develop_preset':
                self.selected_patch(catalog,params)
                id_=self.save(db,params,staged)
                self.bump(db)
                return {'preset_id':id_,**self.page(shared,catalog,db,local,{})}
            if method=='apply_develop_preset':
                row=self.row(db,params['preset_id'])
                changes=self.targets(catalog,params,staged)
                updated=[]
                for photo,recipe in changes:
                    if DevelopHistory(catalog.db).edit(photo['id'],Recipe.parse(recipe),'Preset: '+row['name']):
                        updated.append(photo['id'])
                return {'updated':updated,'targeted':len(changes),'preset_id':row['id'],'preset_name':row['name'],
                        'revision':self.token(shared,catalog)}
            if method=='develop_preset_action':
                id_=self.action(shared,db,params)
                local=bool(shared.execute('SELECT catalog FROM develop_storage').fetchone()[0])
                db=catalog.db if local else shared
                return {'preset_id':id_,**self.page(shared,catalog,db,local,{})}
            return self.page(shared,catalog,db,local,params)

    @staticmethod
    def bump(db):
        db.execute('UPDATE develop_preset_state SET revision=revision+1')

    def group(self, db, name):
        name=title(name)
        row=db.execute('SELECT * FROM develop_preset_groups WHERE normalized=?',(folded(name),)).fetchone()
        if row:
            if row['builtin']:
                raise ValueError('Choose a custom preset group')
            return row['id']
        id_=str(uuid.uuid4())
        db.execute('INSERT INTO develop_preset_groups VALUES(?,?,?,?,0)',(id_,name,folded(name),1))
        return id_

    def save(self, db, params, patch):
        name=title(params['name'])
        group=self.group(db,params['group_name'])
        id_=params.get('preset_id')
        previous=self.row(db,id_) if id_ else None
        if previous and previous['builtin']:
            raise ValueError('Built-in presets cannot be overwritten')
        duplicates=db.execute('SELECT id,builtin FROM develop_presets WHERE group_id=? AND normalized=? AND id!=?',
                              (group,folded(name),id_ or '')).fetchall()
        policy=params.get('duplicate_policy','error')
        if duplicates and policy!='duplicate':
            if policy!='replace' or id_ is not None or len(duplicates)!=1 or duplicates[0]['builtin']:
                raise ValueError('Preset name already exists in this group; rename it or explicitly choose Duplicate or Replace')
            id_=duplicates[0]['id'];previous=self.row(db,id_)
        id_=id_ or str(uuid.uuid4())
        db.execute('INSERT INTO develop_presets VALUES(?,?,?,?,?,?,?,0) ON CONFLICT(id) DO UPDATE SET '
            'name=excluded.name,normalized=excluded.normalized,group_id=excluded.group_id,patch=excluded.patch,field_count=excluded.field_count',
            (id_,name,folded(name),group,json.dumps(validate_patch(patch)),len(patch),previous['favorite'] if previous else 0))
        return id_

    def action(self, shared, db, params):
        action=params['action']
        keys=set(params)-{'action','expected_revision'}
        allowed={'storage':{'store_with_catalog'},'group_visibility':{'group_id','visible'},
                 'group_rename':{'group_id','name'},'favorite':{'preset_id','favorite'},
                 'delete':{'preset_id'},'duplicate':{'preset_id','name','group_name'},
                 'rename':{'preset_id','name'},'move':{'preset_id','group_name'}}
        if keys!=allowed[action]:
            raise ValueError('Provide exactly the fields required for this preset action')
        if action=='storage':
            shared.execute('UPDATE develop_storage SET catalog=?',(int(params['store_with_catalog']),))
            self.bump(shared)
            return None
        if action.startswith('group_'):
            row=db.execute('SELECT * FROM develop_preset_groups WHERE id=?',(params['group_id'],)).fetchone()
            if row is None:
                raise ValueError('Preset group does not exist')
            if action=='group_visibility':
                db.execute('UPDATE develop_preset_groups SET visible=? WHERE id=?',(int(params['visible']),row['id']))
            else:
                if row['builtin']:
                    raise ValueError('The built-in preset group cannot be renamed')
                name=title(params['name'])
                if db.execute('SELECT 1 FROM develop_preset_groups WHERE normalized=? AND id!=?',(folded(name),row['id'])).fetchone():
                    raise ValueError('Preset group name already exists')
                db.execute('UPDATE develop_preset_groups SET name=?,normalized=? WHERE id=?',(name,folded(name),row['id']))
            self.bump(db)
            return None
        row=self.row(db,params['preset_id'])
        id_=row['id']
        if action=='favorite':
            db.execute('UPDATE develop_presets SET favorite=? WHERE id=?',(int(params['favorite']),id_))
        elif action=='duplicate':
            id_=self.save(db,{**params,'preset_id':None,'duplicate_policy':'duplicate'},json.loads(row['patch']))
        else:
            if row['builtin']:
                raise ValueError('Built-in presets cannot be renamed, moved or deleted')
            if action=='delete':
                db.execute('DELETE FROM develop_presets WHERE id=?',(id_,))
            else:
                self.save(db,{'preset_id':id_,'name':params.get('name',row['name']),
                    'group_name':params.get('group_name',row['group_name'])},json.loads(row['patch']))
        self.bump(db)
        return id_
