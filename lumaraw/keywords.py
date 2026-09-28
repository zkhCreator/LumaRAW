"""Catalog keyword identities, hierarchy and bounded assignment workflows.

Inputs: validated tag forms, selected photo revisions and literal search text.
Outputs: paged tags, qualified keyword paths and transactional catalog mutations.
No pixels, original/sidecar writes or metadata encoding. Export policy projection
belongs to keyword_exports; this module stores its flags. Synonyms aid lookup; they
are not separate assignments. Stable IDs distinguish equal names under different
parents. The legacy photo_keywords name is a read-only direct-assignment view.
List rows have an 8 KiB budget; deferred paths/synonyms remain available through
revision-bound details. A missing summary field never means an empty value.
"""
import json
import re
import unicodedata

from .organization import folded


def migrate(db):
    if db.execute('PRAGMA user_version').fetchone()[0] >= 8:
        return
    db.execute('BEGIN IMMEDIATE')
    try:
        statements = (
            'CREATE TABLE keyword_state(id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL)',
            'INSERT INTO keyword_state VALUES(1,0)',
            'CREATE TABLE keywords(id INTEGER PRIMARY KEY AUTOINCREMENT, parent_id INTEGER, '
            'name TEXT NOT NULL, normalized TEXT NOT NULL)',
            'CREATE UNIQUE INDEX keyword_sibling ON keywords(COALESCE(parent_id,0),normalized)',
            'CREATE INDEX keyword_parent ON keywords(parent_id,normalized,id)',
            'CREATE INDEX keyword_name ON keywords(normalized,id)',
            'CREATE TABLE keyword_synonyms(keyword_id INTEGER NOT NULL, normalized TEXT NOT NULL, '
            'name TEXT NOT NULL, PRIMARY KEY(keyword_id,normalized))',
            'CREATE INDEX keyword_synonym_lookup ON keyword_synonyms(normalized,keyword_id)',
            'CREATE TABLE keyword_photos(photo_id INTEGER NOT NULL, keyword_id INTEGER NOT NULL, '
            'PRIMARY KEY(photo_id,keyword_id))',
            'CREATE INDEX keyword_photo_lookup ON keyword_photos(keyword_id,photo_id)',
            'INSERT INTO keywords(name,normalized) SELECT MIN(keyword),normalized FROM photo_keywords GROUP BY normalized',
            'INSERT INTO keyword_photos SELECT p.photo_id,k.id FROM photo_keywords p '
            'JOIN keywords k ON k.normalized=p.normalized',
            'DROP TABLE photo_keywords',
            'CREATE VIEW photo_keywords AS SELECT p.photo_id,k.normalized,k.name AS keyword '
            'FROM keyword_photos p JOIN keywords k ON k.id=p.keyword_id',
            'CREATE TRIGGER keyword_assignment_insert AFTER INSERT ON keyword_photos BEGIN '
            'UPDATE keyword_state SET revision=revision+1; END',
            'CREATE TRIGGER keyword_assignment_delete AFTER DELETE ON keyword_photos BEGIN '
            'UPDATE keyword_state SET revision=revision+1; END',
            'CREATE TRIGGER keyword_photo_delete AFTER DELETE ON photos BEGIN '
            'DELETE FROM keyword_photos WHERE photo_id=OLD.id; END',
            'PRAGMA user_version=8',
        )
        for statement in statements:
            db.execute(statement)
        db.commit()
    except BaseException:
        db.rollback()
        raise


def descendants(seed):
    return ('WITH RECURSIVE tags(id) AS (' + seed +
            ' UNION SELECT k.id FROM keywords k JOIN tags t ON k.parent_id=t.id) SELECT id FROM tags')


def matching(text, partial=False):
    expression = 'instr(normalized,?)>0' if partial else 'normalized=?'
    seed = (f'SELECT id FROM keywords WHERE {expression} UNION '
            f'SELECT keyword_id FROM keyword_synonyms WHERE {expression}')
    return ('id IN (SELECT photo_id FROM keyword_photos WHERE keyword_id IN (' +
            descendants(seed) + '))', [folded(text), folded(text)])


def valid_name(value):
    value = unicodedata.normalize('NFC', value.strip())
    if not value:
        raise ValueError('Keywords cannot be blank')
    if len(value) > 120 or any(c in value for c in ',;|<>\n\r\t') or value.endswith('*'):
        raise ValueError('Keyword names must be 1–120 characters without delimiters or a trailing asterisk')
    return value


