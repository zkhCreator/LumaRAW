"""Portable catalog organization, independent of pixels and platform presentation.

Purpose: persist descriptive metadata, delegate collection hierarchy workflows, and compile
bounded library queries. Inputs are schema-validated commands plus a catalog-owned
SQLite connection. Outputs are rows, parameterized predicates and transactions.
Non-goals: no original/sidecar writes, EXIF rewriting, image decoding or UI state.
Metadata revisions are separate from recipes; smart membership is evaluated live.
"""
import json
import os
import unicodedata

COLORS = ('none', 'red', 'yellow', 'green', 'blue', 'purple')
SORTS = {'imported': 'id', 'name': 'name COLLATE NOCASE', 'rating': 'rating',
         'captured': 'taken', 'color': 'color_label'}
FILTER_PROPERTIES = {
    'rating_min': {'type': 'integer', 'minimum': 0, 'maximum': 5},
    'rating_max': {'type': 'integer', 'minimum': 0, 'maximum': 5},
    'flag': {'enum': [-1, 0, 1]},
    'color_label': {'enum': list(COLORS)},
    'keyword': {'type': 'string', 'minLength': 1, 'maxLength': 120},
    'has_keywords': {'type': 'boolean'},
    'camera': {'type': 'string', 'minLength': 1, 'maxLength': 200},
    'folder': {'type': 'string', 'minLength': 1, 'maxLength': 4096},
    'taken_from': {'type': 'integer', 'minimum': 0, 'maximum': 2**53-1},
    'taken_to': {'type': 'integer', 'minimum': 0, 'maximum': 2**53-1},
    'is_virtual': {'type': 'boolean'},
    'source_id': {'type': 'integer', 'minimum': 1, 'maximum': 2**53-1},
    'copy_name': {'type': 'string', 'minLength': 1, 'maxLength': 120},
    'text': {'type': 'string', 'minLength': 1, 'maxLength': 200},
}
FILTER_SCHEMA = {'type': 'object', 'properties': FILTER_PROPERTIES,
                 'additionalProperties': False}


def folded(value):
    return unicodedata.normalize('NFC', value or '').casefold()


def migrate_metadata(db):
    """Add library state once, preserving all previous photo/job identifiers."""
    if db.execute('PRAGMA user_version').fetchone()[0] >= 1:
        return
    with db:
        columns = {row[1] for row in db.execute('PRAGMA table_info(photos)')}
        for name, definition in (
            ('title', "TEXT NOT NULL DEFAULT ''"),
            ('caption', "TEXT NOT NULL DEFAULT ''"),
            ('copyright', "TEXT NOT NULL DEFAULT ''"),
            ('color_label', "TEXT NOT NULL DEFAULT 'none'"),
            ('metadata_revision', 'INTEGER NOT NULL DEFAULT 0'),
        ):
            if name not in columns:
                db.execute(f'ALTER TABLE photos ADD COLUMN {name} {definition}')
        statements = (
            'CREATE TABLE IF NOT EXISTS photo_keywords (photo_id INTEGER NOT NULL, '
            'normalized TEXT NOT NULL, keyword TEXT NOT NULL, PRIMARY KEY(photo_id, normalized))',
            'CREATE INDEX IF NOT EXISTS keyword_lookup ON photo_keywords(normalized, photo_id)',
            'CREATE TABLE IF NOT EXISTS collections (id INTEGER PRIMARY KEY, name TEXT NOT NULL, '
            "kind TEXT NOT NULL, rules TEXT NOT NULL DEFAULT '{}', "
            "match TEXT NOT NULL DEFAULT 'all', revision INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL)",
            'CREATE TABLE IF NOT EXISTS collection_photos (collection_id INTEGER NOT NULL, '
            'photo_id INTEGER NOT NULL, PRIMARY KEY(collection_id, photo_id))',
            'CREATE INDEX IF NOT EXISTS collection_photo_lookup ON collection_photos(photo_id, collection_id)',
            'CREATE INDEX IF NOT EXISTS photo_name ON photos(name COLLATE NOCASE, id)',
            'CREATE INDEX IF NOT EXISTS photo_taken ON photos(taken, id)',
            'CREATE INDEX IF NOT EXISTS photo_label ON photos(color_label, id)',
            'CREATE INDEX IF NOT EXISTS photo_flag ON photos(flag, id)',
            'CREATE INDEX IF NOT EXISTS photo_camera ON photos(camera, id)',
        )
        for statement in statements:
            db.execute(statement)
        db.execute('PRAGMA user_version=1')


def migrate(db):
    migrate_metadata(db)
    from .collections import migrate as migrate_collections
    migrate_collections(db)
    from .virtual_copies import migrate as migrate_virtual_copies
    migrate_virtual_copies(db)
    from .stacks import migrate as migrate_stacks
    migrate_stacks(db)


