"""Nine-slot keyword presets with shared or catalog-local persistence.

Inputs: text slots, captured state tokens and photo metadata revisions. Outputs:
bounded preset pages and atomic additive photo tagging. Presets hold text, recent
keywords hold stable catalog IDs. Revision-bound previews never select a preset.
Switching storage never copies or deletes sets.
The shared SQLite transaction serializes scope/preset edits across catalog brokers;
lock order is always shared storage then catalog. No pixels, original writes,
Lua evaluation, inferred suggestions or platform path conventions live here.
"""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import unicodedata
import uuid

from .keywords import Keywords
from .organization import folded
from .preset_paths import preset_root


def create_tables(db):
    db.execute('CREATE TABLE keyword_sets(id TEXT PRIMARY KEY,name TEXT NOT NULL,'
               'normalized TEXT NOT NULL UNIQUE,slots TEXT NOT NULL)')
    db.execute('CREATE TABLE keyword_set_state(id INTEGER PRIMARY KEY CHECK(id=1),'
               'revision INTEGER NOT NULL,selected TEXT NOT NULL)')
    db.execute("INSERT INTO keyword_set_state VALUES(1,0,'recent')")


def migrate(db):
    if db.execute('PRAGMA user_version').fetchone()[0] >= 13:
        return
    db.execute('BEGIN IMMEDIATE')
    try:
        create_tables(db)
        db.execute('CREATE TABLE keyword_recent(keyword_id INTEGER PRIMARY KEY,used INTEGER NOT NULL)')
        db.execute('CREATE TRIGGER keyword_recent_delete AFTER DELETE ON keywords BEGIN '
                   'DELETE FROM keyword_recent WHERE keyword_id=OLD.id; END')
        db.execute('PRAGMA user_version=13')
        db.commit()
    except BaseException:
        db.rollback()
        raise


def remember(db, ids):
    """Record explicit additions in the caller's transaction, keeping nine IDs."""
    ids = list(dict.fromkeys(ids))
    if not ids:
        return
    order = db.execute('SELECT COALESCE(MAX(used),0) FROM keyword_recent').fetchone()[0]
    for index, keyword_id in enumerate(ids, order + 1):
        db.execute('INSERT INTO keyword_recent VALUES(?,?) ON CONFLICT(keyword_id) DO UPDATE SET used=excluded.used',
                   (keyword_id, index))
    db.execute('DELETE FROM keyword_recent WHERE keyword_id NOT IN '
               '(SELECT keyword_id FROM keyword_recent ORDER BY used DESC LIMIT 9)')
    db.execute('UPDATE keyword_set_state SET revision=revision+1')


def validate_slots(slots):
    if not isinstance(slots, list) or len(slots) != 9 or any(not isinstance(s, str) for s in slots):
        raise ValueError('A keyword set must contain exactly nine text slots')
    result = [unicodedata.normalize('NFC', s.strip()) for s in slots]
    if any(len(s) > 4096 or any(c in s for c in '\n\r\t\x00') for s in result):
        raise ValueError('Keyword set slots must be at most 4096 characters on one line')
    # A slot may reference a legacy literal path. Resolve only when applying, at
    # the captured keyword revision, so saving never creates catalog vocabulary.
    return result


