"""Compile and run native state probes with generated images and new catalogs.

Input: an explicit new work directory and optional engine. Output: Swift binaries,
synthetic photographs and JSON receipts inside that directory. No personal library
or desktop automation. Source engine uses this environment's installed CLI entry.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys

from PIL import Image


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--engine',type=Path,default=Path(sys.executable).with_name('lumaraw'))
    suites=('NativeStateRegression','NativeLibraryRegression','NativeSelectionRegression','NativeReviewRegression','NativeThumbnailRegression','NativeCollectionRegression','NativeVirtualCopyRegression')
    parser.add_argument('--suite',choices=suites,action='append',help='Run selected suites; default: all')
    args=parser.parse_args()
    work=args.work.resolve()
    if work.exists():
        raise SystemExit('Choose a new work directory')
    work.mkdir(parents=True)
    root=Path(__file__).resolve().parents[1]
    sources=sorted(path for path in (root/'native').glob('*.swift') if path.name != 'LumaRAWApp.swift')
    paths=[]
    for index,color in enumerate(('navy','orange','green','purple','teal')):
        path=work/f'photo-{index}.png'
        Image.new('RGB',(160,100),color).save(path)
        paths.append(str(path))
    for suite in args.suite or suites:
        executable=work/suite
        subprocess.run(['xcrun','swiftc','-swift-version','5','-parse-as-library',
            '-target','arm64-apple-macosx14.0','-module-cache-path',str(work/'module-cache'),
            *map(str,sources),str(root/'tests'/f'{suite}.swift'),'-o',str(executable)],check=True)
        suite_paths=paths if suite in ('NativeSelectionRegression','NativeReviewRegression','NativeThumbnailRegression','NativeCollectionRegression','NativeVirtualCopyRegression') else paths[:2]
        env={**os.environ,'LUMARAW_ENGINE':str(args.engine.resolve()),
            'LUMARAW_CATALOG':str(work/'catalogs'/suite),'LUMARAW_TEST_FIXTURES':'|'.join(suite_paths)}
        result=subprocess.run([str(executable)],env=env,capture_output=True,text=True,timeout=120)
        (work/f'{suite}.json').write_text(result.stdout)
        print(result.stdout)
        if result.returncode:
            print(result.stderr,file=sys.stderr)
            raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
