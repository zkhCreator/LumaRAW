"""Persist the latest committed import source without retaining scanned payloads.

Inputs: trusted internal SQL selecting newly imported source IDs, or one legacy
streaming-import insertion. Outputs: indexed membership and a compact revision.
Callers own the transaction, so failures restore the preceding import. Empty
imports never replace it. Membership follows source families through relinking,
master promotion and virtual copies; removing the last variant removes membership.
No historical inference during migration, photo writes, filesystem I/O or UI state.
"""
import time


def migrate(db):
    if db.execute('PRAGMA user_version').fetchone()[0] >= 21:
        return
    statements = (
        'CREATE TABLE previous_import_state(id INTEGER PRIMARY KEY CHECK(id=1), '
        'revision INTEGER NOT NULL DEFAULT 0, imported INTEGER NOT NULL DEFAULT 0, '
        "created REAL NOT NULL DEFAULT 0, kind TEXT NOT NULL DEFAULT '')",
        'INSERT INTO previous_import_state(id) VALUES(1)',
        'CREATE TABLE previous_import_sources(source_id INTEGER PRIMARY KEY)',
        'CREATE TRIGGER previous_import_photo_deleted AFTER DELETE ON photos '
        'WHEN NOT EXISTS(SELECT 1 FROM photos WHERE source_id=OLD.source_id) BEGIN '
        'UPDATE previous_import_state SET revision=revision+1 WHERE id=1 AND EXISTS '
        '(SELECT 1 FROM previous_import_sources WHERE source_id=OLD.source_id); '
        'DELETE FROM previous_import_sources WHERE source_id=OLD.source_id; END',
        'PRAGMA user_version=21',
    )
    db.execute('BEGIN IMMEDIATE')
    try:
        for statement in statements:
            db.execute(statement)
        db.commit()
    except BaseException:
        db.rollback()
        raise


def state(db):
    return dict(db.execute('SELECT revision,imported,created,kind FROM previous_import_state WHERE id=1').fetchone())


def begin(db, kind):
    """Replace membership within the caller's first successful insertion transaction."""
    db.execute('DELETE FROM previous_import_sources')
    db.execute('UPDATE previous_import_state SET revision=revision+1,imported=0,created=?,kind=? WHERE id=1',
               (time.time(),kind))


def append(db, photo_id, first=False):
    # The legacy importer commits every hundred entries; each committed subset
    # and its source membership must survive a later cancellation or process exit.
    if first:
        begin(db, 'direct')
    inserted = db.execute('INSERT OR IGNORE INTO previous_import_sources SELECT source_id FROM photos WHERE id=?',
                          (photo_id,)).rowcount
    if inserted:
        db.execute('UPDATE previous_import_state SET imported=imported+?,revision=revision+1 WHERE id=1',(inserted,))


def replace(db, query, parameters, kind, imported):
    """Capture a reviewed import via trusted SQL; never materialize its IDs in Python."""
    if not imported:
        return
    begin(db, kind)
    db.execute('INSERT INTO previous_import_sources '+query, parameters)
    db.execute('UPDATE previous_import_state SET imported=? WHERE id=1',(imported,))
