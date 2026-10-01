"""Persistent native relay framing, admission, cancellation and no-replay checks.

Deterministic in-memory transports prove bounded concurrent admission and control
priority. An injected service boundary records calls without catalogs or pixels.
Actual broker/version behavior is also covered by native and lifecycle probes.
"""
import io
import json
import threading
import time

from lumaraw.native_client import run
from lumaraw.bridge import MAX_MESSAGE


def frame(id_, method='read', params=None):
    return json.dumps({'id': id_, 'method': method, 'params': params or {}}).encode()+b'\n'


def relay(data, dispatch):
    output=io.BytesIO()
    run('unused', io.BytesIO(data), output, dispatch)
    return [json.loads(line) for line in output.getvalue().splitlines()]


def test_correlates_out_of_order_without_serial_head_of_line():
    first=threading.Event();release=threading.Event();seen=[]
    def call(root, method, params):
        seen.append(method)
        if method=='slow':
            first.set();assert release.wait(3)
        else:
            assert first.wait(3);release.set()
        return {'ok':True,'result':{'method':method,'unicode':'照片 é'}}
    replies=relay(frame(1,'slow')+frame(2,'fast'),call)
    assert {r['id']:r['result']['method'] for r in replies}=={1:'slow',2:'fast'}
    assert all(r['result']['unicode']=='照片 é' for r in replies)
    assert sorted(seen)==['fast','slow']


def test_bounded_queue_reserves_control_capacity():
    release=threading.Event();lock=threading.Lock();ordinary=[]
    def call(root, method, params):
        if method=='cancel_preview':release.set()
        else:
            with lock:ordinary.append(params['index'])
            assert release.wait(3)
        return {'ok':True,'result':{}}
    replies=relay(b''.join(frame(i+1,'preview_photo',{'index':i}) for i in range(80))+frame(81,'cancel_preview'),call)
    assert len(replies)==81 and len(ordinary)==32
    assert sum(r.get('type')=='NativeBusy' for r in replies)==48
    assert next(r for r in replies if r['id']==81)['ok']


def test_failures_and_unknown_mutation_outcomes_never_replay():
    calls=[]
    class ActivationError(RuntimeError):can_activate=True
    def call(root, method, params):
        calls.append(method)
        if method=='activate':raise ActivationError('Busy engine')
        raise EOFError('Lost mutation response')
    replies=relay(frame(1,'edit_photo')+frame(2,'activate'),call)
    assert sorted(calls)==['activate','edit_photo']
    assert {r['id']:r['type'] for r in replies}=={1:'EOFError',2:'ActivationError'}
    assert next(r for r in replies if r['id']==2)['can_activate']


def test_invalid_envelopes_never_dispatch_and_valid_next_frame_survives():
    invalid=[b'not json\n',b'[]\n',frame(True),frame(-1),b'{"id":3,"method":"read","params":[]}\n',
             b'{"id":4,"method":"read","params":{"value":NaN}}\n']
    called=[]
    def call(root, method, params):called.append(method);return {'ok':True,'result':{}}
    replies=relay(b''.join(invalid)+frame(10),call)
    assert called==['read'] and len(replies)==7
    assert sum(r['ok'] for r in replies)==1


def test_oversize_or_unterminated_frame_never_dispatches_suffix():
    called=[]
    for data in [b'x'*(MAX_MESSAGE+1)+b'\n'+frame(1),frame(1).rstrip(b'\n')]:
        replies=relay(data,lambda *args:called.append(args))
        assert len(replies)==1 and not replies[0]['ok']
    assert not called


def test_duplicate_inflight_id_is_not_dispatched_twice():
    called=[]
    def call(*args):
        called.append(args);time.sleep(.05)
        return {'ok':True,'result':{}}
    replies=relay(frame(1,'edit_photo')+frame(1,'edit_photo')+frame(2),call)
    assert len(called)==1 and len(replies)==2
    assert any(r['id'] is None and not r['ok'] for r in replies)


def test_eof_drains_admitted_calls_and_oversize_response_is_explicit():
    called=[]
    def call(root,method,params):
        time.sleep(.02);called.append(method)
        return {'ok':True,'result':{'value':'x'*MAX_MESSAGE}}
    replies=relay(frame(1,'edit_photo'),call)
    assert called==['edit_photo'] and replies[0]['type']=='ResponseTooLarge'
    assert 'unknown' in replies[0]['error']
