"""Build an Apple Silicon native SwiftUI app with a self-contained Python engine.

Inputs: source and an explicit, new build directory. Outputs: a local ad-hoc signed
.app with registered photo and collection-node transfer types. Never accesses
signing identities, credentials or Keychain. No notarization or public distribution
claim. Records installed RAW build inputs and compares a collected-engine import
probe before copying/signing the app. Builds can be repeated into a fresh directory.
"""
import argparse
import json
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--build-root',required=True,type=Path);args=parser.parse_args()
    source=Path(__file__).resolve().parents[1];build=args.build_root.resolve()
    if build.exists():raise SystemExit('Choose a new build directory; existing outputs are preserved.')
    if source==build or build in source.parents:raise SystemExit('Unsafe build directory')
    build.mkdir(parents=True)
    from build_metal import build as build_metal
    metal_library=build_metal(source)
    sys.path.insert(0,str(source))
    from lumaraw.runtime import source_digest, raw_backend
    from lumaraw.raw_backend_probe import inspect_backend
    expected_backend=inspect_backend()
    manifest=build/'engine_build.json'
    manifest.write_text(json.dumps({'digest':source_digest(source),'raw_backend':raw_backend()},sort_keys=True))
    subprocess.run([sys.executable,'-m','PyInstaller','--clean','--noconfirm','--onedir','--console',
        '--name','LumaRAWEngine','--exclude-module','PySide6','--exclude-module','shiboken6','--exclude-module','pytest','--exclude-module','tkinter',
        '--add-data',str(manifest)+':lumaraw',
        '--add-binary',str(metal_library)+':lumaraw/accelerators','--collect-data','lumaraw','--collect-data','jsonschema_specifications',
        '--distpath',str(build/'engine'),'--workpath',str(build/'intermediate'),'--specpath',str(build),
        '--paths',str(source),str(source/'launch.py')],check=True,cwd=source)
    actual_backend=json.loads(subprocess.run([
        str(build/'engine/LumaRAWEngine/LumaRAWEngine'),'--backend-info'],
        check=True,capture_output=True,text=True,timeout=60).stdout)
    if actual_backend!=expected_backend:
        raise RuntimeError('The collected RAW backend differs from the source build inputs')
    (build/'backend_probe.json').write_text(json.dumps(actual_backend,sort_keys=True))
    app=build/'LumaRAW.app';contents=app/'Contents';mac=contents/'MacOS';resources=contents/'Resources'
    mac.mkdir(parents=True);resources.mkdir()
    subprocess.run(['xcrun','swiftc','-swift-version','5','-parse-as-library','-O','-target','arm64-apple-macosx14.0','-file-prefix-map',f'{source}=.','-debug-prefix-map',f'{source}=.',
        *map(str,sorted((source/'native').glob('*.swift'))),'-o',str(mac/'LumaRAW')],check=True)
    shutil.copytree(build/'engine/LumaRAWEngine',resources/'Engine',symlinks=True)
    shutil.copy2(source/'assets/LumaRAW.icns',resources/'LumaRAW.icns')
    shutil.copytree(source/'skills',resources/'skills')
    shutil.copytree(source/'licenses',resources/'licenses')
    shutil.copy2(source/'THIRD_PARTY_NOTICES.md',resources/'THIRD_PARTY_NOTICES.md')
    shutil.copy2(source/'LICENSE',resources/'LICENSE')
    (contents/'Info.plist').write_bytes(plistlib.dumps({
        'CFBundleExecutable':'LumaRAW','CFBundleIdentifier':'local.lumaraw.native','CFBundleName':'LumaRAW',
        'CFBundleDisplayName':'LumaRAW','CFBundleShortVersionString':'0.4.1','CFBundleVersion':'6',
        'CFBundleDevelopmentRegion':'en','CFBundleLocalizations':['en'],
        'CFBundlePackageType':'APPL','CFBundleIconFile':'LumaRAW.icns','LSMinimumSystemVersion':'14.0',
        'NSHighResolutionCapable':True,'NSPrincipalClass':'NSApplication',
        'LSApplicationCategoryType':'public.app-category.photography',
        'UTExportedTypeDeclarations':[
            {'UTTypeIdentifier':'local.lumaraw.catalog-photo',
             'UTTypeDescription':'LumaRAW Catalog Photo','UTTypeConformsTo':['public.data']},
            {'UTTypeIdentifier':'local.lumaraw.catalog-collection-node',
             'UTTypeDescription':'LumaRAW Catalog Collection','UTTypeConformsTo':['public.data']}
        ],
        'CFBundleDocumentTypes':[{'CFBundleTypeName':'Photographs','CFBundleTypeRole':'Viewer','LSHandlerRank':'Alternate',
            'CFBundleTypeExtensions':['nef','nrw','dng','arw','cr2','cr3','raf','orf','rw2','jpg','jpeg','png','tif','tiff']}]
    }))
    subprocess.run(['codesign','--force','--deep','--sign','-',str(app)],check=True)
    subprocess.run(['codesign','--verify','--deep','--strict',str(app)],check=True)
    print(app)
if __name__=='__main__':main()
