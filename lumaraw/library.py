"""Read-only source indexing and portable library artifacts.

Inputs: catalog references and explicitly selected assets/backups. Outputs: exact
hash duplicate groups, EXIF burst groups, validated recipe bundles and new catalogs.
Original images are never moved/deleted. Backup restore creates a new catalog and
never replaces the active database. Hashes stream in 1 MiB blocks with cancellation.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import time
import tempfile
from urllib.parse import quote
import zipfile
from .model import Recipe
from .capture_time import read_capture_time


def hash_file(path,cancelled=lambda:False):
    p=Path(path);before=p.stat();h=hashlib.sha256()
    with p.open('rb') as f:
        while chunk:=f.read(1024*1024):
            if cancelled(): raise InterruptedError('Cancelled')
            h.update(chunk)
    after=p.stat()
    if before.st_size!=after.st_size or before.st_mtime_ns!=after.st_mtime_ns:
        raise OSError('The original changed while reading; retry the operation')
    return h.hexdigest()


def import_asset(path,root,kind):
    path=Path(path).resolve(strict=True)
    caps={'lut':32*1024**2,'icc':8*1024**2,'profile':32*1024}
    if kind not in caps or path.stat().st_size>caps[kind]: raise ValueError('Unsupported file type or size')
    data=path.read_bytes();sha=hashlib.sha256(data).hexdigest()
    if kind=='profile':
        profile=json.loads(data);Recipe(camera_profile=profile);return profile
    if kind=='lut':
        from .color import read_cube
        read_cube(str(path),sha)
    else:
        from PIL import ImageCms
        ImageCms.ImageCmsProfile(io.BytesIO(data))
    dest=Path(root)/'assets';dest.mkdir(exist_ok=True)
    target=dest/(sha+('.cube' if kind=='lut' else '.icc'))
    if not target.exists():
        with target.open('xb') as f: f.write(data)
    return {'path':str(target),'sha256':sha,'title':path.name}


def save_recipe(path,recipe):
    """Portable zip with one fixed JSON name and an optional verified LUT asset."""
    path=Path(path)
    payload=recipe.dict();asset=None
    if recipe.lut:
        p=Path(recipe.lut['path']);asset=p.read_bytes()
        if len(asset)>32*1024**2 or hashlib.sha256(asset).hexdigest()!=recipe.lut['sha256']:
            raise ValueError('LUT has changed or is too large; import it again')
        payload['lut']={**recipe.lut,'path':'lut.cube'}
    with path.open('xb') as stream:
        with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('recipe.json',json.dumps(payload,ensure_ascii=False))
            if asset is not None: archive.writestr('lut.cube',asset)


def load_recipe(path,root):
    with zipfile.ZipFile(path) as archive:
        if set(archive.namelist())-{'recipe.json','lut.cube'} or len(archive.namelist())!=len(set(archive.namelist())):
            raise ValueError('Recipe bundle contains unexpected files')
        if sum(i.file_size for i in archive.infolist())>34*1024**2 or archive.getinfo('recipe.json').file_size>256*1024:
            raise ValueError('Recipe bundle is too large')
        payload=json.loads(archive.read('recipe.json'))
        recipe=Recipe.parse(payload)
        if recipe.lut:
            data=archive.read('lut.cube');sha=hashlib.sha256(data).hexdigest()
            if sha!=recipe.lut['sha256']: raise ValueError('LUT checksum verification failed')
            folder=Path(root)/'assets';folder.mkdir(exist_ok=True)
            dest=folder/(sha+'.cube')
            if not dest.exists():
                with dest.open('xb') as f: f.write(data)
            payload['lut']={**recipe.lut,'path':str(dest)}
    return Recipe.parse(payload)


def backup_catalog(catalog,path):
    path=Path(path)
    companion=path.with_suffix(path.suffix+'.assets')
    if path.exists() or companion.exists():raise FileExistsError('Backup or companion directory already exists; choose a new name')
    created_assets=False
    with tempfile.TemporaryDirectory(prefix='.lumaraw-backup-',dir=path.parent) as scratch:
        database=Path(scratch)/'catalog.sqlite';target=sqlite3.connect(database)
        try: catalog.db.backup(target)
        finally: target.close()
        try:
            assets=catalog.root/'assets'
            if assets.exists():
                companion.mkdir();created_assets=True
                shutil.copytree(assets,companion,dirs_exist_ok=True)
            # Publish only a complete database, and never replace an existing file.
            os.link(database,path)
        except Exception:
            if created_assets:shutil.rmtree(companion)
            raise
    return str(path)


def restore_catalog(path,destination):
    path=Path(path).resolve(strict=True);dest=Path(destination).resolve()
    if dest.exists() and any(dest.iterdir()): raise ValueError('Choose a new empty folder to avoid overwriting an existing catalog')
    src=sqlite3.connect('file:'+quote(str(path))+'?mode=ro',uri=True)
    try:
        if src.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise ValueError('Backup integrity check failed')
        names={r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'photos','history','jobs'}<=names: raise ValueError('Not a LumaRAW catalog backup')
        for (payload,) in src.execute('SELECT recipe FROM photos'): Recipe.parse(json.loads(payload))
        dest.mkdir(parents=True,exist_ok=True);target=sqlite3.connect(dest/'catalog.sqlite')
        try: src.backup(target)
        finally: target.close()
    finally: src.close()
    assets=path.with_suffix(path.suffix+'.assets')
    if assets.is_dir(): shutil.copytree(assets,dest/'assets')
    from .catalog import Catalog
    catalog=Catalog(dest)
    try:
        # Rebind assets by their immutable content address, including named versions.
        for table,key,column in [('photos','id','recipe'),('photos','id','history_base_recipe'),('photo_before','photo_id','recipe'),('history','id','recipe'),('versions','id','recipe'),('jobs','id','recipe'),('develop_presets','id','patch'),('import_processing','plan_id','develop_patch')]:
            for id_,payload in catalog.db.execute(f'SELECT {key},{column} FROM {table} WHERE {column} IS NOT NULL'):
                recipe=json.loads(payload)
                if recipe.get('lut'):
                    candidate=dest/'assets'/(recipe['lut']['sha256']+'.cube')
                    if candidate.exists(): recipe['lut']['path']=str(candidate)
                    catalog.db.execute(f'UPDATE {table} SET {column}=? WHERE {key}=?',(json.dumps(recipe),id_))
        # Never start restored exports automatically against old destinations.
        catalog.db.execute("UPDATE jobs SET state='interrupted',error='Restored from backup; check the destination before retrying' WHERE state IN ('running','pending')")
        catalog.db.commit()
    finally: catalog.close()
    return dest


def index_library(catalog,cancelled=lambda:False,progress=lambda n:None):
    total=0
    for photo in catalog.db.execute('SELECT source_id,path,mtime,bytes,sha256 FROM photos WHERE is_virtual=0 ORDER BY id'):
        if cancelled(): break
        id_,path,mtime,size,sha=photo
        p=Path(path)
        try:
            stat=p.stat();clock=read_capture_time(p)
            if not sha or stat.st_mtime_ns!=mtime or stat.st_size!=size:
                sha=hash_file(p,cancelled)
            catalog.db.execute('UPDATE photos SET sha256=?,taken=?,taken_us=?,taken_submicro=?,capture_clock=?,camera=?,mtime=?,bytes=?,missing=0 WHERE source_id=?',
                               (sha,clock['taken'],clock['taken_us'],clock['taken_submicro'],clock['capture_clock'],clock['camera'],stat.st_mtime_ns,stat.st_size,id_))
        except InterruptedError: break
        except OSError:
            catalog.db.execute('UPDATE photos SET missing=1 WHERE source_id=?',(id_,))
        total+=1
        if total%25==0: catalog.db.commit();progress(total)
    catalog.db.commit()
    previous=None;group=0
    for id_,camera,taken in catalog.db.execute('SELECT source_id,camera,taken FROM photos WHERE taken>0 AND is_virtual=0 ORDER BY camera,taken,id'):
        if cancelled(): break
        if previous is None or previous[0]!=camera or taken-previous[1]>2: group=id_
        catalog.db.execute('UPDATE photos SET burst=? WHERE source_id=?',(group,id_));previous=(camera,taken)
    catalog.db.commit();return {'indexed':total}
