"""Measure indexed snapshot-status filtering in disposable synthetic catalogs.

Inputs: a new work directory and row/sample counts. Outputs: warm service latency,
page size, compact token cost and RSS. One 64x48 original plus synthetic references
have minimal recipes; setup, IPC, native UI and image workers are excluded. These
catalog measurements are not RAW processing or end-to-end interaction claims.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import resource

from PIL import Image

from library_probe import measure
from lumaraw.runtime import engine_identity
from lumaraw.service import Service


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--rows', type=int, default=100000)
    parser.add_argument('--samples', type=int, default=30)
    args = parser.parse_args()
    if not 100 <= args.rows <= 1000000 or not 1 <= args.samples <= 1000:
        raise ValueError('Counts outside probe bounds')
    root = args.work.resolve();root.mkdir()
    path = root / 'original.png';Image.new('RGB', (64, 48), 'navy').save(path)
    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    s = Service(root / 'catalog', presets_root=root / 'presets')
    try:
        s.dispatch('queue_control', {'action': 'pause'})
        s.dispatch('import_photos', {'paths': [str(path)]})
        with s.catalog() as c, c.db:
            c.db.executemany('INSERT INTO photos(path,name,bytes,mtime,recipe,created,rating) '
                "VALUES(?,?,0,0,'{}',0,?)", ((str(root / 'synthetic' / f'{i}.png'), f'{i:08d}.png', i % 6)
                                            for i in range(2, args.rows+1)))
            c.db.execute("INSERT INTO versions(photo_id,source_id,name,name_key,recipe,created,updated) "
                "SELECT id,source_id,'Seed','seed',recipe,0,0 FROM photos WHERE id%5=0")
            c.db.execute('UPDATE snapshot_identity SET next_id=(SELECT coalesce(max(id),0)+1 FROM versions)')
        smart = s.dispatch('save_collection', {'name': 'With snapshots', 'kind': 'smart', 'rules': {'has_snapshots': True}})
        cases = {
            'present_first': {'filters': {'has_snapshots': True}},
            'present_default_stacks': {'filters': {'has_snapshots': True}, 'stacked': True},
            'absent_first': {'filters': {'has_snapshots': False}},
            'present_deep': {'filters': {'has_snapshots': True}, 'offset': args.rows//10},
            'smart_present': {'collection_id': smart['id']},
            'present_rating': {'filters': {'has_snapshots': True, 'rating_min': 4}},
        }
        report = {'system': platform.platform(), 'machine': platform.machine(), 'rows': args.rows,
                  'snapshot_families': args.rows//5, 'source_dimensions': [64, 48], 'engine': engine_identity(),
                  'scope': 'Warm in-process service with SQL counts/pages; minimal synthetic recipes; setup, IPC, UI and image workers excluded'}
        for name, params in cases.items():
            def run(): return s.dispatch('list_photos', {'stacked': False, **params})
            row = run()
            report[name] = {**measure(run, args.samples), 'total': row['total'],
                            'page_rows': len(row['photos']), 'json_bytes': len(json.dumps(row).encode())}
            assert len(row['photos']) <= 60 and all('recipe' not in p for p in row['photos'])
        assert report['present_first']['total'] == args.rows//5
        assert report['absent_first']['total'] == args.rows-args.rows//5
        assert report['smart_present']['total'] == args.rows//5
        report['state_poll'] = measure(lambda: s.dispatch('library_state'), args.samples)
        report['state_bytes'] = len(json.dumps(s.dispatch('library_state')).encode())
        # Keep a sparse real result set and then an empty set; both must avoid
        # choosing an ordered full-photo scan just to find very few matches.
        sparse_count=max(1,args.rows//1000)
        with s.catalog() as c,c.db:
            c.db.execute('DELETE FROM versions WHERE photo_id>?',(sparse_count*5,))
        def present():return s.dispatch('list_photos',{'filters':{'has_snapshots':True},'stacked':False})
        assert present()['total']==sparse_count
        report['rare_present']={**measure(present,args.samples),'total':sparse_count}
        with s.catalog() as c,c.db:c.db.execute('DELETE FROM versions')
        assert present()['total']==0 and not present()['photos']
        report['empty_present']=measure(present,args.samples)
        assert s.peak == 0 and hashlib.sha256(path.read_bytes()).hexdigest() == source_hash
        report['worker_peak_mb'] = s.peak
        report['peak_rss_mib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024**2 if platform.system() == 'Darwin' else 1024)
        report['original_unchanged'] = True
        (root / 'report.json').write_text(json.dumps(report, indent=2));print(json.dumps(report, indent=2))
    finally:
        s.close()


if __name__ == '__main__':
    main()