def text_predicate(text):
    """Search literal Unicode text; '%' and '_' never become SQL wildcards."""
    return (
        '(instr(casefold(name), ?) > 0 OR instr(casefold(title), ?) > 0 '
        'OR instr(casefold(caption), ?) > 0 OR instr(casefold(copyright), ?) > 0 '
        'OR instr(casefold(copy_name), ?) > 0 '
        'OR EXISTS (SELECT 1 FROM photo_keywords k WHERE k.photo_id=photos.id '
        'AND instr(k.normalized, ?) > 0))', [folded(text)] * 6)


def criteria(filters, match='all'):
    clauses, values = [], []
    if match == 'all' and filters.get('rating_min', 0) > filters.get('rating_max', 5):
        raise ValueError('Minimum rating exceeds maximum rating')
    if match == 'all' and filters.get('taken_from', 0) > filters.get('taken_to', 2**63 - 1):
        raise ValueError('Start capture date exceeds end capture date')
    for key, value in filters.items():
        if key in ('rating_min', 'rating_max', 'taken_from', 'taken_to'):
            column, operation = {
                'rating_min': ('rating', '>='), 'rating_max': ('rating', '<='),
                'taken_from': ('taken', '>='), 'taken_to': ('taken', '<='),
            }[key]
            clauses.append(f'{column} {operation} ?')
            values.append(value)
        elif key in ('flag', 'color_label', 'camera', 'is_virtual', 'source_id'):
            clauses.append(f'{key}=?')
            values.append(value)
        elif key == 'copy_name':
            clauses.append('instr(casefold(copy_name), ?) > 0')
            values.append(folded(value))
        elif key == 'keyword':
            if not value.strip():
                raise ValueError('Keyword cannot be blank')
            clauses.append('id IN (SELECT photo_id FROM photo_keywords WHERE normalized=?)')
            values.append(folded(value.strip()))
        elif key == 'has_keywords':
            clauses.append(('' if value else 'NOT ') +
                           'EXISTS (SELECT 1 FROM photo_keywords k WHERE k.photo_id=photos.id)')
        elif key == 'folder':
            prefix = os.path.abspath(os.path.expanduser(value)).rstrip(os.sep) + os.sep
            clauses.append('substr(path, 1, ?) = ?')
            values.extend((len(prefix), prefix))
        elif key == 'text':
            clause, params = text_predicate(value)
            clauses.append(clause)
            values.extend(params)
        else:
            raise ValueError('Unsupported library filter: ' + key)
    if match not in ('all', 'any'):
        raise ValueError('Invalid collection rule match')
    return '(' + (' AND ' if match == 'all' else ' OR ').join(clauses) + ')' if clauses else '1', values


class Organization:
    def __init__(self, catalog):
        self.catalog = catalog
        self.db = catalog.db

    @property
    def collections(self):
        from .collections import Collections
        return Collections(self.catalog)

    def collection(self, collection_id):
        return self.collections.get(collection_id)

    def collection_predicate(self, collection_id):
        return self.collections.predicate(collection_id)

    def list_collections(self, **params):
        return self.collections.list(**params)

    def save_collection(self, **params):
        return self.collections.save(**params)

    def membership(self, collection_id, expected_revision, ids, action):
        return self.collections.membership(collection_id,expected_revision,ids,action)

    def delete_collection(self, collection_id, expected_revision):
        return self.collections.delete(collection_id,expected_revision)

    def edit_metadata(self, targets, patch):
        ids = [target['photo_id'] for target in targets]
        if len(ids) != len(set(ids)):
            raise ValueError('Duplicate photo targets are not allowed')
        for target in targets:
            row = self.catalog.photo(target['photo_id'])
            if not row:
                raise ValueError('Photo does not exist')
            if row['metadata_revision'] != target['expected_metadata_revision']:
                raise ValueError('Metadata conflict; reload the photo before editing')
        keywords = None
        if 'keywords' in patch:
            keywords = {}
            for keyword in patch['keywords']:
                keyword = unicodedata.normalize('NFC', keyword.strip())
                if not keyword:
                    raise ValueError('Keywords cannot be blank')
                keywords.setdefault(folded(keyword), keyword)
        fields = {k: v for k, v in patch.items() if k != 'keywords'}
        if set(fields) - {'title', 'caption', 'copyright', 'color_label', 'copy_name'}:
            raise ValueError('Unsupported descriptive metadata field')
        with self.db:
            for photo_id in ids:
                if fields:
                    self.db.execute('UPDATE photos SET ' + ','.join(f'{key}=?' for key in fields)
                                    + ' WHERE id=?', [*fields.values(), photo_id])
                if keywords is not None:
                    self.db.execute('DELETE FROM photo_keywords WHERE photo_id=?', (photo_id,))
                    self.db.executemany('INSERT INTO photo_keywords VALUES(?,?,?)',
                                        [(photo_id, key, value) for key, value in keywords.items()])
                if patch:
                    self.db.execute('UPDATE photos SET metadata_revision=metadata_revision+1 WHERE id=?',
                                    (photo_id,))
        return ids
