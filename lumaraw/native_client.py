"""Persistent bounded stdio relay for the native shell's existing service calls.

Inputs: newline JSON {id, method, params} from one owning app. Outputs: correlated
service envelopes, possibly out of order. Every call retains bridge identity
negotiation; no SQL/pixels, mutation retries or alternate broker ownership.
Eight workers/32 admitted ordinary calls plus two control workers/eight control
calls bound queueing and let cancellation overtake image waits. EOF drains
already admitted calls; a lost response never replays an uncertain mutation.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import sys
import threading

from .bridge import call, MAX_MESSAGE

CONTROL = frozenset(('cancel_preview', 'service_connection'))


def invalid_constant(value):
    raise ValueError('Non-finite JSON constant')


def run(root, source=None, destination=None, dispatch=None):
    source = source or sys.stdin.buffer
    destination = destination or sys.stdout.buffer
    dispatch = dispatch or call
    output_lock = threading.Lock()
    active_lock = threading.Lock()
    active = set()
    slots = [threading.BoundedSemaphore(32), threading.BoundedSemaphore(8)]

    def emit(identity, result):
        payload = json.dumps({'id': identity, **result}, ensure_ascii=False, allow_nan=False).encode()+b'\n'
        if len(payload) > MAX_MESSAGE:
            payload = json.dumps({'id': identity, 'ok': False,
                'error': 'Service response exceeded the native transport limit. Its outcome is unknown; read current state before retrying.',
                'type': 'ResponseTooLarge'}).encode()+b'\n'
        with output_lock:
            destination.write(payload)
            destination.flush()

    def error(identity, message, kind='NativeProtocolError'):
        emit(identity, {'ok': False, 'error': message, 'type': kind})

    def execute(request, lane):
        try:
            try:
                result = dispatch(root, request['method'], request['params'])
            except Exception as exc:
                result = {'ok': False, 'error': str(exc)[:2000], 'type': type(exc).__name__,
                          'can_activate': getattr(exc, 'can_activate', False)}
            emit(request['id'], result)
        finally:
            with active_lock:
                active.discard(request['id'])
            slots[lane].release()

    with ThreadPoolExecutor(max_workers=8) as ordinary, ThreadPoolExecutor(max_workers=2) as control:
        while True:
            data = source.readline(MAX_MESSAGE+1)
            if not data:
                break
            if len(data) > MAX_MESSAGE or not data.endswith(b'\n'):
                # Framing is no longer trustworthy. Never parse or dispatch a
                # suffix of an oversized command as another command.
                error(None, 'Native command framing exceeded the limit; no command from this frame was admitted.')
                break
            try:
                request = json.loads(data, parse_constant=invalid_constant)
            except (ValueError, UnicodeDecodeError):
                error(None, 'Invalid native command JSON; no command was admitted.')
                continue
            identity = request.get('id') if isinstance(request, dict) else None
            if (not isinstance(request, dict) or set(request) != {'id', 'method', 'params'} or
                    type(identity) is not int or not 1 <= identity <= 2**53-1 or
                    not isinstance(request['method'], str) or not 0 < len(request['method']) <= 128 or
                    not isinstance(request['params'], dict)):
                error(identity, 'Invalid native command fields; no command was admitted.')
                continue
            lane = int(request['method'] in CONTROL)
            with active_lock:
                duplicate = identity in active
                if not duplicate:
                    active.add(identity)
            if duplicate:
                # A duplicate ID cannot safely identify which response a client
                # intended. Close this stream; the first admitted call drains.
                error(None, 'Duplicate in-flight native command ID; duplicate command was not admitted.')
                break
            if not slots[lane].acquire(blocking=False):
                with active_lock:
                    active.discard(identity)
                error(identity, 'Native command capacity reached; this command was not admitted.', 'NativeBusy')
                continue
            (control if lane else ordinary).submit(execute, request, lane)