class Keywords:
    def __init__(self, catalog):
        self.catalog = catalog
        self.db = catalog.db

    def revision(self):
        return self.db.execute('SELECT revision FROM keyword_state WHERE id=1').fetchone()[0]

    def check_revision(self, expected):
        if self.revision() != expected:
            raise ValueError('Keyword list changed; refresh before editing')

    def get(self, keyword_id):
        row = self.db.execute('SELECT * FROM keywords WHERE id=?', (keyword_id,)).fetchone()
        if not row:
            raise ValueError('Keyword does not exist')
        return dict(row)

    def ancestors(self, keyword_id):
        result = []
        while keyword_id is not None:
            row = self.get(keyword_id)
            if len(result) >= 32 or any(item['id'] == keyword_id for item in result):
                raise ValueError('Keyword hierarchy is too deep or cyclic')
            result.append(row)
            keyword_id = row['parent_id']
        return list(reversed(result))

    def photo(self, photo_id, limit=100, offset=0):
        rows = self.db.execute('WITH RECURSIVE paths(id,parent_id,path,depth) AS ('
            'SELECT k.id,k.parent_id,k.name,1 FROM keywords k JOIN keyword_photos p '
            'ON p.keyword_id=k.id WHERE p.photo_id=? UNION ALL '
            "SELECT p.id,k.parent_id,k.name || ' | ' || p.path,p.depth+1 "
            'FROM paths p JOIN keywords k ON k.id=p.parent_id WHERE p.depth<32) '
            'SELECT id,path FROM paths WHERE parent_id IS NULL ORDER BY casefold(path),id LIMIT ? OFFSET ?', (photo_id,limit,offset))
        return [{'id':row[0], 'path':row[1]} for row in rows]

    def details(self, keyword_id, expected_revision):
        self.check_revision(expected_revision)
        item = self.get(keyword_id)
        ancestors = self.ancestors(keyword_id)
        item['path'] = ' | '.join(a['name'] for a in ancestors)
        item['parent_path'] = ' | '.join(a['name'] for a in ancestors[:-1])
        item['synonyms'] = self.synonyms(keyword_id)
        item['details_deferred'] = False
        item['has_children'] = self.db.execute(
            'SELECT 1 FROM keywords WHERE parent_id=? LIMIT 1', (keyword_id,)).fetchone() is not None
        return {'keyword':item, 'keyword_revision':expected_revision}

    def synonyms(self, keyword_id):
        return [r[0] for r in self.db.execute(
            'SELECT name FROM keyword_synonyms WHERE keyword_id=? ORDER BY normalized', (keyword_id,))]

    def list(self, parent_id=None, offset=0, search='', photo_ids=()):
        if parent_id is not None:
            self.get(parent_id)
        if search:
            where = ('instr(k.normalized,?)>0 OR EXISTS (SELECT 1 FROM keyword_synonyms s '
                     'WHERE s.keyword_id=k.id AND instr(s.normalized,?)>0)')
            params = [folded(search), folded(search)]
        else:
            where, params = 'k.parent_id IS ?', [parent_id]
        total = self.db.execute('SELECT COUNT(*) FROM keywords k WHERE ' + where, params).fetchone()[0]
        offset = min(offset, max(0, (total-1)//60*60))
        ids = list(dict.fromkeys(photo_ids))
        placeholders = ','.join('?' for _ in ids) or 'NULL'
        rows = self.db.execute('SELECT k.*, '
            '(SELECT COUNT(*) FROM keyword_photos p WHERE p.keyword_id=k.id) AS photo_count, '
            'EXISTS(SELECT 1 FROM keywords child WHERE child.parent_id=k.id) AS has_children, '
            f'(SELECT COUNT(*) FROM keyword_photos p WHERE p.keyword_id=k.id AND p.photo_id IN ({placeholders})) AS selected_count '
            'FROM keywords k WHERE ' + where + ' ORDER BY k.normalized,k.id LIMIT 60 OFFSET ?',
            [*ids, *params, offset])
        items = []
        ancestors_by_id = {}
        def path_names(keyword_id, seen=()):
            if keyword_id in seen or len(seen) >= 32:
                raise ValueError('Keyword hierarchy is too deep or cyclic')
            if keyword_id not in ancestors_by_id:
                tag = self.get(keyword_id)
                parents = path_names(tag['parent_id'], (*seen, keyword_id)) if tag['parent_id'] is not None else []
                if len(parents) >= 32:
                    raise ValueError('Keyword hierarchy is too deep or cyclic')
                ancestors_by_id[keyword_id] = [*parents, tag['name']]
            return ancestors_by_id[keyword_id]
        for row in rows:
            item = dict(row)
            item['has_children'] = bool(item['has_children'])
            item['synonyms'] = self.synonyms(row['id'])
            names = path_names(row['id'])
            item['path'] = ' | '.join(names)
            item['details_deferred'] = False
            if len(json.dumps(item, ensure_ascii=False).encode()) > 8192:
                item['path'] = None
                item['synonyms'] = None
                item['details_deferred'] = True
                item['path_preview'] = ' | '.join([names[0], '…', names[-1]]) if len(names) > 2 else ' | '.join(names)
            items.append(item)
        return {'keywords':items, 'total':total, 'offset':offset, 'page_size':60,
                'keyword_revision':self.revision(), 'selected_total':len(ids)}

    def save(self, name, expected_revision, keyword_id=None, parent_id=None, synonyms=(), targets=(),
             include_export=None, export_containing=None, export_synonyms=None):
        name = valid_name(name)
        aliases = {folded(valid_name(alias)):valid_name(alias) for alias in synonyms}
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            self.check_revision(expected_revision)
            if keyword_id is not None and targets:
                raise ValueError('Add to selected photos is available only when creating a keyword')
            photo_ids = self.check_targets(targets)
            previous = self.get(keyword_id) if keyword_id is not None else None
            policies = {'include_export':include_export, 'export_containing':export_containing,
                        'export_synonyms':export_synonyms}
            if any(value is not None and type(value) is not bool for value in policies.values()):
                raise ValueError('Keyword export options must be booleans')
            policies = {key:int(value) if value is not None else previous[key] if previous else 1
                        for key,value in policies.items()}
            parents = self.ancestors(parent_id) if parent_id is not None else []
            if any(row['id'] == keyword_id for row in parents):
                raise ValueError('A keyword cannot be moved into itself or its descendants')
            height = 1
            if previous:
                height = self.db.execute('WITH RECURSIVE tree(id,depth) AS (SELECT ?,1 UNION ALL '
                    'SELECT k.id,t.depth+1 FROM keywords k JOIN tree t ON k.parent_id=t.id) '
                    'SELECT MAX(depth) FROM tree', (keyword_id,)).fetchone()[0]
            if len(parents)+height > 32:
                raise ValueError('Keyword hierarchy cannot exceed 32 levels')
            if self.db.execute('SELECT 1 FROM keywords WHERE parent_id IS ? AND normalized=? AND id!=?',
                               (parent_id, folded(name), keyword_id or 0)).fetchone():
                raise ValueError('A keyword with this name already exists inside this parent')
            if previous:
                # Qualified names of every assigned descendant may change. A stale
                # photo metadata editor must not silently restore an old path.
                self.db.execute('UPDATE photos SET metadata_revision=metadata_revision+1 WHERE id IN '
                    '(SELECT photo_id FROM keyword_photos WHERE keyword_id IN ('+
                    descendants('SELECT ?')+'))', (keyword_id,))
                self.db.execute('UPDATE keywords SET name=?,normalized=?,parent_id=? WHERE id=?',
                                (name, folded(name), parent_id, keyword_id))
                self.db.execute('DELETE FROM keyword_synonyms WHERE keyword_id=?', (keyword_id,))
            else:
                keyword_id = self.db.execute('INSERT INTO keywords(name,normalized,parent_id) VALUES(?,?,?)',
                                            (name, folded(name), parent_id)).lastrowid
            self.db.executemany('INSERT INTO keyword_synonyms VALUES(?,?,?)',
                                [(keyword_id, key, value) for key, value in aliases.items()])
            self.db.execute('UPDATE keywords SET include_export=?,export_containing=?,export_synonyms=? WHERE id=?',
                            (*policies.values(),keyword_id))
            self.assign(keyword_id, photo_ids, 'add')
            self.db.execute('UPDATE keyword_state SET revision=revision+1')
        return {'keyword_id':keyword_id, 'keyword_revision':self.revision()}

    def delete(self, keyword_id, expected_revision):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            self.check_revision(expected_revision)
            self.get(keyword_id)
            subtree = descendants('SELECT ?')
            self.db.execute('UPDATE photos SET metadata_revision=metadata_revision+1 WHERE id IN '
                            '(SELECT photo_id FROM keyword_photos WHERE keyword_id IN ('+subtree+'))', (keyword_id,))
            for table in ('keyword_photos', 'keyword_synonyms'):
                self.db.execute(f'DELETE FROM {table} WHERE keyword_id IN ('+subtree+')', (keyword_id,))
            self.db.execute('DELETE FROM keywords WHERE id IN ('+subtree+')', (keyword_id,))
            self.db.execute('UPDATE keyword_state SET revision=revision+1')
        return {'keyword_revision':self.revision()}

    def check_targets(self, targets):
        ids = [target['photo_id'] for target in targets]
        if len(ids) != len(set(ids)):
            raise ValueError('Duplicate photo targets are not allowed')
        for target in targets:
            row = self.db.execute('SELECT metadata_revision FROM photos WHERE id=?', (target['photo_id'],)).fetchone()
            if not row:
                raise ValueError('Photo does not exist')
            if row[0] != target['expected_metadata_revision']:
                raise ValueError('Metadata conflict; reload the photo before editing')
        return ids

    def membership(self, keyword_id, targets, action, expected_revision):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            self.check_revision(expected_revision)
            self.get(keyword_id)
            ids = self.check_targets(targets)
            self.assign(keyword_id, ids, action)
        return {'keyword_revision':self.revision(), 'updated':ids}

    def assign(self, keyword_id, ids, action):
        """Apply validated targets inside the caller's single transaction."""
        for photo_id in ids:
            if action == 'add':
                self.db.execute('INSERT OR IGNORE INTO keyword_photos VALUES(?,?)', (photo_id, keyword_id))
                if self.db.execute('SELECT COUNT(*) FROM keyword_photos WHERE photo_id=?', (photo_id,)).fetchone()[0] > 100:
                    raise ValueError('A photo cannot have more than 100 directly assigned keywords')
            else:
                self.db.execute('DELETE FROM keyword_photos WHERE photo_id=? AND keyword_id=?', (photo_id, keyword_id))
            self.db.execute('UPDATE photos SET metadata_revision=metadata_revision+1 WHERE id=?', (photo_id,))

    def resolve(self, text):
        # Legacy strings remain usable. Explicit paths disambiguate duplicate leaf
        # names; do not choose an arbitrary branch merely because it was first.
        normalized = folded(text.strip())
        # Legacy names may themselves contain separators. Match existing canonical
        # paths first, pruning every branch by the input prefix; parsing the string
        # first could otherwise create a different tree during metadata round-trip.
        if ' | ' not in normalized:
            existing = self.db.execute('SELECT id FROM keywords WHERE parent_id IS NULL AND normalized=?',
                                       (normalized,)).fetchall()
        else:
            existing = self.db.execute('WITH RECURSIVE paths(id,path,depth) AS ('
                'SELECT id,normalized,1 FROM keywords WHERE parent_id IS NULL AND '
                "(normalized=? OR substr(?,1,length(normalized)+3)=normalized || ' | ') UNION ALL "
                "SELECT k.id,p.path || ' | ' || k.normalized,p.depth+1 FROM keywords k "
                'JOIN paths p ON k.parent_id=p.id WHERE p.depth<32 AND '
                "(p.path || ' | ' || k.normalized=? OR substr(?,1,length(p.path)+length(k.normalized)+6)="
                "p.path || ' | ' || k.normalized || ' | ')) SELECT id FROM paths WHERE path=? LIMIT 2",
                [normalized]*5).fetchall()
        if len(existing) > 1:
            raise ValueError('Ambiguous legacy keyword path; use the Keyword List to assign by identity')
        if existing:
            return existing[0][0]
        parts = re.split(r'[|>]', text) if '<' not in text else list(reversed(text.split('<')))
        parts = [valid_name(part) for part in parts]
        if len(parts) > 32:
            raise ValueError('Keyword hierarchy cannot exceed 32 levels')
        if len(parts) == 1:
            rows = self.db.execute('SELECT id,parent_id FROM keywords WHERE normalized=? ORDER BY id',
                                   (folded(parts[0]),)).fetchall()
            root = next((row for row in rows if row['parent_id'] is None), None)
            if root:
                return root['id']
            if len(rows) == 1:
                return rows[0]['id']
            if rows:
                raise ValueError('Ambiguous keyword; use its full parent | child path')
        parent = None
        for part in parts:
            row = self.db.execute('SELECT id FROM keywords WHERE parent_id IS ? AND normalized=?',
                                   (parent, folded(part))).fetchone()
            if row:
                parent = row[0]
            else:
                parent = self.db.execute('INSERT INTO keywords(parent_id,name,normalized) VALUES(?,?,?)',
                                         (parent, part, folded(part))).lastrowid
                self.db.execute('UPDATE keyword_state SET revision=revision+1')
        return parent

    def replace(self, photo_ids, values):
        """Inside the caller's metadata transaction; failure rolls back all tags."""
        ids = set(self.resolve(value) for value in values)
        self.replace_ids(photo_ids, ids)

    def replace_ids(self, photo_ids, keyword_ids, additions=()):
        """Replace complete assignments by stable identity in the caller's transaction."""
        ids = set(keyword_ids)
        for keyword_id in ids:
            self.get(keyword_id)
        ids.update(self.resolve(value) for value in additions)
        if len(ids) > 100:
            raise ValueError('A photo cannot have more than 100 directly assigned keywords')
        for photo_id in photo_ids:
            self.db.execute('DELETE FROM keyword_photos WHERE photo_id=?', (photo_id,))
            self.db.executemany('INSERT INTO keyword_photos VALUES(?,?)', [(photo_id, id_) for id_ in ids])
