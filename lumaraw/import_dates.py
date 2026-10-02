"""Captured civil-date folder layouts for reviewed Copy imports.

Inputs: an explicit format ID and scanned original EXIF civil date fields.
Outputs: a safe relative date folder and an additive catalog option migration.
No filesystem I/O, locale dependence, UTC conversion or modification-time fallback.
Legacy plans default to their original year/date layout; transfer journals remain
immutable. Month names and Adobe's complete localized format menu are out of scope.
"""
from datetime import date
import re


DEFAULT = 'year_date'
FORMATS = ('year_date', 'year_month_day', 'date')


def validate(value):
    if value not in FORMATS:
        raise ValueError('Unsupported import date folder format')
    return value


def folder(clock, date_format=DEFAULT):
    """Render captured camera time; malformed/unknown clocks use an explicit bucket."""
    validate(date_format)
    if not isinstance(clock, dict):
        return 'Unknown Date'
    civil = clock.get('capture_civil', {})
    if civil:
        if not isinstance(civil, dict):
            return 'Unknown Date'
        parts = [civil.get(key, '') for key in ('year', 'month', 'day')]
    else:
        # Pre-template plans retained only this original civil-date representation.
        previous = clock.get('capture_date', '')
        match = re.fullmatch(r'([0-9]{4})/\1-([0-9]{2})-([0-9]{2})', previous) if isinstance(previous,str) else None
        parts = list(match.groups()) if match else []
    try:
        if len(parts) != 3 or any(not isinstance(p, str) or not re.fullmatch(r'[0-9]{1,4}', p) for p in parts):
            return 'Unknown Date'
        captured = date(*map(int, parts))
    except (ValueError, OverflowError):
        return 'Unknown Date'
    year, month, day = f'{captured.year:04}', f'{captured.month:02}', f'{captured.day:02}'
    if date_format == 'year_month_day':
        return f'{year}/{month}/{day}'
    numeric = f'{year}-{month}-{day}'
    return f'{year}/{numeric}' if date_format == 'year_date' else numeric


def migrate(db):
    if db.execute('PRAGMA user_version').fetchone()[0] >= 31:
        return
    db.execute('BEGIN IMMEDIATE')
    try:
        db.execute("ALTER TABLE import_copy_plans ADD COLUMN date_format TEXT NOT NULL DEFAULT 'year_date'")
        db.execute('PRAGMA user_version=31')
        db.commit()
    except BaseException:
        db.rollback()
        raise
