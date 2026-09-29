"""Captured Develop/metadata presets and keywords for reviewed Add imports.

Inputs: explicit preset revisions, a ready plan revision and keyword text. Outputs:
durable setting snapshots, bounded summaries and atomic new-photo application.
Preset libraries are read before catalog writes; LUT copying/hashing stays outside
SQL locks. Later preset changes cannot retarget a saved choice. Originals, existing
photos and queued exports are untouched. No Adobe preset translation or sidecars.
"""
import hashlib
import json
from pathlib import Path

from .develop_presets import stage_lut, read_lut
from .keywords import Keywords, valid_name
from .organization import folded
from .metadata_presets import MetadataPresets, validate_patch
from .model import Recipe


def migrate(db):
    if db.execute('PRAGMA user_version').fetchone()[0] >= 20:
        return
    db.execute('BEGIN IMMEDIATE')
    try:
        db.execute("CREATE TABLE import_processing(plan_id INTEGER PRIMARY KEY,"
                   "develop_id TEXT NOT NULL DEFAULT '',develop_name TEXT NOT NULL DEFAULT '',"
                   "develop_patch TEXT NOT NULL DEFAULT '{}',metadata_id TEXT NOT NULL DEFAULT '',"
                   "metadata_name TEXT NOT NULL DEFAULT '',metadata_patch TEXT NOT NULL DEFAULT '{}',"
                   "keywords TEXT NOT NULL DEFAULT '[]',keyword_paths TEXT NOT NULL DEFAULT '{}')")
        db.execute('CREATE TRIGGER import_processing_delete AFTER DELETE ON import_plans BEGIN '
                   'DELETE FROM import_processing WHERE plan_id=OLD.id; END')
        db.execute('PRAGMA user_version=20')
        db.commit()
    except BaseException:
        db.rollback()
        raise


def settings(catalog, plan_id):
    row = catalog.db.execute('SELECT * FROM import_processing WHERE plan_id=?', (plan_id,)).fetchone()
    result = dict(row) if row else {'plan_id':plan_id, 'develop_id':'', 'develop_name':'',
                                  'develop_patch':'{}', 'metadata_id':'', 'metadata_name':'',
                                  'metadata_patch':'{}', 'keywords':'[]', 'keyword_paths':'{}'}
    for key in ('develop_patch', 'metadata_patch', 'keywords', 'keyword_paths'):
        result[key] = json.loads(result[key])
    return result


def summary(value):
    return {key:value[key] for key in ('develop_id', 'develop_name', 'metadata_id', 'metadata_name')} | {
        'keyword_count':len(value['keywords']),
        'develop_key':hashlib.sha256(json.dumps(value['develop_patch'], sort_keys=True).encode()).hexdigest()}


def brief(catalog, plan_id):
    # Paging never materializes a captured metadata preset or keyword text.
    row = catalog.db.execute('SELECT develop_id,develop_name,metadata_id,metadata_name,'
        'develop_patch,json_array_length(keywords) AS keyword_count FROM import_processing WHERE plan_id=?',
        (plan_id,)).fetchone()
    if row is None:
        return summary(settings(catalog, plan_id))
    result = dict(row)
    patch = json.loads(result.pop('develop_patch'))
    result['develop_key'] = hashlib.sha256(json.dumps(patch, sort_keys=True).encode()).hexdigest()
    return result


def develop_patch(catalog, plan_id):
    row = catalog.db.execute('SELECT develop_patch FROM import_processing WHERE plan_id=?', (plan_id,)).fetchone()
    return json.loads(row[0]) if row else {}


def capture_keywords(catalog, values, transport_limit=False):
    """Resolve ambiguous legacy leaf text without committing vocabulary changes."""
    tags = Keywords(catalog)
    result, paths = [], []
    catalog.db.execute('SAVEPOINT import_keyword_capture')
    try:
        for value in values:
            parts = [row['name'] for row in tags.ancestors(tags.resolve(value))]
            path = ' | '.join(parts)
            if path not in result:
                result.append(path)
                paths.append(parts)
    finally:
        catalog.db.execute('ROLLBACK TO import_keyword_capture')
        catalog.db.execute('RELEASE import_keyword_capture')
    if transport_limit and len(json.dumps(result).encode()) > 128 * 1024:
        raise ValueError('Import keyword text exceeds the 128 KiB transport limit')
    return result, paths


def resolve_paths(catalog, paths):
    # Captured root names must not become a same-named leaf introduced by XMP.
    # Exact segments also preserve legacy names that contain path delimiters.
    cache, result = {}, []
    for parts in paths:
        parent = None
        prefix = []
        for name in parts:
            prefix.append(folded(name))
            key = tuple(prefix)
            if key not in cache:
                row = catalog.db.execute('SELECT id FROM keywords WHERE parent_id IS ? AND normalized=?',
                                         (parent, key[-1])).fetchone()
                if row:
                    cache[key] = row[0]
                else:
                    valid_name(name)
                    cache[key] = catalog.db.execute('INSERT INTO keywords(parent_id,name,normalized) VALUES(?,?,?)',
                                                    (parent, name, key[-1])).lastrowid
                    catalog.db.execute('UPDATE keyword_state SET revision=revision+1')
            parent = cache[key]
        if parent not in result:
            result.append(parent)
    return result


def check_camera(patch, camera):
    if profile := patch.get('camera_profile'):
        if not camera or camera != profile['camera']:
            raise ValueError('Import Develop preset camera profile is incompatible with a checked photo')


def verify_asset(value):
    if lut := value['develop_patch'].get('lut'):
        if Path(lut['path']).is_symlink() or read_lut(lut['path']) != lut['sha256']:
            raise ValueError('Import preset LUT changed; choose the preset again')


