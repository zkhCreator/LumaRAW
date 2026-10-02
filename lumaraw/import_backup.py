"""One-time original-state second copies for explicit reviewed Copy imports.

Inputs: an existing secondary root and captured primary/source boundaries.
Outputs: pinned destinations, dated original-name targets and compact progress.
Filesystem inspection stays outside SQL locks. Transfer writes use the existing
exclusive Copy adapter; this module never catalogs backups or applies naming,
presets or recipes to them. This is not ongoing photo/catalog backup management.
"""
from datetime import datetime
import json
from pathlib import Path


def migrate(db):
    if db.execute('PRAGMA user_version').fetchone()[0] >= 28:
        return
    db.execute('BEGIN IMMEDIATE')
    try:
        db.execute("ALTER TABLE import_copy_plans ADD COLUMN backup TEXT NOT NULL DEFAULT '{}'")
        db.execute('ALTER TABLE import_copy_plans ADD COLUMN backup_copied INTEGER NOT NULL DEFAULT 0')
        db.execute('ALTER TABLE import_copy_plans ADD COLUMN backup_bytes INTEGER NOT NULL DEFAULT 0')
        db.execute('ALTER TABLE import_copy_plans ADD COLUMN backup_transfer_count INTEGER NOT NULL DEFAULT 0')
        db.execute("ALTER TABLE import_transfers ADD COLUMN role TEXT NOT NULL DEFAULT 'primary'")
        db.execute('PRAGMA user_version=28')
        db.commit()
    except BaseException:
        db.rollback()
        raise


def capture(destination, primary, catalog):
    from .import_copy_io import validate_destination, check_destination
    from .organization import folded
    check_destination(primary)
    sources = [{'path':path,'directory':True} for path in primary['roots']]
    value = validate_destination(destination,sources,catalog)
    a,b = Path(primary['destination']),Path(value['destination'])
    left,right = folded(str(a)).rstrip('/'),folded(str(b)).rstrip('/')
    if left == right or left.startswith(right+'/') or right.startswith(left+'/') or primary['destination_identity'] == value['destination_identity']:
        raise ValueError('Choose a second-copy folder separate from the main destination, with no overlap')
    value['subfolder'] = 'Imported on '+datetime.now().astimezone().strftime('%Y-%m-%d')
    value['same_volume'] = primary['destination_identity'][0] == value['destination_identity'][0]
    return value


def settings(copy):
    return json.loads(copy['backup'])


def target(backup, source):
    result = Path(backup['destination'])/backup['subfolder']/Path(source).name
    if len(str(result).encode('utf-8')) > 4096:
        raise ValueError('Second-copy destination exceeds the supported filesystem path length')
    return str(result)


def destination(copy, row):
    if row.get('role','primary') == 'primary':
        return copy
    backup = settings(copy)
    if row['role'] != 'second' or not backup:
        raise ValueError('The transfer has no captured destination')
    return backup


def summary(copy):
    value = settings(copy)
    if not value:
        return None
    return {key:value[key] for key in ('destination','subfolder','same_volume')} | {
        'copied':copy['backup_copied'],'copied_bytes':copy['backup_bytes'],'transfer_count':copy['backup_transfer_count']}


def set_backup(service, plan_id, expected_revision, destination):
    from .import_copy import settings as copy_settings
    from .import_review import ImportReview
    with service.catalog() as catalog:
        ImportReview(catalog).check(plan_id,expected_revision,('ready',))
        copy = copy_settings(catalog.db,plan_id)
        if copy is None:
            raise ValueError('Second copies require Copy mode; Add keeps files in place')
    # Filesystem availability and boundaries are inspected without holding SQL.
    value = capture(destination,copy,service.root) if destination is not None else {}
    with service.catalog() as catalog,catalog.db:
        catalog.db.execute('BEGIN IMMEDIATE')
        ImportReview(catalog).check(plan_id,expected_revision,('ready',))
        catalog.db.execute('UPDATE import_copy_plans SET backup=? WHERE plan_id=?',(json.dumps(value),plan_id))
        catalog.db.execute('UPDATE import_plans SET revision=revision+1 WHERE id=?',(plan_id,))
        return ImportReview(catalog).get(plan_id)
