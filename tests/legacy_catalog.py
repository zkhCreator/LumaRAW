"""Build genuine earlier catalog schemas for migration regressions.

Inputs: a base Catalog SQLite connection and the desired published schema version.
Outputs: only that version's migration chain. Never fake an old catalog by lowering
user_version on current tables or invoking current domain commands before upgrade.
"""
from lumaraw.organization import migrate_metadata
from lumaraw.collections import migrate as collections, migrate_identities
from lumaraw.virtual_copies import migrate as copies
from lumaraw.stacks import migrate as stacks
from lumaraw.capture_time import migrate as capture
from lumaraw.folders import migrate as folders
from lumaraw.keywords import migrate as keywords
from lumaraw.relocations import migrate as relocations
from lumaraw.folder_sync import migrate as folder_sync
from lumaraw.keyword_exports import migrate as keyword_exports
from lumaraw.keyword_exchange import migrate as keyword_exchange
from lumaraw.keyword_sets import migrate as keyword_sets
from lumaraw.library_painter import migrate as painter
from lumaraw.orientation import migrate as orientation
from lumaraw.develop_presets import migrate as develop_presets
from lumaraw.iptc import migrate as iptc
from lumaraw.metadata_presets import migrate as metadata_presets
from lumaraw.import_review import migrate as import_review
from lumaraw.import_processing import migrate as import_processing
from lumaraw.previous_import import migrate as previous_import
from lumaraw.develop_history import migrate as develop_history
from lumaraw.before_after import migrate as before_after
from lumaraw.snapshots import migrate as snapshots
from lumaraw.snapshot_status import migrate as snapshot_status
from lumaraw.import_copy import migrate as import_copy
from lumaraw.import_naming import migrate as import_naming
from lumaraw.import_backup import migrate as import_backup
import json
from pathlib import Path
from lumaraw.model import Recipe


def seed_photo(db, path):
    """Insert a fixture using the original schema, without current import behavior."""
    path=Path(path).resolve();stat=path.stat()
    with db:
        return db.execute('INSERT INTO photos(path,name,bytes,mtime,recipe,created) VALUES(?,?,?,?,?,?)',
                          (str(path),path.name,stat.st_size,stat.st_mtime_ns,json.dumps(Recipe().dict()),0)).lastrowid


def migrate_to(db, version):
    migrations = (migrate_metadata, collections, copies, stacks, migrate_identities, capture, folders, keywords, relocations, folder_sync, keyword_exports, keyword_exchange, keyword_sets, painter, orientation, develop_presets, iptc, metadata_presets, import_review, import_processing, previous_import, develop_history, before_after, snapshots, snapshot_status, import_copy, import_naming, import_backup)
    if not 0 <= version <= len(migrations):
        raise ValueError('Unsupported legacy fixture version')
    for migration in migrations[:version]:
        migration(db)
