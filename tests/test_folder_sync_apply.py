"""Folder Sync apply regressions for sparse work and catalog consistency.

Purpose: exercise the transactional apply path after a reviewed scan. Inputs are
isolated generated originals, XMP sidecars, staged rows and controlled catalog
changes; outputs are catalog-only synchronization results and query-shape
evidence. These tests do not claim RAW decoder or desktop performance.
Filesystem identity validation remains owned by FolderSyncRunner; direct domain
calls below are used only for synthetic staged-row scale evidence.
"""
import hashlib
from pathlib import Path

from PIL import Image
import pytest

from lumaraw.folder_sync import FolderSync
from lumaraw.service import Service
from test_xmp_read import packet


def _image(path, size=(12, 8), color='navy'):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new('RGB', size, color).save(path)
    return path


def _photo_id(service, path):
    with service.catalog() as catalog:
        row = catalog.db.execute('SELECT id FROM photos WHERE path=?', (str(path),)).fetchone()
    assert row is not None
    return row['id']


def _photo(service, path):
    return service.dispatch('get_photo', {'photo_id': _photo_id(service, path)})


def _prepare(service, metadata=True):
    photos = service.dispatch('list_photos', {'stacked': False})['photos']
    assert photos
    folder = service.dispatch('get_folder', {'photo_id': photos[0]['id']})
    return service.dispatch('prepare_folder_sync', {
        'folder_id': folder['id'], 'expected_revision': folder['folder_revision'],
        'scan_metadata': metadata,
    })['plan']


def _scan(service, plan):
    while plan['state'] in ('planning', 'interrupted'):
        plan = service.dispatch('scan_folder_sync', {
            'plan_id': plan['id'], 'expected_revision': plan['revision'],
        })['plan']
    return plan


def _apply(service, plan, **options):
    return service.dispatch('apply_folder_sync', {
        'plan_id': plan['id'], 'expected_revision': plan['revision'], **options,
    })['plan']


def _select(service, plan, kind, item_id, selected=False):
    return service.dispatch('select_folder_sync_items', {
        'plan_id': plan['id'], 'expected_revision': plan['revision'],
        'kind': kind, 'item_ids': [item_id], 'selected': selected,
    })['plan']


def _items(service, kind):
    return service.dispatch('get_folder_sync', {'kind': kind})['items']


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_mixed_apply_refreshes_deselected_stats_and_keeps_unselected_metadata(tmp_path):
    root = tmp_path / 'Photos'
    first, changed, missing = (_image(root / name) for name in ('first.png', 'changed.png', 'missing.png'))
    service = Service(tmp_path / 'catalog')
    try:
        service.dispatch('queue_control', {'action': 'pause'})
        service.dispatch('import_photos', {'paths': [str(first), str(changed), str(missing)]})
        first_before, changed_before, missing_before = (_photo(service, path) for path in (first, changed, missing))
        for path, prior, title in ((first, first_before, 'First local'),
                                   (changed, changed_before, 'Changed local'),
                                   (missing, missing_before, 'Missing local')):
            service.dispatch('edit_metadata', {
                'targets': [{'photo_id': prior['id'], 'expected_metadata_revision': prior['metadata_revision']}],
                'patch': {'title': title},
            })

        first.with_suffix('.xmp').write_bytes(packet('<dc:title>First from XMP</dc:title>'))
        changed.with_suffix('.xmp').write_bytes(packet('<dc:title>Changed from XMP</dc:title>'))
        _image(changed, size=(19, 11), color='orange')
        missing.unlink()
        added = _image(root / 'Added' / 'new.png', size=(9, 7), color='red')
        before_apply = {path: _sha256(path) for path in root.rglob('*') if path.is_file()}

        plan = _scan(service, _prepare(service, metadata=True))
        assert plan['state'] == 'ready'
        assert plan['counts'] == {'updated': 2, 'missing': 1, 'new': 1}
        changed_item = next(row for row in _items(service, 'updated') if row['path'] == str(changed))
        missing_item = next(row for row in _items(service, 'missing') if row['path'] == str(missing))
        plan = _select(service, plan, 'updated', changed_item['id'])
        plan = _select(service, plan, 'missing', missing_item['id'])

        result = _apply(service, plan, read_metadata=True)
        assert result['state'] == 'applied' and result['imported'] == 1

        first_after = _photo(service, first)
        changed_after = _photo(service, changed)
        missing_after = _photo(service, missing)
        assert first_after['title'] == 'First from XMP'
        assert first_after['source_revision'] == first_before['source_revision']
        assert changed_after['title'] == 'Changed local'
        assert changed_after['bytes'] == changed.stat().st_size
        assert changed_after['mtime'] == changed.stat().st_mtime_ns
        assert changed_after['source_revision'] == changed_before['source_revision'] + 1
        assert changed_after['metadata_revision'] == changed_before['metadata_revision'] + 1
        assert missing_after['missing'] == 1
        assert missing_after['title'] == 'Missing local'
        assert missing_after['source_revision'] == missing_before['source_revision'] + 1
        assert _photo(service, added)['bytes'] == added.stat().st_size
        assert {path: _sha256(path) for path in before_apply} == before_apply
    finally:
        service.close()


