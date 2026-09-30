"""Measure bounded shared snapshot operations without pixel or desktop work.

Input: a new private directory, synthetic snapshot count and sample count. Output:
warm service medians/p95, summary bytes, peak process RSS and source invariants.
Setup is excluded; SQLite opens, validation and commits are included. Results do
not represent cold disk, broker, UI, RAW rendering or Adobe processing latency.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import resource

from PIL import Image

from library_probe import measure
from lumaraw.model import Recipe
from lumaraw.service import Service
from lumaraw.runtime import engine_identity


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--rows', type=int, default=100000)
    parser.add_argument('--samples', type=int, default=30)
    args = parser.parse_args()
    if not 100 <= args.rows <= 1000000 or not 1 <= args.samples <= 1000:
        raise ValueError('Counts outside probe bounds')
    root = args.work.resolve(); root.mkdir()
    path = root / 'original.png'; Image.new('RGB', (64, 48), 'navy').save(path)
    original = hashlib.sha256(path.read_bytes()).hexdigest()
    s = Service(root / 'catalog', presets_root=root / 'presets')
    try:
        s.dispatch('queue_control', {'action': 'pause'})
        s.dispatch('import_photos', {'paths': [str(path)]})
        recipe = json.dumps(Recipe(exposure=1).dict())
        with s.catalog() as c, c.db:
            c.db.executemany('INSERT INTO versions(id,photo_id,source_id,name,name_key,recipe,created,updated) '
                'VALUES(?,1,1,?,?,?,?,?)', ((i, f'Snapshot {i:08d}', f'snapshot {i:08d}', recipe, float(i), float(i))
                                         for i in range(1, args.rows+1)))
            c.db.execute('UPDATE snapshot_identity SET next_id=?', (args.rows+1,))
            c.db.execute('UPDATE photo_sources SET snapshots_revision=? WHERE id=1', (args.rows,))
        def page(**extra): return s.dispatch('list_versions', {'photo_id': 1, **extra})
        report = {'system': platform.platform(), 'machine': platform.machine(), 'rows': args.rows,
                  'source_dimensions': [64, 48], 'engine': engine_identity(),
                  'scope': 'Warm in-process service; SQLite connection/validation/commits included; setup, broker, pixels and UI excluded'}
        report['first_page'] = measure(page, args.samples)
        report['deep_page'] = measure(lambda: page(after_id=args.rows//2, expected_snapshots_revision=args.rows), args.samples)
        report['conditional_unchanged'] = measure(lambda: page(known_revision=args.rows), args.samples)
        report['page_bytes'] = len(json.dumps(page()).encode())
        report['unchanged_bytes'] = len(json.dumps(page(known_revision=args.rows)).encode())
        revision = 0
        def rename():
            nonlocal revision
            result = s.dispatch('rename_version', {'photo_id': 1, 'version_id': 1,
                'expected_version_revision': revision, 'name': f'Renamed {revision % 2}'})
            revision = result['version']['revision']
        report['rename'] = measure(rename, args.samples)
        # Alternating two existing settings makes every update a material write.
        # Choosing the source recipe is fixture setup, excluded from each timing.
        update_times = []
        for i in range(args.samples):
            with s.catalog() as c, c.db:
                c.db.execute('UPDATE photos SET recipe=? WHERE id=1', (json.dumps(Recipe(exposure=i % 2 + 2).dict()),))
            def update():
                nonlocal revision
                result = s.dispatch('update_version', {'photo_id': 1, 'version_id': 1,
                    'expected_version_revision': revision, 'expected_revision': 0})
                revision = result['version']['revision']
            update_times.append(measure(update, 1)['median_ms'])
        import statistics
        report['update'] = {'samples': args.samples, 'median_ms': round(statistics.median(update_times), 3),
                            'p95_ms': sorted(update_times)[min(len(update_times)-1, int(len(update_times)*.95))]}
        sequence = 0
        def create_delete():
            nonlocal sequence
            sequence += 1
            row = s.dispatch('save_version', {'photo_id': 1, 'name': f'New {sequence}', 'expected_revision': 0})['version']
            s.dispatch('delete_version', {'photo_id': 1, 'version_id': row['id'], 'expected_version_revision': row['revision']})
        report['create_delete_pair'] = measure(create_delete, args.samples)
        assert len(page()['versions']) == 60 and s.peak == 0
        assert hashlib.sha256(path.read_bytes()).hexdigest() == original
        report['worker_peak_mb'] = s.peak
        report['peak_rss_mib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024**2 if platform.system() == 'Darwin' else 1024)
        report['original_unchanged'] = True
        (root / 'report.json').write_text(json.dumps(report, indent=2)); print(json.dumps(report, indent=2))
    finally:
        s.close()


if __name__ == '__main__':
    main()
