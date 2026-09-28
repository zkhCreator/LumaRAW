"""Single-owner broker admission and idle engine handoff.

Inputs: validated local engine identities, normal command admission and idle state.
Outputs: atomic admission decisions, a durable target reservation and one-use
clean-handoff receipt. Never terminate active image work or replay uncertain jobs.
The transport holds a lifetime owner lock before opening/migrating the catalog.
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import threading
import tempfile

from .runtime import engine_identity, valid_identity


class ServiceConnectionError(RuntimeError):
    def __init__(self, message, can_activate=False):
        super().__init__(message)
        self.can_activate = can_activate


def state_path(root):
    return Path(root)/'.broker-state.json'


def read_state(root):
    path = state_path(root)
    if not path.exists():
        return None
    if path.is_symlink() or path.stat().st_size > 4096:
        raise ServiceConnectionError('Invalid background service state; choose a different catalog or inspect its state file')
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or not valid_identity(value.get('engine')):
        raise ServiceConnectionError('Invalid background service identity')
    return value


def write_state(root, value):
    path = state_path(root)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,prefix='.broker-state-',suffix='.tmp',delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream)
            stream.flush();os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)


def allow_start(root, identity, activate=False):
    state = read_state(root)
    if not state or state['engine'] == identity:
        return
    current = state['engine']
    if current['generation'] > identity['generation'] or current['catalog_version'] > identity['catalog_version']:
        raise ServiceConnectionError('This catalog uses a newer LumaRAW engine. Open it with the newer application.')
    if current['generation'] == identity['generation'] and not activate:
        raise ServiceConnectionError('This catalog last used another build of LumaRAW. Choose Connect with This Version in Settings to switch.', True)


@contextmanager
def owner_lock(root):
    """Nonblocking lifetime lock; a second broker cannot unlink the live endpoint."""
    path = Path(root)/'.broker-owner.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        if os.name == 'nt':
            import msvcrt
            stream.seek(0,os.SEEK_END)
            if stream.tell()==0:stream.write(b'0');stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == 'nt':
                stream.seek(0);msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


class BrokerLifecycle:
    def __init__(self, service):
        self.service = service
        self.identity = engine_identity()
        self.lock = threading.RLock()
        self.requests = 0
        self.retiring = False
        self.finished = threading.Event()
        write_state(service.root, {'engine':self.identity, 'pid':os.getpid(), 'phase':'active'})

    def info(self):
        with self.lock:
            return {'engine':self.identity, 'pid':os.getpid(), 'retiring':self.retiring}

    @contextmanager
    def admit(self, identity):
        with self.lock:
            if identity != self.identity:
                raise ServiceConnectionError('The client and background service use different engines. Reconnect before applying changes.', True)
            if self.retiring:
                raise ServiceConnectionError('Background service is switching versions. Retry after the switch finishes.', True)
            self.requests += 1
        try:
            yield
        finally:
            with self.lock:
                self.requests -= 1

    def handoff(self, expected, target, explicit=False):
        if not valid_identity(target) or expected != self.identity:
            raise ServiceConnectionError('Background service changed during connection; retry without applying changes', True)
        if target['generation'] < self.identity['generation'] or target['catalog_version'] < self.identity['catalog_version']:
            raise ServiceConnectionError('A newer background service is already using this catalog')
        if target['generation'] == self.identity['generation'] and not explicit:
            raise ServiceConnectionError('Choose Connect with This Version to switch between builds', True)
        with self.lock:
            if self.retiring or self.requests:
                raise ServiceConnectionError('The background service is busy. Wait for the current operation, then reconnect.', True)
            # Serializes against queue acquisition. A reserved export is already
            # marked running before it leaves this lock, even before worker launch.
            with self.service.catalog() as catalog:
                if self.service.active or catalog.job_counts().get('running', 0):
                    raise ServiceConnectionError('An image is being processed. It will finish normally; reconnect afterward to switch versions.', True)
                self.service.upgrading = True
                try:
                    catalog.set_setting('clean_handoff', {'target':target})
                    write_state(self.service.root, {'engine':target, 'pid':os.getpid(), 'phase':'handoff'})
                except BaseException:
                    catalog.set_setting('clean_handoff', None)
                    self.service.upgrading = False
                    raise
                self.retiring = True
        return {'accepted':True, 'target':target}

    def retire_if_idle(self, seconds=180):
        import time
        with self.lock:
            if self.requests or self.retiring or time.monotonic()-self.service.last_activity <= seconds:
                return False
            with self.service.catalog() as catalog:
                if self.service.active or any(catalog.job_counts().get(key, 0) for key in ('pending','running')):
                    return False
                self.service.upgrading = True
                self.retiring = True
            return True
