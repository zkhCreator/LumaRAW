# Third-party notices

LumaRAW Native 0.4 original source is licensed under MIT; see LICENSE. This does not relicense dependencies or third-party assets. The native UI uses Apple SwiftUI/AppKit. The application build excludes the Qt/PySide runtime. Four ICC profile assets were generated from the unmodified Qt 6.11.2 named color spaces at build preparation; the original Qt notices are retained with the source provenance. PySide is a development-only regression-test dependency.

Building the self-contained engine bundles CPython, rawpy 0.27.1 / LibRaw 0.22.1, NumPy 2.5.3, SciPy 1.18.1, Pillow 12.3.0, tifffile 2026.9.20, psutil 7.2.2, jsonschema 4.26.0 and its dependencies. Exact versions are in uv.lock. Dependency and bundled numerical-library notices are under licenses and within the engine distribution.

- rawpy: https://github.com/letmaik/rawpy (BSD-3-Clause)
- LibRaw: https://www.libraw.org (LGPL route; library remains dynamically bundled)
- NumPy: https://numpy.org; SciPy: https://scipy.org (BSD and bundled library notices)
- Pillow: https://python-pillow.org; tifffile: https://github.com/cgohlke/tifffile
- psutil: https://github.com/giampaolo/psutil (BSD-3-Clause)
- jsonschema: https://github.com/python-jsonschema/jsonschema (MIT)
- CPython: https://www.python.org (PSF)
- PyInstaller: https://pyinstaller.org (GPL with distribution exception for built applications)
- Qt profile-generation provenance: https://code.qt.io/cgit/qt/qtbase.git/ (unmodified named profiles)

Replace compatible dynamic libraries and rebuild using scripts/build_macos.py to produce a modified local build. No signing identity or Keychain access is needed. The build script applies ad-hoc signing for local use. Public binary distribution needs a separate dependency-license review (including LibRaw/LGPL obligations), Developer ID signing and notarization; this source cleanup does not establish binary release compliance. Public RAW test samples are not included in the application or source archive.
