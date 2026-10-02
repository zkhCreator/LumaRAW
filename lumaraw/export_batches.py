"""Catalog-local batch provenance and destination/naming validation.

Inputs: one atomically accepted batch, frozen preset destinations/options, and its
queue jobs. Outputs: bounded batch summaries, job pages and checked destination
components/identities. Destination checks read filesystem state; the service owns
directory creation and transactional acceptance.
The schema migration is additive; this module never renders pixels, touches photo
sources, changes saved presets, or advances the catalog-local Previous settings.
"""
import json
import os
from pathlib import Path
import stat
import unicodedata

PAGE = 30
JOB_PAGE = 60
MAX_BATCH_JOBS = 1000
MAX_PRESET_IDS = 30
MAX_FILENAME_SUFFIX_BYTES = 120
MAX_SUBFOLDER_BYTES = 255


def validate_component(value, label, maximum_bytes):
    if not isinstance(value, str) or not value or value in ('.', '..'):
        raise ValueError(f'{label} must be one nonempty path component')
    try:
        encoded = value.encode('utf-8')
    except UnicodeEncodeError as error:
        raise ValueError(f'{label} must be valid Unicode text') from error
    if len(encoded) > maximum_bytes:
        raise ValueError(f'{label} exceeds {maximum_bytes} UTF-8 bytes')
    if value[-1] in ('.', ' '):
        raise ValueError(f'{label} cannot end in a dot or space')
    if any(ord(char) < 32 or ord(char) == 127 or char in '/\\<>:"|?*' for char in value):
        raise ValueError(f'{label} contains a separator, control, or reserved path character')
    device = value.split('.', 1)[0].upper()
    if device in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)),
                  *(f'LPT{i}' for i in range(1, 10))}:
        raise ValueError(f'{label} is reserved in portable filenames')
    return value


def component_key(value):
    return unicodedata.normalize('NFC', value).casefold()


def resolve_directory(value, label):
    if (not isinstance(value, str) or not value or '\x00' in value
            or len(value) > 4096 or not os.path.isabs(value)):
        raise ValueError(f'{label} must be an absolute local folder path')
    try:
        value.encode('utf-8')
        return str(Path(value).expanduser().resolve())
    except (UnicodeEncodeError, OSError, RuntimeError) as error:
        raise ValueError(f'{label} cannot be resolved') from error


def preflight_directory(value, label):
    """Reject an existing file or blocked ancestor before creating any target."""
    target = Path(value)
    cursor = target
    while True:
        if cursor.is_symlink():
            raise ValueError(f'{label} traverses a symbolic link that changed during preflight')
        if cursor.exists():
            if not cursor.is_dir():
                raise ValueError(f'{label} or one of its existing ancestors is not a folder')
            return
        parent = cursor.parent
        if parent == cursor:
            raise ValueError(f'{label} has no existing folder ancestor')
        cursor = parent


def preflight_child(parent, subfolder):
    """Require an existing parent child to be a real direct subdirectory."""
    parent_path = Path(parent)
    child = parent_path / subfolder
    if child.is_symlink():
        raise ValueError('Parent export subfolders cannot be symbolic links')
    if child.exists():
        if not child.is_dir():
            raise ValueError('A parent export subfolder already exists as a non-folder')
        resolved_parent = parent_path.resolve(strict=True)
        resolved_child = child.resolve(strict=True)
        if resolved_child.parent != resolved_parent:
            raise ValueError('A parent export subfolder must remain directly inside its chosen parent')
    preflight_directory(child, 'parent export subfolder')
    return child


def directory_identity(value, label):
    """Return a non-following directory identity for post-mkdir verification."""
    path = Path(value)
    try:
        metadata = path.stat(follow_symlinks=False)
    except OSError as error:
        raise ValueError(f'{label} changed after directory creation') from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise ValueError(f'{label} changed to a non-folder or symbolic link')
    return metadata.st_dev, metadata.st_ino


