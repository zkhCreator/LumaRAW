"""Read-only, paginated destination-folder summaries for Copy reviews.

Inputs: a ready Copy plan revision, an optional relative-path cursor, and
transactionally maintained counts of selected originals. Outputs: one bounded
page of primary destination folders plus a separate flat second-copy summary.
No filesystem inspection, directory creation, clock parsing, filename ranking,
XMP counting, or transfer-journal mutation occurs in this read domain.
"""
import json
from pathlib import Path

from .import_copy import settings as copy_settings
from .import_review import ImportReview
from . import import_backup


PAGE_SIZE = 60
MAX_CURSOR_LENGTH = 4096


def migrate(db):
    """Add destination directory keys and materialized selected-photo counts."""
    if db.execute('PRAGMA user_version').fetchone()[0] >= 32:
        return
    db.execute('BEGIN IMMEDIATE')
    try:
        db.execute('ALTER TABLE import_files ADD COLUMN destination_directory TEXT')
        db.execute('CREATE TABLE import_destination_groups('
                   'plan_id INTEGER NOT NULL,directory TEXT COLLATE BINARY NOT NULL,'
                   'new_count INTEGER NOT NULL DEFAULT 0 CHECK(new_count>=0),'
                   'duplicate_count INTEGER NOT NULL DEFAULT 0 CHECK(duplicate_count>=0),'
                   'PRIMARY KEY(plan_id,directory))')
        db.execute('CREATE INDEX import_destination_group_new ON import_destination_groups(plan_id,directory) '
                   'WHERE new_count>0')
        db.execute('CREATE INDEX import_destination_group_selected ON import_destination_groups(plan_id,directory) '
                   'WHERE new_count+duplicate_count>0')

        db.execute("CREATE TRIGGER import_destination_group_insert AFTER INSERT ON import_files "
                   "WHEN NEW.destination_directory IS NOT NULL AND NEW.selected=1 "
                   "AND NEW.state IN ('new','duplicate') BEGIN "
                   'INSERT INTO import_destination_groups(plan_id,directory,new_count,duplicate_count) '
                   "VALUES(NEW.plan_id,NEW.destination_directory,NEW.state='new',NEW.state='duplicate') "
                   'ON CONFLICT(plan_id,directory) DO UPDATE SET '
                   'new_count=import_destination_groups.new_count+excluded.new_count,'
                   'duplicate_count=import_destination_groups.duplicate_count+excluded.duplicate_count; END')

        db.execute("CREATE TRIGGER import_destination_group_update_remove AFTER UPDATE OF "
                   "plan_id,destination_directory,selected,state ON import_files "
                   "WHEN OLD.destination_directory IS NOT NULL AND OLD.selected=1 "
                   "AND OLD.state IN ('new','duplicate') BEGIN "
                   'UPDATE import_destination_groups SET '
                   "new_count=new_count-(OLD.state='new'),"
                   "duplicate_count=duplicate_count-(OLD.state='duplicate') "
                   'WHERE plan_id=OLD.plan_id AND directory=OLD.destination_directory; '
                   'DELETE FROM import_destination_groups WHERE plan_id=OLD.plan_id '
                   'AND directory=OLD.destination_directory AND new_count=0 AND duplicate_count=0; END')

        db.execute("CREATE TRIGGER import_destination_group_update_add AFTER UPDATE OF "
                   "plan_id,destination_directory,selected,state ON import_files "
                   "WHEN NEW.destination_directory IS NOT NULL AND NEW.selected=1 "
                   "AND NEW.state IN ('new','duplicate') BEGIN "
                   'INSERT INTO import_destination_groups(plan_id,directory,new_count,duplicate_count) '
                   "VALUES(NEW.plan_id,NEW.destination_directory,NEW.state='new',NEW.state='duplicate') "
                   'ON CONFLICT(plan_id,directory) DO UPDATE SET '
                   'new_count=import_destination_groups.new_count+excluded.new_count,'
                   'duplicate_count=import_destination_groups.duplicate_count+excluded.duplicate_count; END')

        db.execute("CREATE TRIGGER import_destination_group_delete AFTER DELETE ON import_files "
                   "WHEN OLD.destination_directory IS NOT NULL AND OLD.selected=1 "
                   "AND OLD.state IN ('new','duplicate') BEGIN "
                   'UPDATE import_destination_groups SET '
                   "new_count=new_count-(OLD.state='new'),"
                   "duplicate_count=duplicate_count-(OLD.state='duplicate') "
                   'WHERE plan_id=OLD.plan_id AND directory=OLD.destination_directory; '
                   'DELETE FROM import_destination_groups WHERE plan_id=OLD.plan_id '
                   'AND directory=OLD.destination_directory AND new_count=0 AND duplicate_count=0; END')
        db.execute('CREATE TRIGGER import_destination_plan_delete AFTER DELETE ON import_plans BEGIN '
                   'DELETE FROM import_destination_groups WHERE plan_id=OLD.id; END')

        # Schema 31 Copy reviews already captured their layout and EXIF civil
        # clocks. Backfill in small stable pages; do not touch immutable transfer
        # targets, plan revisions, or global Import/Image counters.
        from .import_copy import relative_directory
        copies = db.execute('SELECT plan_id,organization,subfolder,roots,date_format '
                            'FROM import_copy_plans ORDER BY plan_id')
        for saved in copies:
            copy = dict(saved)
            copy['roots'] = json.loads(copy['roots'])
            after = 0
            while True:
                rows = db.execute('SELECT id,path,clock FROM import_files '
                                  'WHERE plan_id=? AND id>? ORDER BY id LIMIT 60',
                                  (copy['plan_id'],after)).fetchall()
                if not rows:
                    break
                for row in rows:
                    try:
                        clock = json.loads(row['clock'])
                    except (TypeError, json.JSONDecodeError):
                        clock = {}
                    if not isinstance(clock, dict):
                        clock = {}
                    directory = relative_directory(copy,{'path':row['path'],'clock':clock})
                    db.execute('UPDATE import_files SET destination_directory=? WHERE id=?',
                               (directory,row['id']))
                after = rows[-1]['id']
        db.execute('PRAGMA user_version=32')
        db.commit()
    except BaseException:
        db.rollback()
        raise


