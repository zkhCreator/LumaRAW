"""Alternate current and legacy Folder Sync INSERTs on disposable catalogs.

Inputs: a new work directory, bounded synthetic row counts and pair count.
Outputs: exact trigger-write counts and first/warm SQL/apply timings using the
shared mutation probe. Only the profiled INSERT can substitute generation 55's
SQL; production source is never patched. Each sample starts from a fresh backup.
Original paths are absent. No filesystem scan, IPC, pixels or UI is measured.
OS caches are not flushed; process RSS includes setup and all preceding samples.
"""
import argparse
import json
from pathlib import Path
import platform
import resource
import statistics

import folder_sync_mutation_probe as probe


BASE_FACADE = probe.DatabaseFacade
INSERT_COLUMNS = 'INSERT INTO photos(path,name,original_name,bytes,mtime,recipe,created,import_number,image_number) '
INSERT_VALUES = 'SELECT path,folder_name(path),folder_name(path),bytes,mtime,'


class InsertVariantFacade(BASE_FACADE):
    def __init__(self, connection, profile, variant):
        super().__init__(connection, profile)
        self._variant = variant
        self._insert_calls = 0
        self._insert_changes = 0

    def execute(self, sql, parameters=()):
        if not self._profile.enabled or probe._sql_category(sql) != 'insert_new_photos':
            return super().execute(sql, parameters)
        if not sql.startswith(INSERT_COLUMNS + INSERT_VALUES):
            raise ValueError('Folder Sync INSERT changed; review this comparison before measuring')
        if self._variant == 'legacy':
            sql = sql.replace(INSERT_COLUMNS, INSERT_COLUMNS.replace('original_name,', ''), 1)
            sql = sql.replace(INSERT_VALUES, INSERT_VALUES.replace('folder_name(path),', '', 1), 1)
        before = self._connection.total_changes
        result = super().execute(sql, parameters)
        self._insert_calls += 1
        self._insert_changes += self._connection.total_changes - before
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--rows', type=int, default=100000)
    parser.add_argument('--new-rows', type=int, default=10000)
    parser.add_argument('--pairs', type=int, default=5)
    args = parser.parse_args()
    if not 1000 <= args.rows <= 100000 or not 1 <= args.new_rows <= 100000 or not 2 <= args.pairs <= 8:
        parser.error('Use 1000..100000 existing rows, 1..100000 new rows and 2..8 pairs')
    root = args.work.resolve()
    root.mkdir(parents=True, exist_ok=False)
    templates = root / 'templates'
    empty = templates / 'empty'
    empty_photos = root / 'absent-originals' / 'empty' / 'Photos'
    empty_id = probe.seed_empty_catalog(empty, empty_photos)
    populated, photos, folder_id, _ = probe.seed_catalog(
        templates / 'populated', root / 'absent-originals', args.rows)
    report = {'scope': 'Same-process alternating SQL variants, synthetic FolderSync.apply only',
              'engine': probe.engine_identity(), 'platform': platform.platform(),
              'cache': 'Fresh SQLite backup and connection per sample; no OS cache flush',
              'rows': args.rows, 'new_rows': args.new_rows, 'pairs': args.pairs, 'cases': []}
    for name, template, folder, directory, existing in (
        ('new_only', empty, empty_id, empty_photos, 0),
        ('unchanged_plus_new', Path(populated), folder_id, photos, args.rows),
    ):
        samples = []
        for pair in range(args.pairs):
            order = ('legacy', 'current') if pair % 2 == 0 else ('current', 'legacy')
            pair_changes = {}
            for variant in order:
                captured = []

                def facade(connection, profile):
                    value = InsertVariantFacade(connection, profile, variant)
                    captured.append(value)
                    return value

                probe.DatabaseFacade = facade
                try:
                    result = probe.run_trial(template, root / f'{name}-{pair}-{variant}',
                                             folder, directory, existing, existing, 0,
                                             args.new_rows, False)
                finally:
                    probe.DatabaseFacade = BASE_FACADE
                assert len(captured) == 1 and captured[0]._insert_calls == 1
                changes = captured[0]._insert_changes
                pair_changes[variant] = changes
                result.update(variant=variant, pair=pair, sample_kind='first' if pair == 0 else 'warm',
                              insert_total_changes=changes)
                samples.append(result)
            assert pair_changes['legacy'] - pair_changes['current'] == args.new_rows
        summary = {}
        for variant in ('legacy', 'current'):
            values = [sample for sample in samples if sample['variant'] == variant and sample['pair'] > 0]
            summary[variant] = {
                'warm_apply_median_ms': statistics.median(sample['apply_wall_ms'] for sample in values),
                'warm_insert_median_ms': statistics.median(
                    sample['sql_profile']['categories']['insert_new_photos']['execute_ms'] for sample in values),
            }
        report['cases'].append({'name': name, 'samples': samples, 'summary': summary,
                                'one_fewer_write_per_new_photo': True})
    report['process_peak_rss_mb'] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024**2, 2)
    (root / 'report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'cases': [{key: value for key, value in case.items() if key != 'samples'}
                               for case in report['cases']],
                      'process_peak_rss_mb': report['process_peak_rss_mb']}, indent=2))


if __name__ == '__main__':
    main()
