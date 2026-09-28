"""Bounded keyword descriptions for photo details and native assignment pickers.

Inputs: photo/tag identities, captured metadata revisions and bounded filters.
Outputs: compact photo summaries or twenty complete paths per page. Assignment
IDs are always complete; deferred paths are never represented as an empty set.
No catalog writes, pixel access or whole-vocabulary loading.
"""
from .keywords import Keywords
from .organization import folded

PAGE_SIZE = 20
INLINE_BYTES = 32 * 1024


class KeywordDetails:
    def __init__(self, catalog):
        self.catalog = catalog
        self.db = catalog.db
        self.tags = Keywords(catalog)

    def summary(self, photo_id):
        # Measure encoded ancestor names, without concatenating a large path for
        # every assignment merely to read a recipe or render a thumbnail.
        rows = self.db.execute(
            'WITH RECURSIVE sizes(id,parent_id,bytes,depth) AS ('
            'SELECT k.id,k.parent_id,length(CAST(json_quote(k.name) AS BLOB))-2,1 '
            'FROM keywords k JOIN keyword_photos p ON p.keyword_id=k.id WHERE p.photo_id=? UNION ALL '
            'SELECT s.id,k.parent_id,s.bytes+length(CAST(json_quote(k.name) AS BLOB))+1,s.depth+1 '
            'FROM sizes s JOIN keywords k ON k.id=s.parent_id WHERE s.depth<32) '
            'SELECT id,bytes FROM sizes WHERE parent_id IS NULL ORDER BY id', (photo_id,)).fetchall()
        ids = [row['id'] for row in rows]
        deferred = sum(row['bytes'] * 2 + 80 for row in rows) > INLINE_BYTES
        tags = [] if deferred else self.tags.photo(photo_id)
        return {'keyword_ids': ids, 'keyword_count': len(ids), 'keywords_deferred': deferred,
                'keyword_tags': tags, 'keywords': [tag['path'] for tag in tags]}

    def photo(self, photo_id, expected_metadata_revision, offset=0):
        row = self.db.execute('SELECT metadata_revision FROM photos WHERE id=?', (photo_id,)).fetchone()
        if row is None:
            raise ValueError('Photo does not exist')
        if row[0] != expected_metadata_revision:
            raise ValueError('Metadata conflict; reload the photo before reading keywords')
        total = self.db.execute('SELECT count(*) FROM keyword_photos WHERE photo_id=?', (photo_id,)).fetchone()[0]
        offset = min(offset, max(0, (total-1)//PAGE_SIZE*PAGE_SIZE))
        return {'photo_id': photo_id, 'metadata_revision': row[0], 'total': total,
                'offset': offset, 'page_size': PAGE_SIZE,
                'keywords': self.tags.photo(photo_id, limit=PAGE_SIZE, offset=offset)}

    def choices(self, search='', keyword_ids=None, offset=0):
        where, values = [], []
        if keyword_ids is not None:
            ids = sorted(set(keyword_ids))
            where.append('k.id IN (' + (','.join('?' for _ in ids) or 'NULL') + ')')
            values.extend(ids)
        if search:
            where.append('(instr(k.normalized,?)>0 OR EXISTS (SELECT 1 FROM keyword_synonyms s '
                         'WHERE s.keyword_id=k.id AND instr(s.normalized,?)>0))')
            values.extend([folded(search)]*2)
        clause = ' AND '.join(where) or '1'
        total = self.db.execute('SELECT count(*) FROM keywords k WHERE '+clause, values).fetchone()[0]
        offset = min(offset, max(0, (total-1)//PAGE_SIZE*PAGE_SIZE))
        rows = self.db.execute('SELECT k.id,k.name FROM keywords k WHERE '+clause+
                               ' ORDER BY k.normalized,k.id LIMIT ? OFFSET ?', [*values, PAGE_SIZE, offset])
        items = [{'id': row['id'], 'name': row['name'],
                  'path': ' | '.join(node['name'] for node in self.tags.ancestors(row['id']))} for row in rows]
        return {'keywords': items, 'total': total, 'offset': offset, 'page_size': PAGE_SIZE,
                'keyword_revision': self.tags.revision()}