class ImportDestinations:
    """Return revision-bound pages of selected eligible primary folders."""

    def __init__(self,catalog):
        self.catalog,self.db=catalog,catalog.db

    def get(self,plan_id,expected_revision,after=None):
        if after is not None and (not isinstance(after,str) or len(after)>MAX_CURSOR_LENGTH):
            raise ValueError('Destination folder cursor exceeds the supported length')
        review=ImportReview(self.catalog)
        plan=review.check(plan_id,expected_revision,('ready',))
        copy=copy_settings(self.db,plan_id)
        if copy is None:
            raise ValueError('Destination folders are available only for a ready Copy review')

        if plan['skip_duplicates']:
            eligible='new_count>0'
        else:
            eligible='new_count+duplicate_count>0'
        where='plan_id=? AND '+eligible
        args=[plan_id]
        if after is not None:
            where+=' AND directory COLLATE BINARY>?'
            args.append(after)
        rows=self.db.execute('SELECT directory,new_count,duplicate_count FROM import_destination_groups '
                             'WHERE '+where+' ORDER BY directory COLLATE BINARY LIMIT ?',
                             (*args,PAGE_SIZE+1)).fetchall()
        more=len(rows)>PAGE_SIZE
        rows=rows[:PAGE_SIZE]
        items=[]
        for row in rows:
            relative=row['directory']
            items.append({'relative_path':relative,
                          'path':str(Path(copy['destination'])/relative) if relative else copy['destination'],
                          'photo_count':row['new_count'] if plan['skip_duplicates'] else
                              row['new_count']+row['duplicate_count']})
        next_after=rows[-1]['directory'] if more and rows else None
        backup=import_backup.settings(copy)
        return {'plan_id':plan_id,'revision':plan['revision'],'destination':copy['destination'],
                'selected_count':plan['selected_count'],'items':items,'next_after':next_after,
                'page_size':PAGE_SIZE,
                'backup':({'destination':backup['destination'],'subfolder':backup['subfolder'],
                           'photo_count':plan['selected_count']} if backup else None)}
