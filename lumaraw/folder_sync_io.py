"""Bounded filesystem reads for durable folder synchronization.

Inputs: a staged directory/file and cancellation callback. Outputs: at most 256
directory entries or one file's stat/metadata snapshot (optionally retaining the
camera's civil date for Copy organization). No catalog connection,
pixel decoding, hashing or original writes. One live directory iterator survives
page requests; after restart it can replay into unique on-disk staging rows.
"""
import os
from pathlib import Path
import stat

from .capture_time import read_capture_time
from .model import IMAGE_EXTENSIONS
from .relocations import identity
from .xmp_read import read_xmp


def directory_identity(path):
    value = os.stat(path, follow_symlinks=False)
    if not stat.S_ISDIR(value.st_mode):
        raise ValueError('The synchronized location must remain a real directory')
    return [value.st_dev, value.st_ino, value.st_mtime_ns]


class DirectoryReader:
    def __init__(self):
        self.path = None
        self.iterator = None

    def close(self):
        if self.iterator is not None:
            self.iterator.close()
        self.path = self.iterator = None

    def read(self, path, expected, cancelled):
        if directory_identity(path) != expected:
            raise ValueError('Folder contents changed during scanning; create a fresh plan')
        if self.path != path:
            self.close()
            self.iterator = os.scandir(path)
            self.path = path
        files, directories, done = [], [], False
        for _ in range(256):
            if cancelled():
                raise InterruptedError('Folder synchronization cancelled')
            try:
                entry = next(self.iterator)
            except StopIteration:
                done = True
                break
            if entry.name.startswith('.') or entry.is_symlink():
                continue
            if entry.is_dir(follow_symlinks=False):
                directories.append((entry.path,directory_identity(entry.path)))
            elif entry.is_file(follow_symlinks=False) and Path(entry.name).suffix.lower() in IMAGE_EXTENSIONS:
                files.append(entry.path)
        if directory_identity(path) != expected:
            raise ValueError('Folder contents changed during scanning; create a fresh plan')
        if done:
            self.close()
        return {'files':files,'directories':directories,'done':done}


def inspect_file(row, scan_metadata, cancelled, include_date=False):
    if cancelled():
        raise InterruptedError('Folder synchronization cancelled')
    path = Path(row['path'])
    try:
        if path.resolve() != path:
            raise ValueError('A catalog path now traverses a symbolic link; locate its real folder first')
        before = identity(path)
        if before is None:
            if not row['source_id']:
                raise ValueError('A newly discovered file disappeared; scan again')
            return {'missing':True,'fingerprints':{str(path):None},'clock':{},'patch':{},'notes':[]}
        result = {'missing':False,'fingerprints':{str(path):before},'clock':{},'patch':{},'notes':[]}
        if scan_metadata or not row['source_id']:
            result.update(read_xmp(path))
            result['clock'] = read_capture_time(path, include_date=include_date)
        if cancelled():
            raise InterruptedError('Folder synchronization cancelled')
        if identity(path) != before:
            raise ValueError('Original changed during metadata reading; scan again')
        return result
    except InterruptedError:
        raise
    except (OSError,ValueError) as error:
        return {'error':str(error),'fingerprints':{},'clock':{},'patch':{},'notes':[]}
