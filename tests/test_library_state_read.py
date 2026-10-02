"""Verify coherent read-only snapshots for compact Library state.

Inputs: disposable catalogs and the four bounded Library/state read commands.
Outputs: lock-bypass, transaction-snapshot and compatibility assertions. The
suite uses event-gated writes and real interleaved domain commits. No production
data, pixels beyond tiny fixtures, or UI interaction are used.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import threading

from PIL import Image
import pytest
import jsonschema

from lumaraw.catalog_read import CatalogReadSnapshot
from lumaraw.collections import Collections
from lumaraw.folders import Folders
from lumaraw.library_queries import LibraryQueries
from lumaraw.previous_import import replace as replace_previous_import
from lumaraw.service import Service


STATE_KEYS = {
    'stack_revision', 'folder_revision', 'keyword_revision',
    'previous_import', 'snapshot_filter_revision',
}


@pytest.fixture
def library_service(tmp_path):
    root = tmp_path / 'state catalog % ? # 旅行'
    service = Service(root, presets_root=tmp_path / 'private-presets')
    try:
        service.dispatch('queue_control', {'action': 'pause'})
        photo_dir = tmp_path / '旅行' / '夏'
        photo_dir.mkdir(parents=True)
        paths = []
        for index in range(8):
            path = photo_dir / f'風景-{index:02}.png'
            Image.new('RGB', (8, 8), (index * 20, 80, 120)).save(path)
            paths.append(path)
        service.dispatch('import_photos', {'paths': [str(path) for path in paths]})
        with service.catalog() as catalog:
            ids = [row[0] for row in catalog.db.execute('SELECT id FROM photos ORDER BY id')]
        yield service, root, ids, paths
    finally:
        if not service.stopping.is_set():
            service.close()


def _write_while_holding_service_lock(service, command, params, mutate):
    before = service.dispatch(command, params)
    started = threading.Event()
    release = threading.Event()

    def writer():
        with service.catalog() as catalog:
            catalog.db.execute('BEGIN IMMEDIATE')
            mutate(catalog.db)
            started.set()
            if not release.wait(timeout=10):
                raise TimeoutError('Test writer was not released')
            catalog.db.commit()

    with ThreadPoolExecutor(max_workers=2) as pool:
        writer_future = pool.submit(writer)
        reader_future = None
        try:
            assert started.wait(timeout=5)
            reader_future = pool.submit(service.dispatch, command, params)
            during = reader_future.result(timeout=3)
        finally:
            release.set()
            writer_future.result(timeout=5)
            if reader_future is not None and not reader_future.done():
                reader_future.result(timeout=5)

    after = service.dispatch(command, params)
    return before, during, after


def _mutate_library_state(photo_id):
    def mutate(db):
        # Use the catalog's real Previous Import transition inside the writer's
        # still-uncommitted transaction; do not forge revision counters.
        replace_previous_import(db, 'SELECT source_id FROM photos WHERE id=?',
                                [photo_id], 'direct', 1)
    return mutate


def _mutate_photo_summary(photo_id):
    def mutate(db):
        db.execute('UPDATE photos SET rating=5,revision=revision+1 WHERE id=?', (photo_id,))
    return mutate


def _mutate_collection_state(collection_id, photo_id):
    def mutate(db):
        db.execute('INSERT INTO collection_photos(collection_id,photo_id) VALUES(?,?)',
                   (collection_id, photo_id))
        db.execute('UPDATE collections SET revision=revision+1 WHERE id=?', (collection_id,))
    return mutate


def _mutate_orientation_state(photo_id):
    def mutate(db):
        row = db.execute('SELECT orientation FROM photos WHERE id=?', (photo_id,)).fetchone()
        before = row['orientation']
        after = 1
        changes = json.dumps([{'photo_id': photo_id, 'before': before, 'after': after}])
        db.execute('UPDATE photos SET orientation=?,revision=revision+1 WHERE id=?', (after, photo_id))
        db.execute('UPDATE orientation_state SET revision=revision+1 WHERE id=1')
        db.execute('INSERT INTO orientation_history(action,changes) VALUES(?,?)',
                   ('rotate_right', changes))
    return mutate


def test_each_state_read_bypasses_service_catalog_and_keeps_old_then_new_snapshot(library_service, monkeypatch):
    service, _, ids, _ = library_service
    target = service.dispatch('collection_state', {'photo_ids': ids[:2]})['target']
    cases = [
        ('library_state', {}, _mutate_library_state(ids[0])),
        ('photo_summaries', {'photo_ids': ids[:3]}, _mutate_photo_summary(ids[0])),
        ('collection_state', {'photo_ids': ids[:3]},
         _mutate_collection_state(target['id'], ids[0])),
        ('orientation_state', {}, _mutate_orientation_state(ids[0])),
    ]

    for command, params, mutate in cases:
        def forbidden_catalog(*_args, **_kwargs):
            raise AssertionError(f'{command} must not open the serialized writable catalog')

        with monkeypatch.context() as patch:
            patch.setattr(service, 'catalog', forbidden_catalog)
            result = service.dispatch(command, params)
            assert result

        before, during, after = _write_while_holding_service_lock(
            service, command, params, mutate)
        assert during == before
        assert after != before

        if command == 'library_state':
            assert set(before) == STATE_KEYS
            assert after['previous_import']['revision'] == before['previous_import']['revision'] + 1
            assert after['previous_import']['imported'] == 1
        elif command == 'photo_summaries':
            assert set(before) == STATE_KEYS | {'photos'}
            changed = {row['id']: row for row in after['photos']}[ids[0]]
            assert changed['rating'] == 5 and changed['revision'] == before['photos'][0]['revision'] + 1
        elif command == 'collection_state':
            assert set(before) == {'revision', 'tree_revision', 'quick', 'target', 'members'}
            assert before['members'] == []
            assert set(after['members']) == {ids[0]}
            assert after['quick']['revision'] == before['quick']['revision'] + 1
            assert after['tree_revision'] > before['tree_revision']
        else:
            assert set(before) == {'revision', 'latest'}
            assert before['latest'] is None
            assert after['revision'] == before['revision'] + 1
            assert after['latest']['action'] == 'rotate_right'


def test_photo_summaries_preserve_bounded_ids_fields_and_photo_order(library_service):
    service, root, ids, _ = library_service
    requested = [ids[5], ids[1], ids[5], ids[3]]
    result = service.dispatch('photo_summaries', {'photo_ids': requested})
    assert set(result) == STATE_KEYS | {'photos'}
    assert [row['id'] for row in result['photos']] == sorted({ids[1], ids[3], ids[5]})
    assert all('recipe' not in row and 'metadata' not in row for row in result['photos'])

    with service.catalog() as catalog:
        writable_wrapper = catalog.summaries(requested)
    with CatalogReadSnapshot(root) as snapshot:
        queries = LibraryQueries(snapshot)
        snapshot_rows = queries.summaries(requested)
        with pytest.raises(ValueError, match='1 to 60'):
            queries.summaries([])
        with pytest.raises(ValueError, match='1 to 60'):
            queries.summaries((ids * 8)[:61])
    assert snapshot_rows == writable_wrapper == result['photos']

    with pytest.raises(jsonschema.ValidationError):
        service.dispatch('photo_summaries', {'photo_ids': []})
    with pytest.raises(jsonschema.ValidationError):
        service.dispatch('photo_summaries', {'photo_ids': (ids * 8)[:61]})
    with pytest.raises(jsonschema.ValidationError):
        service.dispatch('collection_state', {'photo_ids': (ids * 8)[:61]})


def test_collection_state_members_are_a_bounded_membership_set(library_service):
    service, _, ids, _ = library_service
    state = service.dispatch('collection_state', {'photo_ids': ids[:5]})
    assert set(state) == {'revision', 'tree_revision', 'quick', 'target', 'members'}
    assert state['quick']['kind'] == 'quick'
    assert state['target']['id'] == state['quick']['id']
    assert state['members'] == []

    service.dispatch('target_membership', {
        'collection_id': state['target']['id'],
        'expected_state_revision': state['revision'],
        'expected_revision': state['target']['revision'],
        'photo_ids': ids[1:4], 'action': 'add',
    })
    updated = service.dispatch('collection_state', {'photo_ids': [ids[4], ids[1], ids[3], ids[1]]})
    assert set(updated['members']) == {ids[1], ids[3]}
    # The target-member query has no ORDER BY. Membership is a set, not an order contract.


def test_library_state_interleaved_import_keeps_all_revisions_from_one_snapshot(library_service, monkeypatch):
    service, _, _, paths = library_service
    before = service.dispatch('library_state')
    new_path = paths[0].parent / 'new-state-read.png'
    Image.new('RGB', (8, 8), (180, 40, 80)).save(new_path)

    original_revision = Folders.revision
    imported = False

    def revision_then_import(folders):
        nonlocal imported
        revision = original_revision(folders)
        if not imported:
            imported = True
            service.dispatch('import_photos', {'paths': [str(new_path)]})
        return revision

    monkeypatch.setattr(Folders, 'revision', revision_then_import)
    during = service.dispatch('library_state')
    assert imported
    assert during == before

    after = service.dispatch('library_state')
    assert after['folder_revision'] > before['folder_revision']
    assert after['previous_import']['revision'] > before['previous_import']['revision']


def test_photo_summaries_interleaved_photo_edit_keeps_revision_envelope_and_rows_coherent(library_service, monkeypatch):
    service, _, ids, _ = library_service
    params = {'photo_ids': ids[:2]}
    before = service.dispatch('photo_summaries', params)
    original_revision = Folders.revision
    edited = False

    def revision_then_rate(folders):
        nonlocal edited
        revision = original_revision(folders)
        if not edited:
            edited = True
            service.dispatch('rate_photo', {'photo_id': ids[0], 'rating': 5})
        return revision

    monkeypatch.setattr(Folders, 'revision', revision_then_rate)
    during = service.dispatch('photo_summaries', params)
    assert edited
    assert during == before

    after = service.dispatch('photo_summaries', params)
    photo = {row['id']: row for row in after['photos']}[ids[0]]
    assert photo['rating'] == 5
    assert set(after) == STATE_KEYS | {'photos'}


def test_collection_state_interleaved_membership_keeps_target_and_members_coherent(library_service, monkeypatch):
    service, _, ids, _ = library_service
    params = {'photo_ids': ids[:3]}
    before = service.dispatch('collection_state', params)
    target = before['target']
    original_tree_revision = Collections.tree_revision
    added = False

    def tree_revision_then_membership(collections):
        nonlocal added
        revision = original_tree_revision(collections)
        if not added:
            added = True
            service.dispatch('collection_membership', {
                'collection_id': target['id'], 'expected_revision': target['revision'],
                'photo_ids': [ids[0]], 'action': 'add',
            })
        return revision

    monkeypatch.setattr(Collections, 'tree_revision', tree_revision_then_membership)
    during = service.dispatch('collection_state', params)
    assert added
    assert during == before

    after = service.dispatch('collection_state', params)
    assert set(after['members']) == {ids[0]}
    assert after['tree_revision'] > before['tree_revision']
    assert after['target']['revision'] == before['target']['revision'] + 1


def test_orientation_state_interleaved_action_keeps_history_and_revision_coherent(library_service, monkeypatch):
    service, _, ids, _ = library_service
    before = service.dispatch('orientation_state')
    row = service.dispatch('photo_summaries', {'photo_ids': [ids[0]]})['photos'][0]
    original_enter = CatalogReadSnapshot.__enter__
    injected = False

    class ExecuteHook:
        def __init__(self, db):
            self._db = db

        def __getattr__(self, name):
            return getattr(self._db, name)

        def execute(self, statement, *args, **kwargs):
            nonlocal injected
            cursor = self._db.execute(statement, *args, **kwargs)
            if (not injected and 'FROM orientation_history' in statement
                    and 'ORDER BY id DESC' in statement):
                # Commit a genuine orientation action after the latest-history
                # SELECT runs but before Orientations.state reads its revision.
                # Exceptions deliberately propagate through execute to the test.
                injected = True
                service.dispatch('orient_photos', {
                    'targets': [{'photo_id': ids[0], 'expected_revision': row['revision']}],
                    'action': 'rotate_right',
                })
            return cursor

    def enter_with_between_queries_hook(snapshot):
        opened = original_enter(snapshot)
        snapshot.db = ExecuteHook(snapshot.db)
        return opened

    with monkeypatch.context() as patch:
        patch.setattr(CatalogReadSnapshot, '__enter__', enter_with_between_queries_hook)
        during = service.dispatch('orientation_state')
    assert injected
    assert during == before

    after = service.dispatch('orientation_state')
    assert after['revision'] == before['revision'] + 1
    if before['latest'] is None:
        assert after['latest']['id'] > 0
    else:
        assert after['latest']['id'] > before['latest']['id']
    assert after['latest']['action'] == 'rotate_right'
