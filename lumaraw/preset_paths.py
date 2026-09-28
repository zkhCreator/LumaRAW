"""Replaceable platform adapter for shared, user-owned preset storage.

Input: an explicit root override or host conventions. Output: a directory path;
no directory is created here. Domain preset code does not know Mac/Windows/XDG
locations. Tests and embedders inject a root instead of touching user preferences.
"""
import os
from pathlib import Path
import sys


def preset_root():
    if override := os.environ.get('LUMARAW_PRESETS_ROOT'):
        return Path(override).expanduser().resolve()
    if sys.platform == 'darwin':
        return Path.home() / 'Library/Application Support/LumaRAW/Presets'
    if sys.platform == 'win32':
        return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'LumaRAW/Presets'
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'lumaraw/presets'
