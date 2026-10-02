"""Shared bounded SQL for writable and snapshot-based Library queries.

Inputs: a catalog-like object with a SQLite connection and validated filters,
source, sort, and page parameters. Outputs: parameterized predicates, exact
counts, at most sixty photo rows, and at most sixty photo summaries.
Responsibilities: preserve the existing Library filter, dense-page, summary,
folder, collection, and stack semantics for both the write Catalog and the
independent read snapshot.
Boundaries: no connection lifecycle, migrations, writes, unbounded photo loads,
or UI decisions. Stack and collection domain helpers remain the source of their
own predicates and projections.
"""
from .catalog import SUMMARY_COLUMNS
from .organization import SORTS, criteria, text_predicate


class LibraryQueries:
    def __init__(self, catalog):
        self.catalog = catalog
        self.db = catalog.db

    def count(self, stars=False):
        return self.db.execute(
            'SELECT count(*) FROM photos' + (' WHERE rating>=3' if stars else '')
        ).fetchone()[0]

    def summaries(self, ids):
        if not 1 <= len(ids) <= 60:
            raise ValueError('Summary reads require 1 to 60 photo IDs')
        placeholders = ','.join('?' for _ in ids)
        return [dict(row) for row in self.db.execute(
            f'SELECT {SUMMARY_COLUMNS} FROM photos WHERE id IN ({placeholders}) ORDER BY id', ids)]

    def filter_sql(self, mode='all', search='', filters=None, collection_id=None,
                   folder_id=None, include_subfolders=True, *, ordered_page=False):
        if collection_id is not None and folder_id is not None:
            raise ValueError('Choose either a folder or collection source')
        if mode == 'previous_import' and (collection_id is not None or folder_id is not None):
            raise ValueError('Previous Import cannot be combined with a folder or collection source')
        clauses, params = [], []
        if mode == 'stars':
            clauses.append('rating>=3')
        elif mode == 'rejects':
            clauses.append('flag=-1')
        elif mode == 'keepers':
            clauses.append('flag=1')
        elif mode == 'missing':
            clauses.append('missing=1')
        elif mode == 'previous_import':
            clauses.append('source_id IN (SELECT source_id FROM previous_import_sources)')
        elif mode == 'duplicates':
            clauses.append("sha256!='' AND sha256 IN (SELECT sha256 FROM photos WHERE sha256!='' GROUP BY sha256 HAVING count(DISTINCT source_id)>1)")
        elif mode.startswith('burst:'):
            clauses.append('burst=?')
            params.append(int(mode.split(':')[1]))
        if search:
            clause, values = text_predicate(search[:200])
            clauses.append(clause)
            params.extend(values)
        if filters:
            clause, values = criteria(filters, ordered_page=ordered_page)
            clauses.append(clause)
            params.extend(values)
        if collection_id is not None:
            from .organization import Organization
            clause, values = Organization(self.catalog).collection_predicate(
                collection_id, ordered_page=ordered_page)
            clauses.append(clause)
            params.extend(values)
        if folder_id is not None:
            from .folders import Folders
            clause, values = Folders(self.catalog).predicate(folder_id, include_subfolders)
            clauses.append(clause)
            params.extend(values)
        return (' WHERE ' + ' AND '.join(clauses) if clauses else ''), params

    def filtered_page(self, offset=0, mode='all', search='', filters=None, collection_id=None,
                      sort='imported', descending=True, stacked=True, folder_id=None,
                      include_subfolders=True, *, match_count=None):
        # Dense import-order pages can stop after sixty correlated family checks
        # instead of sorting every matching source. Keep indexed membership for
        # sparse results, other sorts and actual stack projection. match_count
        # comes from the caller's exact count under this same SQLite snapshot.
        ordered_page = False
        if (sort == 'imported' and match_count is not None and match_count >= 60 and
                ('has_snapshots' in (filters or {}) or collection_id is not None)):
            ordered_page = match_count * 20 >= self.count()
        if stacked and ordered_page:
            from .stacks import Stacks
            scope = Stacks(self.catalog).scope(collection_id)
            if scope is not None and self.db.execute(
                    'SELECT 1 FROM photo_stacks WHERE scope=? LIMIT 1', (scope,)).fetchone():
                ordered_page = False
        where, params = self.filter_sql(
            mode, search, filters, collection_id, folder_id, include_subfolders,
            ordered_page=ordered_page)
        if stacked:
            from .stacks import Stacks
            return Stacks(self.catalog).projection(
                where, params, collection_id, sort, descending, offset)
        if sort not in SORTS:
            raise ValueError('Unsupported library sort')
        order = 'DESC' if descending else 'ASC'
        # Keep large recipe/decoder metadata JSON out of the grid query entirely.
        return [dict(row) for row in self.db.execute(
            f'SELECT {SUMMARY_COLUMNS},NULL AS stack_ordinal FROM photos{where} '
            f'ORDER BY {SORTS[sort]} {order},id {order} LIMIT 60 OFFSET ?',
            params + [max(0, offset)])]

    def filtered_count(self, mode='all', search='', filters=None, collection_id=None,
                       stacked=True, folder_id=None, include_subfolders=True):
        if folder_id is not None and collection_id is None and mode == 'all' and not search and not filters:
            from .folders import Folders
            return Folders(self.catalog).count(folder_id, include_subfolders, stacked)
        where, params = self.filter_sql(
            mode, search, filters, collection_id, folder_id, include_subfolders)
        if stacked:
            from .stacks import Stacks
            return Stacks(self.catalog).projection(where, params, collection_id)
        return self.db.execute('SELECT count(*) FROM photos' + where, params).fetchone()[0]
