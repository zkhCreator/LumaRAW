"""Compile the optional Metal C ABI without credentials or Xcode Metal tool downloads.
Inputs: Objective-C++ source. Output: package-local dylib; shader compiles on device.
The portable core never requires this library on Windows or CPU-only hosts.
"""
from pathlib import Path
import subprocess

def build(source):
    source=Path(source).resolve();target=source/'lumaraw/accelerators/libLumaMetal.dylib'
    subprocess.run(['xcrun','clang++','-std=c++17','-O2','-fobjc-arc','-dynamiclib','-mmacosx-version-min=14.0','-arch','arm64','-install_name','@rpath/libLumaMetal.dylib',f'-ffile-prefix-map={source}=.',f'-fdebug-prefix-map={source}=.','-framework','Foundation','-framework','Metal',str(source/'metal/Bridge.mm'),'-o',str(target)],check=True)
    return target
if __name__=='__main__':print(build(Path(__file__).resolve().parents[1]))
