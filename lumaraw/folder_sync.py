"""Durable folder synchronization plans and atomic catalog application.

Inputs: a catalog folder, captured revisions, bounded filesystem observations and
explicit import/remove/read-metadata selections. Outputs: review pages and one
transaction preserving existing edits, copies and frozen export jobs. Filesystem
I/O belongs to folder_sync_io/runner; this module never opens or deletes originals.
New imports reference files in place. Removal is catalog-only and includes a
missing original's variants; descriptive XMP updates apply to its master only.
"""
import json
import os
import time

from .folders import Folders, chain, descendants
from .keywords import Keywords, valid_name
from .model import Recipe
from .organization import folded
from .relocations import RelocationBusy

ACTIVE = ('planning','scanning','ready','verifying','interrupted')
STATES = ('new','missing','updated','error','unchanged')


def migrate(db):
    if db.execute('PRAGMA user_version').fetchone()[0] >= 10:
        return
    statements = (
        'CREATE TABLE folder_sync_plans(id INTEGER PRIMARY KEY AUTOINCREMENT, folder_id INTEGER NOT NULL, '
        'path TEXT NOT NULL, fingerprint TEXT NOT NULL, folder_revision INTEGER NOT NULL, scan_metadata INTEGER NOT NULL, '
        "state TEXT NOT NULL DEFAULT 'planning',phase TEXT NOT NULL DEFAULT 'directories',revision INTEGER NOT NULL DEFAULT 0, "
        'file_count INTEGER NOT NULL DEFAULT 0,directory_count INTEGER NOT NULL DEFAULT 1,directories_done INTEGER NOT NULL DEFAULT 0,'
        'scanned INTEGER NOT NULL DEFAULT 0,checked INTEGER NOT NULL DEFAULT 0,'
        "counts TEXT NOT NULL DEFAULT '{}',selected_counts TEXT NOT NULL DEFAULT '{}',error TEXT NOT NULL DEFAULT '',"
        'imported INTEGER NOT NULL DEFAULT 0,removed INTEGER NOT NULL DEFAULT 0,modified INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL)',
        "CREATE UNIQUE INDEX folder_sync_active ON folder_sync_plans((1)) WHERE state IN ('planning','scanning','ready','verifying','interrupted')",
        'CREATE TABLE folder_sync_directories(id INTEGER PRIMARY KEY AUTOINCREMENT,plan_id INTEGER NOT NULL,path TEXT NOT NULL,'
        'fingerprint TEXT NOT NULL,done INTEGER NOT NULL DEFAULT 0,UNIQUE(plan_id,path))',
        'CREATE INDEX folder_sync_directory_queue ON folder_sync_directories(plan_id,done,id)',
        'CREATE INDEX folder_sync_directory_page ON folder_sync_directories(plan_id,id)',
        'CREATE TABLE folder_sync_files(id INTEGER PRIMARY KEY AUTOINCREMENT,plan_id INTEGER NOT NULL,path TEXT NOT NULL,'
        "source_id INTEGER NOT NULL DEFAULT 0,state TEXT NOT NULL DEFAULT 'pending',selected INTEGER NOT NULL DEFAULT 1,"
        "bytes INTEGER NOT NULL DEFAULT 0,mtime INTEGER NOT NULL DEFAULT 0,fingerprints TEXT NOT NULL DEFAULT '{}',patch TEXT NOT NULL DEFAULT '{}',clock TEXT NOT NULL DEFAULT '{}',"
        "notes TEXT NOT NULL DEFAULT '[]',error TEXT NOT NULL DEFAULT '',UNIQUE(plan_id,path))",
        'CREATE INDEX folder_sync_file_state ON folder_sync_files(plan_id,state,id)',
        'CREATE INDEX folder_sync_file_page ON folder_sync_files(plan_id,id)',
        "CREATE INDEX folder_sync_changes ON folder_sync_files(plan_id,id) WHERE state IN ('new','missing','updated','error')",
        'CREATE INDEX folder_sync_file_source ON folder_sync_files(plan_id,source_id)',
        'CREATE TABLE folder_sync_photos(plan_id INTEGER NOT NULL,photo_id INTEGER NOT NULL,source_id INTEGER NOT NULL,'
        'source_revision INTEGER NOT NULL,revision INTEGER NOT NULL,metadata_revision INTEGER NOT NULL,rating INTEGER NOT NULL,'
        'flag INTEGER NOT NULL,bytes INTEGER NOT NULL,mtime INTEGER NOT NULL,sha256 TEXT NOT NULL,PRIMARY KEY(plan_id,photo_id))',
        'CREATE INDEX folder_sync_photo_source ON folder_sync_photos(plan_id,source_id)',
        'PRAGMA user_version=10',
    )
    with db:
        db.execute('BEGIN IMMEDIATE')
        for statement in statements:
            db.execute(statement)
        for name, event in (('folder_member_added','INSERT'),('folder_member_removed','DELETE')):
            row = db.execute('SELECT sql FROM sqlite_master WHERE name=?',(name,)).fetchone()
            marker = f'AFTER {event} ON folder_photos BEGIN'
            if not row or marker not in row[0]:
                raise ValueError('Unsupported folder trigger; synchronization migration was not applied')
            db.execute('DROP TRIGGER '+name)
            db.execute(row[0].replace(marker,f'AFTER {event} ON folder_photos WHEN (SELECT enabled FROM folder_maintenance WHERE id=1)=1 BEGIN'))


