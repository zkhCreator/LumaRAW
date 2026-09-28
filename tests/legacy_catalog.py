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


def migrate_to(db, version):
    migrations = (migrate_metadata, collections, copies, stacks, migrate_identities, capture, folders, keywords, relocations, folder_sync)
    if not 0 <= version <= len(migrations):
        raise ValueError('Unsupported legacy fixture version')
    for migration in migrations[:version]:
        migration(db)