def test_unchanged_apply_repairs_index_missing_for_original_family(tmp_path, monkeypatch):
    root = tmp_path / 'Photos'
    original = _image(root / 'family.png')
    service = Service(tmp_path / 'catalog')
    try:
        service.dispatch('queue_control', {'action': 'pause'})
        service.dispatch('import_photos', {'paths': [str(original)]})
        master = _photo(service, original)
        service.dispatch('edit_photo', {
            'photo_id': master['id'], 'expected_revision': master['revision'],
            'patch': {'exposure': 0.75},
        })
        master = _photo(service, original)
        variant = service.dispatch('create_virtual_copies', {'targets': [{
            'photo_id': master['id'], 'expected_revision': master['revision'],
            'expected_metadata_revision': master['metadata_revision'],
        }]})['photos'][0]
        service.dispatch('edit_metadata', {
            'targets': [{'photo_id': master['id'], 'expected_metadata_revision': master['metadata_revision']}],
            'patch': {'title': 'Master title'},
        })
        service.dispatch('edit_metadata', {
            'targets': [{'photo_id': variant['id'], 'expected_metadata_revision': variant['metadata_revision']}],
            'patch': {'title': 'Copy title'},
        })
        service.dispatch('index_library')
        master_before, variant_before = _photo(service, original), service.dispatch(
            'get_photo', {'photo_id': variant['id']})
        plan = _scan(service, _prepare(service, metadata=False))
        assert plan['counts'] == {'unchanged': 1}

        real_stat = Path.stat

        def fail_only_original(path, *args, **kwargs):
            if path == original:
                raise FileNotFoundError(str(path))
            return real_stat(path, *args, **kwargs)

        with monkeypatch.context() as patch:
            patch.setattr(Path, 'stat', fail_only_original)
            service.dispatch('index_library')

        master_missing, variant_missing = _photo(service, original), service.dispatch(
            'get_photo', {'photo_id': variant['id']})
        assert master_missing['missing'] == variant_missing['missing'] == 1
        assert master_missing['source_revision'] == master_before['source_revision']
        assert variant_missing['source_revision'] == variant_before['source_revision']

        result = _apply(service, plan, read_metadata=False)
        assert result['state'] == 'applied'
        master_after, variant_after = _photo(service, original), service.dispatch(
            'get_photo', {'photo_id': variant['id']})
        assert master_after['missing'] == variant_after['missing'] == 0
        assert master_after['source_revision'] == master_before['source_revision'] + 1
        assert variant_after['source_revision'] == variant_before['source_revision'] + 1
        assert master_after['recipe'] == master_before['recipe']
        assert variant_after['recipe'] == variant_before['recipe']
        assert master_after['title'] == 'Master title'
        assert variant_after['title'] == 'Copy title'
    finally:
        service.close()


@pytest.mark.parametrize('conflict', ['source', 'file'])
def test_late_source_and_file_conflicts_reject_without_partial_apply(tmp_path, conflict):
    root = tmp_path / 'Photos'
    original = _image(root / 'original.png')
    added = _image(root / 'new.png', size=(8, 6), color='red')
    original.with_suffix('.xmp').write_bytes(packet('<dc:title>External title</dc:title>'))
    service = Service(tmp_path / 'catalog')
    try:
        service.dispatch('queue_control', {'action': 'pause'})
        service.dispatch('import_photos', {'paths': [str(original)]})
        photo_before_scan = _photo(service, original)
        service.dispatch('edit_metadata', {
            'targets': [{'photo_id': photo_before_scan['id'],
                         'expected_metadata_revision': photo_before_scan['metadata_revision']}],
            'patch': {'title': 'Catalog title'},
        })
        plan = _scan(service, _prepare(service, metadata=True))
        assert plan['counts'] == {'updated': 1, 'new': 1}

        if conflict == 'source':
            with service.catalog() as catalog, catalog.db:
                source_id = catalog.db.execute(
                    'SELECT source_id FROM photos WHERE path=?', (str(original),)).fetchone()['source_id']
                catalog.db.execute('UPDATE photo_sources SET revision=revision+1 WHERE id=?', (source_id,))
        else:
            _image(original, size=(15, 10), color='purple')
        before_apply = _photo(service, original)
        if conflict == 'source':
            assert before_apply['source_revision'] == photo_before_scan['source_revision'] + 1

        result = _apply(service, plan, read_metadata=True)
        assert result['state'] == 'failed'
        assert 'changed' in result['error'].lower() or 'scan again' in result['error'].lower()
        after = _photo(service, original)
        for field in ('recipe', 'title', 'metadata_revision', 'revision', 'source_revision',
                      'bytes', 'mtime', 'sha256', 'missing'):
            assert after[field] == before_apply[field]
        with service.catalog() as catalog:
            assert catalog.db.execute('SELECT 1 FROM photos WHERE path=?', (str(added),)).fetchone() is None
            assert catalog.db.execute('SELECT count(*) FROM photos').fetchone()[0] == 1
    finally:
        service.close()


