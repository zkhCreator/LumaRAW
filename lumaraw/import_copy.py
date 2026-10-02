"""Durable destination contracts and transfer journals for reviewed Copy imports.

Inputs: captured destination/source roots, bounded selected rows and I/O receipts.
Outputs: deterministic target paths, collision checks and resumable ownership state.
Captured naming/counters affect destination basenames and associated XMP stems only.
Date-folder format uses captured camera civil time, independent of host locale.
Second-copy transfers retain original names/bytes and never become catalog photos.
This domain owns SQL only; import_copy_io owns filesystem writes. Originals and
existing targets are never overwritten. Cancelled copies retain published files.
Restored catalogs cannot resume another catalog's filesystem operation.
"""
import json
from pathlib import Path
import uuid

from .organization import folded

COPY_PHASES = ('copy_preparing', 'copying')


def migrate(db):
    if db.execute('PRAGMA user_version').fetchone()[0] >= 26:
        return
    db.execute('BEGIN IMMEDIATE')
    try:
        db.execute("ALTER TABLE import_files ADD COLUMN catalog_path TEXT NOT NULL DEFAULT ''")
        db.execute('CREATE TABLE import_copy_plans(plan_id INTEGER PRIMARY KEY, destination TEXT NOT NULL,'
                   ' destination_identity TEXT NOT NULL, organization TEXT NOT NULL, subfolder TEXT NOT NULL,'
                   ' roots TEXT NOT NULL, owner TEXT NOT NULL, copied INTEGER NOT NULL DEFAULT 0,'
                   ' copied_bytes INTEGER NOT NULL DEFAULT 0, transfer_count INTEGER NOT NULL DEFAULT 0)')
        db.execute('CREATE TABLE import_transfers(id INTEGER PRIMARY KEY AUTOINCREMENT, plan_id INTEGER NOT NULL,'
                   ' source TEXT NOT NULL, target TEXT NOT NULL, target_key TEXT NOT NULL, source_identity TEXT NOT NULL,'
                   " temporary TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'planned', ownership TEXT NOT NULL DEFAULT '',"
                   " fingerprint TEXT NOT NULL DEFAULT '', sha256 TEXT NOT NULL DEFAULT '', UNIQUE(plan_id,target_key))")
        db.execute('CREATE INDEX import_transfer_page ON import_transfers(plan_id,id)')
        db.execute('CREATE TRIGGER import_copy_delete AFTER DELETE ON import_plans BEGIN '
                   'DELETE FROM import_copy_plans WHERE plan_id=OLD.id; '
                   'DELETE FROM import_transfers WHERE plan_id=OLD.id; END')
        db.execute('PRAGMA user_version=26')
        db.commit()
    except BaseException:
        db.rollback()
        raise


def settings(db, plan_id):
    row = db.execute('SELECT * FROM import_copy_plans WHERE plan_id=?', (plan_id,)).fetchone()
    if row is None:
        return None
    result = dict(row)
    for key in ('destination_identity', 'roots'):
        result[key] = json.loads(result[key])
    from .import_sequence import for_plan
    result['sequence'] = for_plan(db,plan_id)
    return result


def target(settings, row, ordinal=None, total=0):
    source = Path(row['path'])
    clock = row['clock'] if isinstance(row['clock'], dict) else json.loads(row['clock'])
    relative = Path(source.name)
    if settings['organization'] == 'source':
        roots = [Path(value) for value in settings['roots'] if Path(value) in source.parents]
        if roots:
            root = max(roots, key=lambda p: len(p.parts))
            relative = Path(root.name)/source.relative_to(root)
    elif settings['organization'] == 'date':
        # The original civil date is captured before UTC conversion; neither
        # the host timezone nor file modification time defines date folders.
        from .import_dates import folder
        relative = Path(folder(clock,settings.get('date_format','year_date')))/source.name
    from .import_naming import settings as naming_settings
    from .filename_templates import render
    name = render(naming_settings(settings), {**row,'clock':clock}, ordinal or row.get('naming_index',0), total,
                  settings.get('sequence'))
    result = Path(settings['destination'])/settings['subfolder']/relative.with_name(name)
    if len(str(result).encode()) > 4096:
        raise ValueError('Copy destination exceeds the supported filesystem path length')
    return str(result)


