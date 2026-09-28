"""Durable, bounded plans for reconnecting missing catalog folder trees.

Inputs: an existing catalog folder, chosen replacement directory and revisions.
Outputs: staged file checks, cancellable progress and one atomic catalog remap.
Originals are read-only. Filesystem hashing/stat checks run outside the service
catalog lock; SQL application preserves edits, copies, keywords and whole stacks.
This is not filesystem move/rename, folder synchronization or photo deduplication.
"""
import json
import os
from pathlib import Path
import stat
import time

from .folders import Folders, chain, descendants

ACTIVE = ('planning', 'scanning', 'ready', 'verifying', 'interrupted')


class RelocationBusy(ValueError):
    """A retryable admission failure; retain the already verified staging plan."""


def migrate(db):
    if db.execute('PRAGMA user_version').fetchone()[0] >= 9:
        return
    statements = (
        'CREATE TABLE folder_maintenance(id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL CHECK(enabled IN (0,1)))',
        'INSERT INTO folder_maintenance VALUES(1,1)',
        'CREATE TABLE folder_relocations(id INTEGER PRIMARY KEY AUTOINCREMENT, folder_id INTEGER NOT NULL, '
        'source TEXT NOT NULL, destination TEXT NOT NULL, destination_identity TEXT NOT NULL, '
        "state TEXT NOT NULL DEFAULT 'planning', revision INTEGER NOT NULL DEFAULT 0, "
        'folder_revision INTEGER NOT NULL, physical_count INTEGER NOT NULL DEFAULT 0, '
        'photo_count INTEGER NOT NULL DEFAULT 0, folder_count INTEGER NOT NULL DEFAULT 0, '
        'merge_count INTEGER NOT NULL DEFAULT 0, scanned INTEGER NOT NULL DEFAULT 0, '
        'verified INTEGER NOT NULL DEFAULT 0, unverified INTEGER NOT NULL DEFAULT 0, '
        'missing INTEGER NOT NULL DEFAULT 0, conflicts INTEGER NOT NULL DEFAULT 0, checked INTEGER NOT NULL DEFAULT 0, '
        "error TEXT NOT NULL DEFAULT '', result_folder_id INTEGER, created REAL NOT NULL)",
        "CREATE UNIQUE INDEX relocation_active ON folder_relocations((1)) WHERE state IN "
        "('planning','scanning','ready','verifying','interrupted')",
        'CREATE TABLE relocation_folders(plan_id INTEGER NOT NULL, folder_id INTEGER NOT NULL, '
        'source TEXT NOT NULL, destination TEXT NOT NULL, merge_id INTEGER, favorite INTEGER NOT NULL, '
        'color_label TEXT NOT NULL, revision INTEGER NOT NULL, direct_count INTEGER NOT NULL, total_count INTEGER NOT NULL, PRIMARY KEY(plan_id,folder_id))',
        'CREATE UNIQUE INDEX relocation_folder_path ON relocation_folders(plan_id,destination)',
        'CREATE TABLE relocation_files(plan_id INTEGER NOT NULL, source_id INTEGER NOT NULL, '
        'source_revision INTEGER NOT NULL, source TEXT NOT NULL, destination TEXT NOT NULL, '
        'sha256 TEXT NOT NULL, source_bytes INTEGER NOT NULL, source_mtime INTEGER NOT NULL, bytes INTEGER NOT NULL, mtime INTEGER NOT NULL, '
        "state TEXT NOT NULL DEFAULT 'pending', fingerprint TEXT NOT NULL DEFAULT '', "
        "error TEXT NOT NULL DEFAULT '', PRIMARY KEY(plan_id,source_id))",
        'CREATE INDEX relocation_file_state ON relocation_files(plan_id,state,source_id)',
        "CREATE INDEX relocation_file_issues ON relocation_files(plan_id,source_id) WHERE state IN ('blocked','missing')",
        'PRAGMA user_version=9',
    )
    with db:
        db.execute('BEGIN IMMEDIATE')
        for statement in statements:
            db.execute(statement)
        trigger = db.execute("SELECT sql FROM sqlite_master WHERE name='folder_photo_relinked'").fetchone()
        if not trigger or 'WHEN NEW.path!=OLD.path' not in trigger[0]:
            raise ValueError('Unsupported folder maintenance trigger; migration was not applied')
        db.execute('DROP TRIGGER folder_photo_relinked')
        db.execute(trigger[0].replace('WHEN NEW.path!=OLD.path',
            'WHEN NEW.path!=OLD.path AND (SELECT enabled FROM folder_maintenance WHERE id=1)=1'))