def test_large_unchanged_stage_uses_bounded_change_pages_and_sparse_repair(tmp_path, monkeypatch):
    from folder_sync_apply_probe import BASE_BYTES, BASE_MTIME, prepare_and_stage, seed_catalog
    from lumaraw.catalog import Catalog

    unchanged_count = 10_000
    catalog_path, photo_dir, folder_id, _seed_ms = seed_catalog(
        tmp_path / 'catalog', tmp_path, unchanged_count)
    plan_id, ready_revision, _folder_revision, counts = prepare_and_stage(
        catalog_path, folder_id, unchanged_count, changed=1)
    assert counts == {'unchanged': unchanged_count - 1, 'updated': 1}

    catalog = Catalog(catalog_path)
    try:
        db = catalog.db
        first_path = str(Path(photo_dir) / 'photo-00000000.jpg')
        first = db.execute('SELECT id,source_id,bytes,mtime FROM photos WHERE path=?', (first_path,)).fetchone()
        assert first is not None
        source_revision = db.execute('SELECT revision FROM photo_sources WHERE id=?',
                                     (first['source_id'],)).fetchone()[0]
        apply_page_sizes, missing_page_sizes, trace = [], [], []
        original_apply_pages = FolderSync.apply_pages
        original_missing_pages = FolderSync.unchanged_missing_pages

        def bounded_apply_pages(self, *args, **kwargs):
            rows = original_apply_pages(self, *args, **kwargs)
            apply_page_sizes.append(len(rows))
            assert len(rows) <= 60
            return rows

        def sparse_missing_pages(self, *args, **kwargs):
            rows = original_missing_pages(self, *args, **kwargs)
            missing_page_sizes.append(len(rows))
            assert len(rows) <= 60
            return rows

        def forbidden_full_plan_pages(*_args, **_kwargs):
            pytest.fail('apply must not materialize a whole-plan Python page')

        sync = FolderSync(catalog)
        verifying = sync.start_apply(plan_id, ready_revision, read_metadata=False, import_new=False)
        db.set_trace_callback(trace.append)
        monkeypatch.setattr(FolderSync, 'apply_pages', bounded_apply_pages)
        monkeypatch.setattr(FolderSync, 'unchanged_missing_pages', sparse_missing_pages)
        monkeypatch.setattr(FolderSync, 'pages', forbidden_full_plan_pages, raising=False)
        result = sync.apply(plan_id, verifying['revision'], import_new=False,
                            remove_missing=False, read_metadata=False)
        db.set_trace_callback(None)

        assert result['plan']['state'] == 'applied'
        assert apply_page_sizes and sum(apply_page_sizes) == 1 and max(apply_page_sizes) <= 60
        assert missing_page_sizes == [0]
        traced_change_query = next(sql for sql in trace
                                   if 'FROM folder_sync_files f JOIN photos p' in sql
                                   and "f.state IN ('new','duplicate','missing','updated','error')" in sql)
        explain = [row['detail'] for row in db.execute('EXPLAIN QUERY PLAN ' + traced_change_query)]
        assert any('folder_sync_changes' in detail for detail in explain), explain
        assert not any('TEMP B-TREE' in detail.upper() for detail in explain), explain
        assert not any('folder_sync_file_page' in detail for detail in explain), explain
        assert not any('SELECT * FROM folder_sync_files WHERE plan_id=' in sql
                       and 'ORDER BY id LIMIT 60' in sql for sql in trace)
        current = db.execute('SELECT bytes,mtime FROM photos WHERE id=?', (first['id'],)).fetchone()
        assert tuple(current) == (BASE_BYTES + 1, BASE_MTIME + 1)
        assert db.execute('SELECT revision FROM photo_sources WHERE id=?',
                          (first['source_id'],)).fetchone()[0] == source_revision + 1
        assert db.execute('SELECT count(*) FROM photos').fetchone()[0] == unchanged_count
        assert not Path(photo_dir).exists()
    finally:
        catalog.close()