class ImportCopy:
    def __init__(self, catalog):
        self.catalog, self.db = catalog, catalog.db

    def capture(self, plan_id, value):
        self.db.execute('INSERT INTO import_copy_plans(plan_id,destination,destination_identity,organization,subfolder,roots,owner,date_format) '
                        'VALUES(?,?,?,?,?,?,?,?)', (plan_id, value['destination'], json.dumps(value['destination_identity']),
                        value['organization'], value['subfolder'], json.dumps(value['roots']), str(self.catalog.root),
                        value.get('date_format','year_date')))
        if value.get('backup'):
            self.db.execute('UPDATE import_copy_plans SET backup=? WHERE plan_id=?',(json.dumps(value['backup']),plan_id))

    def page(self, plan_id, after=0):
        return [dict(row) for row in self.db.execute('SELECT * FROM import_transfers WHERE plan_id=? AND id>? '
                                                    'ORDER BY id LIMIT 60', (plan_id, after))]

    def stage(self, plan_id, rows, value):
        from . import import_backup
        backup = import_backup.settings(value)
        total = self.db.execute('SELECT selected_count FROM import_plans WHERE id=?',(plan_id,)).fetchone()[0]
        with self.db:
            for row in rows:
                destination = target(value, row, total=total)
                if Path(destination) == self.catalog.root or self.catalog.root in Path(destination).parents:
                    raise ValueError('Copy destinations cannot be inside the active catalog')
                self.db.execute('UPDATE import_files SET catalog_path=? WHERE id=? AND plan_id=?',
                                (destination, row['id'], plan_id))
                seen = set()
                for source, fingerprint in json.loads(row['fingerprints']).items():
                    if fingerprint is None or tuple(fingerprint[:2]) in seen:
                        continue
                    seen.add(tuple(fingerprint[:2]))
                    if backup:
                        self.stage_transfer(plan_id,source,import_backup.target(backup,source),fingerprint,'second')
                    output = destination if source == row['path'] else str(Path(destination).with_suffix(Path(source).suffix))
                    self.stage_transfer(plan_id,source,output,fingerprint,'primary')

    def stage_transfer(self,plan_id,source,output,fingerprint,role):
        catalog_key=folded(str(self.catalog.root)).rstrip('/')
        if folded(output)==catalog_key or folded(output).startswith(catalog_key+'/'):
            raise ValueError('Copy destinations cannot be inside the active catalog')
        key = folded(output)
        previous = self.db.execute('SELECT source,source_identity,role FROM import_transfers '
                                   'WHERE plan_id=? AND target_key=?', (plan_id,key)).fetchone()
        if previous:
            if previous['source'] != source or previous['role'] != role or json.loads(previous['source_identity']) != fingerprint:
                raise ValueError('Selected files would share a destination: '+output)
            return  # One shared RAW/JPEG XMP is copied exactly once per target.
        self.db.execute('INSERT INTO import_transfers(plan_id,source,target,target_key,source_identity,temporary,role) '
                        'VALUES(?,?,?,?,?,?,?)',(plan_id,source,output,key,json.dumps(fingerprint),'.lumaraw-copy-'+uuid.uuid4().hex+'.part',role))
        self.db.execute('UPDATE import_copy_plans SET transfer_count=transfer_count+1,backup_transfer_count=backup_transfer_count+? '
                        'WHERE plan_id=?',(int(role=='second'),plan_id))

    def save(self, row, **patch):
        if not set(patch) <= {'state', 'ownership', 'fingerprint', 'sha256'}:
            raise ValueError('Invalid transfer receipt')
        with self.db:
            old = self.db.execute('SELECT state FROM import_transfers WHERE id=? AND plan_id=?',
                                  (row['id'], row['plan_id'])).fetchone()
            if old is None:
                raise ValueError('Copy journal is no longer available')
            self.db.execute('UPDATE import_transfers SET '+','.join(key+'=?' for key in patch)+' WHERE id=?',
                            (*patch.values(), row['id']))
            if patch.get('state') == 'published' and old['state'] != 'published':
                self.db.execute('UPDATE import_copy_plans SET copied=copied+1,copied_bytes=copied_bytes+? WHERE plan_id=?',
                                (json.loads(row['source_identity'])[2], row['plan_id']))
                if row.get('role') == 'second':
                    self.db.execute('UPDATE import_copy_plans SET backup_copied=backup_copied+1,backup_bytes=backup_bytes+? WHERE plan_id=?',
                                    (json.loads(row['source_identity'])[2],row['plan_id']))
        row.update(patch)

    def receipt(self, plan_id, offset=0):
        value = settings(self.db, plan_id)
        if value is None:
            raise ValueError('This is not a Copy import')
        rows = self.db.execute('SELECT source,target,state,role FROM import_transfers WHERE plan_id=? '
                               'ORDER BY id LIMIT 60 OFFSET ?', (plan_id, offset))
        return {'items':[dict(row) for row in rows], 'total':value['transfer_count'], 'offset':offset, 'page_size':60}
