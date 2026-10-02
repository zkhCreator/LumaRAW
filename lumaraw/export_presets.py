"""Saved export settings with shared-default and catalog-local storage.

Inputs: revision-bound preset commands and validated format/options/destination values.
Outputs: bounded name pages, captured settings, and explicit preset mutations.
Presets never contain photos, recipes, request keys, or queue state. Destination
paths are preserved as literal user data and are never inspected during preset IO.
Shared storage locks before catalog storage; changing mode never moves records.
No image processing, filesystem destination creation, or job replay lives here.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import uuid

from .model import ExportOptions
from .organization import folded
from .develop_presets import title
from .preset_paths import preset_root

PAGE = 30
SETTINGS_FIELDS = {'format', 'options', 'destination'}
FORMAT_VALUES = ('jpeg', 'tiff16')


def create_tables(db):
    db.execute('CREATE TABLE IF NOT EXISTS export_preset_state('
               'id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER NOT NULL)')
    db.execute('INSERT OR IGNORE INTO export_preset_state VALUES(1,0)')
    db.execute('CREATE TABLE IF NOT EXISTS export_presets('
               'id TEXT PRIMARY KEY,name TEXT NOT NULL,normalized TEXT NOT NULL UNIQUE,settings TEXT NOT NULL)')
    db.execute('CREATE INDEX IF NOT EXISTS export_preset_names ON export_presets(normalized,id)')


def migrate(db):
    """Schema 34: add empty catalog-local export preset storage."""
    if db.execute('PRAGMA user_version').fetchone()[0] >= 34:
        return
    db.execute('BEGIN IMMEDIATE')
    try:
        create_tables(db)
        db.execute('PRAGMA user_version=34')
        db.commit()
    except BaseException:
        db.rollback()
        raise


def validate_settings(value):
    if not isinstance(value, dict) or set(value) != SETTINGS_FIELDS:
        raise ValueError('Export preset settings require exactly format, options, and destination')
    if value['format'] not in FORMAT_VALUES:
        raise ValueError('Unsupported export format')
    options = value['options']
    if not isinstance(options, dict):
        raise ValueError('Export preset options must be an object')
    try:
        options = ExportOptions.parse(options).dict()
    except (TypeError, ValueError) as error:
        raise ValueError(str(error)) from error
    destination = value['destination']
    if destination is not None:
        if (not isinstance(destination, str) or not destination or '\x00' in destination
                or len(destination) > 4096 or not os.path.isabs(destination)):
            raise ValueError('Export preset destination must be null or an absolute local path')
        try:
            destination.encode('utf-8')
        except UnicodeEncodeError as error:
            raise ValueError('Export preset destination is not valid UTF-8 text') from error
    result = {'format': value['format'], 'options': options, 'destination': destination}
    try:
        encoded = json.dumps(result, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    except UnicodeEncodeError as error:
        raise ValueError('Export preset settings must contain valid Unicode text') from error
    if len(encoded) > 32768:
        raise ValueError('Export preset settings exceed the 32 KiB limit')
    return result


class ExportPresets:
    def __init__(self, service, root=None):
        self.service = service
        self.root = (Path(root) if root is not None else preset_root()) / 'export'

    @contextmanager
    def transaction(self):
        self.root.mkdir(parents=True, exist_ok=True)
        shared = sqlite3.connect(self.root / 'presets.sqlite', timeout=5)
        shared.row_factory = sqlite3.Row
        try:
            shared.execute('BEGIN IMMEDIATE')
            version = shared.execute('PRAGMA user_version').fetchone()[0]
            if version > 1:
                raise ValueError('Export preset storage was created by a newer engine')
            if version == 0:
                create_tables(shared)
                shared.execute('CREATE TABLE IF NOT EXISTS export_storage('
                               'id INTEGER PRIMARY KEY CHECK(id=1),catalog INTEGER NOT NULL)')
                shared.execute('INSERT OR IGNORE INTO export_storage VALUES(1,0)')
                shared.execute('PRAGMA user_version=1')
            with self.service.catalog() as catalog, catalog.db:
                catalog.db.execute('BEGIN IMMEDIATE')
                local = bool(shared.execute('SELECT catalog FROM export_storage WHERE id=1').fetchone()[0])
                yield shared, catalog, catalog.db if local else shared, local
            shared.commit()
        except BaseException:
            shared.rollback()
            raise
        finally:
            shared.close()

    def token(self, shared, catalog):
        state = [str(catalog.root), str(self.root.resolve()),
                 shared.execute('SELECT revision FROM export_preset_state WHERE id=1').fetchone()[0],
                 catalog.db.execute('SELECT revision FROM export_preset_state WHERE id=1').fetchone()[0],
                 shared.execute('SELECT catalog FROM export_storage WHERE id=1').fetchone()[0]]
        return hashlib.sha256(json.dumps(state).encode('utf-8')).hexdigest()

    def page(self, shared, catalog, db, local, params):
        query = folded(params.get('search', ''))
        if query:
            total = db.execute('SELECT COUNT(*) FROM export_presets WHERE instr(normalized,?)>0',
                               (query,)).fetchone()[0]
        else:
            total = db.execute('SELECT COUNT(*) FROM export_presets').fetchone()[0]
        offset = min(params.get('offset', 0), max(0, (total - 1) // PAGE * PAGE))
        if query:
            rows = [dict(row) for row in db.execute(
                'SELECT id,name FROM export_presets WHERE instr(normalized,?)>0 '
                'ORDER BY normalized,id LIMIT 30 OFFSET ?', (query, offset))]
        else:
            rows = [dict(row) for row in db.execute(
                'SELECT id,name FROM export_presets ORDER BY normalized,id LIMIT 30 OFFSET ?',
                (offset,))]
        return {'presets': rows, 'total': total, 'offset': offset, 'page_size': PAGE,
                'revision': self.token(shared, catalog), 'store_with_catalog': local}

    @staticmethod
    def row(db, preset_id):
        row = db.execute('SELECT id,name,settings FROM export_presets WHERE id=?', (preset_id,)).fetchone()
        if row is None:
            raise ValueError('Export preset does not exist')
        return dict(row)

    @staticmethod
    def bump(db):
        db.execute('UPDATE export_preset_state SET revision=revision+1 WHERE id=1')

    def save(self, db, params):
        name = title(params['name'])
        settings = validate_settings(params['settings'])
        preset_id = params.get('preset_id')
        if preset_id:
            self.row(db, preset_id)
        duplicate = db.execute('SELECT id FROM export_presets WHERE normalized=? AND id!=?',
                               (folded(name), preset_id or '')).fetchone()
        if duplicate:
            raise ValueError('Export preset name already exists; choose another name')
        preset_id = preset_id or str(uuid.uuid4())
        value = json.dumps(settings, ensure_ascii=False, separators=(',', ':'))
        db.execute('INSERT INTO export_presets VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET '
                   'name=excluded.name,normalized=excluded.normalized,settings=excluded.settings',
                   (preset_id, name, folded(name), value))
        self.bump(db)
        return preset_id

    def dispatch(self, method, params):
        with self.transaction() as (shared, catalog, db, local):
            if method != 'list_export_presets' and params['expected_revision'] != self.token(shared, catalog):
                raise ValueError('Export presets or storage changed; refresh before continuing')
            result = {}
            if method == 'list_export_presets':
                return self.page(shared, catalog, db, local, params)
            if method == 'get_export_preset':
                row = self.row(db, params['preset_id'])
                row['settings'] = validate_settings(json.loads(row['settings']))
                return {'preset': row, 'revision': self.token(shared, catalog)}
            if method == 'save_export_preset':
                result['preset_id'] = self.save(db, params)
            elif method == 'export_preset_action':
                action = params['action']
                allowed = {'rename': {'preset_id', 'name'}, 'delete': {'preset_id'},
                           'storage': {'store_with_catalog'}}
                if action not in allowed or set(params) - {'action', 'expected_revision'} != allowed[action]:
                    raise ValueError('Provide exactly the fields required for this export preset action')
                if action == 'storage':
                    if type(params['store_with_catalog']) is not bool:
                        raise ValueError('store_with_catalog must be a boolean')
                    new_local = bool(params['store_with_catalog'])
                    if new_local != local:
                        shared.execute('UPDATE export_storage SET catalog=? WHERE id=1', (int(new_local),))
                        self.bump(shared)
                        local = new_local
                        db = catalog.db if local else shared
                else:
                    row = self.row(db, params['preset_id'])
                    if action == 'delete':
                        db.execute('DELETE FROM export_presets WHERE id=?', (row['id'],))
                        self.bump(db)
                    else:
                        result['preset_id'] = self.save(db, {'preset_id': row['id'], 'name': params['name'],
                                                            'settings': json.loads(row['settings'])})
            else:
                raise ValueError('Unsupported export preset command')
            return {**self.page(shared, catalog, db, local, {}), **result}
