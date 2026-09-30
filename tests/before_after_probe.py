"""Measure persistent-Before preview reuse through isolated packaged workers.

Inputs: one explicit read-only RAW fixture and a new private work directory.
Outputs: CPU/Metal pixels, wall/stage timings, sampled RSS and cache receipts.
Workers run sequentially without setup/build contention. Empty application caches
do not establish cold OS/GPU caches or native slider latency; no Adobe claim.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time

import numpy as np
from PIL import Image
import psutil


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--engine', required=True, type=Path)
    parser.add_argument('--fixture', required=True, type=Path)
    parser.add_argument('--work', required=True, type=Path)
    args = parser.parse_args()
    args.engine = args.engine.resolve()
    args.fixture = args.fixture.resolve()
    args.work.mkdir(parents=True, exist_ok=False)
    args.work = args.work.resolve()
    original = digest(args.fixture)
    after = {'exposure': .35, 'highlights': -25, 'shadows': 20, 'contrast': 12,
             'blue_hue': -9, 'blue_sat': 12,
             'curve_rgb_points': [[0, .03], [.25, .18], [.75, .83], [1, .98]]}
    before = {'exposure': -.2, 'vibrance': -12, 'shadows': 10}
    runs = []

    def run(mode, label, recipe, expected_hit, *, detail=False, include_before=True):
        destination = args.work / f'{label}-{mode}'
        destination.mkdir()
        cache = args.work / f'cache-{mode}'
        request = {'operation': 'detail' if detail else 'preview',
                   'path': str(args.fixture), 'recipe': recipe,
                   'before_recipe': before, 'include_before': include_before,
                   'cache': str(cache), 'compute_backend': mode,
                   'budget_mb': min(4096, int(psutil.virtual_memory().available / 1024**2 * .7))}
        if detail:
            request['detail'] = {'width': 1280, 'height': 900}
        start = time.perf_counter()
        process = subprocess.Popen([str(args.engine), '--worker'], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, 'OMP_NUM_THREADS': '2', 'OPENBLAS_NUM_THREADS': '1',
                 'VECLIB_MAXIMUM_THREADS': '2'})
        peak = [0.]
        done = threading.Event()

        def sample():
            while not done.wait(.02):
                try:
                    peak[0] = max(peak[0], psutil.Process(process.pid).memory_info().rss / 1024**2)
                except psutil.NoSuchProcess:
                    break

        sampler = threading.Thread(target=sample)
        sampler.start()
        try:
            stdout, stderr = process.communicate(json.dumps(request).encode() + b'\n', timeout=300)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise
        finally:
            done.set()
            sampler.join()
        elapsed = time.perf_counter() - start
        result = json.loads(stdout)
        assert process.returncode == 0 and result['ok'], (result, stderr.decode())
        if mode == 'metal':
            assert result['processing']['metal_grade_tiles'] > 0, result
        if include_before:
            assert result['before_cache_hit'] == expected_hit, result
            assert ('before_render' in result['processing']['stages']) != expected_hit, result
        else:
            assert 'before' not in result and 'before_render' not in result['processing']['stages'], result
        saved = {}
        for side in ('preview', 'before'):
            if side in result:
                target = destination / f'{side}.png'
                shutil.copy2(result[side], target)
                saved[side] = str(target)
        item = {'label': label, 'backend': mode, 'wall_seconds': round(elapsed, 6),
                'rss_peak_mib': round(peak[0], 2), 'width': result['width'],
                'height': result['height'], 'before_cache_hit': result.get('before_cache_hit'),
                'processing': result['processing'], **saved}
        runs.append(item)
        return item

    cases = [('cold-fit', after, False, {}), ('warm-fit-1', after, True, {}),
             ('warm-fit-2', after, True, {}),
             ('after-light-change', {**after, 'exposure': .65}, True, {}),
             ('after-geometry-change', {**after, 'straighten': 2}, False, {}),
             ('cold-detail', after, False, {'detail': True}),
             ('warm-detail', after, True, {'detail': True}),
             ('after-only', after, None, {'include_before': False})]
    parity = []
    for index, (label, recipe, hit, options) in enumerate(cases):
        modes = ('cpu', 'metal') if index % 2 == 0 else ('metal', 'cpu')
        pair = {mode: run(mode, label, recipe, hit, **options) for mode in modes}
        for side in ('preview', 'before'):
            if side not in pair['cpu']:
                continue
            with Image.open(pair['cpu'][side]) as image:
                cpu = np.array(image, dtype=np.int16)
            with Image.open(pair['metal'][side]) as image:
                metal = np.array(image, dtype=np.int16)
            assert cpu.shape == metal.shape
            delta = np.abs(cpu - metal)
            measurement = {'label': label, 'side': side, 'shape': list(cpu.shape),
                           'max_code_difference': int(delta.max()),
                           'mean_code_difference': float(delta.mean()), 'limit': 1}
            assert delta.max() <= 1, measurement
            parity.append(measurement)
        print(json.dumps({mode: {key: value for key, value in item.items()
              if key in ('label', 'wall_seconds', 'rss_peak_mib', 'before_cache_hit')}
              for mode, item in pair.items()}), flush=True)
    for mode in ('cpu', 'metal'):
        def get(label):
            return next(item for item in runs if item['label'] == label and item['backend'] == mode)
        assert digest(get('cold-fit')['preview']) == digest(get('after-only')['preview'])
        assert digest(get('cold-fit')['before']) == digest(get('after-light-change')['before'])
    assert digest(args.fixture) == original
    report = {'engine_sha256': digest(args.engine), 'source_sha256': original,
              'source_bytes': args.fixture.stat().st_size, 'original_unchanged': True,
              'after_recipe': after, 'before_recipe': before, 'runs': runs, 'parity': parity,
              'scope': 'Sequential packaged worker wall times including launch, decode/cache, grading and PNG. '
                       'One RAW fixture; not cold OS/GPU, native interaction or Adobe equivalence.'}
    (args.work / 'report.json').write_text(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
