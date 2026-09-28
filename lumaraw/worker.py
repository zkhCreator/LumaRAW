"""One request per disposable image subprocess.

Reads bounded JSON from stdin, returns one JSON result; no pixel buffers cross IPC.
The catalog service owns scheduling, cancellation, and RSS monitoring. Process exit releases
LibRaw/NumPy native allocations even after failure. Original files are read-only.
The engine identity must match its broker before any pixels or outputs are opened.
"""
import json
import sys
import time


def main():
    try:
        payload = sys.stdin.buffer.readline(8*1024*1024+1)
        if len(payload)>8*1024*1024:
            raise ValueError('Image worker request exceeds 8 MiB')
        request = json.loads(payload)
        if 'engine_identity' in request:
            from .runtime import engine_identity, EngineChangedError
            if request['engine_identity'] != engine_identity():
                raise EngineChangedError('The installed engine changed while its service was running. Reconnect with this version in Settings, then retry interrupted exports. No pixels were processed.')
        # Stop orphaned image work when the owning broker disappears.
        if request.get('parent_pid'):
            import os, threading
            import psutil
            parent=psutil.Process(request['parent_pid'])
            def monitor_parent():
                while True:
                    time.sleep(.2)
                    if not parent.is_running():os._exit(75)
            threading.Thread(target=monitor_parent,daemon=True).start()
        from . import accelerators, performance
        accelerators.configure(request.get('compute_backend','auto'),request['budget_mb'])
        performance.reset();started=time.perf_counter()
        from .model import Recipe
        from .imaging import make_preview, make_thumbnail, export_image, trim_cache
        recipe = Recipe.parse(request.get('recipe', {}))
        operation = request['operation']
        if operation in ('preview','detail','reference'):
            result = make_preview(request['path'], recipe, request['cache'], request['budget_mb'],detail=request.get('detail'),display=request.get('display'),include_before=request.get('include_before',True),max_edge=request.get('max_edge'))
        elif operation == 'calibrate':
            from .calibration import calibrate
            result = calibrate(request['path'],request['reference'],request['source_rect'],request['reference_rect'],request['cache'],request['budget_mb'],request['name'],request['lighting'])
        elif operation == 'thumbnail':
            result = make_thumbnail(request['path'], request['cache'], request['budget_mb'],
                                    recipe=recipe if request.get('kind') == 'developed' else None)
        elif operation == 'export':
            result = export_image(request['path'], recipe, request['destination'], request['format'],
                                  request['budget_mb'], request['job_id'],options=request.get('options'),cache=request['cache'],
                                  metadata_snapshot=request.get('metadata_snapshot'))
        else:
            raise ValueError('Unknown worker operation')
        if 'cache' in request:
            try:
                trim_cache(request['cache'], maximum_mb=1024,keep=[result.get('preview', ''), result.get('before', ''), result.get('thumbnail', ''),*result.get('cache_keep',[])])
            except OSError:
                # Cache housekeeping cannot turn a committed export into a failed job.
                result['cache_warning'] = 'Cache cleanup is not yet complete'
        result['processing']={**accelerators.report(),'stages':performance.report(),'worker_seconds':round(time.perf_counter()-started,6)}
        print(json.dumps({'ok': True, **result}), flush=True)
    except Exception as error:
        name = type(error).__name__
        message = str(error)
        if 'LibRaw' in name:
            message = f'RAW decoding failed ({name}). The file may be damaged or use unsupported compression; Nikon HE / HE* support depends on LibRaw.'
        print(json.dumps({'ok': False, 'error': message, 'type': name}), flush=True)
        sys.exit(1)

if __name__ == '__main__':
    main()
