"""Catalog-local session settings for Export With Previous.

Inputs: a successfully accepted manual export's canonical settings and catalog DB.
Outputs: one latest-session settings snapshot and monotonic revision for stale checks.
The singleton contains no selection, recipe, preset binding, or request identity.
Queue insertion owns the transaction; failed submissions and worker outcomes do not
change this state. No file processing or destination inspection occurs here.
"""
import json
import os

from .model import ExportOptions

FORMATS = ('jpeg', 'tiff16')


def migrate(db):
    """Schema 35: create an empty last-accepted-export singleton."""
    if db.execute('PRAGMA user_version').fetchone()[0] >= 35:
        return
    db.execute('BEGIN IMMEDIATE')
    try:
        db.execute('CREATE TABLE IF NOT EXISTS previous_export_session('
                   'id INTEGER PRIMARY KEY CHECK(id=1),'
                   'revision INTEGER NOT NULL CHECK(revision>=1),'
                   'settings TEXT NOT NULL)')
        db.execute('PRAGMA user_version=35')
        db.commit()
    except BaseException:
        db.rollback()
        raise


def canonical_settings(fmt, options, destination):
    """Validate and canonicalize the settings frozen into a queue submission."""
    if fmt not in FORMATS:
        raise ValueError('Unsupported export format')
    if not isinstance(options, dict):
        raise ValueError('Export options must be an object')
    if (not isinstance(destination, str) or not destination or '\x00' in destination
            or len(destination) > 4096 or not os.path.isabs(destination)):
        raise ValueError('Previous export destination must be a resolved absolute local path')
    try:
        destination.encode('utf-8')
    except UnicodeEncodeError as error:
        raise ValueError('Export destination must be valid Unicode text') from error
    try:
        normalized_options = ExportOptions.parse(options).dict()
    except (TypeError, ValueError) as error:
        raise ValueError(str(error)) from error
    return {'format': fmt, 'options': normalized_options, 'destination': destination}


def state(db):
    row = db.execute('SELECT revision,settings FROM previous_export_session WHERE id=1').fetchone()
    if row is None:
        return {'available': False, 'revision': 0, 'settings': None}
    try:
        settings = json.loads(row[1])
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError('Stored Previous export settings are invalid') from error
    if not isinstance(settings, dict) or set(settings) != {'format', 'options', 'destination'}:
        raise ValueError('Stored Previous export settings are invalid')
    # Catalog values are internal, but validate again before using them to create jobs.
    settings = canonical_settings(settings['format'], settings['options'], settings['destination'])
    return {'available': True, 'revision': row[0], 'settings': settings}


def summary(db):
    """Return the bounded polling token without decoding the settings payload."""
    row = db.execute('SELECT revision FROM previous_export_session WHERE id=1').fetchone()
    return {'available': row is not None, 'revision': row[0] if row is not None else 0}


def remember(db, settings):
    """Write a changed configuration inside the caller's queue transaction."""
    normalized = canonical_settings(settings['format'], settings['options'], settings['destination'])
    current = state(db)
    if current['available'] and current['settings'] == normalized:
        return current['revision']
    revision = current['revision'] + 1
    db.execute('INSERT INTO previous_export_session(id,revision,settings) VALUES(1,?,?) '
               'ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,settings=excluded.settings',
               (revision, json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(',', ':'))))
    return revision
