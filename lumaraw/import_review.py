"""Durable selection and catalog-only application of reviewed Add imports.

Inputs: explicit source snapshots, bounded observations and captured plan revisions.
Outputs: review pages, duplicate eligibility and one atomic catalog import. Existing
photos, copies, recipes and exports are never changed. Captured import presets
initialize only new photos. Filesystem reads and pixels
belong to the runner; no original writes, copy/move, DNG conversion or AI selection.
Unknown capture time never falls back to mtime for suspected-duplicate matching.
"""
import json
import os
import sqlite3
import time

from .model import Recipe

ACTIVE=('planning','scanning','ready','verifying','interrupted')
KINDS=('all','new','duplicate','existing','error','selected')


def migrate(db):
    if db.execute('PRAGMA user_version').fetchone()[0]>=19:
        return
    statements=(
        "ALTER TABLE photos ADD COLUMN original_name TEXT NOT NULL DEFAULT ''",
        'UPDATE photos SET original_name=name',
        "CREATE TRIGGER photo_original_name AFTER INSERT ON photos WHEN NEW.original_name='' BEGIN "
        'UPDATE photos SET original_name=NEW.name WHERE id=NEW.id; END',
        'CREATE INDEX photo_import_duplicate ON photos(original_name,bytes,capture_clock,taken_us,taken_submicro) WHERE is_virtual=0',
        'CREATE TABLE import_plans(id INTEGER PRIMARY KEY AUTOINCREMENT,'
        "state TEXT NOT NULL DEFAULT 'planning',phase TEXT NOT NULL DEFAULT 'directories',revision INTEGER NOT NULL DEFAULT 0,"
        'include_subfolders INTEGER NOT NULL,skip_duplicates INTEGER NOT NULL DEFAULT 1,'
        'file_count INTEGER NOT NULL DEFAULT 0,scanned INTEGER NOT NULL DEFAULT 0,checked INTEGER NOT NULL DEFAULT 0,'
        "counts TEXT NOT NULL DEFAULT '{}',selected_count INTEGER NOT NULL DEFAULT 0,selected_bytes INTEGER NOT NULL DEFAULT 0,"
        "error TEXT NOT NULL DEFAULT '',imported INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL)",
        "CREATE UNIQUE INDEX import_active ON import_plans((1)) WHERE state IN ('planning','scanning','ready','verifying','interrupted')",
        'CREATE TABLE import_directories(id INTEGER PRIMARY KEY AUTOINCREMENT,plan_id INTEGER NOT NULL,path TEXT NOT NULL,'
        'fingerprint TEXT NOT NULL,done INTEGER NOT NULL DEFAULT 0,source INTEGER NOT NULL DEFAULT 0,UNIQUE(plan_id,path))',
        'CREATE INDEX import_directory_queue ON import_directories(plan_id,done,id)',
        'CREATE TABLE import_files(id INTEGER PRIMARY KEY AUTOINCREMENT,plan_id INTEGER NOT NULL,path TEXT NOT NULL,name TEXT NOT NULL,extension TEXT NOT NULL,'
        "state TEXT NOT NULL DEFAULT 'pending',selected INTEGER NOT NULL DEFAULT 1,bytes INTEGER NOT NULL DEFAULT 0,mtime INTEGER NOT NULL DEFAULT 0,"
        'taken_us INTEGER,taken_submicro TEXT NOT NULL DEFAULT \'\',capture_clock TEXT NOT NULL DEFAULT \'unknown\','
        "fingerprints TEXT NOT NULL DEFAULT '{}',patch TEXT NOT NULL DEFAULT '{}',clock TEXT NOT NULL DEFAULT '{}',"
        "notes TEXT NOT NULL DEFAULT '[]',error TEXT NOT NULL DEFAULT '',UNIQUE(plan_id,path))",
        'CREATE INDEX import_file_page ON import_files(plan_id,id)',
        'CREATE INDEX import_file_state ON import_files(plan_id,state,id)',
        'CREATE INDEX import_file_name ON import_files(plan_id,name COLLATE NOCASE,id)',
        'CREATE INDEX import_file_capture ON import_files(plan_id,taken_us,id)',
        'CREATE INDEX import_file_checked ON import_files(plan_id,selected,id)',
        'CREATE INDEX import_file_type ON import_files(plan_id,extension COLLATE NOCASE,name COLLATE NOCASE,id)',
        'CREATE INDEX import_file_duplicate ON import_files(plan_id,name,bytes,capture_clock,taken_us,taken_submicro,id)',
        'PRAGMA user_version=19',
    )
    db.execute('BEGIN IMMEDIATE')
    try:
        for statement in statements:db.execute(statement)
        db.commit()
    except BaseException:
        db.rollback();raise


