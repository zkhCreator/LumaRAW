"""Catalog-only variants of a shared physical source.

Inputs: bounded photo targets with recipe/metadata/source revisions. Outputs:
atomic copies, master-role changes and removal receipts. Each copy owns its edits,
descriptive metadata and history; named snapshots and source relocation are shared.
Never copy, rename or delete originals. Export snapshots outlive removed copies.
Stable, non-reused photo IDs protect references held by jobs and other clients.
"""
import re
import time


def migrate(db):
    if db.execute('PRAGMA user_version').fetchone()[0] >= 3:
        return
    # SQLite cannot drop a column UNIQUE constraint in place. Rebuild just photos,
    # retaining its columns, data, indexes and triggers in one rollback-safe unit.
    db.execute('BEGIN IMMEDIATE')
    try:
        columns = {row[1] for row in db.execute('PRAGMA table_info(photos)')}
        if 'source_id' not in columns:
            schema = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='photos'").fetchone()[0]
            schema, replaced = re.subn(r'\bpath\s+TEXT(\s+NOT\s+NULL)?\s+UNIQUE',
                                      r'path TEXT\1', schema, flags=re.I)
            if replaced != 1:
                raise ValueError('Unsupported photos schema; source uniqueness migration was not applied')
            schema = re.sub(r'\bid\s+INTEGER\s+PRIMARY\s+KEY\b(?!\s+AUTOINCREMENT)',
                            'id INTEGER PRIMARY KEY AUTOINCREMENT', schema, count=1, flags=re.I)
            schema = re.sub(r'CREATE TABLE\s+(?:IF NOT EXISTS\s+)?["`\[]?photos["`\]]?',
                            'CREATE TABLE photos_v3', schema, count=1, flags=re.I)
            objects = [row[0] for row in db.execute("SELECT sql FROM sqlite_master WHERE tbl_name='photos' "
                       "AND type IN ('index','trigger') AND sql IS NOT NULL")]
            db.execute(schema)
            db.execute('INSERT INTO photos_v3 SELECT * FROM photos')
            db.execute('DROP TABLE photos')
            db.execute('ALTER TABLE photos_v3 RENAME TO photos')
            for statement in objects:
                db.execute(statement)
            db.execute('ALTER TABLE photos ADD COLUMN source_id INTEGER NOT NULL DEFAULT 0')
            db.execute('ALTER TABLE photos ADD COLUMN is_virtual INTEGER NOT NULL DEFAULT 0 CHECK(is_virtual IN (0,1))')
            db.execute("ALTER TABLE photos ADD COLUMN copy_name TEXT NOT NULL DEFAULT ''")
            db.execute('CREATE TABLE photo_sources (id INTEGER PRIMARY KEY AUTOINCREMENT, '
                       'revision INTEGER NOT NULL DEFAULT 0, next_copy INTEGER NOT NULL DEFAULT 1)')
            db.execute('INSERT INTO photo_sources(id) SELECT id FROM photos')
            db.execute('UPDATE photos SET source_id=id')
            db.execute('CREATE UNIQUE INDEX photo_original_path ON photos(path) WHERE is_virtual=0')
            db.execute('CREATE UNIQUE INDEX photo_master ON photos(source_id) WHERE is_virtual=0')
            db.execute('CREATE INDEX photo_source ON photos(source_id,id)')
            db.execute('CREATE INDEX photo_virtual ON photos(is_virtual,id)')
            db.execute('CREATE TRIGGER photo_source_import AFTER INSERT ON photos WHEN NEW.source_id=0 BEGIN '
                       'INSERT INTO photo_sources(revision) VALUES(0); '
                       'UPDATE photos SET source_id=last_insert_rowid() WHERE id=NEW.id; END')
            for table in ('versions', 'jobs'):
                db.execute(f'ALTER TABLE {table} ADD COLUMN source_id INTEGER NOT NULL DEFAULT 0')
                db.execute(f'UPDATE {table} SET source_id=COALESCE((SELECT source_id FROM photos '
                           f'WHERE photos.id={table}.photo_id),0)')
                db.execute(f'CREATE INDEX {table}_source ON {table}(source_id,id)')
        db.execute('PRAGMA user_version=3')
        db.commit()
    except BaseException:
        db.rollback()
        raise


