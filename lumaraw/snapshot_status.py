"""Indexed snapshot presence for Library and live smart-collection predicates.

Inputs: catalog-owned snapshot inserts/deletes and schema-24 source families.
Outputs: transactional per-family counts and a compact presence-change revision.
Only zero/nonzero transitions invalidate filtered pages. SQL triggers also cover
bulk catalog removal; no recipes, photos, pixels, originals or UI are modified.
Source identity is normally stable; a moved snapshot maintains both counts.
"""


def migrate(db):
    if db.execute('PRAGMA user_version').fetchone()[0] >= 25:
        return
    statements = (
        'ALTER TABLE photo_sources ADD COLUMN snapshot_count INTEGER NOT NULL DEFAULT 0 CHECK(snapshot_count>=0)',
        'UPDATE photo_sources SET snapshot_count=(SELECT count(*) FROM versions WHERE source_id=photo_sources.id)',
        'CREATE INDEX source_snapshot_count ON photo_sources(snapshot_count,id)',
        'CREATE TABLE snapshot_filter_state(id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER NOT NULL DEFAULT 0)',
        'INSERT INTO snapshot_filter_state(id) VALUES(1)',
        'CREATE TRIGGER snapshot_presence_insert AFTER INSERT ON versions BEGIN '
        'UPDATE snapshot_filter_state SET revision=revision+1 WHERE id=1 AND EXISTS '
        '(SELECT 1 FROM photo_sources WHERE id=NEW.source_id AND snapshot_count=0); '
        'UPDATE photo_sources SET snapshot_count=snapshot_count+1 WHERE id=NEW.source_id; END',
        'CREATE TRIGGER snapshot_presence_delete AFTER DELETE ON versions BEGIN '
        'UPDATE snapshot_filter_state SET revision=revision+1 WHERE id=1 AND EXISTS '
        '(SELECT 1 FROM photo_sources WHERE id=OLD.source_id AND snapshot_count=1); '
        'UPDATE photo_sources SET snapshot_count=snapshot_count-1 WHERE id=OLD.source_id; END',
        'CREATE TRIGGER snapshot_presence_move AFTER UPDATE OF source_id ON versions '
        'WHEN NEW.source_id!=OLD.source_id BEGIN '
        'UPDATE snapshot_filter_state SET revision=revision+1 WHERE id=1 AND EXISTS '
        '(SELECT 1 FROM photo_sources WHERE (id=OLD.source_id AND snapshot_count=1) '
        'OR (id=NEW.source_id AND snapshot_count=0)); '
        'UPDATE photo_sources SET snapshot_count=snapshot_count-1 WHERE id=OLD.source_id; '
        'UPDATE photo_sources SET snapshot_count=snapshot_count+1 WHERE id=NEW.source_id; END',
        'PRAGMA user_version=25',
    )
    db.execute('BEGIN IMMEDIATE')
    try:
        for statement in statements:
            db.execute(statement)
        db.commit()
    except BaseException:
        db.rollback()
        raise


def revision(db):
    return db.execute('SELECT revision FROM snapshot_filter_state WHERE id=1').fetchone()[0]
