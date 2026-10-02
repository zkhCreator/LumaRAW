"""Paired raster decode benchmark through explicit packaged app engines.

Purpose: run the existing packaged white_balance_probe against old/new engine
binaries in five alternating pairs. Inputs are two explicit engine paths and a
fresh work directory. Outputs preserve each probe receipt plus paired timing,
worker-peak-memory, fixture-hash and white-balance-candidate comparisons.
It runs the two explicit engines through the existing packaged native relay, but
does not build, install or modify either engine; no desktop or RAW claim. The
probe measures a generated 12 MP PNG through the packaged native relay.
Pixel-array equivalence is asserted separately by test_raster_decode.py against
the former full-frame conversion expression; this benchmark itself does not
capture a full rendered raster from the service.
"""
import argparse
import json
from pathlib import Path
import statistics
import subprocess
import sys


def run_trial(probe, engine, work, width, height):
    command = [
        sys.executable, str(probe),
        '--engine', str(engine),
        '--work', str(work),
        '--width', str(width),
        '--height', str(height),
        '--samples', '5',
    ]
    completed = subprocess.run(command, check=True, capture_output=True, text=True, timeout=300)
    receipt = json.loads((work / 'report.json').read_text())
    return receipt, completed.stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--old-engine', type=Path, required=True)
    parser.add_argument('--new-engine', type=Path, required=True)
    parser.add_argument('--probe', type=Path, default=Path(__file__).with_name('white_balance_probe.py'))
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--pairs', type=int, default=5)
    parser.add_argument('--width', type=int, default=4000)
    parser.add_argument('--height', type=int, default=3000)
    args = parser.parse_args()

    old_engine = args.old_engine.resolve(strict=True)
    new_engine = args.new_engine.resolve(strict=True)
    probe = args.probe.resolve(strict=True)
    root = args.work.resolve()
    if root.exists():
        parser.error('--work must name a new, nonexistent directory')
    if args.pairs != 5:
        parser.error('This receipt format is fixed to five alternating pairs')
    if args.width * args.height != 12_000_000:
        parser.error('Use a 12,000,000-pixel PNG to match the measured 12 MP case')
    if old_engine == new_engine:
        parser.error('--old-engine and --new-engine must be distinct explicit builds')
    root.mkdir(parents=True, exist_ok=False)

    builds = {'old': old_engine, 'new': new_engine}
    runs = []
    for pair_index in range(args.pairs):
        order = ('old', 'new') if pair_index % 2 == 0 else ('new', 'old')
        for pair_position, label in enumerate(order):
            trial_dir = root / f'pair-{pair_index + 1:02d}-{label}'
            receipt, stdout = run_trial(
                probe, builds[label], trial_dir, args.width, args.height
            )
            samples = receipt['samples']
            cold = next(row for row in samples if row['kind'] == 'first-full-source')
            warm = [row['wall_ms'] for row in samples if row['kind'] == 'warm-linear-cache']
            runs.append({
                'pair': pair_index + 1,
                'pair_position': pair_position + 1,
                'build': label,
                'engine': receipt['engine'],
                'fixture_sha256': receipt['fixture_sha256'],
                'dimensions': receipt['dimensions'],
                'cold_wall_ms': cold['wall_ms'],
                'cold_worker_peak_mib': cold['worker_peak_mib'],
                'warm_median_wall_ms': statistics.median(warm),
                'peak_worker_mib': receipt['peak_worker_mib'],
                'candidate': receipt['candidate'],
                'source_and_catalog_unchanged': receipt['original_and_catalog_unchanged'],
                'receipt': str(trial_dir / 'report.json'),
                'stdout': stdout.strip(),
            })

    pair_checks = []
    identities = {}
    for label in builds:
        entries = [row['engine'] for row in runs if row['build'] == label]
        if any(entry != entries[0] for entry in entries):
            raise AssertionError(f'Engine identity changed during {label} trials')
        identities[label] = entries[0]
    if identities['old'] == identities['new']:
        raise AssertionError('The two builds report the same engine identity')
    for pair in range(1, args.pairs + 1):
        rows = [row for row in runs if row['pair'] == pair]
        old = next(row for row in rows if row['build'] == 'old')
        new = next(row for row in rows if row['build'] == 'new')
        max_candidate_delta = max(
            abs(float(old['candidate'][index]) - float(new['candidate'][index]))
            for index in (0, 1)
        )
        if old['fixture_sha256'] != new['fixture_sha256']:
            raise AssertionError(f'Generated fixture differs in pair {pair}')
        if old['dimensions'] != new['dimensions'] or old['dimensions'] != [args.width, args.height]:
            raise AssertionError(f'Fixture dimensions differ in pair {pair}')
        if not old['source_and_catalog_unchanged'] or not new['source_and_catalog_unchanged']:
            raise AssertionError(f'Probe source/catalog guard failed in pair {pair}')
        if max_candidate_delta > 1e-8:
            raise AssertionError(f'White-balance candidate differs in pair {pair}: {max_candidate_delta}')
        pair_checks.append({
            'pair': pair,
            'candidate_max_abs_delta': max_candidate_delta,
            'fixture_sha256': old['fixture_sha256'],
            'candidate_matches': True,
        })

    summary = {
        'scope': '10 subprocess probe runs; 12 MP generated RGB PNG; packaged native relay and worker',
        'order': 'old/new, new/old alternating across five paired trials',
        'pair_count': args.pairs,
        'width': args.width,
        'height': args.height,
        'runs': runs,
        'pairs': pair_checks,
        'old_cold_wall_median_ms': statistics.median(row['cold_wall_ms'] for row in runs if row['build'] == 'old'),
        'new_cold_wall_median_ms': statistics.median(row['cold_wall_ms'] for row in runs if row['build'] == 'new'),
        'old_cold_peak_worker_median_mib': statistics.median(row['cold_worker_peak_mib'] for row in runs if row['build'] == 'old'),
        'new_cold_peak_worker_median_mib': statistics.median(row['cold_worker_peak_mib'] for row in runs if row['build'] == 'new'),
        'pixel_equivalence_evidence': 'Separate test_raster_decode.py compares decoded float32 arrays bit-for-bit with the former full-frame conversion; service probe reports matching WB candidates but does not return full output pixels.',
        'limitations': [
            'Generated PNG only; no RAW, camera-color or Lightroom equivalence.',
            'Fresh catalog and preset root per subprocess; OS page cache is not flushed.',
            'Worker RSS is sampled by the existing probe, not a process-tree peak guarantee.',
            'No desktop interaction or installed-app launch is exercised.',
        ],
    }
    (root / 'comparison.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({key: value for key, value in summary.items() if key != 'runs'}, indent=2))


if __name__ == '__main__':
    main()
