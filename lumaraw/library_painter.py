"""Persistent keyword shortcuts and atomic Library Painter metadata strokes.

Inputs: stable shortcut IDs, explicit new paths, captured photo revisions and
one bounded stroke. Outputs: twenty-path shortcut pages and catalog mutations.
No mouse geometry, pixels, file writes, Develop presets or inferred keywords.
Shortcuts keep identities through rename; removing tags prunes the shortcut.
A stroke validates every target and capacity before writing, and increments each
photo's metadata revision once while preserving its recipe and frozen exports.
"""
import hashlib
import json

from .keywords import Keywords
from .keyword_sets import remember
from .organization import COLORS


def migrate(db):
    if db.execute('PRAGMA user_version').fetchone()[0] >= 14:
        return
    db.execute('BEGIN IMMEDIATE')
    try:
        db.execute('CREATE TABLE keyword_shortcut(keyword_id INTEGER PRIMARY KEY,position INTEGER NOT NULL UNIQUE)')
        db.execute('CREATE TABLE keyword_shortcut_state(id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER NOT NULL)')
        db.execute('INSERT INTO keyword_shortcut_state VALUES(1,0)')
        db.execute('CREATE TRIGGER keyword_shortcut_delete AFTER DELETE ON keywords '
                   'WHEN EXISTS(SELECT 1 FROM keyword_shortcut WHERE keyword_id=OLD.id) BEGIN '
                   'DELETE FROM keyword_shortcut WHERE keyword_id=OLD.id; '
                   'UPDATE keyword_shortcut_state SET revision=revision+1; END')
        db.execute('PRAGMA user_version=14')
        db.commit()
    except BaseException:
        db.rollback()
        raise


class LibraryPainter:
    def __init__(self, catalog):
        self.catalog = catalog
        self.db = catalog.db
        self.tags = Keywords(catalog)

    def revision(self):
        state = self.db.execute('SELECT revision FROM keyword_shortcut_state').fetchone()[0]
        return hashlib.sha256(json.dumps([str(self.catalog.root),state,self.tags.revision()]).encode()).hexdigest()

    def check(self, expected):
        if expected != self.revision():
            raise ValueError('Keyword shortcut or keywords changed; refresh before applying')

    def read(self, offset=0, expected_revision=None):
        if expected_revision is not None:
            self.check(expected_revision)
        ids = [r[0] for r in self.db.execute('SELECT keyword_id FROM keyword_shortcut ORDER BY position')]
        offset = min(offset,max(0,(len(ids)-1)//20*20))
        page = [{'id':id_, 'path':' | '.join(a['name'] for a in self.tags.ancestors(id_))} for id_ in ids[offset:offset+20]]
        return {'keyword_ids':ids, 'keywords':page, 'total':len(ids), 'offset':offset,
                'page_size':20, 'revision':self.revision(), 'keyword_revision':self.tags.revision()}

    def save(self, keyword_ids, expected_revision, keyword_additions=()):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            self.check(expected_revision)
            ids = list(dict.fromkeys(keyword_ids))
            for id_ in ids:
                self.tags.get(id_)
            for value in keyword_additions:
                id_ = self.tags.resolve(value)
                if id_ not in ids:
                    ids.append(id_)
            if len(ids)>100:
                raise ValueError('A keyword shortcut cannot contain more than 100 keywords')
            self.db.execute('DELETE FROM keyword_shortcut')
            self.db.executemany('INSERT INTO keyword_shortcut VALUES(?,?)', ((id_,i) for i,id_ in enumerate(ids)))
            self.db.execute('UPDATE keyword_shortcut_state SET revision=revision+1')
            # The Keyword List displays shortcut membership; invalidate other
            # clients' list snapshots even if no new vocabulary was created.
            self.db.execute('UPDATE keyword_state SET revision=revision+1')
        return self.read()

    def paint(self, targets, kind, value=None, erase=False, expected_shortcut_revision=None):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            ids = self.tags.check_targets(targets)
            keyword_ids = []
            if kind == 'keywords':
                if value is not None:
                    raise ValueError('Keyword painting uses the configured shortcut, not a value')
                self.check(expected_shortcut_revision)
                keyword_ids = [r[0] for r in self.db.execute('SELECT keyword_id FROM keyword_shortcut ORDER BY position')]
                if not keyword_ids:
                    raise ValueError('Set a keyword shortcut before painting')
                if not erase:
                    additions = set(keyword_ids)
                    for photo_id in ids:
                        existing = {r[0] for r in self.db.execute('SELECT keyword_id FROM keyword_photos WHERE photo_id=?',(photo_id,))}
                        if len(existing | additions)>100:
                            raise ValueError('A photo cannot have more than 100 directly assigned keywords')
                for photo_id in ids:
                    if erase:
                        self.db.executemany('DELETE FROM keyword_photos WHERE photo_id=? AND keyword_id=?',
                                            ((photo_id,id_) for id_ in keyword_ids))
                    else:
                        self.db.executemany('INSERT OR IGNORE INTO keyword_photos VALUES(?,?)',
                                            ((photo_id,id_) for id_ in keyword_ids))
                if not erase:
                    remember(self.db,keyword_ids)
            else:
                if erase or expected_shortcut_revision is not None:
                    raise ValueError('Only keyword painting supports shortcut erasure; choose None or Unflagged to clear other attributes')
                valid = ((kind=='rating' and type(value) is int and 0<=value<=5) or
                         (kind=='flag' and type(value) is int and value in (-1,0,1)) or
                         (kind=='label' and value in COLORS))
                if not valid:
                    raise ValueError('Choose a supported Painter attribute and value')
                column = {'rating':'rating','flag':'flag','label':'color_label'}[kind]
                self.db.executemany(f'UPDATE photos SET {column}=? WHERE id=?', ((value,id_) for id_ in ids))
            self.db.executemany('UPDATE photos SET metadata_revision=metadata_revision+1 WHERE id=?', ((id_,) for id_ in ids))
        return {'updated':ids, 'kind':kind, 'erased':erase, 'keyword_ids':keyword_ids, 'shortcut':self.read()}
