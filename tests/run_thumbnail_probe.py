"""Measure native warm thumbnail publications through real catalog workflows.

Inputs: a new work directory, a fixed packaged engine and a Swift probe source.
Outputs: one executable, fresh generated fixture/catalog pairs and JSON reports
for five and sixty visible thumbnails. No desktop automation or source mutation.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
from PIL import Image


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', required=True, type=Path)
    parser.add_argument('--engine', required=True, type=Path)
    parser.add_argument('--probe', type=Path, default=Path(__file__).with_name('NativeThumbnailRefreshProbe.swift'))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    sources = sorted(path for path in (root / 'native').glob('*.swift') if path.name != 'LumaRAWApp.swift')
    executable = work / 'NativeThumbnailRefreshProbe'
    subprocess.run(['xcrun', 'swiftc', '-swift-version', '5', '-parse-as-library',
                    '-target', 'arm64-apple-macosx14.0', '-module-cache-path', str(work / 'module-cache'),
                    *map(str, sources), str(args.probe.resolve()), '-o', str(executable)], check=True)
    reports = []
    for count in (5, 60):
        case = work / f'photos-{count}'
        fixtures = case / 'fixtures'
        fixtures.mkdir(parents=True)
        paths = []
        for index in range(count):
            path = fixtures / f'photo-{index:03}.png'
            Image.new('RGB', (160, 100), (index * 31 % 256, index * 73 % 256, index * 17 % 256)).save(path)
            paths.append(str(path))
        env = {**os.environ, 'LUMARAW_ENGINE': str(args.engine.resolve()),
               'LUMARAW_CATALOG': str(case / 'catalog'),
               'LUMARAW_PRESETS_ROOT': str(case / 'presets'),
               'LUMARAW_TEST_FIXTURES': '|'.join(paths), 'LUMARAW_PROBE_DISPOSABLE_CATALOG': '1'}
        result = subprocess.run([str(executable)], env=env, capture_output=True, text=True, timeout=180)
        (case / 'report.json').write_text(result.stdout)
        (case / 'stderr.txt').write_text(result.stderr)
        if result.returncode:
            print(result.stdout, result.stderr)
            raise SystemExit(result.returncode)
        report = json.loads(result.stdout)
        assert report['ok'] and report['visible_photo_count'] == count
        for measurement in report['measurements']:
            assert measurement['all_renderer_calls_succeeded']
            assert measurement['same_visible_page'] and measurement['same_nsimage_objects']
            assert not measurement['renderer_errors']
            assert measurement['thumbnail_ipc_counts'] == {'cached_thumbnails': 1, 'cancel_preview': 1, 'thumbnail': 0}
            assert measurement['cached_worker_spawned'] == [False]
        reports.append(report)
        print(json.dumps({'visible': count, 'measurements': report['measurements']}), flush=True)
    (work / 'report.json').write_text(json.dumps(reports, indent=2) + '\n')


if __name__ == '__main__':
    main()