def apply_metadata(catalog, value, where, params, cancelled):
    """Apply the captured patch in sixty-photo batches inside the import transaction."""
    patch = value['metadata_patch']
    paths = [*value['keyword_paths'].get('metadata', []), *value['keyword_paths'].get('additional', [])]
    if not patch and not paths:
        return
    additions = resolve_paths(catalog, paths)
    if len(additions) > 100:
        raise ValueError('Import settings exceed 100 assigned keywords per photo')
    after = 0
    while True:
        if cancelled():
            raise InterruptedError('Import cancelled')
        rows = catalog.db.execute('SELECT f.id AS import_id,p.id,p.metadata_revision,p.rating FROM photos p '
            'JOIN import_files f ON p.path=f.path AND p.is_virtual=0 WHERE '+where+
            ' AND f.id>? ORDER BY f.id LIMIT 60', (*params, after)).fetchall()
        if not rows:
            return
        targets = [{'photo_id':row['id'], 'expected_metadata_revision':row['metadata_revision'],
                    'expected_rating':row['rating']} for row in rows]
        MetadataPresets.apply(catalog, patch, targets, keyword_ids=additions)
        after = rows[-1]['import_id']


class ImportProcessing:
    def __init__(self, service):
        self.service = service

    def capture_metadata(self, choice):
        repository = self.service.metadata_presets
        with repository.transaction() as (shared, catalog, db, _):
            if choice['expected_revision'] != repository.token(shared, catalog):
                raise ValueError('Metadata presets, storage or keywords changed; refresh before continuing')
            row = repository.row(db, choice['preset_id'])
            patch = validate_patch(json.loads(row['patch']))
            words, paths = capture_keywords(catalog, patch.get('keywords', []))
            if 'keywords' in patch:
                patch['keywords'] = words
            return {'id':row['id'], 'name':row['name'], 'patch':patch, 'keyword_paths':paths}

    def get(self, plan_id):
        from .import_review import ImportReview
        with self.service.catalog() as catalog:
            plan = ImportReview(catalog).row(plan_id)
            value = settings(catalog, plan_id)
            return {'plan_id':plan_id, 'revision':plan['revision'], 'state':plan['state'],
                    **summary(value), 'keywords':value['keywords']}

    def set(self, plan_id, expected_revision, **changes):
        from .import_review import ImportReview
        if not changes:
            raise ValueError('Choose an import setting to change')
        with self.service.catalog() as catalog:
            ImportReview(catalog).check(plan_id, expected_revision, ('ready',))
        captured = {}
        for kind in ('develop', 'metadata'):
            key = kind+'_preset'
            if key not in changes:
                continue
            choice = changes[key]
            if choice is None:
                captured[kind] = {'id':'', 'name':'', 'patch':{}, 'keyword_paths':[]}
                continue
            if kind == 'metadata':
                captured[kind] = self.capture_metadata(choice)
                continue
            repository = getattr(self.service, kind+'_presets')
            result = repository.dispatch('get_'+kind+'_preset', choice)
            row = result['preset']
            patch = row['patch']
            if kind == 'develop':
                patch = stage_lut(patch, self.service.root)
                # Reject edits/scope changes during asset I/O before persisting.
                repository.dispatch('get_develop_preset', choice)
            captured[kind] = {'id':row['id'], 'name':row['name'], 'patch':patch}
        with self.service.catalog() as catalog, catalog.db:
            catalog.db.execute('BEGIN IMMEDIATE')
            domain = ImportReview(catalog)
            plan = domain.check(plan_id, expected_revision, ('ready',))
            value = settings(catalog, plan_id)
            for kind, row in captured.items():
                value[kind+'_id'], value[kind+'_name'] = row['id'], row['name']
                value[kind+'_patch'] = row['patch']
            if 'metadata' in captured:
                value['keyword_paths']['metadata'] = captured['metadata']['keyword_paths']
            if 'keywords' in changes:
                words, paths = capture_keywords(catalog, changes['keywords'], transport_limit=True)
                value['keywords'], value['keyword_paths']['additional'] = words, paths
            if profile := value['develop_patch'].get('camera_profile'):
                mismatch = catalog.db.execute("SELECT 1 FROM import_files WHERE plan_id=? AND selected=1 AND "+
                    domain.eligible(plan)+" AND COALESCE(json_extract(clock,'$.camera'),'')!=? LIMIT 1",
                    (plan_id, profile['camera'])).fetchone()
                if mismatch:
                    raise ValueError('Import Develop preset camera profile is incompatible with a checked photo')
            Recipe.parse(value['develop_patch'])
            catalog.db.execute('INSERT INTO import_processing VALUES(?,?,?,?,?,?,?,?,?) '
                'ON CONFLICT(plan_id) DO UPDATE SET develop_id=excluded.develop_id,develop_name=excluded.develop_name,'
                'develop_patch=excluded.develop_patch,metadata_id=excluded.metadata_id,metadata_name=excluded.metadata_name,'
                'metadata_patch=excluded.metadata_patch,keywords=excluded.keywords,keyword_paths=excluded.keyword_paths',
                (plan_id, value['develop_id'], value['develop_name'], json.dumps(value['develop_patch']),
                 value['metadata_id'], value['metadata_name'], json.dumps(value['metadata_patch']), json.dumps(value['keywords']),
                 json.dumps(value['keyword_paths'])))
            catalog.db.execute('UPDATE import_plans SET revision=revision+1 WHERE id=?', (plan_id,))
        return self.get(plan_id)
