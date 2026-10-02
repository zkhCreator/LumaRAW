"""Measure packaged WB sampling on one generated raster through the native relay.

Inputs: explicit engine, fresh work directory, bounded dimensions/sample count.
Outputs: first-full-source and warm-cache wall/worker timings, sampled worker RSS,
source identity and unchanged catalog/original checks. Fit preview setup is timed
separately. No OS cache flush, RAW, desktop input or Lightroom comparison occurs.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import select
import statistics
import subprocess
import time

import numpy as np
from PIL import Image


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--engine', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--width', type=int, default=4000)
    parser.add_argument('--height', type=int, default=3000)
    parser.add_argument('--samples', type=int, default=5)
    args = parser.parse_args()
    if not (64 <= args.width <= 6000 and 64 <= args.height <= 6000 and
            args.width*args.height <= 24_000_000 and 2 <= args.samples <= 10):
        parser.error('Use 64..6000 dimensions, at most 24 megapixels and 2..10 samples')
    root = args.work.resolve()
    root.mkdir(parents=True, exist_ok=False)
    fixture = root / 'generated-gradient.png'
    pixels = np.empty((args.height,args.width,3), np.uint8)
    pixels[:,:,0] = np.linspace(120,170,args.width,dtype=np.uint8)[None,:]
    pixels[:,:,1] = np.linspace(110,145,args.height,dtype=np.uint8)[:,None]
    pixels[:,:,2] = 115
    Image.fromarray(pixels).save(fixture)
    del pixels
    digest = hashlib.sha256(fixture.read_bytes()).hexdigest()
    relay = subprocess.Popen([
        str(args.engine.resolve()), '--catalog', str(root/'catalog'), '--native-client',
    ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        env={**os.environ, 'LUMARAW_PRESETS_ROOT':str(root/'presets')})
    counter = 0

    def call(method, params=None):
        nonlocal counter
        counter += 1
        started = time.perf_counter()
        relay.stdin.write(json.dumps({'id':counter,'method':method,'params':params or {}}).encode()+b'\n')
        relay.stdin.flush()
        if not select.select([relay.stdout], [], [], 120)[0]:
            raise TimeoutError('Native relay did not reply')
        envelope = json.loads(relay.stdout.readline(1024*1024+1))
        assert envelope.get('ok') and envelope['id'] == counter, envelope
        return envelope['result'], round((time.perf_counter()-started)*1000,3)

    try:
        call('queue_control', {'action':'pause'})
        call('settings', {'compute_backend':'cpu','budget_mb':4096})
        connection, _ = call('service_connection', {'action':'status'})
        call('import_photos', {'paths':[str(fixture)]})
        photo, _ = call('get_photo', {'photo_id':1})
        preview, preview_ms = call('preview_photo', {
            'photo_id':1, 'expected_revision':photo['revision'], 'include_before':False,
        })
        baseline, _ = call('get_photo', {'photo_id':1})
        samples = []
        candidate = None
        for index in range(args.samples):
            result, elapsed = call('sample_white_balance', {
                'photo_id':1, 'expected_revision':photo['revision'],
                'expected_source_fingerprint':preview['source_fingerprint'],
                'client_id':'wb-performance', 'generation':index+1,
                'point':{'x':.5,'y':.5},
            })
            assert result['solver'] == 'raster_linear' and result['sampled_pixels'] == 25
            values = [result['temperature'],result['tint']]
            if candidate is None:
                candidate = values
            np.testing.assert_allclose(values, candidate, atol=1e-8)
            decoded = 'source_decode' in result['processing']['stages']
            assert decoded == (index == 0)
            samples.append({'kind':'first-full-source' if index == 0 else 'warm-linear-cache',
                            'wall_ms':elapsed, 'worker_peak_mib':result['peak_mb'],
                            'source_decode':decoded, 'processing':result['processing']})
        after, _ = call('get_photo', {'photo_id':1})
        assert after == baseline
        assert hashlib.sha256(fixture.read_bytes()).hexdigest() == digest
        report = {
            'scope':'Generated raster, packaged native relay and disposable image workers; no edit',
            'platform':platform.platform(), 'engine':connection['engine'],
            'dimensions':[args.width,args.height], 'fixture_sha256':digest,
            'cache':'New catalog; Fit proxy primed separately; no OS page-cache flush',
            'preview_setup_ms':preview_ms, 'samples':samples,
            'warm_median_ms':statistics.median(row['wall_ms'] for row in samples[1:]),
            'peak_worker_mib':max(row['worker_peak_mib'] for row in samples),
            'candidate':candidate, 'original_and_catalog_unchanged':True,
        }
        (root/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({key:value for key,value in report.items() if key!='samples'},indent=2))
    finally:
        relay.stdin.close()
        try:
            relay.wait(timeout=10)
        except subprocess.TimeoutExpired:
            relay.kill()
            relay.wait()


if __name__ == '__main__':
    main()
