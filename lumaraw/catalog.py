"""SQLite catalog, history, and durable export queue; originals stay untouched.

Inputs: explicit local paths and validated recipes. Outputs: paginated rows/jobs.
Responsibilities: store references, edits, undo history, and export snapshots.
Library orientation is independent of Develop recipes and frozen in each job.
Photo details keep complete keyword IDs; large display paths use explicit pages.
Boundaries: never copy/write original photos; never eagerly load full catalogs.
Each connection belongs to its creating thread. Bulk insertion commits in batches.
Direct imports number successful new originals with item savepoints and retain a
single import number across the invocation's bounded commit batches.
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import time

from .runtime import CATALOG_VERSION
from .model import Recipe, ExportOptions, SYNC_GROUPS, IMAGE_EXTENSIONS
from .organization import Organization, SORTS, criteria, folded, migrate, text_predicate

FAMILY_COLUMNS = ('source_id,is_virtual,copy_name,'
                  '(SELECT revision FROM photo_sources WHERE id=photos.source_id) AS source_revision,'
                  '(SELECT id FROM photos master WHERE master.source_id=photos.source_id AND master.is_virtual=0) AS master_id')
SUMMARY_COLUMNS = ('id,path,name,bytes,mtime,rating,flag,revision,orientation,color_label,title,metadata_revision,taken,camera,missing,error,'
                   + FAMILY_COLUMNS)

class Catalog:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.root / 'catalog.sqlite', timeout=10)
        if self.db.execute("PRAGMA user_version").fetchone()[0] > CATALOG_VERSION:
            self.db.close()
            raise ValueError("This catalog was upgraded by a newer LumaRAW version; open it with that version")
        self.db.row_factory = sqlite3.Row
        self.db.create_function('casefold', 1, folded, deterministic=True)
        from .folders import register
        register(self.db)
        self.db.executescript('''
            PRAGMA journal_mode=WAL;
            PRAGMA busy_timeout=10000;
            CREATE TABLE IF NOT EXISTS photos (
                id INTEGER PRIMARY KEY, path TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
                bytes INTEGER NOT NULL, mtime INTEGER NOT NULL, rating INTEGER DEFAULT 0,
                recipe TEXT NOT NULL, metadata TEXT DEFAULT '{}', error TEXT DEFAULT '',
                revision INTEGER DEFAULT 0, created REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS photo_rating ON photos(rating, id);
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY, photo_id INTEGER NOT NULL, recipe TEXT NOT NULL,
                label TEXT NOT NULL, created REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS history_photo ON history(photo_id, id);
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY, photo_id INTEGER NOT NULL, source TEXT NOT NULL,
                recipe TEXT NOT NULL, destination TEXT NOT NULL, format TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'pending', error TEXT DEFAULT '',
                peak_mb REAL DEFAULT 0, created REAL NOT NULL);
        ''')
        columns = {row[1] for row in self.db.execute('PRAGMA table_info(jobs)')}
        if 'output' not in columns:
            self.db.execute("ALTER TABLE jobs ADD COLUMN output TEXT NOT NULL DEFAULT ''")
        photo_columns={r[1] for r in self.db.execute('PRAGMA table_info(photos)')}
        for name,definition in [('flag','INTEGER DEFAULT 0'),('sha256',"TEXT DEFAULT ''"),('taken','INTEGER DEFAULT 0'),('camera',"TEXT DEFAULT ''"),('burst','INTEGER DEFAULT 0'),('missing','INTEGER DEFAULT 0')]:
            if name not in photo_columns: self.db.execute(f'ALTER TABLE photos ADD COLUMN {name} {definition}')
        for name,definition in [('options',"TEXT DEFAULT '{}'"),('priority','INTEGER DEFAULT 0')]:
            if name not in columns: self.db.execute(f'ALTER TABLE jobs ADD COLUMN {name} {definition}')
        self.db.executescript('CREATE TABLE IF NOT EXISTS versions(id INTEGER PRIMARY KEY,photo_id INTEGER NOT NULL,name TEXT NOT NULL,recipe TEXT NOT NULL,created REAL NOT NULL); CREATE INDEX IF NOT EXISTS photo_hash ON photos(sha256);')
        self.db.commit()
        migrate(self.db)

    def setting(self, key, default=None):
        row = self.db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, key, value):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)', (key, json.dumps(value)))

    def close(self):
        self.db.close()

    def recover_jobs(self):
        # Never replay interrupted exports automatically: user decides to retry.
        with self.db:
            self.db.execute("UPDATE jobs SET state='interrupted',error='Job was unfinished at exit; an explicit retry is required' WHERE state='running'")

    def import_paths(self, paths, cancelled=lambda: False):
        count = skipped = 0
        batch_number = None
        for path in paths:
            if cancelled():
                break
            p = Path(path)
            if p.is_symlink() or p.suffix.lower() not in IMAGE_EXTENSIONS:
                skipped += 1
                continue
            try:
                p = p.resolve(strict=True)
                stat = p.stat()
                if not p.is_file():
                    continue
                if not self.db.in_transaction:
                    self.db.execute('BEGIN')
                self.db.execute('SAVEPOINT import_path')
                allocation = None
                try:
                    cur = self.db.execute(
                        'INSERT OR IGNORE INTO photos(path,name,bytes,mtime,recipe,created) VALUES(?,?,?,?,?,?)',
                        (str(p), p.name, stat.st_size, stat.st_mtime_ns, json.dumps(Recipe().dict()), time.time()))
                    if cur.rowcount:
                        from .previous_import import append
                        append(self.db,cur.lastrowid,first=count == 0)
                        from .capture_time import read_capture_time
                        try:
                            clock=read_capture_time(p)
                        except OSError:
                            clock=None  # The reference is imported; capture metadata remains unknown.
                        if clock:
                            self.db.execute('UPDATE photos SET taken=?,taken_us=?,taken_submicro=?,capture_clock=?,camera=? WHERE id=?',
                                            (clock['taken'],clock['taken_us'],clock['taken_submicro'],clock['capture_clock'],clock['camera'],cur.lastrowid))
                        from .import_sequence import allocate
                        allocation = allocate(self.db,1,import_number=batch_number)
                        self.db.execute('UPDATE photos SET import_number=?,image_number=? WHERE id=?',
                                        (allocation['import_number'],allocation['image_number'],cur.lastrowid))
                    self.db.execute('RELEASE import_path')
                except BaseException:
                    self.db.execute('ROLLBACK TO import_path')
                    self.db.execute('RELEASE import_path')
                    raise
                if cur.rowcount:
                    if batch_number is None:
                        batch_number = allocation['import_number']
                    count += 1
                else:
                    skipped += 1
                if (count + skipped) % 100 == 0:
                    self.db.commit()
            except OSError:
                skipped += 1
        self.db.commit()
        return count, skipped

    def count(self, stars=False):
        return self.db.execute('SELECT count(*) FROM photos' + (' WHERE rating>=3' if stars else '')).fetchone()[0]

    def page(self, offset=0, limit=60, stars=False):
        return [dict(r) for r in self.db.execute(
            'SELECT * FROM photos' + (' WHERE rating>=3' if stars else '') + ' ORDER BY id DESC LIMIT ? OFFSET ?',
            (min(max(limit, 1), 60), max(offset, 0)))]

    def photo(self, photo_id):
        row = self.db.execute('SELECT photos.*, (SELECT revision FROM photo_sources WHERE id=photos.source_id) AS source_revision, (SELECT id FROM photos master WHERE master.source_id=photos.source_id AND master.is_virtual=0) AS master_id FROM photos WHERE id=?', (photo_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        from .keyword_details import KeywordDetails
        result.update(KeywordDetails(self).summary(photo_id))
        return result

    def recipe(self, photo_id):
        return Recipe.parse(json.loads(self.photo(photo_id)['recipe']))

    def edit(self, photo_id, recipe, label='Adjustments'):
        from .develop_history import DevelopHistory
        with self.db:
            DevelopHistory(self.db).edit(photo_id, recipe, label)

    def undo(self, photo_id):
        from .develop_history import DevelopHistory
        with self.db:
            return DevelopHistory(self.db).move(photo_id)

    def update_metadata(self, photo_id, metadata):
        with self.db:
            self.db.execute("UPDATE photos SET metadata=?,error='' WHERE source_id=(SELECT source_id FROM photos WHERE id=?)", (json.dumps(metadata), photo_id))

    def set_error(self, photo_id, message):
        with self.db:
            self.db.execute('UPDATE photos SET error=? WHERE id=?', (message, photo_id))

    def rate(self, photo_id, rating):
        with self.db:
            self.db.execute('UPDATE photos SET rating=? WHERE id=?', (max(0, min(5, rating)), photo_id))

    def enqueue(self, ids, destination, fmt, options=None):
        options = ExportOptions.parse(options)
        if fmt not in ('tiff16', 'jpeg'):
            raise ValueError('Unsupported export format')
        dest = Path(destination).resolve()
        dest.mkdir(parents=True, exist_ok=True)
        count = 0
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            # Freeze recipe and descriptive metadata in the same transaction.
            for photo_id in ids:
                row = self.photo(photo_id)
                if row:
                    self.enqueue_one(row, dest, fmt, options)
                    count += 1
        return count

    def enqueue_one(self, row, destination, fmt, options):
        """Insert one complete snapshot inside the caller's batch transaction."""
        from .keyword_exports import KeywordExports, encode, receipt
        snapshot = KeywordExports(self).snapshot(row['id'], options)
        return self.db.execute(
            'INSERT INTO jobs(photo_id,source,recipe,destination,format,created,options,priority,source_id,'
            'metadata_snapshot,export_metadata,orientation) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
            (row['id'],row['path'],row['recipe'],str(destination),fmt,time.time(),json.dumps(options.dict()),
             options.priority,row['source_id'],encode(snapshot),json.dumps(receipt(snapshot)),row['orientation'])).lastrowid

    def all_ids(self, stars=False):
        for row in self.db.execute('SELECT id FROM photos' + (' WHERE rating>=3' if stars else '') + ' ORDER BY id'):
            yield row[0]

    def next_job(self):
        # One atomic statement reserves the job even if another connection is active.
        with self.db:
            row = self.db.execute("UPDATE jobs SET state='running' WHERE id=(SELECT id FROM jobs WHERE state='pending' ORDER BY priority DESC,id LIMIT 1) RETURNING *").fetchone()
        return dict(row) if row else None

    def finish_job(self, job_id, state, error='', peak_mb=0, output=''):
        with self.db:
            self.db.execute('UPDATE jobs SET state=?,error=?,peak_mb=?,output=? WHERE id=?', (state, error, peak_mb, output, job_id))

    def jobs(self, limit=60):
        return [dict(r) for r in self.db.execute('SELECT '+self.job_columns()+' FROM jobs ORDER BY id DESC LIMIT ?', (limit,))]

    def job_columns(self):
        # Queue pages expose the small frozen receipt, never sixty full packets.
        return ','.join('"'+row[1].replace('"','""')+'"' for row in self.db.execute('PRAGMA table_info(jobs)')
                        if row[1] != 'metadata_snapshot')

    def job_counts(self):
        return dict(self.db.execute('SELECT state,count(*) FROM jobs GROUP BY state'))

    def cancel_pending(self):
        with self.db:
            self.db.execute("UPDATE jobs SET state='cancelled' WHERE state='pending'")

    def retry_failed(self):
        with self.db:
            self.db.execute("UPDATE jobs SET state='pending',error='' WHERE state IN ('failed','interrupted','cancelled')")


    def filter_sql(self,mode='all',search='',filters=None,collection_id=None,folder_id=None,include_subfolders=True,*,ordered_page=False):
        if collection_id is not None and folder_id is not None:
            raise ValueError('Choose either a folder or collection source')
        if mode=='previous_import' and (collection_id is not None or folder_id is not None):
            raise ValueError('Previous Import cannot be combined with a folder or collection source')
        clauses=[];params=[]
        if mode=='stars': clauses.append('rating>=3')
        elif mode=='rejects': clauses.append('flag=-1')
        elif mode=='keepers': clauses.append('flag=1')
        elif mode=='missing': clauses.append('missing=1')
        elif mode=='previous_import': clauses.append('source_id IN (SELECT source_id FROM previous_import_sources)')
        elif mode=='duplicates': clauses.append("sha256!='' AND sha256 IN (SELECT sha256 FROM photos WHERE sha256!='' GROUP BY sha256 HAVING count(DISTINCT source_id)>1)")
        elif mode.startswith('burst:'):
            clauses.append('burst=?');params.append(int(mode.split(':')[1]))
        if search:
            clause, values = text_predicate(search[:200])
            clauses.append(clause);params.extend(values)
        if filters:
            clause, values = criteria(filters,ordered_page=ordered_page)
            clauses.append(clause);params.extend(values)
        if collection_id is not None:
            clause, values = Organization(self).collection_predicate(collection_id,ordered_page=ordered_page)
            clauses.append(clause);params.extend(values)
        if folder_id is not None:
            from .folders import Folders
            clause, values = Folders(self).predicate(folder_id,include_subfolders)
            clauses.append(clause);params.extend(values)
        return (' WHERE '+' AND '.join(clauses) if clauses else ''),params

    def filtered_page(self,offset=0,mode='all',search='',filters=None,collection_id=None,sort='imported',descending=True,stacked=True,folder_id=None,include_subfolders=True,*,match_count=None):
        # Dense import-order pages can stop after sixty correlated family checks
        # instead of sorting every matching source. Keep indexed membership for
        # sparse results, other sorts and actual stack projection. match_count
        # comes from the service's exact count under the same catalog lock.
        ordered_page=False
        if (sort=='imported' and match_count is not None and match_count>=60 and
                ('has_snapshots' in (filters or {}) or collection_id is not None)):
            ordered_page=match_count*20>=self.count()
        if stacked and ordered_page:
            from .stacks import Stacks
            scope=Stacks(self).scope(collection_id)
            if scope is not None and self.db.execute('SELECT 1 FROM photo_stacks WHERE scope=? LIMIT 1',(scope,)).fetchone():
                ordered_page=False
        where,params=self.filter_sql(mode,search,filters,collection_id,folder_id,include_subfolders,ordered_page=ordered_page)
        if stacked:
            from .stacks import Stacks
            return Stacks(self).projection(where,params,collection_id,sort,descending,offset)
        if sort not in SORTS:
            raise ValueError('Unsupported library sort')
        order = 'DESC' if descending else 'ASC'
        # Keep large recipe/decoder metadata JSON out of the grid query entirely.
        return [dict(r) for r in self.db.execute(
            f'SELECT {SUMMARY_COLUMNS} FROM photos{where} ORDER BY {SORTS[sort]} {order},id {order} LIMIT 60 OFFSET ?',
            params+[max(0,offset)])]

    def summaries(self, ids):
        if not 1 <= len(ids) <= 60:
            raise ValueError('Summary reads require 1 to 60 photo IDs')
        placeholders=','.join('?' for _ in ids)
        return [dict(row) for row in self.db.execute(
            f'SELECT {SUMMARY_COLUMNS} FROM photos WHERE id IN ({placeholders}) ORDER BY id',ids)]

    def filtered_count(self,mode='all',search='',filters=None,collection_id=None,stacked=True,folder_id=None,include_subfolders=True):
        if folder_id is not None and collection_id is None and mode=='all' and not search and not filters:
            from .folders import Folders
            return Folders(self).count(folder_id,include_subfolders,stacked)
        where,params=self.filter_sql(mode,search,filters,collection_id,folder_id,include_subfolders)
        if stacked:
            from .stacks import Stacks
            return Stacks(self).projection(where,params,collection_id)
        return self.db.execute('SELECT count(*) FROM photos'+where,params).fetchone()[0]

    def filtered_ids(self,mode='all',search=''):
        where,params=self.filter_sql(mode,search)
        for row in self.db.execute('SELECT id FROM photos'+where+' ORDER BY id',params): yield row[0]

    def flag(self,photo_id,value):
        if value not in (-1,0,1): raise ValueError('Invalid pick flag')
        with self.db: self.db.execute('UPDATE photos SET flag=? WHERE id=?',(value,photo_id))

    def bursts(self):
        return [dict(r) for r in self.db.execute('SELECT burst,camera,min(taken) AS taken,count(*) AS count FROM photos WHERE burst>0 AND is_virtual=0 GROUP BY burst HAVING count(*)>1 ORDER BY taken DESC LIMIT 200')]

    def save_version(self,photo_id,name,expected_revision=None,step_id=None):
        from .snapshots import Snapshots
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            return Snapshots(self.db).create(photo_id,name,expected_revision,step_id)

    def versions(self,photo_id):
        return [dict(r) for r in self.db.execute('SELECT * FROM versions WHERE source_id=? ORDER BY id DESC LIMIT 100',(self.photo(photo_id)['source_id'],))]

    def restore_version(self,photo_id,version_id,expected_version_revision=None):
        from .snapshots import Snapshots
        recipe,name=Snapshots(self.db).value(photo_id,version_id,expected_version_revision)
        self.edit(photo_id,recipe,'Snapshot: '+name[:110]);return recipe

    def sync(self,source_id,target_ids,groups):
        source=self.recipe(source_id).dict();keys=[key for group in groups for key in SYNC_GROUPS[group]];count=0
        for id_ in target_ids:
            if id_==source_id: continue
            values=self.recipe(id_).dict();values.update({key:source[key] for key in keys})
            self.edit(id_,Recipe.parse(values),'Selective Sync');count+=1
        return count

    def relink(self,photo_id,new_path):
        p=Path(new_path).resolve(strict=True)
        if p.suffix.lower() not in IMAGE_EXTENSIONS or not p.is_file(): raise ValueError('Not a supported photo')
        old=self.photo(photo_id)
        if Path(old['path']).exists(): raise ValueError('The original is still available; only missing files can be relinked')
        # If a fingerprint exists, require the exact original, not an unrelated file.
        if old['sha256']:
            from .library import hash_file
            if hash_file(p)!=old['sha256']: raise ValueError('New file content differs from the indexed original')
        stat=p.stat()
        with self.db:
            if p.parent != Path(old['path']).parent:
                # A folder stack cannot span two folders. Collection stacks are
                # unaffected by relocation of the family's shared original.
                self.db.execute("DELETE FROM stack_members WHERE scope='folder' AND photo_id IN "
                                '(SELECT id FROM photos WHERE source_id=?)',(old['source_id'],))
            self.db.execute('UPDATE photo_sources SET revision=revision+1 WHERE id=?',(old['source_id'],))
            self.db.execute("UPDATE photos SET path=?,name=?,bytes=?,mtime=?,missing=0,error='' WHERE source_id=?",(str(p),p.name,stat.st_size,stat.st_mtime_ns,old['source_id']))
            self.db.execute("UPDATE jobs SET source=? WHERE source_id=? AND state IN ('pending','interrupted','failed','cancelled')",(str(p),old['source_id']))

    def prioritize(self,job_id,priority=9):
        with self.db: self.db.execute("UPDATE jobs SET priority=? WHERE id=? AND state='pending'",(max(0,min(9,priority)),job_id))


def walk_images(root, cancelled=lambda: False):
    """Stream directory entries without following symlinks or retaining a file list."""
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if not d.startswith('.') and not Path(directory, d).is_symlink()]
        if cancelled():
            return
        for name in files:
            if cancelled():
                return
            if not name.startswith('.') and Path(name).suffix.lower() in IMAGE_EXTENSIONS:
                yield str(Path(directory, name))
