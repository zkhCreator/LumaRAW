"""Reusable catalog-local import configurations, separate from source selections.

Inputs: ready review/library revisions and explicit save/use/rename/delete actions.
Outputs: bounded preset names and frozen options, processing and naming snapshots.
Sources, checked rows, destination identities, transfer journals and dated backup
folders are never saved in presets. Each use pins fresh filesystem identities.
Date-folder layout is a captured option; old presets retain the year/date default.
Replacing a ready review requires explicit rescan and atomically retains its old
receipt; failures before commit preserve it. No original writes or preset replay.
"""
import json
import uuid

from . import import_processing as processing, import_naming as naming
from .import_copy import settings as copy_settings
from .import_review import ImportReview
from .develop_presets import title
from .organization import folded


def migrate(db):
    if db.execute('PRAGMA user_version').fetchone()[0] >= 29:
        return
    db.execute('BEGIN IMMEDIATE')
    try:
        db.execute('CREATE TABLE import_presets(id TEXT PRIMARY KEY,name TEXT NOT NULL,normalized TEXT NOT NULL UNIQUE,mode TEXT NOT NULL,value TEXT NOT NULL)')
        db.execute('CREATE INDEX import_preset_names ON import_presets(normalized,id)')
        db.execute('CREATE TABLE import_preset_state(id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER NOT NULL)')
        db.execute('INSERT INTO import_preset_state VALUES(1,0)')
        db.execute('CREATE TABLE import_sources(plan_id INTEGER PRIMARY KEY,paths TEXT NOT NULL)')
        db.execute('CREATE TRIGGER import_sources_delete AFTER DELETE ON import_plans BEGIN DELETE FROM import_sources WHERE plan_id=OLD.id; END')
        db.execute("ALTER TABLE import_plans ADD COLUMN preset_name TEXT NOT NULL DEFAULT ''")
        db.execute('PRAGMA user_version=29')
        db.commit()
    except BaseException:
        db.rollback()
        raise


def capture(catalog, plan_id, expected_revision):
    plan = ImportReview(catalog).check(plan_id, expected_revision, ('ready',))
    copy = copy_settings(catalog.db, plan_id)
    options = {'mode':'copy' if copy else 'add', 'include_subfolders':bool(plan['include_subfolders']),
               'skip_duplicates':bool(plan['skip_duplicates'])}
    value = {'options':options, 'processing':processing.settings(catalog, plan_id)}
    value['processing'].pop('plan_id')
    if copy:
        options.update({key:copy[key] for key in ('destination','organization','subfolder','date_format')})
        from .import_backup import settings
        options['second_copy_destination'] = settings(copy).get('destination')
        value['naming'] = naming.settings(copy)
    return value


def install(catalog, plan_id, value):
    """Install captured values inside the caller's plan-creation transaction."""
    p = value['processing']
    catalog.db.execute('INSERT INTO import_processing VALUES(?,?,?,?,?,?,?,?,?)',
        (plan_id, p['develop_id'], p['develop_name'], json.dumps(p['develop_patch']),
         p['metadata_id'], p['metadata_name'], json.dumps(p['metadata_patch']),
         json.dumps(p['keywords']), json.dumps(p['keyword_paths'])))
    if 'naming' in value:
        catalog.db.execute('UPDATE import_copy_plans SET naming=? WHERE plan_id=?', (json.dumps(value['naming']), plan_id))