class VirtualCopies:
    def __init__(self, catalog):
        self.catalog = catalog
        self.db = catalog.db

    def check(self, target, source=False):
        row = self.catalog.photo(target['photo_id'])
        if not row:
            raise ValueError('Photo does not exist')
        if row['revision'] != target['expected_revision']:
            raise ValueError('Edit conflict; reload the photo')
        if row['metadata_revision'] != target['expected_metadata_revision']:
            raise ValueError('Metadata conflict; reload the photo')
        if source and row['source_revision'] != target['expected_source_revision']:
            raise ValueError('Source conflict; reload the photo family')
        return row

    def copy_name(self, source_id):
        number = self.db.execute('UPDATE photo_sources SET next_copy=next_copy+1 WHERE id=? '
                                 'RETURNING next_copy-1', (source_id,)).fetchone()[0]
        return f'Copy {number}'

    def touch(self, source_ids):
        self.db.executemany('UPDATE photo_sources SET revision=revision+1 WHERE id=?',
                            [(id_,) for id_ in set(source_ids)])

    def create(self, targets, collection_id=None, expected_collection_revision=None):
        from .collections import Collections
        from .stacks import Stacks
        if len({target['photo_id'] for target in targets}) != len(targets):
            raise ValueError('Duplicate photo targets are not allowed')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            rows = [self.check(target) for target in targets]
            collection = None
            if collection_id is not None:
                collection = Collections(self.catalog).checked(collection_id, expected_collection_revision)
                if collection['kind'] not in ('regular', 'quick'):
                    raise ValueError('Copies can only be added directly to regular or Quick collections')
            columns = [row[1] for row in self.db.execute('PRAGMA table_info(photos)') if row[1] != 'id']
            ids = []
            for row in rows:
                values = {**row, 'is_virtual':1, 'copy_name':self.copy_name(row['source_id']),
                          'created':time.time(), 'revision':0, 'metadata_revision':0,
                          'history_base_recipe':None,'history_base_label':'Virtual Copy',
                          'history_base_created':None,'history_cursor':0}
                new_id = self.db.execute('INSERT INTO photos (' + ','.join(columns) + ') VALUES (' +
                    ','.join('?' for _ in columns) + ')', [values[key] for key in columns]).lastrowid
                self.db.execute('INSERT INTO keyword_photos SELECT ?,keyword_id FROM keyword_photos WHERE photo_id=?',
                                (new_id, row['id']))
                if collection:
                    self.db.execute('INSERT INTO collection_photos VALUES(?,?)', (collection_id, new_id))
                ids.append(new_id)
                Stacks(self.catalog).copy_created(row,new_id)
            self.touch(row['source_id'] for row in rows)
            if collection:
                self.db.execute('UPDATE collections SET revision=revision+1 WHERE id=?', (collection_id,))
                Collections(self.catalog).touch_ancestors(collection['parent_id'])
        return {'photos':self.catalog.summaries(ids), 'created':len(ids)}

    def promote(self, target):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            row = self.check(target, source=True)
            if not row['is_virtual']:
                raise ValueError('The photo is already the master')
            old = self.db.execute('SELECT id,copy_name FROM photos WHERE source_id=? AND is_virtual=0',
                                  (row['source_id'],)).fetchone()
            name = old['copy_name'] or self.copy_name(row['source_id'])
            self.db.execute('UPDATE photos SET is_virtual=1,copy_name=?,metadata_revision=metadata_revision+1 WHERE id=?',
                            (name, old['id']))
            self.db.execute('UPDATE photos SET is_virtual=0 WHERE id=?', (row['id'],))
            self.touch([row['source_id']])
        return self.catalog.photo(row['id'])

    def remove(self, targets):
        from .collections import Collections
        if len({target['photo_id'] for target in targets}) != len(targets):
            raise ValueError('Duplicate photo targets are not allowed')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            rows = [self.check(target, source=True) for target in targets]
            if any(not row['is_virtual'] for row in rows):
                raise ValueError('Only virtual copies can be removed with this command')
            ids = [row['id'] for row in rows]
            placeholders = ','.join('?' for _ in ids)
            collections = self.db.execute('SELECT DISTINCT c.id,c.parent_id FROM collections c '
                'JOIN collection_photos m ON m.collection_id=c.id WHERE m.photo_id IN ('+placeholders+')', ids).fetchall()
            for collection in collections:
                self.db.execute('UPDATE collections SET revision=revision+1 WHERE id=?', (collection['id'],))
                Collections(self.catalog).touch_ancestors(collection['parent_id'])
            # Shared snapshots and immutable export jobs intentionally survive.
            for table, column in (('history','photo_id'), ('keyword_photos','photo_id'),
                                  ('collection_photos','photo_id'), ('photos','id')):
                self.db.execute(f'DELETE FROM {table} WHERE {column} IN ({placeholders})', ids)
            self.touch(row['source_id'] for row in rows)
        return {'removed':ids}
