"""Observable warm-grid cache behavior without bypassing source invalidation.

Uses generated raster fixtures and real cold workers. Warm requests must not
spawn workers; corrupted, changed-source and symlink entries must not be reused.
These thumbnails remain source previews, not developed-recipe thumbnails.
"""
import os
import subprocess
import sys

from PIL import Image
import pytest

from lumaraw.service import Service
from lumaraw.source_identity import cached_thumbnail, thumbnail_path


def test_warm_page_avoids_workers_and_changed_original_invalidates(tmp_path, monkeypatch):
    path=tmp_path/'original.png'
    Image.new('RGB',(120,80),'navy').save(path)
    service=Service(tmp_path/'catalog')
    try:
        service.dispatch('queue_control',{'action':'pause'})
        service.dispatch('import_photos',{'paths':[str(path)]})
        assert service.dispatch('cached_thumbnails',{'photo_ids':[1]})['thumbnails'] == []
        cold=service.dispatch('thumbnail',{'photo_id':1})
        with Image.open(cold['thumbnail']) as image:
            assert image.width <= 220 and image.height <= 140
        def forbidden(*args,**kwargs):
            raise AssertionError('Warm thumbnails must not start a worker')
        monkeypatch.setattr(service,'run_worker',forbidden)
        warm=service.dispatch('thumbnail',{'photo_id':1})
        assert warm['cache_hit'] and not warm['worker_spawned']
        page=service.dispatch('cached_thumbnails',{'photo_ids':[1,1]})
        assert page['thumbnails'] == [{'photo_id':1,'thumbnail':cold['thumbnail']}]
        assert not page['worker_spawned']
        Image.new('RGB',(121,81),'red').save(path)
        assert service.dispatch('cached_thumbnails',{'photo_ids':[1]})['thumbnails'] == []
    finally:
        service.close()


def test_partial_and_symlink_thumbnail_not_reused(tmp_path):
    path=tmp_path/'photo.png'
    Image.new('RGB',(40,30),'green').save(path)
    cache=tmp_path/'cache';cache.mkdir()
    target=thumbnail_path(path,cache)
    target.write_bytes(b'\xff\xd8unfinished')
    assert cached_thumbnail(path,cache) is None
    target.unlink()
    target.symlink_to(path)
    assert cached_thumbnail(path,cache) is None
    assert path.exists()


def test_broker_identity_layer_does_not_import_pixel_stack():
    result=subprocess.run([sys.executable,'-c',
        'import sys; import lumaraw.source_identity; '
        'assert not any(x in sys.modules for x in ("numpy", "rawpy", "PIL", "scipy"))'],
        capture_output=True,text=True)
    assert result.returncode == 0,result.stderr
