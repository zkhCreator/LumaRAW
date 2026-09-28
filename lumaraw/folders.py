"""Catalog folder hierarchy, source queries and presentation metadata.

Inputs: catalog photo paths and explicit revision-checked folder commands. Outputs:
bounded tree/search pages, maintained photo counts and source predicates. SQLite
triggers keep imports, virtual copies, removal and relinking consistent. Ancestors
are catalog records, not a scan of the filesystem. Folder labels/favorites and
root visibility are catalog-only; no directory creation, moves or original writes.
"""
import os

from .organization import COLORS, folded


def folder_path(path):
    return os.path.dirname(os.path.abspath(path))


def parent_path(path):
    parent = os.path.dirname(path)
    return parent if parent != path else None


def register(db):
    db.create_function('folder_path', 1, folder_path, deterministic=True)
    db.create_function('folder_parent', 1, parent_path, deterministic=True)
    db.create_function('folder_name', 1, lambda path: os.path.basename(path) or path, deterministic=True)


def chain(start):
    # start is a fixed SQL expression owned by this module, never caller input.
    return ('WITH RECURSIVE branch(path) AS (SELECT ' + start + ' UNION ALL '
            'SELECT f.parent_path FROM catalog_folders f JOIN branch b ON f.path=b.path '
            'WHERE f.parent_path IS NOT NULL) SELECT path FROM branch')


def descendants(start):
    return ('WITH RECURSIVE branch(path) AS (SELECT ' + start + ' UNION ALL '
            'SELECT f.path FROM catalog_folders f JOIN branch b ON f.parent_path=b.path) '
            'SELECT path FROM branch')


def migrate(db):
    if db.execute('PRAGMA user_version').fetchone()[0] >= 7:
        return
    ancestors = chain('NEW.folder_path')
    previous = chain('OLD.folder_path')
    statements = [
        'CREATE TABLE folder_state(id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL DEFAULT 0)',
        'INSERT INTO folder_state(id) VALUES(1)',
        "CREATE TABLE catalog_folders(id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT NOT NULL UNIQUE, "
        "name TEXT NOT NULL, parent_path TEXT, direct_count INTEGER NOT NULL DEFAULT 0, "
        "total_count INTEGER NOT NULL DEFAULT 0, is_root INTEGER NOT NULL DEFAULT 0, "
        "favorite INTEGER NOT NULL DEFAULT 0, color_label TEXT NOT NULL DEFAULT 'none', "
        'revision INTEGER NOT NULL DEFAULT 0)',
        'CREATE INDEX folder_parent_order ON catalog_folders(parent_path,name COLLATE NOCASE,id)',
        'CREATE INDEX folder_root_order ON catalog_folders(is_root,name COLLATE NOCASE,id)',
        'CREATE TABLE folder_photos(photo_id INTEGER PRIMARY KEY, folder_path TEXT NOT NULL)',
        'CREATE INDEX folder_photo_order ON folder_photos(folder_path,photo_id)',
        'CREATE TRIGGER folder_root_added AFTER UPDATE OF is_root ON catalog_folders '
        'WHEN NEW.is_root=1 AND OLD.is_root=0 BEGIN '
        'UPDATE catalog_folders SET is_root=0 WHERE is_root=1 AND path!=NEW.path AND path IN (' +
        descendants('NEW.path') + '); END',
        'CREATE TRIGGER folder_member_added AFTER INSERT ON folder_photos BEGIN '
        'INSERT OR IGNORE INTO catalog_folders(path,name,parent_path) '
        'SELECT path,folder_name(path),folder_parent(path) FROM ('
        'WITH RECURSIVE paths(path) AS (SELECT NEW.folder_path WHERE NOT EXISTS '
        '(SELECT 1 FROM catalog_folders WHERE path=NEW.folder_path) UNION ALL '
        'SELECT folder_parent(path) FROM paths WHERE folder_parent(path) IS NOT NULL) '
        'SELECT path FROM paths); '
        'UPDATE catalog_folders SET total_count=total_count+1, '
        'direct_count=direct_count+(path=NEW.folder_path) WHERE path IN (' + ancestors + '); '
        'UPDATE catalog_folders SET is_root=1 WHERE path=NEW.folder_path AND NOT EXISTS '
        '(SELECT 1 FROM catalog_folders WHERE is_root=1 AND path IN (' + ancestors + ')); '
        'UPDATE folder_state SET revision=revision+1 WHERE id=1; END',
        'CREATE TRIGGER folder_member_removed AFTER DELETE ON folder_photos BEGIN '
        'UPDATE catalog_folders SET total_count=total_count-1, '
        'direct_count=direct_count-(path=OLD.folder_path) WHERE path IN (' + previous + '); '
        'UPDATE folder_state SET revision=revision+1 WHERE id=1; END',
        'CREATE TRIGGER folder_photo_added AFTER INSERT ON photos BEGIN '
        'INSERT INTO folder_photos VALUES(NEW.id,folder_path(NEW.path)); END',
        'CREATE TRIGGER folder_photo_removed AFTER DELETE ON photos BEGIN '
        'DELETE FROM folder_photos WHERE photo_id=OLD.id; END',
        'CREATE TRIGGER folder_photo_relinked AFTER UPDATE OF path ON photos WHEN NEW.path!=OLD.path BEGIN '
        'DELETE FROM folder_photos WHERE photo_id=OLD.id; '
        'INSERT INTO folder_photos VALUES(NEW.id,folder_path(NEW.path)); END',
    ]
    with db:
        db.execute('BEGIN IMMEDIATE')
        for statement in statements:
            db.execute(statement)
        # SQL streams existing photos; migration never materializes the catalog.
        db.execute('INSERT INTO folder_photos SELECT id,folder_path(path) FROM photos ORDER BY id')
        db.execute('PRAGMA user_version=7')