class ImportPresets:
    def __init__(self, catalog):
        self.catalog, self.db = catalog, catalog.db

    def revision(self):
        return self.db.execute('SELECT revision FROM import_preset_state WHERE id=1').fetchone()[0]

    def check(self, expected_revision):
        if expected_revision != self.revision():
            raise ValueError('Import presets changed; refresh before continuing')

    def list(self, offset=0):
        rows = self.db.execute('SELECT id,name,mode FROM import_presets '
                               'ORDER BY normalized,id LIMIT 30 OFFSET ?', (offset,))
        return {'items':[dict(r) for r in rows], 'total':self.db.execute('SELECT count(*) FROM import_presets').fetchone()[0],
                'offset':offset, 'page_size':30, 'revision':self.revision(), 'storage':'catalog'}

    def read(self, preset_id, expected_revision):
        self.check(expected_revision)
        row = self.db.execute('SELECT id,name,value FROM import_presets WHERE id=?', (preset_id,)).fetchone()
        if row is None:
            raise ValueError('Import preset no longer exists')
        return {'id':row['id'], 'name':row['name'], 'value':json.loads(row['value'])}

    def get(self, preset_id, expected_revision):
        row = self.read(preset_id, expected_revision)
        value = row.pop('value')
        if value['options']['mode'] == 'copy':
            value['options'].setdefault('date_format','year_date')
        # Preset pickers do not transport potentially large recipe/metadata patches.
        return {**row, 'revision':expected_revision, 'options':value['options'],
                'processing':processing.summary(value['processing']), 'renaming':value.get('naming',{}).get('enabled',False)}

    def unique(self, name, preset_id):
        if self.db.execute('SELECT 1 FROM import_presets WHERE normalized=? AND id!=?', (folded(name), preset_id)).fetchone():
            raise ValueError('An import preset already has that name')

    def save(self, name, plan_id, expected_plan_revision, expected_revision, preset_id=None):
        name = title(name)
        with self.db:
            self.db.execute('BEGIN IMMEDIATE'); self.check(expected_revision)
            if preset_id:
                self.read(preset_id, expected_revision)
            else:
                preset_id = str(uuid.uuid4())
            self.unique(name, preset_id)
            value = json.dumps(capture(self.catalog, plan_id, expected_plan_revision))
            if len(value.encode()) > 1024*1024:
                raise ValueError('Import preset exceeds the 1 MiB settings limit')
            self.db.execute('INSERT INTO import_presets VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET '
                            'name=excluded.name,normalized=excluded.normalized,mode=excluded.mode,value=excluded.value',
                            (preset_id, name, folded(name), json.loads(value)['options']['mode'], value))
            self.db.execute('UPDATE import_preset_state SET revision=revision+1')
        return {**self.list(), 'preset_id':preset_id}

    def action(self, action, preset_id, expected_revision, name=None):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE'); self.read(preset_id, expected_revision)
            if action == 'rename':
                name = title(name or ''); self.unique(name, preset_id)
                self.db.execute('UPDATE import_presets SET name=?,normalized=? WHERE id=?', (name, folded(name), preset_id))
            elif action == 'delete':
                self.db.execute('DELETE FROM import_presets WHERE id=?', (preset_id,))
            else:
                raise ValueError('Unsupported import preset action')
            self.db.execute('UPDATE import_preset_state SET revision=revision+1')
        return self.list()


def prepare(service, params, replace=None):
    """Resolve source-neutral settings, inspect files unlocked, then commit once."""
    from .import_runner import sources
    from .import_copy_io import validate_destination
    from .import_backup import capture as backup_capture
    choice = params.get('preset')
    row = None
    with service.catalog() as catalog:
        if replace:
            ImportReview(catalog).check(replace['plan_id'], replace['expected_revision'], ('ready',))
            saved = catalog.db.execute('SELECT paths FROM import_sources WHERE plan_id=?', (replace['plan_id'],)).fetchone()
            if saved is None:
                raise ValueError('This older review has no source selection receipt; choose sources for a new review')
            params = {**params, 'paths':json.loads(saved[0])}
        if choice:
            row = ImportPresets(catalog).read(**choice)
    options = {**(row['value']['options'] if row else {}), **params}
    captured = sources(options['paths'])
    from pathlib import Path
    if any(Path(item['path']) == service.root or service.root in Path(item['path']).parents for item in captured):
        raise ValueError('The active catalog and its generated cache are not import sources')
    copy = None
    if options.get('mode','add') == 'copy':
        if not options.get('destination'):
            raise ValueError('Choose a Copy destination')
        copy = validate_destination(options['destination'], captured, service.root, options.get('organization','flat'),
                                    options.get('subfolder',''),options.get('date_format','year_date'))
        if options.get('second_copy_destination'):
            copy['backup'] = backup_capture(options['second_copy_destination'], copy, service.root)
    elif any(key in params for key in ('destination','organization','subfolder','date_format','second_copy_destination')):
        raise ValueError('Destination options require Copy mode')
    if row:
        processing.verify_asset(row['value']['processing'])
    def setup(catalog, plan_id):
        if row:
            ImportPresets(catalog).read(**choice)  # Recheck after unlocked file I/O.
            install(catalog, plan_id, row['value'])
            catalog.db.execute('UPDATE import_plans SET preset_name=? WHERE id=?', (row['name'], plan_id))
    with service.catalog() as catalog:
        return ImportReview(catalog).prepare(captured, options.get('include_subfolders',True),
            options.get('skip_duplicates',True), copy=copy, setup=setup, replace=replace)