class ImportReview:
    def __init__(self,catalog):
        self.catalog,self.db=catalog,catalog.db

    def row(self,plan_id):
        row=self.db.execute('SELECT * FROM import_plans WHERE id=?',(plan_id,)).fetchone()
        if row is None:raise ValueError('Import review does not exist')
        return dict(row)

    def check(self,plan_id,expected_revision,states):
        plan=self.row(plan_id)
        if plan['revision']!=expected_revision or plan['state'] not in states:
            raise ValueError('Import review changed; read it before continuing')
        return plan

    @staticmethod
    def eligible(plan):
        return "state='new'" if plan['skip_duplicates'] else "state IN ('new','duplicate')"

    def recount(self,plan_id):
        plan=self.row(plan_id)
        count,size=self.db.execute('SELECT count(*),COALESCE(sum(bytes),0) FROM import_files WHERE plan_id=? '
                                  'AND selected=1 AND '+self.eligible(plan),(plan_id,)).fetchone()
        self.db.execute('UPDATE import_plans SET selected_count=?,selected_bytes=? WHERE id=?',(count,size,plan_id))

    def get(self,plan_id=None,kind='all',offset=0,sort='name',descending=False):
        if plan_id is None:
            row=self.db.execute('SELECT id FROM import_plans ORDER BY id DESC LIMIT 1').fetchone()
            if row is None:return {'plan':None,'items':[],'total':0,'offset':0,'page_size':60}
            plan_id=row[0]
        plan=self.row(plan_id);plan['counts']=json.loads(plan['counts'])
        from .import_processing import brief
        plan['processing']=brief(self.catalog,plan_id)
        if kind not in KINDS:raise ValueError('Unsupported import filter')
        clause='plan_id=?';args=[plan_id]
        if kind=='selected':clause+=' AND selected=1 AND '+self.eligible(plan)
        elif kind!='all':clause+=' AND state=?';args.append(kind)
        total=plan['file_count'] if kind=='all' else plan['selected_count'] if kind=='selected' else plan['counts'].get(kind,0)
        if plan['state'] not in ACTIVE:total=0
        offset=min(offset,max(0,(total-1)//60*60))
        order={'name':['name COLLATE NOCASE'],'captured':['taken_us'],'checked':['selected'],
               'type':['extension COLLATE NOCASE','name COLLATE NOCASE']}.get(sort)
        if order is None:raise ValueError('Unsupported import sort')
        direction=' DESC' if descending else ' ASC'
        rows=self.db.execute('SELECT id,path,name,state,selected,bytes,mtime,clock,substr(error,1,500) AS error,'
            'length(notes)>2 AS has_notes FROM import_files WHERE '+clause+' ORDER BY '+','.join(value+direction for value in order)+',id LIMIT 60 OFFSET ?',[*args,offset])
        items=[]
        for row in rows:
            item=dict(row);item['clock']=json.loads(item['clock'])
            item['eligible']=item['state']=='new' or item['state']=='duplicate' and not plan['skip_duplicates']
            items.append(item)
        return {'plan':plan,'items':items,'total':total,'offset':offset,'page_size':60}

    def item(self,plan_id,item_id,expected_revision):
        self.check(plan_id,expected_revision,ACTIVE)
        row=self.db.execute('SELECT * FROM import_files WHERE plan_id=? AND id=?',(plan_id,item_id)).fetchone()
        if row is None:raise ValueError('Import item does not exist')
        return dict(row)

    def prepare(self,sources,include_subfolders=True,skip_duplicates=True):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            if self.db.execute("SELECT 1 FROM import_plans WHERE state IN ('planning','scanning','ready','verifying','interrupted')").fetchone():
                raise ValueError('Finish or cancel the existing import review first')
            self.db.execute('DELETE FROM import_plans WHERE id NOT IN (SELECT id FROM import_plans ORDER BY id DESC LIMIT 31)')
            plan_id=self.db.execute('INSERT INTO import_plans(include_subfolders,skip_duplicates,created) VALUES(?,?,?)',
                (int(include_subfolders),int(skip_duplicates),time.time())).lastrowid
            for source in sources:
                if source['directory']:
                    self.db.execute('INSERT INTO import_directories(plan_id,path,fingerprint,source) VALUES(?,?,?,1) '
                        'ON CONFLICT(plan_id,path) DO UPDATE SET source=1',
                        (plan_id,source['path'],json.dumps(source['fingerprint'])))
                else:self.add_file(plan_id,source['path'])
            if not self.db.execute('SELECT 1 FROM import_directories WHERE plan_id=?',(plan_id,)).fetchone():
                self.db.execute("UPDATE import_plans SET phase='files' WHERE id=?",(plan_id,))
        return self.get(plan_id)

    def add_file(self,plan_id,path):
        if len(path.encode())>4096:raise ValueError('Import paths exceed the supported filesystem path length')
        inserted=self.db.execute('INSERT OR IGNORE INTO import_files(plan_id,path,name,extension) VALUES(?,?,?,?)',
                                (plan_id,path,os.path.basename(path),os.path.splitext(path)[1].lower())).rowcount
        self.db.execute('UPDATE import_plans SET file_count=file_count+? WHERE id=?',(inserted,plan_id))

    def recover(self):
        with self.db:
            self.db.execute("UPDATE import_plans SET state='interrupted',revision=revision+1,"
                "error='Import was interrupted; resume the review explicitly' WHERE state IN ('scanning','verifying')")

    def start_scan(self,plan_id,expected_revision):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE');plan=self.check(plan_id,expected_revision,('planning','interrupted'))
            self.db.execute("UPDATE import_plans SET state='scanning',error='',revision=revision+1 WHERE id=?",(plan_id,))
            if plan['phase']=='directories':
                rows=list(self.db.execute('SELECT * FROM import_directories WHERE plan_id=? AND done=0 ORDER BY id LIMIT 1',(plan_id,)))
            else:rows=list(self.db.execute("SELECT * FROM import_files WHERE plan_id=? AND state='pending' ORDER BY id LIMIT 60",(plan_id,)))
        return self.row(plan_id),[dict(row) for row in rows]

    def finish_directory(self,plan_id,revision,directory,result):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE');plan=self.check(plan_id,revision,('scanning',))
            for path in result['files']:self.add_file(plan_id,path)
            if plan['include_subfolders']:
                self.db.executemany('INSERT OR IGNORE INTO import_directories(plan_id,path,fingerprint) VALUES(?,?,?)',
                    ((plan_id,path,json.dumps(value)) for path,value in result['directories']))
            self.db.execute('UPDATE import_directories SET done=? WHERE id=?',(int(result['done']),directory['id']))
            more=self.db.execute('SELECT 1 FROM import_directories WHERE plan_id=? AND done=0 LIMIT 1',(plan_id,)).fetchone()
            self.db.execute("UPDATE import_plans SET state='planning',phase=?,revision=revision+1 WHERE id=?",('directories' if more else 'files',plan_id))
        return self.get(plan_id)

    def duplicate(self,row,clock):
        if clock.get('taken_us') is None:return False
        key=(row['name'],row['bytes'],clock['capture_clock'],clock['taken_us'],clock.get('taken_submicro',''))
        catalog=self.db.execute('SELECT 1 FROM photos WHERE is_virtual=0 AND original_name=? AND bytes=? '
            'AND capture_clock=? AND taken_us=? AND taken_submicro=? LIMIT 1',key).fetchone()
        previous=self.db.execute("SELECT 1 FROM import_files WHERE plan_id=? AND name=? AND bytes=? AND capture_clock=? "
            "AND taken_us=? AND taken_submicro=? AND id<? AND state IN ('new','duplicate') LIMIT 1",(row['plan_id'],*key,row['id'])).fetchone()
        return bool(catalog or previous)

    def finish_files(self,plan_id,revision,observations):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE');plan=self.check(plan_id,revision,('scanning',));counts=json.loads(plan['counts'])
            selected_count,selected_bytes=plan['selected_count'],plan['selected_bytes']
            for row,result in observations:
                clock=result.get('clock',{});fingerprint=result.get('fingerprints',{}).get(row['path'])
                size,mtime=fingerprint[2:] if fingerprint else (0,0);row['bytes']=size
                if result.get('error') or result.get('missing'):state='error'
                elif self.db.execute('SELECT 1 FROM photos WHERE path=? AND is_virtual=0',(row['path'],)).fetchone():state='existing'
                else:state='duplicate' if self.duplicate(row,clock) else 'new'
                self.db.execute('UPDATE import_files SET state=?,bytes=?,mtime=?,taken_us=?,taken_submicro=?,capture_clock=?,'
                    'fingerprints=?,patch=?,clock=?,notes=?,error=? WHERE id=?',
                    (state,size,mtime,clock.get('taken_us'),clock.get('taken_submicro',''),clock.get('capture_clock','unknown'),
                     json.dumps(result.get('fingerprints',{})),json.dumps(result.get('patch',{})),json.dumps(clock),
                     json.dumps(result.get('notes',[])),result.get('error',''),row['id']))
                counts[state]=counts.get(state,0)+1
                if row['selected'] and (state=='new' or state=='duplicate' and not plan['skip_duplicates']):
                    selected_count+=1;selected_bytes+=size
            more=self.db.execute("SELECT 1 FROM import_files WHERE plan_id=? AND state='pending' LIMIT 1",(plan_id,)).fetchone()
            self.db.execute('UPDATE import_plans SET state=?,scanned=scanned+?,counts=?,selected_count=?,selected_bytes=?,revision=revision+1 WHERE id=?',
                ('planning' if more else 'ready',len(observations),json.dumps(counts),selected_count,selected_bytes,plan_id))
        return self.get(plan_id)

    def select(self,plan_id,expected_revision,selected,item_ids=None,kind='all'):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE');plan=self.check(plan_id,expected_revision,('ready',))
            where='plan_id=? AND '+self.eligible(plan);args=[plan_id]
            if kind not in ('all','new','duplicate'):raise ValueError('Unsupported selection filter')
            if kind!='all':where+=' AND state=?';args.append(kind)
            if item_ids is not None:
                where+=' AND id IN ('+','.join('?' for _ in item_ids)+')';args.extend(item_ids)
                if self.db.execute('SELECT count(*) FROM import_files WHERE '+where,args).fetchone()[0]!=len(set(item_ids)):
                    raise ValueError('Some import items are not selectable')
            self.db.execute('UPDATE import_files SET selected=? WHERE '+where,[int(selected),*args])
            self.recount(plan_id);self.db.execute('UPDATE import_plans SET revision=revision+1 WHERE id=?',(plan_id,))
        return self.get(plan_id)

    def options(self,plan_id,expected_revision,skip_duplicates):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE');self.check(plan_id,expected_revision,('ready',))
            self.db.execute('UPDATE import_plans SET skip_duplicates=?,revision=revision+1 WHERE id=?',(int(skip_duplicates),plan_id))
            self.recount(plan_id)
        return self.get(plan_id)

    def start_apply(self,plan_id,expected_revision):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE');plan=self.check(plan_id,expected_revision,('ready',))
            if not plan['selected_count']:raise ValueError('Check at least one new photo to import')
            self.db.execute("UPDATE import_plans SET state='verifying',checked=0,error='',revision=revision+1 WHERE id=?",(plan_id,))
        return self.row(plan_id)

    def pages(self,plan_id,revision,kind,after):
        plan=self.check(plan_id,revision,('verifying',))
        table='import_directories' if kind=='directories' else 'import_files'
        where='plan_id=? AND id>?'
        if kind!='directories':where+=' AND selected=1 AND '+self.eligible(plan)
        return [dict(row) for row in self.db.execute('SELECT * FROM '+table+' WHERE '+where+' ORDER BY id LIMIT 60',(plan_id,after))]

    def discard(self,plan_id):
        for table in ('import_directories','import_files'):self.db.execute('DELETE FROM '+table+' WHERE plan_id=?',(plan_id,))
        self.db.execute('DELETE FROM import_processing WHERE plan_id=?',(plan_id,))

    def terminal(self,plan_id,state,error=''):
        with self.db:
            if self.row(plan_id)['state'] in ACTIVE:
                self.db.execute('UPDATE import_plans SET state=?,error=?,revision=revision+1 WHERE id=?',(state,error,plan_id))
                self.discard(plan_id)
        return self.get(plan_id)

    def apply(self,plan_id,revision,cancelled=lambda:False):
        from .folder_sync import FolderSync
        from .folders import chain
        from . import import_processing
        with self.db:
            self.db.execute('BEGIN IMMEDIATE');plan=self.check(plan_id,revision,('verifying',))
            where='f.plan_id=? AND f.selected=1 AND '+self.eligible(plan).replace('state','f.state')
            processing=import_processing.settings(self.catalog,plan_id)
            recipe=Recipe.parse(processing['develop_patch']).dict()
            self.db.set_progress_handler(lambda:int(cancelled()),2000)
            try:
                if profile:=recipe.get('camera_profile'):
                    if self.db.execute("SELECT 1 FROM import_files f WHERE "+where+
                        " AND COALESCE(json_extract(f.clock,'$.camera'),'')!=? LIMIT 1",(plan_id,profile['camera'])).fetchone():
                        raise ValueError('Import Develop preset camera profile is incompatible with a checked photo')
                if self.db.execute('SELECT 1 FROM import_files f JOIN photos p ON p.path=f.path AND p.is_virtual=0 WHERE '+where+' LIMIT 1',(plan_id,)).fetchone():
                    raise ValueError('A selected photo was imported elsewhere; create a fresh review')
                if plan['skip_duplicates'] and self.db.execute('SELECT 1 FROM import_files f JOIN photos p ON p.is_virtual=0 '
                    'AND p.original_name=f.name AND p.bytes=f.bytes AND p.capture_clock=f.capture_clock '
                    'AND p.taken_us=f.taken_us AND p.taken_submicro=f.taken_submicro WHERE '+where+' LIMIT 1',(plan_id,)).fetchone():
                    raise ValueError('A suspected duplicate appeared after review; create a fresh review')
                imported=self.db.execute('SELECT count(*) FROM import_files f WHERE '+where,(plan_id,)).fetchone()[0]
                self.db.execute('CREATE TEMP TABLE import_deltas(path TEXT PRIMARY KEY,delta INTEGER NOT NULL)')
                self.db.execute('INSERT INTO import_deltas SELECT folder_path(f.path),count(*) FROM import_files f WHERE '+where+' GROUP BY folder_path(f.path)',(plan_id,))
                self.db.execute('INSERT OR IGNORE INTO catalog_folders(path,name,parent_path) WITH RECURSIVE paths(path) AS '
                    '(SELECT path FROM import_deltas UNION SELECT folder_parent(path) FROM paths WHERE folder_parent(path) IS NOT NULL) '
                    'SELECT path,folder_name(path),folder_parent(path) FROM paths')
                self.db.execute('UPDATE folder_maintenance SET enabled=0 WHERE id=1')
                self.db.execute('INSERT INTO photos(path,name,original_name,bytes,mtime,recipe,created,taken,taken_us,taken_submicro,capture_clock,camera) '
                    'SELECT f.path,f.name,f.name,f.bytes,f.mtime,?,?,COALESCE(json_extract(f.clock,\'$.taken\'),0),'
                    'f.taken_us,f.taken_submicro,f.capture_clock,COALESCE(json_extract(f.clock,\'$.camera\'),\'\') FROM import_files f WHERE '+where,
                    (json.dumps(recipe),time.time(),plan_id))
                after=0
                while True:
                    rows=self.db.execute('SELECT f.id,f.patch,p.id AS photo_id FROM import_files f JOIN photos p ON p.path=f.path AND p.is_virtual=0 '
                        'WHERE '+where+" AND f.id>? AND f.patch!='{}' ORDER BY f.id LIMIT 60",(plan_id,after)).fetchall()
                    if not rows:break
                    for row in rows:
                        if cancelled():raise InterruptedError('Import cancelled')
                        FolderSync(self.catalog).apply_metadata(row['photo_id'],json.loads(row['patch']))
                    after=rows[-1]['id']
                import_processing.apply_metadata(self.catalog,processing,where,(plan_id,),cancelled)
                self.db.execute('UPDATE catalog_folders SET direct_count=direct_count+d.delta FROM import_deltas d WHERE catalog_folders.path=d.path')
                self.db.execute('WITH RECURSIVE changes(path,delta) AS (SELECT path,delta FROM import_deltas UNION ALL '
                    'SELECT f.parent_path,c.delta FROM changes c JOIN catalog_folders f ON f.path=c.path WHERE f.parent_path IS NOT NULL),'
                    'totals AS (SELECT path,sum(delta) AS delta FROM changes GROUP BY path) '
                    'UPDATE catalog_folders SET total_count=total_count+t.delta FROM totals t WHERE catalog_folders.path=t.path')
                self.db.execute('UPDATE folder_maintenance SET enabled=1 WHERE id=1')
                for scope,args in [('SELECT path FROM import_directories WHERE plan_id=? AND source=1',(plan_id,)),('SELECT path FROM import_deltas',())]:
                    self.db.execute('UPDATE catalog_folders AS target SET is_root=1 WHERE path IN ('+scope+') AND NOT EXISTS '
                        '(SELECT 1 FROM catalog_folders a WHERE a.is_root=1 AND a.path IN ('+chain('target.path')+'))',args)
                self.db.execute('UPDATE folder_state SET revision=revision+1')
                if cancelled():raise InterruptedError('Import cancelled')
                from .previous_import import replace
                replace(self.db,'SELECT p.source_id FROM import_files f JOIN photos p ON p.path=f.path AND p.is_virtual=0 WHERE '+where,
                        (plan_id,),'reviewed',imported)
                self.db.execute("UPDATE import_plans SET state='applied',imported=?,revision=revision+1 WHERE id=?",(imported,plan_id))
                self.discard(plan_id)
                self.db.execute('DROP TABLE import_deltas')
            except sqlite3.OperationalError:
                if cancelled():raise InterruptedError('Import cancelled')
                raise
            finally:self.db.set_progress_handler(None,0)
        return self.get(plan_id)
