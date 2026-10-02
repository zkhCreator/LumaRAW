"""Bounded, exclusive Copy publication behind the platform filesystem boundary.

Inputs: pinned destination, captured source identity, durable per-file journal and
cancellation callback. Outputs: fsynced byte-identical copies and ownership receipts.
Source files are read-only. Paths are traversed with no-follow directory handles;
publication is an exclusive hard link on the destination volume. Unsupported
filesystems fail visibly. No SQL, image decoding, renaming or deletion of originals
or published copies. Recovery never adopts an unowned file, even with equal bytes.
Destination validation captures explicit date layout without reading photo pixels.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import stat

BLOCK = 1024*1024


def fingerprint(value):
    return [value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns]


@contextmanager
def directory(path, create=False):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('Copy paths must be absolute and normalized')
    fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[1:]:
            if create:
                try:
                    os.mkdir(part, mode=0o755, dir_fd=fd)
                    os.fsync(fd)
                except FileExistsError:
                    pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def validate_destination(path, sources, catalog, organization='flat', subfolder='', date_format='year_date'):
    from .import_dates import validate
    validate(date_format)
    if organization not in ('flat', 'source', 'date'):
        raise ValueError('Unsupported destination organization')
    if subfolder and (subfolder in ('.', '..') or '/' in subfolder or '\\' in subfolder or
                      '\0' in subfolder or len(subfolder.encode()) > 255):
        raise ValueError('Into Subfolder must be one folder name')
    path = Path(path).expanduser().absolute()
    with directory(path) as fd:
        pinned = fingerprint(os.fstat(fd))[:2]
    if path == catalog or catalog in path.parents:
        raise ValueError('The active catalog cannot be a Copy destination')
    roots = [source['path'] for source in sources if source['directory']]
    if any(path == Path(root) or Path(root) in path.parents for root in roots):
        raise ValueError('Choose a destination outside the selected source folders')
    return {'destination':str(path), 'destination_identity':pinned, 'organization':organization,
            'subfolder':subfolder, 'roots':roots, 'date_format':date_format}


def check_destination(value):
    with directory(value['destination']) as fd:
        if fingerprint(os.fstat(fd))[:2] != value['destination_identity']:
            raise ValueError('The selected destination was replaced or is unavailable')


def preflight(row, value):
    check_destination(value)
    target = Path(row['target'])
    # Check every existing ancestor without creating directories or following links.
    try:
        with directory(target.parent) as fd:
            try:
                os.stat(target.name, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                return
            raise FileExistsError('Copy destination already exists: '+str(target))
    except FileNotFoundError:
        return


def check_cancel(cancelled):
    if cancelled():
        raise InterruptedError('Copy import cancelled; completed files remain at the destination')


def digest(fd, cancelled):
    os.lseek(fd, 0, os.SEEK_SET)
    result = hashlib.sha256()
    while True:
        check_cancel(cancelled)
        block = os.read(fd, BLOCK)
        if not block:
            return result.hexdigest()
        result.update(block)


def verify(fd, expected, sha256, cancelled):
    before = os.fstat(fd)
    if not stat.S_ISREG(before.st_mode) or fingerprint(before) != expected:
        raise ValueError('A copied file changed; it will not be overwritten')
    if digest(fd, cancelled) != sha256 or fingerprint(os.fstat(fd)) != expected:
        raise ValueError('A copied file failed checksum verification; it will not be overwritten')


def cleanup(row):
    """Remove only a journal-owned scratch link; never the published target."""
    target = Path(row['target'])
    try:
        handle=directory(target.parent)
        fd=handle.__enter__()
    except FileNotFoundError:
        return
    try:
        try:
            value = os.stat(row['temporary'], dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        if row['ownership'] and stat.S_ISREG(value.st_mode) and fingerprint(value)[:2] == json.loads(row['ownership']):
            os.unlink(row['temporary'], dir_fd=fd)
            os.fsync(fd)
        else:
            raise ValueError('A temporary copy was replaced; it was preserved for inspection')
    finally:
        handle.__exit__(None,None,None)


def transfer(row, value, save, cancelled):
    check_cancel(cancelled)
    check_destination(value)
    source, target = Path(row['source']), Path(row['target'])
    expected = json.loads(row['source_identity'])
    with directory(target.parent, create=True) as output:
        check_destination(value)
        if row['state'] == 'published':
            fd = os.open(target.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=output)
            try:
                verify(fd, json.loads(row['fingerprint']), row['sha256'], cancelled)
            finally:
                os.close(fd)
            cleanup(row)
            return
        flags = os.O_RDWR | os.O_NOFOLLOW
        if row['state'] == 'planned':
            fd = os.open(row['temporary'], flags | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=output)
        else:
            fd = os.open(row['temporary'], flags, dir_fd=output)
        try:
            current = os.fstat(fd)
            if row['state'] == 'planned':
                # Persist the directory entry before its SQL ownership receipt.
                # A crash before the receipt remains deliberately unclaimed.
                os.fsync(output)
                save(row, state='writing', ownership=json.dumps(fingerprint(current)[:2]))
            elif not stat.S_ISREG(current.st_mode) or fingerprint(current)[:2] != json.loads(row['ownership']):
                raise ValueError('Temporary copy ownership changed; it will not be overwritten')
            if row['state'] == 'writing':
                if current.st_nlink != 1:
                    raise ValueError('An incomplete copy has unexpected hard links; it was preserved')
                with directory(source.parent) as original_dir:
                    original = os.open(source.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=original_dir)
                    try:
                        before = os.fstat(original)
                        if not stat.S_ISREG(before.st_mode) or fingerprint(before) != expected:
                            raise ValueError('The original changed before copying')
                        os.ftruncate(fd, 0)
                        os.lseek(fd, 0, os.SEEK_SET)
                        checksum = hashlib.sha256()
                        while True:
                            check_cancel(cancelled)
                            block = os.read(original, BLOCK)
                            if not block:
                                break
                            checksum.update(block)
                            view = memoryview(block)
                            while view:
                                written = os.write(fd, view)
                                if written <= 0:
                                    raise OSError('Copy write made no progress')
                                view = view[written:]
                        if fingerprint(os.fstat(original)) != expected or fingerprint(os.stat(source.name, dir_fd=original_dir, follow_symlinks=False)) != expected:
                            raise ValueError('The original changed during copying')
                        os.utime(fd, ns=(before.st_atime_ns, before.st_mtime_ns))
                        os.fsync(fd)
                        copied = fingerprint(os.fstat(fd))
                        verify(fd, copied, checksum.hexdigest(), cancelled)
                        save(row, state='sealed', fingerprint=json.dumps(copied), sha256=checksum.hexdigest())
                    finally:
                        os.close(original)
            else:
                verify(fd, json.loads(row['fingerprint']), row['sha256'], cancelled)
            check_cancel(cancelled)
            # A replaced ancestor must not redirect publication or produce a
            # catalog path that no longer reaches the pinned output directory.
            with directory(target.parent) as check:
                if fingerprint(os.fstat(check))[:2] != fingerprint(os.fstat(output))[:2]:
                    raise ValueError('The destination folder changed during copying')
            temporary=os.stat(row['temporary'],dir_fd=output,follow_symlinks=False)
            if not stat.S_ISREG(temporary.st_mode) or fingerprint(temporary)!=json.loads(row['fingerprint']):
                raise ValueError('Temporary copy changed before publication')
            try:
                os.link(row['temporary'], target.name, src_dir_fd=output, dst_dir_fd=output, follow_symlinks=False)
            except FileExistsError:
                existing = os.stat(target.name, dir_fd=output, follow_symlinks=False)
                if not stat.S_ISREG(existing.st_mode) or fingerprint(existing) != json.loads(row['fingerprint']):
                    raise FileExistsError('Copy destination already exists; it was preserved: '+str(target))
            os.fsync(output)
            published=os.stat(target.name,dir_fd=output,follow_symlinks=False)
            if not stat.S_ISREG(published.st_mode) or fingerprint(published)!=json.loads(row['fingerprint']):
                raise ValueError('Published copy changed before its receipt was saved')
            save(row, state='published')
        finally:
            os.close(fd)
        cleanup(row)


def verify_published(row, value):
    check_destination(value)
    target = Path(row['target'])
    with directory(target.parent) as fd:
        current = os.stat(target.name, dir_fd=fd, follow_symlinks=False)
        if row['state'] != 'published' or not stat.S_ISREG(current.st_mode) or fingerprint(current) != json.loads(row['fingerprint']):
            raise ValueError('A copied file changed before catalog application')