def migrate(db):
    """Schema 36: add immutable batch provenance and bounded batch browsing."""
    if db.execute('PRAGMA user_version').fetchone()[0] >= 36:
        return
    db.execute('BEGIN IMMEDIATE')
    try:
        columns = {row[1] for row in db.execute('PRAGMA table_info(jobs)')}
        for name, definition in (
            ('batch_id', 'TEXT'),
            ('preset_name', "TEXT NOT NULL DEFAULT ''"),
            ('collision_suffix', "TEXT NOT NULL DEFAULT ''"),
        ):
            if name not in columns:
                db.execute(f'ALTER TABLE jobs ADD COLUMN {name} {definition}')
        db.execute('CREATE TABLE IF NOT EXISTS export_batches('
                   'batch_id TEXT PRIMARY KEY,created REAL NOT NULL,revision TEXT NOT NULL,'
                   'photo_count INTEGER NOT NULL CHECK(photo_count>0),'
                   'preset_count INTEGER NOT NULL CHECK(preset_count>0),'
                   'queued INTEGER NOT NULL CHECK(queued>0),'
                   "destination_mode TEXT NOT NULL CHECK(destination_mode IN ('individual','parent'))," 
                   'parent_destination TEXT)')
        db.execute('CREATE INDEX IF NOT EXISTS export_batches_created '
                   'ON export_batches(created DESC,batch_id DESC)')
        db.execute('CREATE TABLE IF NOT EXISTS export_batch_presets('
                   'batch_id TEXT NOT NULL,preset_order INTEGER NOT NULL,preset_id TEXT NOT NULL,'
                   'name TEXT NOT NULL,format TEXT NOT NULL,options TEXT NOT NULL,destination TEXT NOT NULL,'
                   'subfolder TEXT,filename_suffix TEXT NOT NULL,'
                   'PRIMARY KEY(batch_id,preset_order),UNIQUE(batch_id,preset_id))')
        db.execute('CREATE INDEX IF NOT EXISTS jobs_batch_id_id ON jobs(batch_id,id)')
        db.execute('CREATE INDEX IF NOT EXISTS jobs_batch_id_state_id ON jobs(batch_id,state,id)')
        db.execute('PRAGMA user_version=36')
        db.commit()
    except BaseException:
        db.rollback()
        raise


def _offset(value):
    if type(value) is not int or value < 0:
        raise ValueError('offset must be a non-negative integer')
    return value


def summary(row):
    return {
        'batch_id': row['batch_id'],
        'created': row['created'],
        'photo_count': row['photo_count'],
        'preset_count': row['preset_count'],
        'queued': row['queued'],
        'revision': row['revision'],
        'destination_mode': row['destination_mode'],
    }


def list_batches(db, offset=0):
    """Return thirty compact batch rows; do not aggregate over historical jobs."""
    offset = _offset(offset)
    total = db.execute('SELECT count(*) FROM export_batches').fetchone()[0]
    offset = min(offset, max(0, ((total - 1) // PAGE) * PAGE))
    rows = db.execute('SELECT batch_id,created,photo_count,preset_count,queued,revision,destination_mode '
                      'FROM export_batches ORDER BY created DESC,batch_id DESC LIMIT ? OFFSET ?',
                      (PAGE, offset)).fetchall()
    batches = [summary(row) for row in rows]
    if batches:
        ids = [row['batch_id'] for row in batches]
        placeholders = ','.join('?' for _ in ids)
        counts = db.execute('SELECT batch_id,state,count(*) FROM jobs WHERE batch_id IN ('
                            + placeholders + ') GROUP BY batch_id,state', ids).fetchall()
        by_batch = {batch_id: {} for batch_id in ids}
        for batch_id, state, count in counts:
            by_batch[batch_id][state] = count
        for batch in batches:
            batch['counts'] = by_batch[batch['batch_id']]
    return {'batches': batches, 'total': total,
            'offset': offset, 'page_size': PAGE}


def batch_counts(db, batch_id):
    return {state: count for state, count in db.execute(
        'SELECT state,count(*) FROM jobs WHERE batch_id=? GROUP BY state ORDER BY state', (batch_id,))}


def get_batch(db, batch_id, offset=0):
    """Return captured preset descriptors and one bounded job page without recipes."""
    if not isinstance(batch_id, str) or not batch_id or len(batch_id) > 80:
        raise ValueError('batch_id is invalid')
    offset = _offset(offset)
    row = db.execute('SELECT batch_id,created,revision,photo_count,preset_count,queued,'
                     'destination_mode,parent_destination FROM export_batches WHERE batch_id=?',
                     (batch_id,)).fetchone()
    if row is None:
        raise ValueError('Export batch does not exist')
    batch = summary(row)
    batch['parent_destination'] = row['parent_destination']
    presets = []
    for item in db.execute('SELECT preset_id,name,format,options,destination,subfolder,filename_suffix '
                           'FROM export_batch_presets WHERE batch_id=? ORDER BY preset_order', (batch_id,)):
        presets.append({
            'preset_id': item['preset_id'], 'name': item['name'], 'format': item['format'],
            'options': json.loads(item['options']), 'destination': item['destination'],
            'subfolder': item['subfolder'], 'filename_suffix': item['filename_suffix'],
        })
    total = db.execute('SELECT count(*) FROM jobs WHERE batch_id=?', (batch_id,)).fetchone()[0]
    offset = min(offset, max(0, ((total - 1) // JOB_PAGE) * JOB_PAGE))
    jobs = db.execute(
        'SELECT id,photo_id,source,destination,format,state,error,peak_mb,created,output,priority,'
        'batch_id,preset_name,collision_suffix FROM jobs WHERE batch_id=? ORDER BY id LIMIT ? OFFSET ?',
        (batch_id, JOB_PAGE, offset)).fetchall()
    return {'batch': batch, 'presets': presets, 'jobs': [dict(item) for item in jobs],
            'total': total, 'offset': offset, 'page_size': JOB_PAGE,
            'counts': batch_counts(db, batch_id)}
