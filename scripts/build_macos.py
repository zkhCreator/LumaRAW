"""Build an Apple Silicon native SwiftUI app with a self-contained Python engine.

Inputs: source and an explicit, new build directory. Outputs: a local ad-hoc signed
.app. Never accesses signing identities, credentials or Keychain. No notarization
or public distribution claim. Builds can be repeated into a fresh directory.
"""
import argparse
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
    subprocess.run([sys.executable,'-m','PyInstaller','--clean','--noconfirm','--onedir','--console',
        '--name','LumaRAWEngine','--exclude-module','PySide6','--exclude-module','shiboken6','--exclude-module','pytest','--exclude-module','tkinter',
        '--add-binary',str(metal_library)+':lumaraw/accelerators','--collect-data','lumaraw','--collect-data','jsonschema_specifications',
        '--distpath',str(build/'engine'),'--workpath',str(build/'intermediate'),'--specpath',str(build),
        '--paths',str(source),str(source/'launch.py')],check=True,cwd=source)
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
        'CFBundleDisplayName':'LumaRAW','CFBundleShortVersionString':'0.4.0','CFBundleVersion':'5',
        'CFBundleDevelopmentRegion':'en','CFBundleLocalizations':['en'],
        'CFBundlePackageType':'APPL','CFBundleIconFile':'LumaRAW.icns','LSMinimumSystemVersion':'14.0',
        'NSHighResolutionCapable':True,'NSPrincipalClass':'NSApplication',
        'LSApplicationCategoryType':'public.app-category.photography',
        'CFBundleDocumentTypes':[{'CFBundleTypeName':'Photographs','CFBundleTypeRole':'Viewer','LSHandlerRank':'Alternate',
            'CFBundleTypeExtensions':['nef','nrw','dng','arw','cr2','cr3','raf','orf','rw2','jpg','jpeg','png','tif','tiff']}]
    }))
    subprocess.run(['codesign','--force','--deep','--sign','-',str(app)],check=True)
    subprocess.run(['codesign','--verify','--deep','--strict',str(app)],check=True)
    print(app)
if __name__=='__main__':main()