def identity(path, directory=False):
    try:
        value = os.stat(path)
    except (FileNotFoundError, NotADirectoryError):
        return None
    if directory:
        if not stat.S_ISDIR(value.st_mode):
            raise ValueError('Choose an existing directory')
        # Directory mtime changes when unrelated files are added; inode/device
        # identify the selected location without rejecting those harmless changes.
        return [value.st_dev, value.st_ino]
    if not stat.S_ISREG(value.st_mode):
        raise ValueError('The proposed original is not a regular file')
    return [value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns]


def inspect_file(row, cancelled):
    """One bounded-memory read, with no catalog connection held while hashing."""
    if cancelled():
        raise InterruptedError('Folder relocation cancelled')
    try:
        before = identity(row['destination'])
        if before is None:
            return {**row, 'state':'missing', 'fingerprint':'null', 'error':''}
        if row['sha256']:
            from .library import hash_file
            if hash_file(row['destination'], cancelled) != row['sha256']:
                raise ValueError('Content differs from the indexed original')
        after = identity(row['destination'])
        if before != after:
            raise ValueError('The proposed original changed during verification')
        return {**row, 'state':'verified' if row['sha256'] else 'unverified',
                'fingerprint':json.dumps(after), 'bytes':after[2], 'mtime':after[3], 'error':''}
    except InterruptedError:
        raise
    except (OSError, ValueError) as error:
        return {**row, 'state':'blocked', 'fingerprint':'', 'error':str(error)}