class KeywordSets:
    def __init__(self, service, root=None):
        self.service = service
        self.root = Path(root) if root is not None else preset_root()

    @contextmanager
    def shared(self):
        self.root.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.root / 'keyword-sets.sqlite', timeout=5)
        db.row_factory = sqlite3.Row
        try:
            db.execute('BEGIN IMMEDIATE')
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version > 1:
                raise ValueError('Preset storage was created by a newer engine')
            if version == 0:
                create_tables(db)
                db.execute('CREATE TABLE preset_storage(id INTEGER PRIMARY KEY CHECK(id=1),catalog INTEGER NOT NULL)')
                db.execute('INSERT INTO preset_storage VALUES(1,0)')
                db.execute('PRAGMA user_version=1')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def token(self, shared, catalog):
        values = [str(self.service.root),
                  tuple(shared.execute('SELECT revision,selected FROM keyword_set_state').fetchone()),
                  tuple(catalog.db.execute('SELECT revision,selected FROM keyword_set_state').fetchone()),
                  shared.execute('SELECT catalog FROM preset_storage').fetchone()[0], Keywords(catalog).revision()]
        return hashlib.sha256(json.dumps(values).encode()).hexdigest()

    def snapshot(self, shared, catalog, offset=0, preview_id=None):
        local = bool(shared.execute('SELECT catalog FROM preset_storage').fetchone()[0])
        db = catalog.db if local else shared
        selected = preview_id or db.execute('SELECT selected FROM keyword_set_state').fetchone()[0]
        total = db.execute('SELECT COUNT(*) FROM keyword_sets').fetchone()[0]
        offset = min(offset, max(0, (total-1)//30*30))
        page = [dict(r) for r in db.execute('SELECT id,name FROM keyword_sets ORDER BY normalized,id LIMIT 30 OFFSET ?', (offset,))]
        if selected == 'recent':
            tags = Keywords(catalog)
            ids = [r[0] for r in catalog.db.execute('SELECT keyword_id FROM keyword_recent ORDER BY used DESC LIMIT 9')]
            slots = [' | '.join(a['name'] for a in tags.ancestors(id_)) for id_ in ids]
            current = {'id':'recent', 'name':'Recent Keywords', 'slots':slots+['']*(9-len(slots)),
                       'keyword_ids':ids+[None]*(9-len(ids))}
        else:
            row = db.execute('SELECT id,name,slots FROM keyword_sets WHERE id=?', (selected,)).fetchone()
            if not row:
                raise ValueError('Selected keyword set no longer exists')
            current = dict(row)
            current['slots'] = json.loads(current['slots'])
            current['keyword_ids'] = [None]*9
        return {'sets':page, 'selected':current, 'total':total, 'offset':offset,
                'page_size':30, 'store_with_catalog':local, 'revision':self.token(shared,catalog),
                'keyword_revision':Keywords(catalog).revision()}

    def dispatch(self, method, params):
        with self.shared() as shared, self.service.catalog() as catalog:
            # Keep validation, slot resolution and target writes in one catalog
            # transaction. Shared mutations commit after catalog commit; no command
            # mutates both databases (scope changes touch only shared preferences).
            with catalog.db:
                catalog.db.execute('BEGIN IMMEDIATE')
                local = bool(shared.execute('SELECT catalog FROM preset_storage').fetchone()[0])
                db = catalog.db if local else shared
                if method != 'list_keyword_sets' and params['expected_revision'] != self.token(shared,catalog):
                    raise ValueError('Keyword sets or keywords changed; refresh before editing')
                if method == 'get_keyword_set':
                    return self.snapshot(shared,catalog,params.get('offset',0),params['set_id'])
                if method == 'save_keyword_set':
                    name = unicodedata.normalize('NFC', params['name'].strip())
                    if not name or len(name)>120 or any(ord(c)<32 for c in name):
                        raise ValueError('Keyword set names must be 1–120 characters on one line')
                    slots = validate_slots(params['slots'])
                    id_ = params.get('set_id')
                    if id_ is not None and not db.execute('SELECT 1 FROM keyword_sets WHERE id=?', (id_,)).fetchone():
                        raise ValueError('Keyword set does not exist')
                    if db.execute('SELECT 1 FROM keyword_sets WHERE normalized=? AND id!=?', (folded(name),id_ or '')).fetchone():
                        raise ValueError('A keyword set with this name already exists')
                    id_ = id_ or str(uuid.uuid4())
                    db.execute('INSERT INTO keyword_sets VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET '
                               'name=excluded.name,normalized=excluded.normalized,slots=excluded.slots',
                               (id_,name,folded(name),json.dumps(slots,ensure_ascii=False)))
                    db.execute('UPDATE keyword_set_state SET revision=revision+1,selected=?', (id_,))
                elif method == 'keyword_set_action':
                    action = params['action']
                    if action == 'storage':
                        if 'store_with_catalog' not in params or 'set_id' in params:
                            raise ValueError('Storage changes require only the catalog storage option')
                        shared.execute('UPDATE preset_storage SET catalog=?', (int(params['store_with_catalog']),))
                        shared.execute('UPDATE keyword_set_state SET revision=revision+1')
                    else:
                        id_ = params.get('set_id')
                        if 'store_with_catalog' in params or id_ is None:
                            raise ValueError('Select or delete requires only a keyword set identity')
                        if id_ != 'recent' and not db.execute('SELECT 1 FROM keyword_sets WHERE id=?', (id_,)).fetchone():
                            raise ValueError('Keyword set does not exist')
                        if action == 'delete':
                            if id_ == 'recent':
                                raise ValueError('Recent Keywords cannot be deleted')
                            db.execute('DELETE FROM keyword_sets WHERE id=?', (id_,))
                            db.execute("UPDATE keyword_set_state SET selected='recent' WHERE selected=?", (id_,))
                        else:
                            db.execute('UPDATE keyword_set_state SET selected=?', (id_,))
                        db.execute('UPDATE keyword_set_state SET revision=revision+1')
                elif method == 'apply_keyword_set':
                    return self.apply(shared,catalog,params)
                return self.snapshot(shared,catalog,params.get('offset',0))

    def apply(self, shared, catalog, params):
        current = self.snapshot(shared,catalog)['selected']
        tags = Keywords(catalog)
        ids = tags.check_targets(params['targets'])
        index = params['slot']-1
        if current['id'] == 'recent':
            if 'draft_slots' in params:
                raise ValueError('Recent Keywords cannot be edited')
            rows = catalog.db.execute('SELECT keyword_id FROM keyword_recent ORDER BY used DESC LIMIT 9').fetchall()
            if index >= len(rows):
                raise ValueError('This keyword slot is empty')
            keyword_id = rows[index][0]
        else:
            slots = validate_slots(params.get('draft_slots',current['slots']))
            if not slots[index]:
                raise ValueError('This keyword slot is empty')
            keyword_id = tags.resolve(slots[index])
        tags.assign(keyword_id,ids,'add')
        remember(catalog.db,[keyword_id])
        return {'updated':ids, 'keyword_id':keyword_id, **self.snapshot(shared,catalog)}
