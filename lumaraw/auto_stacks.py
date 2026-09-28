"""Capture-time stack planning and atomic application for one explicit source.

Inputs: a folder or regular collection, duration and preview fingerprint. Outputs:
bounded preview examples, streamed groups and a revision-checked replacement.
Every source photo participates regardless of selection/filter/visibility. Unknown
clocks remain unstacked. No AI, original writes, pixel decoding or implicit retry.
Metadata refresh is separately paged at 60 physical sources, avoiding whole-library
hashing and letting native callers report progress or stop between pages.
"""
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
import os
from pathlib import Path

from .capture_time import read_capture_time
from .collections import Collections
from .stacks import Stacks


class AutoStacks:
    def __init__(self, catalog):
        self.catalog=catalog;self.db=catalog.db

    def source(self, folder=None, collection_id=None):
        if (folder is None)==(collection_id is None):
            raise ValueError('Choose exactly one folder or regular collection')
        if collection_id is not None:
            scope=Stacks(self.catalog).scope(collection_id,writable=True)
            collection=Collections(self.catalog).get(collection_id)
            return {'scope':scope,'folder':'','collection_id':collection_id,'name':collection['name'],
                    'where':'id IN (SELECT photo_id FROM collection_photos WHERE collection_id=?)','params':[collection_id]}
        path=str(Path(folder).expanduser().resolve())
        prefix=path.rstrip(os.sep)+os.sep
        return {'scope':'folder','folder':path,'collection_id':None,'name':Path(path).name or path,
                'where':'substr(path,1,?)=? AND instr(substr(path,?),?)=0',
                'params':[len(prefix),prefix,len(prefix)+1,os.sep]}

    def rows(self, source):
        return self.db.execute('SELECT id,source_id,path,taken_us,taken_submicro,capture_clock FROM photos WHERE '+
            source['where']+' ORDER BY taken_us,taken_submicro,id',source['params'])

    @staticmethod
    def duration(seconds):
        try:gap=Decimal(str(seconds))*1000000
        except InvalidOperation:raise ValueError('Invalid time between stacks') from None
        if not gap.is_finite() or not 0<=gap<=3600000000:
            raise ValueError('Time between stacks must be between zero and one hour')
        return gap

    @staticmethod
    def instant(row):
        if row['taken_us'] is None:return None
        if not row['taken_submicro']:return row['taken_us']
        with localcontext() as context:
            context.prec=600  # EXIF ASCII fields are capped at 512 bytes.
            return Decimal(row['taken_us'])+Decimal('0.'+row['taken_submicro'])

    @staticmethod
    def separated(current, previous, gap):
        if previous is None:return True
        if isinstance(current,int) and isinstance(previous,int):return current-previous>=gap
        with localcontext() as context:
            context.prec=600
            return current-previous>=gap

    def plan(self, source, gap):
        revision=Stacks(self.catalog).revision()
        digest=hashlib.sha256(json.dumps([source['scope'],source['folder'],str(gap.normalize()),revision]).encode())
        result={'photos':0,'known':0,'unknown':0,'stacks':0,'stacked_photos':0,'clock_types':{},'examples':[]}
        size=0;first=None;previous=None
        def finish():
            if size>=2:
                result['stacks']+=1;result['stacked_photos']+=size
                if len(result['examples'])<20:result['examples'].append({'top_id':first,'count':size})
        for row in self.rows(source):
            digest.update(json.dumps(tuple(row),ensure_ascii=False,separators=(',',':')).encode()+b'\n')
            result['photos']+=1
            current=self.instant(row)
            if current is None:
                result['unknown']+=1;continue
            result['known']+=1
            basis=row['capture_clock'];result['clock_types'][basis]=result['clock_types'].get(basis,0)+1
            if self.separated(current,previous,gap):
                finish();size=0;first=row['id']
            size+=1;previous=current
        finish()
        result['unstacked_photos']=result['photos']-result['stacked_photos']
        result['existing_stacks']=self.db.execute('SELECT count(*) FROM photo_stacks WHERE scope=? AND folder=?',
                                                 (source['scope'],source['folder'])).fetchone()[0]
        return {**result,'token':digest.hexdigest(),'stack_revision':revision,'source':source['name']}

    def preview(self, seconds, folder=None, collection_id=None):
        with self.db:
            self.db.execute('BEGIN')
            return self.plan(self.source(folder,collection_id),self.duration(seconds))

    def apply(self, seconds, token, folder=None, collection_id=None):
        gap=self.duration(seconds)
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            source=self.source(folder,collection_id);plan=self.plan(source,gap)
            if token!=plan['token']:
                raise ValueError('Auto-stack conflict; capture times, source membership or stacks changed. Preview again before applying')
            if not plan['known']:
                raise ValueError('No capture times are available; refresh capture metadata first')
            self.db.execute('DELETE FROM photo_stacks WHERE scope=? AND folder=?',(source['scope'],source['folder']))
            previous=None;first=None;size=0;stack_id=None
            def finish():
                if stack_id is not None:
                    self.db.execute('UPDATE photo_stacks SET size=?,top_id=? WHERE id=?',(size,first,stack_id))
            for row in self.rows(source):
                current=self.instant(row)
                if current is None:continue
                if self.separated(current,previous,gap):
                    finish();first=row['id'];size=0;stack_id=None
                if size==1:
                    stack_id=self.db.execute('INSERT INTO photo_stacks(scope,folder,collapsed) VALUES(?,?,1)',
                                            (source['scope'],source['folder'])).lastrowid
                    self.db.execute('INSERT INTO stack_members VALUES(?,?,?,0)',(source['scope'],first,stack_id))
                if stack_id is not None:
                    self.db.execute('INSERT INTO stack_members VALUES(?,?,?,?)',(source['scope'],row['id'],stack_id,size))
                size+=1;previous=current
            finish()
            if collection_id is not None:
                collection=Collections(self.catalog).get(collection_id)
                self.db.execute('UPDATE collections SET revision=revision+1 WHERE id=?',(collection_id,))
                Collections(self.catalog).touch_ancestors(collection['parent_id'])
        return {**plan,'stack_revision':Stacks(self.catalog).revision(),'applied':True}

    def refresh_times(self, folder=None, collection_id=None, after_source_id=0):
        source=self.source(folder,collection_id)
        rows=self.db.execute('SELECT source_id,path FROM photos WHERE is_virtual=0 AND source_id>? AND source_id IN '
            '(SELECT source_id FROM photos WHERE '+source['where']+') ORDER BY source_id LIMIT 61',
            [after_source_id,*source['params']]).fetchall()
        result={'processed':0,'known':0,'unknown':0,'failed':0,'after_source_id':after_source_id,'done':len(rows)<=60}
        with self.db:
            for row in rows[:60]:
                result['processed']+=1;result['after_source_id']=row['source_id']
                try:clock=read_capture_time(row['path'])
                except OSError:
                    result['failed']+=1;continue
                result['known' if clock['taken_us'] is not None else 'unknown']+=1
                self.db.execute('UPDATE photos SET taken=?,taken_us=?,taken_submicro=?,capture_clock=?,camera=? WHERE source_id=?',
                    (clock['taken'],clock['taken_us'],clock['taken_submicro'],clock['capture_clock'],clock['camera'],row['source_id']))
        return result
