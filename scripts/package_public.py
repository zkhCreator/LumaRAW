"""Create a checked source-only ZIP, with no Git history or local metadata.

Inputs: current source and a new archive path outside it. Output: deterministic ZIP.
Never opens credential-looking entries, modifies source, publishes or overwrites.
"""
import argparse
from pathlib import Path
import zipfile
import sys
sys.dont_write_bytecode = True  # Keep a clean public snapshot clean when packaging it.
from check_public import audit


def package(root, destination):
    root = Path(root).resolve(); destination = Path(destination).resolve()
    if destination == root or root in destination.parents:
        raise ValueError('Choose an archive path outside the source directory.')
    files, findings = audit(root)
    if findings:
        raise ValueError('Public check failed; run check_public.py for redacted categories.')
    with zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            # Recheck immediately before reading; source must be idle during packaging.
            item = root / path
            if item.is_symlink(): raise ValueError('Source changed during packaging.')
            info = zipfile.ZipInfo('LumaRAW-public/' + path.as_posix(), (2026, 1, 1, 0, 0, 0))
            info.create_system = 3; info.external_attr = 0o100644 << 16
            archive.writestr(info, item.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return len(files)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    print('Archived source files:', package(Path(__file__).resolve().parents[1], args.destination))
