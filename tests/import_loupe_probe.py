"""Measure real-RAW Import Loupe Fit and 1:1 reuse through a packaged native relay.

Inputs: an explicit read-only RAW, packaged engine and new disposable work folder.
Outputs: first/exact-repeat Fit, central ROI and panned ROI latency, image identity,
actual CPU/Metal work and sampled broker/worker memory evidence. No photos are
imported or edited. Fresh application caches do not imply cold OS storage caches;
IPC measurements exclude SwiftUI, ImageIO display decoding and desktop input.
"""
import argparse
import json
from pathlib import Path
import platform
import threading
import time

import numpy as np
from PIL import Image
import psutil
import rawpy

from import_copy_probe import Relay, sha


def main():
    parser = argparse.ArgumentParser()
    for name in ('engine', 'fixture', 'work'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--legacy-fit', action='store_true',
                        help='Measure Fit on an older engine without import preview reuse')
    args = parser.parse_args()
    root = args.work.resolve()
    root.mkdir(parents=True, exist_ok=False)
    fixture = args.fixture.resolve()
    original = sha(fixture)
    with rawpy.imread(str(fixture)) as raw:
        dimensions = [raw.sizes.width, raw.sizes.height]
    runs, pixels = [], {}
    for backend in ('cpu', 'metal'):
        relay = Relay(args.engine.resolve(), root / backend, root / 'presets' / backend)
        stop = threading.Event()
        sampler = None
        peak = [0.0]
        try:
            relay.call('queue_control', {'action': 'pause'})
            relay.call('settings', {'compute_backend': backend})
            status = relay.call('service_connection', {'action': 'status'})
            broker = psutil.Process(status['pid'])
            plan = relay.call('prepare_import', {'paths': [str(fixture)]})['plan']
            while plan['state'] == 'planning':
                plan = relay.call('scan_import', {'plan_id': plan['id'],
                                  'expected_revision': plan['revision']})['plan']
            assert plan['state'] == 'ready' and plan['selected_count'] == 1
            item = relay.call('get_import', {'plan_id': plan['id']})['items'][0]

            def sample():
                while not stop.wait(.005):
                    try:
                        peak[0] = max(peak[0], broker.memory_info().rss / 1024**2)
                    except psutil.NoSuchProcess:
                        return
            sampler = threading.Thread(target=sample, daemon=True)
            sampler.start()
            generation = 0
            modes = (
                ('fit', None),
                ('center', {'cx': .5, 'cy': .5, 'width': 800, 'height': 600}),
                ('pan', {'cx': .82, 'cy': .77, 'width': 800, 'height': 600}),
            )
            for mode, viewport in modes[:1] if args.legacy_fit else modes:
                expected_pixels = None
                for repetition in range(6):
                    generation += 1
                    params = {'plan_id': plan['id'], 'item_id': item['id'],
                              'expected_revision': plan['revision'], 'detail': True,
                              'client_id': 'import-loupe-probe', 'generation': generation}
                    if viewport is not None:
                        params['viewport'] = viewport
                    peak[0] = broker.memory_info().rss / 1024**2
                    started = time.perf_counter()
                    result = relay.call('preview_import_item', params)
                    elapsed = (time.perf_counter() - started) * 1000
                    broker_peak = peak[0]
                    with Image.open(result['preview']) as image:
                        assert image.info.get('icc_profile')
                        assert image.size == (result['width'], result['height'])
                        current = np.asarray(image).copy()
                    if viewport is None:
                        assert result['detail'] is False and result['roi'] is None
                        assert max(result['width'], result['height']) <= 1600
                    else:
                        assert result['detail'] is True
                        assert [result['full_width'], result['full_height']] == dimensions
                        x, y, w, h = result['roi']
                        assert [w, h] == [800, 600]
                        assert x == max(0, min(dimensions[0] - w, round(viewport['cx'] * dimensions[0] - w / 2)))
                        assert y == max(0, min(dimensions[1] - h, round(viewport['cy'] * dimensions[1] - h / 2)))
                    if expected_pixels is None:
                        expected_pixels = current
                        pixels[backend, mode] = current
                    else:
                        np.testing.assert_array_equal(current, expected_pixels)
                    hit = result.get('preview_cache_hit', False)
                    if repetition and not args.legacy_fit:
                        assert hit and result['worker_spawned'] is False
                        assert result['processing']['backend'] == 'cache'
                        assert result['processing']['metal_grade_tiles'] == result['processing']['cpu_tiles'] == 0
                    else:
                        assert not hit
                        if backend == 'metal':
                            assert result['processing']['metal_grade_tiles'] > 0
                        else:
                            assert result['processing']['cpu_tiles'] > 0
                    runs.append({'backend': backend, 'mode': mode, 'repetition': repetition,
                                 'wall_ms': round(elapsed, 3), 'broker_peak_mib': round(broker_peak, 3),
                                 'worker_peak_mib': result['peak_mb'], 'roi': result['roi'],
                                 'width': result['width'], 'height': result['height'],
                                 'preview_cache_hit': hit, 'worker_spawned': result.get('worker_spawned', True),
                                 'processing': result['processing']})
            final = relay.call('get_import', {'plan_id': plan['id']})['plan']
            assert final['state'] == 'ready' and final['revision'] == plan['revision']
            assert relay.call('list_photos')['total'] == 0
            relay.call('cancel_import', {'plan_id': plan['id']})
        finally:
            stop.set()
            if sampler:
                sampler.join()
            relay.close()
    differences = {}
    for mode in (('fit',) if args.legacy_fit else ('fit', 'center', 'pan')):
        maximum = int(np.abs(pixels['cpu', mode].astype(np.int16) - pixels['metal', mode].astype(np.int16)).max())
        assert maximum <= 1
        differences[mode] = maximum
    assert sha(fixture) == original
    report = {'system': platform.platform(), 'memory_gib': round(psutil.virtual_memory().total / 1024**3, 1),
              'engine_sha256': sha(args.engine.resolve()), 'fixture_sha256': original,
              'legacy_fit_only': args.legacy_fit,
              'fixture_bytes': fixture.stat().st_size, 'dimensions': dimensions,
              'cache': ('Fresh catalog per backend; first Fit has cold application caches; OS caches are warm.'
                        + ('' if args.legacy_fit else ' First ROI populates a full-resolution linear base.')),
              'scope': 'Persistent relay IPC; first request plus five exact repeats per mode; no desktop input/display decoding. Broker RSS sampled every 5 ms; worker RSS is separately reported, not whole-app memory.',
              'runs': runs, 'cpu_metal_max_code_difference': differences, 'original_unchanged': True}
    (root / 'report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
