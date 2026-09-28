"""Compile and run native state probes with generated images and new catalogs.

Input: an explicit new work directory and optional engine. Output: Swift binaries,
synthetic photographs and JSON receipts inside that directory. No personal library
or desktop automation. Source engine uses this environment's installed CLI entry.
"""
import argparse
import json
from multiprocessing.connection import Client
import os
from pathlib import Path
import subprocess
import sys
import time

from PIL import Image
from lumaraw.bridge import endpoint


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--engine',type=Path,default=Path(sys.executable).with_name('lumaraw'))
    suites=('NativeStateRegression','NativeLibraryRegression','NativeSelectionRegression','NativeReviewRegression','NativeThumbnailRegression','NativeCollectionRegression','NativeVirtualCopyRegression','NativeConnectionRegression','NativeStackRegression','NativeAutoStackRegression','NativeFolderRegression')
    parser.add_argument('--suite',choices=suites,action='append',help='Run selected suites; default: all')
    args=parser.parse_args()
    work=args.work.resolve()
    if work.exists():
        raise SystemExit('Choose a new work directory')
    work.mkdir(parents=True)
    root=Path(__file__).resolve().parents[1]
    sources=sorted(path for path in (root/'native').glob('*.swift') if path.name != 'LumaRAWApp.swift')
    for suite in args.suite or suites:
        # Relink/eviction suites deliberately move their own originals. Every
        # suite needs fresh files as well as its own catalog, independent of order.
        fixtures=work/'fixtures'/suite
        fixtures.mkdir(parents=True)
        paths=[]
        for index,color in enumerate(('navy','orange','green','purple','teal')):
            path=fixtures/f'photo-{index}.png'
            if suite=='NativeFolderRegression':
                path=fixtures / ('Parent/direct.png','Parent/child/a.png','Parent/child/b.png','Elsewhere/c.png','Elsewhere/d.png')[index]
                path.parent.mkdir(parents=True,exist_ok=True)
            if suite=='NativeAutoStackRegression':
                path=path.with_suffix('.jpg');exif=Image.Exif()
                second,fraction=((0,'9'),(1,'1'),(2,'0'),(2,'3'),(4,'0'))[index]
                exif[34665]={36867:f'2026:09:26 12:00:{second:02d}',37521:fraction,36881:'+00:00'}
                Image.new('RGB',(160,100),color).save(path,exif=exif)
            else:Image.new('RGB',(160,100),color).save(path)
            paths.append(str(path))
        executable=work/suite
        subprocess.run(['xcrun','swiftc','-swift-version','5','-parse-as-library',
            '-target','arm64-apple-macosx14.0','-module-cache-path',str(work/'module-cache'),
            *map(str,sources),str(root/'tests'/f'{suite}.swift'),'-o',str(executable)],check=True)
        suite_paths=paths if suite in ('NativeSelectionRegression','NativeReviewRegression','NativeThumbnailRegression','NativeCollectionRegression','NativeVirtualCopyRegression','NativeStackRegression','NativeAutoStackRegression','NativeFolderRegression') else paths[:2]
        env={**os.environ,'LUMARAW_ENGINE':str(args.engine.resolve()),
            'LUMARAW_CATALOG':str(work/'catalogs'/suite),'LUMARAW_TEST_FIXTURES':'|'.join(suite_paths)}
        fixture=None
        try:
            if suite=='NativeConnectionRegression':
                catalog=Path(env['LUMARAW_CATALOG'])
                fixture=subprocess.Popen([sys.executable,str(root/'tests'/'broker_fixture.py'),'--catalog',str(catalog),
                    *[arg for path in suite_paths for arg in ('--photo',path)]],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
                address,family=endpoint(catalog);deadline=time.monotonic()+8
                while True:
                    if fixture.poll() is not None:raise RuntimeError(fixture.stderr.read().decode())
                    try:
                        with Client(address,family=family) as conn:
                            conn.send_bytes(json.dumps({'method':'__broker_info__'}).encode())
                            if conn.poll(1) and json.loads(conn.recv_bytes()).get('ok'):break
                    except (OSError,EOFError):pass
                    if time.monotonic()>deadline:raise RuntimeError('Connection fixture did not become ready')
                    time.sleep(.03)
            result=subprocess.run([str(executable)],env=env,capture_output=True,text=True,timeout=120)
        finally:
            if fixture is not None:
                if fixture.poll() is None:fixture.terminate()
                fixture.wait(timeout=5);fixture.stderr.close()
        (work/f'{suite}.json').write_text(result.stdout)
        print(result.stdout)
        if result.returncode:
            print(result.stderr,file=sys.stderr)
            raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
