"""Versioned recipe snapshots shared by a source's master and virtual copies.

Inputs: one catalog connection, captured revisions and explicit named actions.
Outputs: bounded alphabetical summaries and frozen recipe values. Callers own
write transactions. Snapshot identities never repeat; list revisions invalidate
name-based cursors. No pixels, originals, metadata/orientation writes or global
undo. Legacy duplicate names and payloads are preserved by migration.
"""
import json
import time
import unicodedata

from .develop_history import DevelopHistory
from .model import Recipe
from .organization import folded

PAGE = 60
SUMMARY = 'id,photo_id,name,created,updated,revision'


def migrate(db):
    if db.execute('PRAGMA user_version').fetchone()[0] >= 24:
        return
    db.execute('BEGIN IMMEDIATE')
    try:
        db.execute('ALTER TABLE versions ADD COLUMN revision INTEGER NOT NULL DEFAULT 0')
        db.execute('ALTER TABLE versions ADD COLUMN updated REAL NOT NULL DEFAULT 0')
        db.execute("ALTER TABLE versions ADD COLUMN name_key TEXT NOT NULL DEFAULT ''")
        db.execute('UPDATE versions SET updated=created,name_key=casefold(name)')
        db.execute('CREATE INDEX versions_alphabetical ON versions(source_id,name_key,id)')
        db.execute('ALTER TABLE photo_sources ADD COLUMN snapshots_revision INTEGER NOT NULL DEFAULT 0')
        db.execute('CREATE TABLE snapshot_identity(id INTEGER PRIMARY KEY CHECK(id=1),next_id INTEGER NOT NULL)')
        db.execute('INSERT INTO snapshot_identity SELECT 1,COALESCE(max(id),0)+1 FROM versions')
        db.execute('PRAGMA user_version=24')
        db.commit()
    except BaseException:
        db.rollback()
        raise


