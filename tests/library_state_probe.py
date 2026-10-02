"""Measure sequential Library-state reads during one large Folder Sync.

Inputs: a new work directory and synthetic catalog row count. Outputs: per-command
and whole-chain timings while the same bounded folder scan and atomic apply run.
Catalog rows point to absent synthetic originals except one empty placeholder;
10% empty .png files exercise discovery without pixel decoding. Direct in-process
Service.dispatch only: no IPC, broker admission, valid-image/RAW or desktop claims.
Separate commands commit/read independently, so only each reply's own page/count
shape is checked; cross-command revisions are recorded but intentionally not equated.
"""
import argparse
import json
import platform
import resource
import sqlite3
import sys
import threading
import time
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lumaraw.folder_sync import FolderSync
from lumaraw.model import Recipe
from lumaraw.runtime import CATALOG_VERSION, ENGINE_GENERATION
from lumaraw.service import Service


COMMANDS = ('list_photos', 'collection_state', 'orientation_state',
            'photo_summaries', 'library_state')
MAX_RECORDED_CHAINS = 1000


def summary(values):
    ordered = sorted(values)
    if not ordered:
        return {'samples': 0, 'median_ms': None, 'p95_ms': None, 'max_ms': None}
    return {'samples': len(values), 'median_ms': round(ordered[len(ordered)//2], 3)
            if len(ordered) % 2 else round((ordered[len(ordered)//2-1] + ordered[len(ordered)//2])/2, 3),
            'p95_ms': round(ordered[min(len(ordered)-1, int(len(ordered)*.95))], 3),
            'max_ms': round(ordered[-1], 3)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--rows', type=int, default=100000)
    args = parser.parse_args()
    if not 120 <= args.rows <= 1000000:
        raise SystemExit('Row count outside probe bounds')
    root = args.work.resolve()
    if root.exists():
        raise SystemExit('Choose a new work directory')
    root.mkdir(parents=True)
    pictures = root / 'Photos'
    pictures.mkdir()
    placeholder = pictures / 'existing.png'
    placeholder.touch()
    new = pictures / 'New'
    new.mkdir()
    new_count = args.rows // 10
    for index in range(new_count):
        (new / f'{index:08}.png').touch()

    service = Service(root / 'catalog', presets_root=root / 'presets')
    stop = threading.Event()
    phase_lock = threading.Lock()
    phase = 'setup'
    samples = []
    sample_counts = {'omitted': 0}
    command_times = {command: [] for command in COMMANDS}
    failures = []
    thread = None

    def set_phase(value):
        nonlocal phase
        with phase_lock:
            phase = value

    def current_phase():
        with phase_lock:
            return phase

    def dispatch_timed(method, params, times, active):
        active['command'] = method
        started = time.perf_counter()
        try:
            return service.dispatch(method, params)
        finally:
            elapsed = (time.perf_counter() - started) * 1000
            times[method] = round(elapsed, 3)
            if active.get('record_sample', True):
                command_times[method].append(elapsed)

    def read_chain(start_phase, active):
        started = time.perf_counter()
        times = {}

        page = dispatch_timed('list_photos', {'stacked': False}, times, active)
        rows = page.get('photos')
        if not isinstance(rows, list) or len(rows) > 60:
            raise AssertionError('list_photos must return at most sixty rows')
        if type(page.get('total')) is not int or page['total'] not in (args.rows, new_count + 1):
            raise AssertionError(f"Unexpected atomic before/after photo count: {page.get('total')}")
        if (page.get('offset') != 0 or page.get('page_size') != 60 or
                len(rows) > page['total']):
            raise AssertionError('list_photos count/page shape is inconsistent')
        page_ids = [row.get('id') for row in rows]
        if not page_ids or any(type(photo_id) is not int for photo_id in page_ids) or len(set(page_ids)) != len(page_ids):
            raise AssertionError('list_photos must return unique photo IDs for this nonempty fixture')
        for key in ('stack_revision', 'folder_revision', 'keyword_revision',
                    'snapshot_filter_revision'):
            if type(page.get(key)) is not int:
                raise AssertionError(f'list_photos is missing {key}')

        active['command'] = 'collection_state'
        collection = dispatch_timed('collection_state', {'photo_ids': page_ids}, times, active)
        if (type(collection.get('revision')) is not int or type(collection.get('tree_revision')) is not int or
                not isinstance(collection.get('quick'), dict) or not isinstance(collection.get('target'), dict)):
            raise AssertionError('collection_state response is incomplete')
        if any(type(collection[key].get('id')) is not int for key in ('quick', 'target')):
            raise AssertionError('collection_state quick/target IDs are malformed')
        members = collection.get('members')
        if (not isinstance(members, list) or any(type(photo_id) is not int for photo_id in members) or
                len(set(members)) != len(members) or not set(members).issubset(set(page_ids))):
            raise AssertionError('collection_state members must be a subset of the captured page IDs')

        active['command'] = 'orientation_state'
        orientation = dispatch_timed('orientation_state', {}, times, active)
        if type(orientation.get('revision')) is not int:
            raise AssertionError('orientation_state revision is missing')
        latest = orientation.get('latest')
        if latest is not None and (not isinstance(latest, dict) or type(latest.get('id')) is not int):
            raise AssertionError('orientation_state latest action is malformed')

        active['command'] = 'photo_summaries'
        summaries = dispatch_timed('photo_summaries', {'photo_ids': page_ids}, times, active)
        summary_rows = summaries.get('photos')
        if not isinstance(summary_rows, list) or len(summary_rows) > len(page_ids):
            raise AssertionError('photo_summaries must return no more than the captured page IDs')
        summary_ids = [row.get('id') for row in summary_rows]
        if (any(type(photo_id) is not int for photo_id in summary_ids) or
                len(set(summary_ids)) != len(summary_ids) or
                summary_ids != sorted(summary_ids) or
                not set(summary_ids).issubset(set(page_ids))):
            raise AssertionError('photo_summaries rows must be unique members of the captured page')
        if any(type(row.get('revision')) is not int or
               type(row.get('metadata_revision')) is not int for row in summary_rows):
            raise AssertionError('photo_summaries returned an invalid photo revision')
        for key in ('stack_revision', 'folder_revision', 'keyword_revision', 'snapshot_filter_revision'):
            if type(summaries.get(key)) is not int:
                raise AssertionError(f'photo_summaries is missing {key}')

        active['command'] = 'library_state'
        library = dispatch_timed('library_state', {}, times, active)
        previous = library.get('previous_import')
        if (not isinstance(previous, dict) or type(previous.get('revision')) is not int or
                any(type(library.get(key)) is not int for key in
                    ('stack_revision', 'folder_revision', 'keyword_revision', 'snapshot_filter_revision'))):
            raise AssertionError('library_state revision shape is incomplete')

        # Each endpoint owns its own transaction. Changes may commit between
        # replies, so preserve each token for analysis without asserting equality.
        signatures = {
            'list_photos': {'total': page['total'], 'ids': page_ids,
                            'offset': page['offset'], 'page_size': page['page_size'],
                            'stack_revision': page['stack_revision'],
                            'folder_revision': page['folder_revision'],
                            'keyword_revision': page['keyword_revision'],
                            'snapshot_filter_revision': page['snapshot_filter_revision'],
                            'previous_import_revision': page['previous_import']['revision']},
            'collection_state': {'revision': collection['revision'],
                                 'tree_revision': collection['tree_revision'],
                                 'quick_revision': collection['quick']['revision'],
                                 'target_revision': collection['target']['revision']},
            'orientation_state': {'revision': orientation['revision'],
                                  'latest_id': orientation['latest']['id'] if orientation['latest'] else None},
            'photo_summaries': {'ids': summary_ids,
                                'stack_revision': summaries['stack_revision'],
                                'folder_revision': summaries['folder_revision'],
                                'keyword_revision': summaries['keyword_revision'],
                                'snapshot_filter_revision': summaries['snapshot_filter_revision']},
            'library_state': {'folder_revision': library['folder_revision'],
                              'stack_revision': library['stack_revision'],
                              'keyword_revision': library['keyword_revision'],
                              'snapshot_filter_revision': library['snapshot_filter_revision'],
                              'previous_import_revision': previous['revision']},
        }
        return {'phase_started': start_phase, 'phase_finished': current_phase(),
                'chain_elapsed_ms': round((time.perf_counter() - started) * 1000, 3),
                'command_elapsed_ms': times, 'photo_total': page['total'],
                'page_count': len(page_ids), 'summary_count': len(summary_ids),
                'signatures': signatures}

    def reader():
        while not stop.wait(.02):
            phase_at_start = current_phase()
            if phase_at_start not in ('scan', 'apply'):
                continue
            active = {'command': 'list_photos',
                      'record_sample': len(samples) < MAX_RECORDED_CHAINS}
            try:
                sample = read_chain(phase_at_start, active)
                if active['record_sample']:
                    samples.append(sample)
                else:
                    sample_counts['omitted'] += 1
            except Exception as error:
                failures.append({'phase': phase_at_start,
                                 'command': active['command'],
                                 'error': str(error)})
                return

    try:
        service.dispatch('queue_control', {'action': 'pause'})
        seed_started = time.perf_counter()
        with service.catalog() as catalog, catalog.db:
            recipe = json.dumps(Recipe().dict())
            catalog.db.executemany(
                'INSERT INTO photos(path,name,bytes,mtime,recipe,created) VALUES(?,?,0,0,?,0)',
                ((str(placeholder) if index == 0 else
                  str(pictures / f'shoot-{index % 1000:04}' / f'{index:08}.png'),
                  f'{index:08}.png', recipe) for index in range(args.rows))
            )
        setup_ms = (time.perf_counter() - seed_started) * 1000
        folder = service.dispatch('get_folder', {'photo_id': 1})
        new_total = new_count + 1
        report = {
            'platform': platform.platform(),
            'machine': platform.machine(),
            'python_version': platform.python_version(),
            'sqlite_version': sqlite3.sqlite_version,
            'engine_generation': ENGINE_GENERATION,
            'catalog_schema_version': CATALOG_VERSION,
            'service_engine_identity': service.worker_identity,
            'memory_gb': round(psutil.virtual_memory().total / 1024**3, 1),
            'catalog_originals_before_apply': args.rows,
            'catalog_originals_after_apply': new_total,
            'synthetic_new_files': new_count,
            'scope': ('In-process Service.dispatch; list_photos followed sequentially by '
                      'collection_state, orientation_state, photo_summaries and library_state. '
                      'SQLite/control-plane reads plus Folder Sync directory stat only; no IPC/broker/UI/pixels.'),
            'fixture_limits': ('One empty existing.png placeholder; other catalog paths are absent synthetic files; '
                               'new discovered .png files are empty. Not valid-image, RAW, camera or desktop evidence.'),
            'cache': 'Warm catalog and recently created directory entries',
            'synthetic_insert_ms': round(setup_ms, 3),
        }

        set_phase('scan')
        thread = threading.Thread(target=reader, name='library-state-refresh-reader')
        thread.start()
        scan_started = time.perf_counter()
        plan = service.dispatch('prepare_folder_sync', {
            'folder_id': folder['id'], 'expected_revision': folder['folder_revision'],
            'scan_metadata': False})['plan']
        report['prepare_ms'] = round((time.perf_counter() - scan_started) * 1000, 3)
        scan_pages = []
        while plan['state'] == 'planning':
            page_started = time.perf_counter()
            result = service.dispatch('scan_folder_sync', {
                'plan_id': plan['id'], 'expected_revision': plan['revision']})
            plan = result['plan']
            if len(result['items']) > 60:
                raise AssertionError('Folder Sync scan returned more than sixty items')
            scan_pages.append((time.perf_counter() - page_started) * 1000)
        if plan['state'] != 'ready':
            raise AssertionError(plan)
        if plan['counts']['new'] != new_count or plan['counts']['missing'] != args.rows - 1:
            raise AssertionError(f"Unexpected scan counts: {plan['counts']}")
        report['scan_total_ms'] = round((time.perf_counter() - scan_started) * 1000, 3)
        report['scan_request'] = summary(scan_pages)

        original_apply = FolderSync.apply
        atomic_ms = []

        def timed_apply(self, *parameters, **keywords):
            apply_started = time.perf_counter()
            try:
                return original_apply(self, *parameters, **keywords)
            finally:
                atomic_ms.append((time.perf_counter() - apply_started) * 1000)

        set_phase('apply')
        apply_started = time.perf_counter()
        try:
            FolderSync.apply = timed_apply
            applied = service.dispatch('apply_folder_sync', {
                'plan_id': plan['id'], 'expected_revision': plan['revision'],
                'remove_missing': True, 'read_metadata': False})['plan']
        finally:
            FolderSync.apply = original_apply
        report['apply_total_ms'] = round((time.perf_counter() - apply_started) * 1000, 3)
        report['atomic_commit_ms'] = round(atomic_ms[0], 3) if atomic_ms else None
        if applied['state'] != 'applied' or applied['imported'] != new_count or applied['removed'] != args.rows - 1:
            raise AssertionError(f'Unexpected apply result: {applied}')

        set_phase('done')
        stop.set()
        thread.join()
        thread = None
        if failures:
            raise AssertionError(f'Concurrent refresh chain failed: {failures}')

        def phase_summary(phase_name, selector):
            return summary([sample[selector] for sample in samples
                            if sample['phase_started'] == phase_name])

        report['refresh_chain'] = {
            'commands': list(COMMANDS),
            'samples': len(samples),
            'omitted_chain_samples': sample_counts['omitted'],
            'sample_retention_limit': MAX_RECORDED_CHAINS,
            'whole_chain_ms': {
                phase_name: phase_summary(phase_name, 'chain_elapsed_ms')
                for phase_name in ('scan', 'apply')},
            'per_command_ms': {
                phase_name: {
                    command: summary([sample['command_elapsed_ms'][command]
                                      for sample in samples
                                      if sample['phase_started'] == phase_name and
                                      command in sample['command_elapsed_ms']])
                    for command in COMMANDS}
                for phase_name in ('scan', 'apply')},
            'command_samples_recorded_chains': {
                command: summary(command_times[command]) for command in COMMANDS},
            'sample_phase_transitions': {
                'scan_to_apply': sum(sample['phase_started'] == 'scan' and sample['phase_finished'] == 'apply'
                                     for sample in samples),
                'apply_to_done': sum(sample['phase_started'] == 'apply' and sample['phase_finished'] == 'done'
                                     for sample in samples)},
            'revision_coherence': ('Each command result is internally shape-checked. Revision vectors are '
                                   'recorded per reply; equality across separate calls is not asserted.'),
        }

        with service.catalog() as catalog:
            photo_count = catalog.db.execute('SELECT count(*) FROM photos').fetchone()[0]
            folder_count = catalog.db.execute(
                'SELECT total_count FROM catalog_folders WHERE id=?', (folder['id'],)).fetchone()[0]
            staging_count = catalog.db.execute('SELECT count(*) FROM folder_sync_files').fetchone()[0]
            maintenance = catalog.db.execute('SELECT enabled FROM folder_maintenance WHERE id=1').fetchone()[0]
        if (photo_count != new_total or folder_count != new_total or
                staging_count != 0 or maintenance != 1):
            raise AssertionError('Post-apply catalog/folder/staging invariants failed')
        report['post_apply'] = {'photo_count': photo_count, 'folder_total_count': folder_count,
                                'folder_sync_staging_rows': staging_count,
                                'folder_maintenance_enabled': bool(maintenance)}
        sample_receipt = {
            'commands': list(COMMANDS),
            'recorded_chain_count': len(samples),
            'omitted_chain_count': sample_counts['omitted'],
            'retention_limit': MAX_RECORDED_CHAINS,
            'samples': samples,
        }
        (root / 'samples.json').write_text(json.dumps(sample_receipt, indent=2) + '\n')
        report['sample_receipt'] = {'file': 'samples.json',
                                    'recorded_chain_count': len(samples),
                                    'omitted_chain_count': sample_counts['omitted'],
                                    'retention_limit': MAX_RECORDED_CHAINS}
        rss_divisor = 1024**2 if platform.system() == 'Darwin' else 1024
        report['peak_rss_mb'] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / rss_divisor, 2)
        report['worker_peak_mb'] = service.peak
        (root / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
    finally:
        set_phase('done')
        stop.set()
        if thread:
            thread.join()
        service.close()


if __name__ == '__main__':
    main()
