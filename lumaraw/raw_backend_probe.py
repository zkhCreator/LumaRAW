"""Build-only smoke probe for the imported RAW implementation.

Inputs: the active engine environment and its validated build identity. Outputs:
path-free version/capability/identity JSON; no catalog, photo or service access.
This explicitly imports pixel libraries in a short diagnostic process. Ordinary
broker startup and cache lookup use the stdlib-only runtime_backend descriptor.
No camera support or processing accuracy is inferred from the version or marker.
"""
from pathlib import Path
import sys


def inspect_backend():
    import rawpy
    from rawpy import _rawpy
    from .runtime import engine_identity, pixel_cache_namespace, raw_backend

    if rawpy.__version__ != raw_backend()['version']:
        raise ValueError('The loaded RAW version differs from the build descriptor')
    marker = getattr(_rawpy, 'GREYBOX_WB_API_VERSION', None)
    if marker is not None and (type(marker) is not int or marker < 1):
        raise ValueError('Invalid RAW greybox capability marker')
    if getattr(sys, 'frozen', False):
        bundle = Path(sys._MEIPASS).resolve(strict=True)
        if not Path(_rawpy.__file__).resolve(strict=True).is_relative_to(bundle):
            raise ValueError('The RAW extension was loaded outside the engine bundle')
    return {'rawpy_version': rawpy.__version__,
            'libraw_version': list(rawpy.libraw_version),
            'greybox_wb_api': marker, 'pixel_cache_namespace': pixel_cache_namespace(),
            'engine': engine_identity()}