class Snapshots:
    def __init__(self, db):
        self.db = db

    def family(self, photo_id, recipe=False):
        row = self.db.execute('SELECT p.id,p.source_id,p.revision,s.snapshots_revision' +
            (',p.recipe' if recipe else '') + ' FROM photos p JOIN photo_sources s ON s.id=p.source_id '
            'WHERE p.id=?', (photo_id,)).fetchone()
        if row is None:
            raise ValueError('Photo does not exist')
        return row

    def entry(self, source_id, version_id, expected_version_revision=None, recipe=False):
        row = self.db.execute('SELECT ' + SUMMARY + (',recipe' if recipe else '') +
            ' FROM versions WHERE id=? AND source_id=?', (version_id, source_id)).fetchone()
        if row is None:
            raise ValueError('Snapshot does not exist for this photo family')
        if expected_version_revision is not None and row['revision'] != expected_version_revision:
            raise ValueError('Snapshot conflict: settings or name changed; refresh before applying this action')
        return row

    def name(self, source_id, name, excluding=None):
        if not isinstance(name, str):
            raise ValueError('Snapshot name must be text')
        name = unicodedata.normalize('NFC', name.strip())
        if not name or len(name) > 120 or any(ord(c) < 32 or ord(c) == 127 for c in name):
            raise ValueError('Snapshot name must contain 1 to 120 characters without control characters')
        row = self.db.execute('SELECT id FROM versions WHERE source_id=? AND name_key=? '
            'AND id!=? LIMIT 1', (source_id, folded(name), excluding or 0)).fetchone()
        if row is not None:
            raise ValueError('A snapshot with this name already exists; choose another name or explicitly update it')
        return name

    def touch(self, source_id):
        self.db.execute('UPDATE photo_sources SET snapshots_revision=snapshots_revision+1 WHERE id=?', (source_id,))

    def receipt(self, photo_id, version_id, changed):
        family = self.family(photo_id)
        return {'photo_id': photo_id, 'source_id': family['source_id'],
                'snapshots_revision': family['snapshots_revision'], 'changed': changed,
                'version': dict(self.entry(family['source_id'], version_id))}

    def create(self, photo_id, name, expected_revision=None, step_id=None):
        family = self.family(photo_id, recipe=True)
        if expected_revision is not None and expected_revision != family['revision']:
            raise ValueError('Edit conflict: photo changed; refresh before saving a snapshot')
        if step_id is not None and expected_revision is None:
            raise ValueError('Creating a history snapshot requires the captured photo revision')
        name = self.name(family['source_id'], name)
        recipe = (DevelopHistory(self.db).value(photo_id, step_id) if step_id is not None
                  else Recipe.parse(json.loads(family['recipe'])))
        identity = self.db.execute('SELECT next_id FROM snapshot_identity WHERE id=1').fetchone()[0]
        if identity > 2**53-1:
            raise ValueError('Snapshot identity limit reached')
        self.db.execute('UPDATE snapshot_identity SET next_id=next_id+1 WHERE id=1')
        now = time.time()
        self.db.execute('INSERT INTO versions(id,photo_id,name,recipe,created,source_id,updated,name_key) '
            'VALUES(?,?,?,?,?,?,?,?)', (identity, photo_id, name, json.dumps(recipe.dict()), now,
                                      family['source_id'], now, folded(name)))
        self.touch(family['source_id'])
        return self.receipt(photo_id, identity, True)

    def page(self, photo_id, after_id=None, expected_snapshots_revision=None, known_revision=None):
        family = self.family(photo_id)
        revision = family['snapshots_revision']
        result = {'photo_id': photo_id, 'source_id': family['source_id'],
                  'photo_revision': family['revision'], 'snapshots_revision': revision}
        if after_id is not None and (expected_snapshots_revision is None or known_revision is not None):
            raise ValueError('Snapshot paging requires its captured list revision and no conditional refresh')
        if expected_snapshots_revision is not None and expected_snapshots_revision != revision:
            raise ValueError('Snapshot list changed; start again from the first page')
        if known_revision == revision:
            return {**result, 'unchanged': True}
        params = [family['source_id']]
        where = 'source_id=?'
        if after_id is not None:
            cursor = self.db.execute('SELECT name_key,id FROM versions WHERE source_id=? AND id=?',
                                     (family['source_id'], after_id)).fetchone()
            if cursor is None:
                raise ValueError('Snapshot page cursor does not exist for this photo family')
            where += ' AND (name_key,id)>(?,?)'
            params.extend(cursor)
        rows = self.db.execute('SELECT ' + SUMMARY + ' FROM versions WHERE ' + where +
            ' ORDER BY name_key,id LIMIT ?', (*params, PAGE+1)).fetchall()
        return {**result, 'unchanged': False, 'versions': [dict(row) for row in rows[:PAGE]],
                'next_after': rows[PAGE-1]['id'] if len(rows) > PAGE else None}

    def rename(self, photo_id, version_id, expected_version_revision, name):
        family = self.family(photo_id)
        row = self.entry(family['source_id'], version_id, expected_version_revision)
        # Preserve legacy equal-name no-ops even when old catalogs contain duplicates.
        if name == row['name']:
            return self.receipt(photo_id, version_id, False)
        name = self.name(family['source_id'], name, excluding=version_id)
        changed = name != row['name']
        if changed:
            self.db.execute('UPDATE versions SET name=?,name_key=?,revision=revision+1,updated=? WHERE id=?',
                            (name, folded(name), time.time(), version_id))
            self.touch(family['source_id'])
        return self.receipt(photo_id, version_id, changed)

    def update(self, photo_id, version_id, expected_version_revision, expected_revision):
        family = self.family(photo_id, recipe=True)
        if family['revision'] != expected_revision:
            raise ValueError('Edit conflict: photo changed; refresh before updating a snapshot')
        row = self.entry(family['source_id'], version_id, expected_version_revision, recipe=True)
        recipe = Recipe.parse(json.loads(family['recipe'])).dict()
        changed = recipe != Recipe.parse(json.loads(row['recipe'])).dict()
        if changed:
            self.db.execute('UPDATE versions SET recipe=?,revision=revision+1,updated=? WHERE id=?',
                            (json.dumps(recipe), time.time(), version_id))
            self.touch(family['source_id'])
        return self.receipt(photo_id, version_id, changed)

    def delete(self, photo_id, version_id, expected_version_revision):
        family = self.family(photo_id)
        self.entry(family['source_id'], version_id, expected_version_revision)
        self.db.execute('DELETE FROM versions WHERE id=?', (version_id,))
        self.touch(family['source_id'])
        return {'deleted': version_id, 'source_id': family['source_id'],
                'snapshots_revision': family['snapshots_revision']+1}

    def value(self, photo_id, version_id, expected_version_revision=None):
        family = self.family(photo_id)
        row = self.entry(family['source_id'], version_id, expected_version_revision, recipe=True)
        return Recipe.parse(json.loads(row['recipe'])), row['name']
