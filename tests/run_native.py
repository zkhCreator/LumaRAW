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
    suites=('NativeStateRegression','NativeLibraryRegression','NativeSelectionRegression','NativeReviewRegression','NativeThumbnailRegression','NativeCollectionRegression','NativeVirtualCopyRegression','NativeConnectionRegression','NativeStackRegression','NativeAutoStackRegression','NativeFolderRegression','NativeKeywordRegression','NativeFolderRelocationRegression','NativeFolderSyncRegression','NativeExportMetadataRegression','NativeKeywordDetailsRegression','NativeKeywordVocabularyRegression','NativeKeywordExchangeRegression','NativeKeywordSetRegression','NativePainterRegression')
    suites+=('NativePainterKeywordPickerRegression',)
    suites+=('NativeTargetPainterRegression',)
    suites+=('NativeOrientationRegression',)
    suites+=('NativeDevelopPresetRegression',)
    suites+=('NativeMetadataPresetRegression',)
    suites+=('NativeImportRegression',)
    suites+=('NativeImportProcessingRegression',)
    suites+=('NativeImportNamingRegression',)
    suites+=('NativeImportBackupRegression',)
    suites+=('NativeImportPresetRegression',)
    suites+=('NativeImportSequenceRegression',)
    suites+=('NativePreviousImportRegression',)
    suites+=('NativeColorMixerRegression',)
    suites+=('NativePointCurveRegression',)
    suites+=('NativeParametricCurveRegression',)
    suites+=('NativeCurveTargetRegression',)
    suites+=('NativeMixerTargetRegression',)
    suites+=('NativeHistoryRegression',)
    suites+=('NativeBeforeAfterRegression',)
    suites+=('NativeComparisonLayoutRegression',)
    suites+=('NativeSnapshotsRegression',)
    suites+=('NativeSnapshotFilterRegression',)
    suites+=('NativeReferenceRegression',)
    suites+=('NativeTransportRegression',)
    suites+=('NativeResponsivenessRegression',)
    suites+=('NativeColorReadoutRegression',)
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
            if suite in ('NativeFolderRegression','NativeFolderRelocationRegression','NativeFolderSyncRegression'):
                path=fixtures / ('Parent/direct.png','Parent/child/a.png','Parent/child/b.png','Elsewhere/c.png','Elsewhere/d.png')[index]
                path.parent.mkdir(parents=True,exist_ok=True)
            if suite=='NativeAutoStackRegression':
                path=path.with_suffix('.jpg');exif=Image.Exif()
                second,fraction=((0,'9'),(1,'1'),(2,'0'),(2,'3'),(4,'0'))[index]
                exif[34665]={36867:f'2026:09:26 12:00:{second:02d}',37521:fraction,36881:'+00:00'}
                Image.new('RGB',(160,100),color).save(path,exif=exif)
            else:Image.new('RGB',(2400,1800) if suite in ('NativeComparisonLayoutRegression','NativeReferenceRegression','NativeResponsivenessRegression','NativeColorReadoutRegression') else (160,100),color).save(path)
            paths.append(str(path))
        executable=work/suite
        subprocess.run(['xcrun','swiftc','-swift-version','5','-parse-as-library',
            '-target','arm64-apple-macosx14.0','-module-cache-path',str(work/'module-cache'),
            *map(str,sources),str(root/'tests'/f'{suite}.swift'),'-o',str(executable)],check=True)
        suite_paths=paths if suite in ('NativeSelectionRegression','NativeReviewRegression','NativeThumbnailRegression','NativeCollectionRegression','NativeVirtualCopyRegression','NativeStackRegression','NativeAutoStackRegression','NativeFolderRegression','NativeKeywordRegression','NativeFolderRelocationRegression','NativeFolderSyncRegression','NativePainterRegression','NativeTargetPainterRegression','NativeOrientationRegression','NativeDevelopPresetRegression','NativeMetadataPresetRegression','NativeImportRegression','NativeImportProcessingRegression','NativePreviousImportRegression') else paths[:2]
        env={**os.environ,'LUMARAW_ENGINE':str(args.engine.resolve()),
            'LUMARAW_CATALOG':str(work/'catalogs'/suite),'LUMARAW_TEST_FIXTURES':'|'.join(suite_paths),
            'LUMARAW_PRESETS_ROOT':str(work/'presets'/suite)}
        if suite=='NativeReferenceRegression':env['LUMARAW_TEST_FIXTURES']='|'.join(paths)
        if suite=='NativeImportNamingRegression':env['LUMARAW_TEST_FIXTURES']='|'.join(paths)
        if suite in ('NativeImportBackupRegression','NativeImportPresetRegression','NativeImportSequenceRegression'):env['LUMARAW_TEST_FIXTURES']='|'.join(paths)
        if suite=='NativeResponsivenessRegression':env['LUMARAW_TEST_FIXTURES']='|'.join(paths)
        if suite=='NativeTransportRegression':
            relay=fixtures/'native-relay'
            relay.write_text('#!'+sys.executable+'\n'+(root/'tests/native_transport_fixture.py').read_text())
            relay.chmod(0o700)
            env['LUMARAW_TEST_RELAY']=str(relay);env['LUMARAW_TEST_WORK']=str(fixtures)
        if suite=='NativePointCurveRegression':
            import numpy as np
            from lumaraw.curves import packed_curve,evaluate
            cases=[[[0,0],[1,1]],[[.1,.2],[.4,.7],[.8,.9]],[[0,1],[.25,.1],[.5,.8],[1,0]],
                   [[0,0],[.25,.3],[.2501,.9],[1,1]],[[0,.3],[.2,.3],[.7,.6],[1,.6]]]
            references=[]
            for points in cases:
                values=np.unique(np.concatenate([np.linspace(0,1,257,dtype=np.float32),
                    np.array([(a[0]+b[0])/2 for a,b in zip(points,points[1:])],np.float32)]))
                references.append({'points':points,'samples':np.column_stack([values,evaluate(values,packed_curve(points))]).tolist()})
            curve_path=fixtures/'curve-geometry.json';curve_path.write_text(json.dumps(references))
            env['LUMARAW_TEST_CURVES']=str(curve_path)
        if suite=='NativeParametricCurveRegression':
            import numpy as np
            from lumaraw.model import Recipe,PARAMETRIC_FIELDS
            from lumaraw.parametric import packed,evaluate
            references=[]
            values=np.linspace(0,1,4097,dtype=np.float32)
            for amounts,splits in [([0,0,0,0],[.25,.5,.75]),([100,100,100,100],[.25,.5,.75]),
                                   ([-100,-100,-100,-100],[.01,.02,.03]),([100,-100,100,-100],[.01,.5,.99]),
                                   ([65,-45,35,-60],[.18,.52,.83])]:
                recipe=Recipe(**dict(zip(PARAMETRIC_FIELDS,amounts)),parametric_splits=splits)
                references.append({'recipe':recipe.dict(),'samples':np.column_stack([values,evaluate(values,packed(recipe))]).tolist()})
            curve_path=fixtures/'curve-geometry.json';curve_path.write_text(json.dumps(references))
            env['LUMARAW_TEST_CURVES']=str(curve_path)
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