class Folders:
    def __init__(self, catalog):
        self.db = catalog.db

    def revision(self):
        return self.db.execute('SELECT revision FROM folder_state WHERE id=1').fetchone()[0]

    def get(self, folder_id):
        row = self.db.execute('SELECT * FROM catalog_folders WHERE id=?', (folder_id,)).fetchone()
        if row is None:
            raise ValueError('Folder does not exist in this catalog')
        return dict(row)

    def display(self, row):
        row = dict(row)
        row['has_children'] = self.db.execute(
            'SELECT 1 FROM catalog_folders WHERE parent_path=? LIMIT 1', (row['path'],)).fetchone() is not None
        row['missing'] = not os.path.isdir(row['path'])
        return row

    def list(self, parent_id=None, offset=0, search='', favorites=False, color_label=None):
        filtered = bool(search or favorites or color_label)
        if parent_id is not None and filtered:
            raise ValueError('Folder search and label filters use a flat catalog list')
        params = []
        if parent_id is not None:
            where = 'parent_path=?'
            params.append(self.get(parent_id)['path'])
        elif filtered:
            where = ('path IN (WITH RECURSIVE visible(path) AS '
                     '(SELECT path FROM catalog_folders WHERE is_root=1 UNION ALL '
                     'SELECT f.path FROM catalog_folders f JOIN visible v ON f.parent_path=v.path) '
                     'SELECT path FROM visible)')
        else:
            where = 'is_root=1'
        if search:
            where += ' AND instr(casefold(name),?)>0'
            params.append(folded(search))
        if favorites:
            where += ' AND favorite=1'
        if color_label:
            if color_label not in COLORS:
                raise ValueError('Unsupported folder color label')
            where += ' AND color_label=?'
            params.append(color_label)
        total = self.db.execute('SELECT count(*) FROM catalog_folders WHERE ' + where, params).fetchone()[0]
        offset = min(offset, max(0, ((total - 1) // 60) * 60))
        rows = self.db.execute('SELECT * FROM catalog_folders WHERE ' + where +
                               ' ORDER BY name COLLATE NOCASE,id LIMIT 60 OFFSET ?', [*params, offset])
        return {'folders': [self.display(row) for row in rows], 'total': total, 'offset': offset,
                'page_size': 60, 'folder_revision': self.revision(), 'filtered': filtered}

    def details(self, folder_id=None, photo_id=None):
        if (folder_id is None) == (photo_id is None):
            raise ValueError('Choose exactly one folder or photo')
        if photo_id is not None:
            row = self.db.execute('SELECT f.id FROM catalog_folders f JOIN folder_photos p '
                                  'ON p.folder_path=f.path WHERE p.photo_id=?', (photo_id,)).fetchone()
            if row is None:
                raise ValueError('Photo does not exist in this catalog')
            folder_id = row[0]
        current = self.get(folder_id)
        ancestors = []
        parent = current['parent_path']
        while parent is not None:
            if len(ancestors) >= 256:
                raise ValueError('Folder navigation exceeds 256 ancestor levels')
            row = self.db.execute('SELECT * FROM catalog_folders WHERE path=?', (parent,)).fetchone()
            ancestors.append(self.location(row))
            parent = row['parent_path']
        result = {**self.location(current), 'ancestors': list(reversed(ancestors)),
                  'folder_revision': self.revision()}
        if photo_id is not None:
            count = self.db.execute('SELECT count(*) FROM folder_photos WHERE folder_path=? AND photo_id>?',
                                    (current['path'], photo_id)).fetchone()[0]
            result['photo_offset'] = count // 60 * 60
        return result

    def location(self, row):
        where = 'is_root=1' if row['is_root'] else 'parent_path IS ?'
        params = [] if row['is_root'] else [row['parent_path']]
        count = self.db.execute('SELECT count(*) FROM catalog_folders WHERE ' + where +
            ' AND (name COLLATE NOCASE<? OR (name COLLATE NOCASE=? AND id<?))',
            [*params, row['name'], row['name'], row['id']]).fetchone()[0]
        return {**self.display(row), 'page_offset': count // 60 * 60}

    def predicate(self, folder_id, include_subfolders=True):
        row = self.get(folder_id)
        if include_subfolders:
            return ('id IN (SELECT photo_id FROM folder_photos WHERE folder_path IN (' + descendants('?') + '))',
                    [row['path']])
        return 'id IN (SELECT photo_id FROM folder_photos WHERE folder_path=?)', [row['path']]

    def count(self, folder_id, include_subfolders=True, stacked=True):
        row = self.get(folder_id)
        count = row['total_count'] if include_subfolders else row['direct_count']
        if stacked:
            source = 'folder IN (' + descendants('?') + ')' if include_subfolders else 'folder=?'
            hidden = self.db.execute("SELECT COALESCE(sum(size-1),0) FROM photo_stacks "
                "WHERE scope='folder' AND collapsed=1 AND " + source, (row['path'],)).fetchone()[0]
            count -= hidden
        return count

    def edit(self, folder_id, expected_revision, patch):
        if not patch or set(patch) - {'favorite', 'color_label'}:
            raise ValueError('Choose a folder favorite or color label change')
        if 'color_label' in patch and patch['color_label'] not in COLORS:
            raise ValueError('Unsupported folder color label')
        if 'favorite' in patch and type(patch['favorite']) is not bool:
            raise ValueError('Folder favorite must be a boolean')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            if self.get(folder_id)['revision'] != expected_revision:
                raise ValueError('Folder conflict; reload before editing')
            self.db.execute('UPDATE catalog_folders SET ' + ','.join(key + '=?' for key in patch) +
                            ',revision=revision+1 WHERE id=?', [*patch.values(), folder_id])
            self.db.execute('UPDATE folder_state SET revision=revision+1 WHERE id=1')
        return self.display(self.get(folder_id))

    def visibility(self, folder_id, expected_revision, action):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            if expected_revision != self.revision():
                raise ValueError('Folder tree changed; refresh before changing its roots')
            current = self.get(folder_id)
            if not current['is_root']:
                raise ValueError('Choose a top-level folder')
            if action == 'show_parent':
                parent = current['parent_path']
                if parent is None:
                    raise ValueError('This folder has no parent')
                self.db.execute('UPDATE catalog_folders SET is_root=1 WHERE path=?', (parent,))
            elif action == 'hide_parent':
                if current['direct_count']:
                    raise ValueError('A folder containing photos directly cannot be hidden')
                if not self.display(current)['has_children']:
                    raise ValueError('This folder has no children to show')
                self.db.execute('UPDATE catalog_folders SET is_root=0 WHERE id=?', (folder_id,))
                self.db.execute('UPDATE catalog_folders SET is_root=1 WHERE parent_path=?', (current['path'],))
            else:
                raise ValueError('Unsupported folder visibility action')
            self.db.execute('UPDATE folder_state SET revision=revision+1 WHERE id=1')
        return {'folder_revision': self.revision()}