class FolderSync:
    def __init__(self,catalog):
        self.catalog, self.db = catalog, catalog.db

    def row(self,plan_id):
        row = self.db.execute('SELECT * FROM folder_sync_plans WHERE id=?',(plan_id,)).fetchone()
        if row is None:
            raise ValueError('Folder synchronization plan does not exist')
        return dict(row)

    def recover(self):
        with self.db:
            self.db.execute("UPDATE folder_sync_plans SET state='interrupted',revision=revision+1,"
                "error='Synchronization was interrupted; resume scanning explicitly' WHERE state IN ('scanning','verifying')")

    def check(self,plan_id,expected_revision,states):
        plan = self.row(plan_id)
        if plan['revision'] != expected_revision or plan['state'] not in states:
            raise ValueError('Synchronization plan changed; read it before continuing')
        if plan['folder_revision'] != Folders(self.catalog).revision():
            raise ValueError('Folder membership changed; cancel this plan and scan again')
        return plan

    def get(self,plan_id=None,kind='changes',offset=0):
        if plan_id is None:
            row = self.db.execute('SELECT id FROM folder_sync_plans ORDER BY id DESC LIMIT 1').fetchone()
            if row is None:
                return {'plan':None,'items':[],'total':0,'offset':0,'page_size':60}
            plan_id = row[0]
        plan = self.row(plan_id)
        for key in ('counts','selected_counts'):
            plan[key] = json.loads(plan[key])
        if kind not in ('all','changes',*STATES):
            raise ValueError('Unsupported synchronization item filter')
        clause = '' if kind == 'all' else " AND state IN ('new','missing','updated','error')" if kind == 'changes' else ' AND state=?'
        params = [plan_id] if kind in ('all','changes') else [plan_id,kind]
        total = plan['file_count'] if kind == 'all' else sum(plan['counts'].get(key,0) for key in STATES[:-1]) if kind == 'changes' else plan['counts'].get(kind,0)
        if plan['state'] not in ACTIVE:
            total = 0
        offset = min(offset,max(0,(total-1)//60*60))
        rows = self.db.execute('SELECT id,path,source_id,state,selected,patch,clock,notes,error,'
            '(SELECT count(*) FROM folder_sync_photos p WHERE p.plan_id=f.plan_id AND p.source_id=f.source_id) AS catalog_photos '
            'FROM folder_sync_files f WHERE plan_id=?'+clause+' ORDER BY id LIMIT 60 OFFSET ?',[*params,offset]) if total else []
        items = []
        for row in rows:
            item = dict(row)
            for key in ('patch','clock','notes'):
                item[key] = json.loads(item[key])
            items.append(item)
        return {'plan':plan,'items':items,'total':total,'offset':offset,'page_size':60}

    def prepare(self,folder_id,expected_revision,scan_metadata,fingerprint):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            folders = Folders(self.catalog)
            if folders.revision() != expected_revision:
                raise ValueError('Folder membership changed; refresh before synchronizing')
            folder = folders.get(folder_id)
            if self.db.execute("SELECT 1 FROM folder_sync_plans WHERE state IN ('planning','scanning','ready','verifying','interrupted')").fetchone():
                raise ValueError('Finish or cancel the existing synchronization plan first')
            self.db.execute('DELETE FROM folder_sync_plans WHERE id NOT IN (SELECT id FROM folder_sync_plans ORDER BY id DESC LIMIT 31)')
            plan_id = self.db.execute('INSERT INTO folder_sync_plans(folder_id,path,fingerprint,folder_revision,scan_metadata,created) '
                'VALUES(?,?,?,?,?,?)',(folder_id,folder['path'],json.dumps(fingerprint),expected_revision,int(scan_metadata),time.time())).lastrowid
            self.db.execute('INSERT INTO folder_sync_directories(plan_id,path,fingerprint) VALUES(?,?,?)',
                            (plan_id,folder['path'],json.dumps(fingerprint)))
            self.db.execute('INSERT INTO folder_sync_photos SELECT ?,p.id,p.source_id,s.revision,p.revision,p.metadata_revision,'
                'p.rating,p.flag,p.bytes,p.mtime,p.sha256 FROM photos p JOIN photo_sources s ON s.id=p.source_id '
                'WHERE p.id IN (SELECT photo_id FROM folder_photos WHERE folder_path IN ('+descendants('?')+'))',(plan_id,folder['path']))
            self.db.execute('INSERT INTO folder_sync_files(plan_id,path,source_id) SELECT ?,p.path,p.source_id FROM photos p '
                'JOIN folder_sync_photos s ON s.photo_id=p.id WHERE s.plan_id=? AND p.is_virtual=0',(plan_id,plan_id))
            self.db.execute('UPDATE folder_sync_plans SET file_count=(SELECT count(*) FROM folder_sync_files WHERE plan_id=?) WHERE id=?',(plan_id,plan_id))
        return self.get(plan_id)

    def start_scan(self,plan_id,expected_revision):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            plan = self.check(plan_id,expected_revision,('planning','interrupted'))
            self.db.execute("UPDATE folder_sync_plans SET state='scanning',error='',revision=revision+1 WHERE id=?",(plan_id,))
            if plan['phase'] == 'directories':
                rows = [dict(row) for row in self.db.execute('SELECT * FROM folder_sync_directories WHERE plan_id=? AND done=0 ORDER BY id LIMIT 1',(plan_id,))]
            else:
                rows = [dict(row) for row in self.db.execute("SELECT * FROM folder_sync_files WHERE plan_id=? AND state='pending' ORDER BY id LIMIT 60",(plan_id,))]
        return self.row(plan_id),rows

    def finish_directory(self,plan_id,revision,directory,result):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE');self.check(plan_id,revision,('scanning',))
            added_files = added_directories = 0
            for path in result['files']:
                added_files += self.db.execute('INSERT OR IGNORE INTO folder_sync_files(plan_id,path) VALUES(?,?)',(plan_id,path)).rowcount
            for path,fingerprint in result['directories']:
                added_directories += self.db.execute('INSERT OR IGNORE INTO folder_sync_directories(plan_id,path,fingerprint) VALUES(?,?,?)',
                                                     (plan_id,path,json.dumps(fingerprint))).rowcount
            self.db.execute('UPDATE folder_sync_directories SET done=? WHERE id=?',(int(result['done']),directory['id']))
            more = self.db.execute('SELECT 1 FROM folder_sync_directories WHERE plan_id=? AND done=0 LIMIT 1',(plan_id,)).fetchone()
            self.db.execute("UPDATE folder_sync_plans SET state='planning',phase=?,revision=revision+1,file_count=file_count+?,"
                'directory_count=directory_count+?,directories_done=directories_done+? WHERE id=?',
                ('directories' if more else 'files',added_files,added_directories,int(result['done']),plan_id))
        return self.get(plan_id)

    def finish_files(self,plan_id,revision,observations):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE');plan = self.check(plan_id,revision,('scanning',))
            counts = json.loads(plan['counts'])
            for row,result in observations:
                patch,clock,notes = result.get('patch',{}),result.get('clock',{}),result.get('notes',[])
                if clock.get('taken_us') is None:
                    clock = {'camera':clock['camera']} if clock.get('camera') else {}
                if result.get('error'):
                    state = 'error'
                elif result['missing']:
                    state = 'missing'
                elif not row['source_id']:
                    state = 'new'
                else:
                    # Most scans only need availability/stat fields. Never load
                    # recipes or decoder JSON, especially for missing originals.
                    current = self.db.execute('SELECT id,bytes,mtime,missing,title,caption,copyright,color_label,rating,flag,'
                        'taken,taken_us,taken_submicro,capture_clock,camera FROM photos WHERE source_id=? AND is_virtual=0',
                        (row['source_id'],)).fetchone()
                    if current is None:
                        raise ValueError('The original family changed during scanning; scan again')
                    if 'rating' in patch and current['flag'] == -1:
                        patch['flag'] = 0
                    if 'keyword_paths' in patch:
                        old = {tuple(folded(part) for part in tag['path'].split(' | ')) for tag in Keywords(self.catalog).photo(current['id'])}
                        new = {tuple(folded(part) for part in path) for path in patch['keyword_paths']}
                        if old == new:
                            patch = {key:value for key,value in patch.items() if key!='keyword_paths'}
                    patch = {key:value for key,value in patch.items() if key == 'keyword_paths' or current[key] != value}
                    # Preserve the complete clock/provenance when anything
                    # changes so review never formats camera time as local UTC.
                    if all(current[key] == value for key,value in clock.items()):
                        clock = {}
                    fingerprint = result['fingerprints'][row['path']]
                    state = 'updated' if patch or clock or current['missing'] or (current['bytes'],current['mtime']) != tuple(fingerprint[2:]) else 'unchanged'
                counts[state] = counts.get(state,0)+1
                if notes:
                    counts['with_notes'] = counts.get('with_notes',0)+1
                fingerprint = result['fingerprints'].get(row['path'])
                size,mtime = fingerprint[2:] if fingerprint else (0,0)
                self.db.execute('UPDATE folder_sync_files SET state=?,bytes=?,mtime=?,fingerprints=?,patch=?,clock=?,notes=?,error=? WHERE id=?',
                    (state,size,mtime,json.dumps(result['fingerprints']),json.dumps(patch),json.dumps(clock),json.dumps(notes),result.get('error',''),row['id']))
            more = self.db.execute("SELECT 1 FROM folder_sync_files WHERE plan_id=? AND state='pending' LIMIT 1",(plan_id,)).fetchone()
            self.db.execute('UPDATE folder_sync_plans SET state=?,scanned=scanned+?,counts=?,selected_counts=?,revision=revision+1 WHERE id=?',
                            ('planning' if more else 'ready',len(observations),json.dumps(counts),
                             json.dumps(counts) if observations else plan['selected_counts'],plan_id))
        return self.get(plan_id)

    def select(self,plan_id,expected_revision,selected,kind='new',item_ids=None,folder=None):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE');plan = self.check(plan_id,expected_revision,('ready',))
            if kind not in ('new','updated','missing') or item_ids is not None and folder is not None:
                raise ValueError('Choose one synchronization selection scope')
            clause,params = 'plan_id=? AND state=?',[plan_id,kind]
            if item_ids is not None:
                clause += ' AND id IN ('+','.join('?' for _ in item_ids)+')';params.extend(item_ids)
                if self.db.execute('SELECT count(*) FROM folder_sync_files WHERE '+clause,params).fetchone()[0] != len(set(item_ids)):
                    raise ValueError('Selected synchronization items changed')
            if folder is not None:
                folder = os.path.normpath(folder)
                if folder != plan['path'] and not folder.startswith(plan['path']+os.sep):
                    raise ValueError('Selection folder is outside this plan')
                clause += ' AND substr(path,1,?)=?';params.extend((len(folder)+1,folder+os.sep))
            self.db.execute('UPDATE folder_sync_files SET selected=? WHERE '+clause,[int(selected),*params])
            counts = dict(self.db.execute('SELECT state,count(*) FROM folder_sync_files WHERE plan_id=? AND selected=1 GROUP BY state',(plan_id,)))
            self.db.execute('UPDATE folder_sync_plans SET selected_counts=?,revision=revision+1 WHERE id=?',(json.dumps(counts),plan_id))
        return self.get(plan_id,kind)

    def start_apply(self,plan_id,expected_revision,read_metadata):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE');plan = self.check(plan_id,expected_revision,('ready',))
            if json.loads(plan['counts']).get('error',0):
                raise ValueError('Resolve the reported scan errors before synchronizing')
            if read_metadata and not plan['scan_metadata']:
                raise ValueError('Metadata was not scanned; create a new metadata plan')
            self.db.execute("UPDATE folder_sync_plans SET state='verifying',checked=0,error='',revision=revision+1 WHERE id=?",(plan_id,))
        return self.row(plan_id)

    def validation_page(self,plan_id,revision,kind,after):
        self.check(plan_id,revision,('verifying',))
        table = 'folder_sync_directories' if kind == 'directories' else 'folder_sync_files'
        return [dict(row) for row in self.db.execute(f'SELECT * FROM {table} WHERE plan_id=? AND id>? ORDER BY id LIMIT 60',(plan_id,after))]

    def discard(self,plan_id):
        for table in ('folder_sync_directories','folder_sync_files','folder_sync_photos'):
            self.db.execute(f'DELETE FROM {table} WHERE plan_id=?',(plan_id,))

    def terminal(self,plan_id,state,error=''):
        with self.db:
            if self.row(plan_id)['state'] in ACTIVE:
                self.db.execute('UPDATE folder_sync_plans SET state=?,error=?,revision=revision+1 WHERE id=?',(state,error,plan_id))
                self.discard(plan_id)
        return self.get(plan_id)

    def defer_apply(self,plan_id,revision,error):
        with self.db:
            if self.row(plan_id)['state'] in ACTIVE:
                self.check(plan_id,revision,('verifying',))
                self.db.execute("UPDATE folder_sync_plans SET state='ready',error=?,revision=revision+1 WHERE id=?",(error,plan_id))
        return self.get(plan_id)

    def apply(self,plan_id,revision,import_new,remove_missing,read_metadata):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE');plan = self.check(plan_id,revision,('verifying',))
            if self.db.execute('SELECT 1 FROM folder_sync_photos s LEFT JOIN photos p ON p.id=s.photo_id '
                'LEFT JOIN photo_sources f ON f.id=s.source_id WHERE s.plan_id=? AND (p.id IS NULL OR p.source_id!=s.source_id '
                'OR f.revision!=s.source_revision OR p.bytes!=s.bytes OR p.mtime!=s.mtime OR p.sha256!=s.sha256)',(plan_id,)).fetchone():
                raise ValueError('A catalog source changed; cancel this plan and scan again')
            if self.db.execute("SELECT 1 FROM folder_sync_photos s JOIN photos p ON p.id=s.photo_id JOIN folder_sync_files f "
                "ON f.plan_id=s.plan_id AND f.source_id=s.source_id WHERE s.plan_id=? AND f.selected=1 AND "
                "((? AND f.state='missing') OR (? AND f.state='updated' AND p.is_virtual=0)) AND "
                '(p.revision!=s.revision OR p.metadata_revision!=s.metadata_revision OR p.rating!=s.rating OR p.flag!=s.flag)',
                (plan_id,int(remove_missing),int(read_metadata))).fetchone():
                raise ValueError('A photo was edited after this plan was created; scan again before replacing or removing it')
            if self.db.execute("SELECT 1 FROM jobs WHERE state='running' AND source_id IN "
                '(SELECT source_id FROM folder_sync_files WHERE plan_id=?) LIMIT 1',(plan_id,)).fetchone():
                raise RelocationBusy('Wait for affected exports to finish before synchronizing')
            new_filter = "plan_id=? AND state='new' AND selected=1 AND ?"
            remove_filter = "plan_id=? AND state='missing' AND selected=1 AND ?"
            new_params,remove_params = (plan_id,int(import_new)),(plan_id,int(remove_missing))
            sources = 'SELECT source_id FROM folder_sync_files WHERE '+remove_filter
            removed = self.db.execute('SELECT count(*) FROM photos WHERE source_id IN ('+sources+')',remove_params).fetchone()[0]
            imported = self.db.execute('SELECT count(*) FROM folder_sync_files WHERE '+new_filter,new_params).fetchone()[0]
            modified = 0
            self.db.execute('CREATE TEMP TABLE sync_deltas(path TEXT NOT NULL,delta INTEGER NOT NULL)')
            self.db.execute('INSERT INTO sync_deltas SELECT folder_path(path),-count(*) FROM photos WHERE source_id IN ('+sources+') GROUP BY folder_path(path)',remove_params)
            self.db.execute('INSERT INTO sync_deltas SELECT folder_path(path),count(*) FROM folder_sync_files WHERE '+new_filter+' GROUP BY folder_path(path)',new_params)
            self.db.execute('INSERT OR IGNORE INTO catalog_folders(path,name,parent_path) WITH RECURSIVE paths(path) AS '
                '(SELECT path FROM sync_deltas WHERE delta>0 UNION SELECT folder_parent(path) FROM paths WHERE folder_parent(path) IS NOT NULL) '
                'SELECT path,folder_name(path),folder_parent(path) FROM paths')
            self.db.execute('UPDATE folder_maintenance SET enabled=0 WHERE id=1')
            self.db.execute('UPDATE collections SET revision=revision+1 WHERE id IN (WITH RECURSIVE affected(id) AS '
                '(SELECT collection_id FROM collection_photos WHERE photo_id IN (SELECT id FROM photos WHERE source_id IN ('+sources+')) '
                'UNION SELECT c.parent_id FROM collections c JOIN affected a ON c.id=a.id WHERE c.parent_id IS NOT NULL) SELECT id FROM affected)',remove_params)
            for table,column in (('history','photo_id'),('collection_photos','photo_id')):
                self.db.execute(f'DELETE FROM {table} WHERE {column} IN (SELECT id FROM photos WHERE source_id IN ('+sources+'))',remove_params)
            self.db.execute('DELETE FROM versions WHERE source_id IN ('+sources+')',remove_params)
            self.db.execute('DELETE FROM photos WHERE source_id IN ('+sources+')',remove_params)
            self.db.execute('INSERT INTO photos(path,name,bytes,mtime,recipe,created) SELECT path,folder_name(path),bytes,mtime,?,? FROM folder_sync_files WHERE '+new_filter,
                (json.dumps(Recipe().dict()),time.time(),*new_params))
            # Source stats are refreshed for every existing original. XMP edits
            # are separately selected and never replace a virtual copy's metadata.
            for rows in self.pages(plan_id):
                for row in rows:
                    if row['state'] == 'new' and (not import_new or not row['selected']):
                        continue
                    current = self.db.execute('SELECT id,source_id,bytes,mtime,missing FROM photos WHERE path=? AND is_virtual=0',(row['path'],)).fetchone()
                    if current is None:
                        continue
                    fingerprints = json.loads(row['fingerprints']);fingerprint = fingerprints.get(row['path'])
                    missing = fingerprint is None
                    size,mtime = (current['bytes'],current['mtime']) if missing else fingerprint[2:]
                    changed = (current['bytes'],current['mtime'],current['missing']) != (size,mtime,int(missing))
                    if changed:
                        self.db.execute('UPDATE photo_sources SET revision=revision+1 WHERE id=?',(current['source_id'],))
                        self.db.execute("UPDATE photos SET sha256=CASE WHEN bytes!=? OR mtime!=? THEN '' ELSE sha256 END,"
                            "bytes=?,mtime=?,missing=?,error='' WHERE source_id=?",(size,mtime,size,mtime,int(missing),current['source_id']))
                    if not missing and (row['state']=='new' or read_metadata and row['selected']):
                        clock = json.loads(row['clock'])
                        if clock:
                            self.db.execute('UPDATE photos SET '+','.join(key+'=?' for key in clock)+' WHERE source_id=?',
                                            [*clock.values(),current['source_id']])
                        patch = json.loads(row['patch'])
                        if patch:
                            self.apply_metadata(current['id'],patch)
                        if row['state'] != 'new' and (clock or patch):
                            modified += 1
            self.db.execute('UPDATE catalog_folders SET direct_count=direct_count+COALESCE('
                '(SELECT sum(delta) FROM sync_deltas WHERE sync_deltas.path=catalog_folders.path),0) WHERE path IN (SELECT path FROM sync_deltas)')
            self.db.execute('WITH RECURSIVE changes(path,delta) AS (SELECT path,delta FROM sync_deltas UNION ALL '
                'SELECT f.parent_path,c.delta FROM changes c JOIN catalog_folders f ON f.path=c.path WHERE f.parent_path IS NOT NULL),'
                'totals AS (SELECT path,sum(delta) AS delta FROM changes GROUP BY path) '
                'UPDATE catalog_folders SET total_count=total_count+t.delta FROM totals t WHERE catalog_folders.path=t.path')
            self.db.execute('UPDATE folder_maintenance SET enabled=1 WHERE id=1')
            self.db.execute('UPDATE catalog_folders SET is_root=1 WHERE path=? AND NOT EXISTS '
                '(SELECT 1 FROM catalog_folders WHERE is_root=1 AND path IN ('+chain('?')+'))',(plan['path'],plan['path']))
            self.db.execute('UPDATE folder_state SET revision=revision+1')
            self.db.execute("UPDATE folder_sync_plans SET state='applied',imported=?,removed=?,modified=?,revision=revision+1,error='' WHERE id=?",
                            (imported,removed,modified,plan_id))
            self.discard(plan_id)
        return self.get(plan_id)

    def pages(self,plan_id):
        after = 0
        while True:
            rows = self.db.execute('SELECT * FROM folder_sync_files WHERE plan_id=? AND id>? ORDER BY id LIMIT 60',(plan_id,after)).fetchall()
            if not rows:
                break
            yield rows
            after = rows[-1]['id']

    def apply_metadata(self,photo_id,patch):
        fields = {key:value for key,value in patch.items() if key!='keyword_paths'}
        if fields:
            self.db.execute('UPDATE photos SET '+','.join(key+'=?' for key in fields)+' WHERE id=?',[*fields.values(),photo_id])
        if 'keyword_paths' in patch:
            ids = set()
            for path in patch['keyword_paths']:
                parent = None
                for name in path:
                    name = valid_name(name)
                    row = self.db.execute('SELECT id FROM keywords WHERE parent_id IS ? AND normalized=?',(parent,folded(name))).fetchone()
                    if row:
                        parent = row[0]
                    else:
                        parent = self.db.execute('INSERT INTO keywords(parent_id,name,normalized) VALUES(?,?,?)',(parent,name,folded(name))).lastrowid
                        self.db.execute('UPDATE keyword_state SET revision=revision+1')
                ids.add(parent)
            self.db.execute('DELETE FROM keyword_photos WHERE photo_id=?',(photo_id,))
            self.db.executemany('INSERT INTO keyword_photos VALUES(?,?)',[(photo_id,id_) for id_ in ids])
        self.db.execute('UPDATE photos SET metadata_revision=metadata_revision+1 WHERE id=?',(photo_id,))
