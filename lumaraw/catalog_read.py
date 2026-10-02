"""Read-only, single-snapshot access for responsive Library queries.

Purpose: open an already-migrated catalog without constructing a writable Catalog.
Inputs: an existing catalog root and the shipped schema version. Outputs: one
SQLite read snapshot for the shared Library query layer.
Responsibilities: register deterministic SQL functions and verify the schema in
the same transaction as subsequent count, page, and revision reads.
Boundaries: no directory creation, WAL-mode changes, schema migration, writes,
checkpoint requests, or fallback to a writable connection. Service startup owns
migrations; an incompatible schema is a clear request failure.
"""
from pathlib import Path
import sqlite3

from .organization import folded
from .folders import register as register_folder_functions
from .runtime import CATALOG_VERSION


class CatalogReadSnapshot:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.path = self.root / 'catalog.sqlite'
        self.db = None

    def __enter__(self):
        if self.db is not None:
            raise RuntimeError('Catalog read snapshot is already open')
        try:
            # SQLite URI encoding preserves Unicode and spaces in catalog paths.
            self.db = sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True, timeout=10)
            self.db.row_factory = sqlite3.Row
            self.db.create_function('casefold', 1, folded, deterministic=True)
            register_folder_functions(self.db)
            self.db.execute('PRAGMA busy_timeout=10000')
            self.db.execute('PRAGMA query_only=ON')
            self.db.execute('BEGIN')
            # Force the deferred transaction to acquire its WAL snapshot before
            # checking the schema cookie and before any data/revision query.
            self.db.execute('SELECT 1 FROM sqlite_schema LIMIT 1').fetchone()
            actual = self.db.execute('PRAGMA user_version').fetchone()[0]
            if actual != CATALOG_VERSION:
                if actual > CATALOG_VERSION:
                    raise ValueError(
                        'This catalog was upgraded by a newer LumaRAW version; open it with that version'
                    )
                raise ValueError(
                    f'Catalog schema mismatch: found {actual}, expected {CATALOG_VERSION}; '
                    'restart the service to run catalog migrations'
                )
            return self
        except BaseException:
            self.close()
            raise

    def __exit__(self, exc_type, exc, traceback):
        self.close()
        return False

    def close(self):
        db, self.db = self.db, None
        if db is None:
            return
        try:
            if db.in_transaction:
                db.rollback()
        finally:
            db.close()