class Relocations:
    def __init__(self, catalog):
        self.catalog = catalog
        self.db = catalog.db

    def recover(self):
        with self.db:
            self.db.execute("UPDATE folder_relocations SET state='interrupted',revision=revision+1, "
                "error='Verification was interrupted; continue scanning or cancel this plan' "
                "WHERE state IN ('scanning','verifying')")

    def row(self, plan_id):
        row = self.db.execute('SELECT * FROM folder_relocations WHERE id=?', (plan_id,)).fetchone()
        if not row:
            raise ValueError('Folder relocation plan does not exist')
        return dict(row)

    def get(self, plan_id=None, offset=0, issues_only=True):
        if plan_id is None:
            row = self.db.execute('SELECT id FROM folder_relocations ORDER BY id DESC LIMIT 1').fetchone()
            if not row:
                return {'plan':None, 'items':[], 'total':0, 'offset':0}
            plan_id = row[0]
        plan = self.row(plan_id)
        where = " AND state IN ('blocked','missing')" if issues_only else ''
        # Progress counters are committed with each page. Counting the growing
        # issue set on every page would make a whole-tree scan quadratic.
        total = (plan['conflicts']+plan['missing'] if issues_only else plan['physical_count']) if plan['state'] in ACTIVE else 0
        offset = min(offset, max(0, (total-1)//60*60))
        items = [dict(row) for row in self.db.execute('SELECT source_id,source,destination,state,error '
            'FROM relocation_files WHERE plan_id=?'+where+' ORDER BY source_id LIMIT 60 OFFSET ?', (plan_id, offset))] if total else []
        return {'plan':plan, 'items':items, 'total':total, 'offset':offset, 'page_size':60}

    def check(self, plan_id, revision, states):
        plan = self.row(plan_id)
        if plan['revision'] != revision or plan['state'] not in states:
            raise ValueError('Folder relocation changed; read the plan before continuing')
        if plan['folder_revision'] != Folders(self.catalog).revision():
            raise ValueError('The folder catalog changed; cancel this plan and scan again')
        return plan

    def prepare(self, folder_id, destination, expected_revision):
        directory = Path(destination).expanduser().resolve(strict=True)
        fingerprint = identity(directory, directory=True)
        if fingerprint is None:
            raise ValueError('Choose an existing directory')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            folders = Folders(self.catalog)
            if folders.revision() != expected_revision:
                raise ValueError('The folder catalog changed; refresh before locating it')
            folder = folders.get(folder_id)
            source = folder['path']
            if os.path.exists(source):
                raise ValueError('The original folder is still available; choose a missing folder')
            destination = str(directory)
            try:
                common = os.path.commonpath([source, destination])
            except ValueError:
                common = None  # Different Windows volumes are disjoint trees.
            if common in (source, destination):
                raise ValueError('The old and replacement folder trees must not overlap')
            if self.db.execute("SELECT 1 FROM folder_relocations WHERE state IN "
                               "('planning','scanning','ready','verifying','interrupted')").fetchone():
                raise ValueError('Finish or cancel the existing folder relocation first')
            # Plans contain disposable staging state. Keep 32 small terminal
            # receipts; active plans alone retain their complete on-disk mapping.
            self.db.execute('DELETE FROM folder_relocations WHERE id NOT IN '
                            '(SELECT id FROM folder_relocations ORDER BY id DESC LIMIT 31)')
            plan_id = self.db.execute('INSERT INTO folder_relocations(folder_id,source,destination,destination_identity,'
                'folder_revision,photo_count,created) VALUES(?,?,?,?,?,?,?)',
                (folder_id, source, destination, json.dumps(fingerprint), expected_revision, folder['total_count'], time.time())).lastrowid
            prefix = len(source)+1
            self.db.execute('INSERT INTO relocation_folders SELECT ?,f.id,f.path,? || substr(f.path,?),'
                '(SELECT id FROM catalog_folders existing WHERE existing.path=? || substr(f.path,?)), '
                'f.favorite,f.color_label,f.revision,f.direct_count,f.total_count FROM catalog_folders f WHERE f.path IN ('+descendants('?')+')',
                (plan_id, destination, prefix, destination, prefix, source))
            self.db.execute('INSERT INTO relocation_files(plan_id,source_id,source_revision,source,destination,sha256,source_bytes,source_mtime,bytes,mtime) '
                'SELECT ?,p.source_id,s.revision,p.path,? || substr(p.path,?),p.sha256,p.bytes,p.mtime,p.bytes,p.mtime '
                'FROM photos p JOIN photo_sources s ON s.id=p.source_id WHERE p.is_virtual=0 AND p.id IN '
                '(SELECT photo_id FROM folder_photos WHERE folder_path IN ('+descendants('?')+'))',
                (plan_id, destination, prefix, source))
            self.db.execute('UPDATE folder_relocations SET physical_count=(SELECT count(*) FROM relocation_files WHERE plan_id=?),'
                'folder_count=(SELECT count(*) FROM relocation_folders WHERE plan_id=?),'
                'merge_count=(SELECT count(*) FROM relocation_folders WHERE plan_id=? AND merge_id IS NOT NULL) WHERE id=?',
                (plan_id, plan_id, plan_id, plan_id))
        return self.get(plan_id)

    def start_scan(self, plan_id, expected_revision):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            plan = self.check(plan_id, expected_revision, ('planning','interrupted'))
            self.db.execute("UPDATE folder_relocations SET state='scanning',error='',revision=revision+1 WHERE id=?", (plan_id,))
            rows = [dict(row) for row in self.db.execute("SELECT * FROM relocation_files WHERE plan_id=? AND state='pending' "
                                                        'ORDER BY source_id LIMIT 60', (plan_id,))]
        return self.row(plan_id), rows

    def finish_scan(self, plan_id, revision, rows):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            self.check(plan_id, revision, ('scanning',))
            for row in rows:
                collision = self.db.execute('SELECT 1 FROM photos WHERE is_virtual=0 AND path=? AND source_id!=?',
                                            (row['destination'], row['source_id'])).fetchone()
                if collision:
                    row = {**row, 'state':'blocked', 'error':'A different catalog photo already uses this destination'}
                self.db.execute('UPDATE relocation_files SET state=?,fingerprint=?,bytes=?,mtime=?,error=? '
                    'WHERE plan_id=? AND source_id=?', (row['state'], row['fingerprint'], row['bytes'], row['mtime'],
                                                       row['error'], plan_id, row['source_id']))
            counts = {}
            # Collision states are set on disk after inspection, so count only
            # this bounded page from SQLite before advancing aggregate progress.
            ids = [row['source_id'] for row in rows]
            if ids:
                counts = dict(self.db.execute('SELECT state,count(*) FROM relocation_files WHERE plan_id=? '
                    'AND source_id IN ('+','.join('?' for _ in ids)+') GROUP BY state', [plan_id,*ids]))
            remaining = self.db.execute("SELECT 1 FROM relocation_files WHERE plan_id=? AND state='pending' LIMIT 1", (plan_id,)).fetchone()
            self.db.execute('UPDATE folder_relocations SET state=?,scanned=scanned+?,verified=verified+?,unverified=unverified+?, '
                'missing=missing+?,conflicts=conflicts+?,revision=revision+1 WHERE id=?',
                ('planning' if remaining else 'ready', len(rows), counts.get('verified',0), counts.get('unverified',0),
                 counts.get('missing',0), counts.get('blocked',0), plan_id))
        return self.get(plan_id)

    def start_apply(self, plan_id, expected_revision):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            plan = self.check(plan_id, expected_revision, ('ready',))
            if plan['conflicts']:
                raise ValueError('Resolve the reported file conflicts and scan again before relinking')
            self.db.execute("UPDATE folder_relocations SET state='verifying',checked=0,error='',revision=revision+1 WHERE id=?", (plan_id,))
        return self.row(plan_id)

    def validation_page(self, plan_id, revision, after_source_id):
        self.check(plan_id, revision, ('verifying',))
        return [dict(row) for row in self.db.execute('SELECT source_id,destination,fingerprint FROM relocation_files '
            'WHERE plan_id=? AND source_id>? ORDER BY source_id LIMIT 60', (plan_id, after_source_id))]

    def terminal(self, plan_id, state, error=''):
        with self.db:
            row = self.row(plan_id)
            if row['state'] in ACTIVE:
                self.db.execute('UPDATE folder_relocations SET state=?,error=?,revision=revision+1 WHERE id=?',
                                (state, error, plan_id))
                self.discard_items(plan_id)
        return self.get(plan_id)

    def discard_items(self, plan_id):
        for table in ('relocation_files', 'relocation_folders'):
            self.db.execute(f'DELETE FROM {table} WHERE plan_id=?', (plan_id,))

    def defer_apply(self, plan_id, revision, error):
        with self.db:
            if self.row(plan_id)['state'] not in ACTIVE:
                return self.get(plan_id)
            self.check(plan_id, revision, ('verifying',))
            self.db.execute("UPDATE folder_relocations SET state='ready',error=?,revision=revision+1 WHERE id=?", (error,plan_id))
        return self.get(plan_id)

    def apply(self, plan_id, revision):
        """After external filesystem checks, apply the entire mapping in one write."""
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            plan = self.check(plan_id, revision, ('verifying',))
            if self.db.execute('SELECT 1 FROM relocation_files r LEFT JOIN photo_sources s ON s.id=r.source_id '
                'WHERE r.plan_id=? AND (s.id IS NULL OR s.revision!=r.source_revision)', (plan_id,)).fetchone():
                raise ValueError('A photo family changed; cancel this plan and scan again')
            if self.db.execute('SELECT 1 FROM relocation_files r LEFT JOIN photos p ON p.source_id=r.source_id AND p.is_virtual=0 '
                'WHERE r.plan_id=? AND (p.id IS NULL OR p.path!=r.source OR p.sha256!=r.sha256 OR p.bytes!=r.source_bytes '
                'OR p.mtime!=r.source_mtime)', (plan_id,)).fetchone():
                raise ValueError('Source metadata changed; cancel this plan and scan again')
            if self.db.execute("SELECT 1 FROM jobs WHERE state='running' AND source_id IN "
                '(SELECT source_id FROM relocation_files WHERE plan_id=?) LIMIT 1', (plan_id,)).fetchone():
                raise RelocationBusy('Wait for the affected export to finish before relinking')
            root = plan['destination']
            self.db.execute('INSERT OR IGNORE INTO catalog_folders(path,name,parent_path) '
                'WITH RECURSIVE parents(path) AS (SELECT ? UNION ALL SELECT folder_parent(path) FROM parents '
                'WHERE folder_parent(path) IS NOT NULL) SELECT path,folder_name(path),folder_parent(path) FROM parents', (root,))
            self.db.execute('INSERT OR IGNORE INTO catalog_folders(path,name,parent_path) '
                'SELECT destination,folder_name(destination),folder_parent(destination) FROM relocation_folders WHERE plan_id=?', (plan_id,))
            # One transaction suspends only per-photo path maintenance. SQLite
            # permits no concurrent writer, and rollback also restores the switch.
            # Counts are updated per folder/ancestor, avoiding O(photos * depth)
            # recursive trigger work for a whole-tree move. Other triggers remain.
            self.db.execute('UPDATE folder_maintenance SET enabled=0 WHERE id=1')
            self.db.execute('UPDATE photos SET '
                'path=r.destination,name=folder_name(r.destination),bytes=r.bytes,mtime=r.mtime,missing=(r.state=\'missing\'),error=\'\' '
                'FROM relocation_files r WHERE r.plan_id=? AND photos.source_id=r.source_id', (plan_id,))
            self.db.execute('UPDATE folder_photos SET folder_path=folder_parent(r.destination) FROM photos p '
                'JOIN relocation_files r ON r.source_id=p.source_id WHERE r.plan_id=? AND photo_id=p.id', (plan_id,))
            self.db.execute('UPDATE catalog_folders SET total_count=total_count-? WHERE path IN ('+chain('?')+')',
                            (plan['photo_count'], os.path.dirname(plan['source'])))
            self.db.execute('UPDATE catalog_folders SET total_count=total_count+? WHERE path IN ('+chain('?')+')',
                            (plan['photo_count'], os.path.dirname(root)))
            self.db.execute('UPDATE catalog_folders SET direct_count=catalog_folders.direct_count+r.direct_count, '
                'total_count=catalog_folders.total_count+r.total_count FROM relocation_folders r '
                'WHERE r.plan_id=? AND path=r.destination', (plan_id,))
            self.db.execute('UPDATE folder_maintenance SET enabled=1 WHERE id=1')
            self.db.execute('UPDATE photo_sources SET revision=revision+1 WHERE id IN '
                            '(SELECT source_id FROM relocation_files WHERE plan_id=?)', (plan_id,))
            self.db.execute("UPDATE jobs SET source=r.destination FROM relocation_files r WHERE r.plan_id=? "
                "AND jobs.source_id=r.source_id AND jobs.state IN ('pending','interrupted','failed','cancelled')", (plan_id,))
            self.db.execute("UPDATE photo_stacks SET folder=r.destination FROM relocation_folders r "
                            "WHERE r.plan_id=? AND scope='folder' AND folder=r.source", (plan_id,))
            self.db.execute('DELETE FROM catalog_folders WHERE id IN '
                            '(SELECT folder_id FROM relocation_folders WHERE plan_id=?)', (plan_id,))
            # New locations inherit source IDs. Existing destination nodes retain
            # their own IDs; merged-away IDs are retired rather than redirected.
            self.db.execute('UPDATE catalog_folders SET id=r.folder_id,revision=r.revision+1,favorite=r.favorite,color_label=r.color_label '
                'FROM relocation_folders r WHERE r.plan_id=? AND r.merge_id IS NULL AND path=r.destination', (plan_id,))
            self.db.execute("UPDATE catalog_folders SET revision=catalog_folders.revision+1, "
                "favorite=(catalog_folders.favorite OR r.favorite),color_label=CASE WHEN catalog_folders.color_label='none' "
                'THEN r.color_label ELSE catalog_folders.color_label END FROM relocation_folders r '
                'WHERE r.plan_id=? AND r.merge_id=catalog_folders.id', (plan_id,))
            self.db.execute('UPDATE catalog_folders SET is_root=1 WHERE path=? AND NOT EXISTS '
                '(SELECT 1 FROM catalog_folders WHERE is_root=1 AND path!=? AND path IN ('+chain('?')+'))', (root,root,root))
            root_id = self.db.execute('SELECT id FROM catalog_folders WHERE path=?', (root,)).fetchone()[0]
            self.db.execute('UPDATE folder_state SET revision=revision+1')
            self.db.execute("UPDATE folder_relocations SET state='applied',result_folder_id=?,revision=revision+1,error='' WHERE id=?", (root_id,plan_id))
            self.discard_items(plan_id)
        return self.get(plan_id)
