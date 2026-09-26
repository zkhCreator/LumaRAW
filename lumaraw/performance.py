"""Process-local stage timings; measurements describe one worker, not cached history."""
from contextlib import contextmanager
import time
_totals={}
_counts={}
@contextmanager
def stage(name):
    start=time.perf_counter()
    try:yield
    finally:
        _totals[name]=_totals.get(name,0.)+time.perf_counter()-start
        _counts[name]=_counts.get(name,0)+1

def reset():_totals.clear();_counts.clear()
def report():return {k:{'seconds':round(v,6),'calls':_counts[k]} for k,v in _totals.items()}
