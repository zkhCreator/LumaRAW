"""Stream keyword dictionaries between catalog state and explicit UTF-8 files.

Inputs: a selected text/CSV file or new export destination and vocabulary revision.
Outputs: atomic additive imports or collision-safe dictionary files. A disk-backed
staging table validates the complete input before catalog writes. Existing tag
identities, synonyms, policies, assignments and photo revisions are preserved.
No pixels, original writes, bulk rename/delete or AI/person recognition. CSV
retains the manual person flag; text can represent only the exclusion flag.
"""
from contextlib import contextmanager
import csv
import hashlib
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import tempfile

from .keywords import Keywords, valid_name
from .organization import folded

MAX_BYTES = 64 * 1024 * 1024
MAX_TAGS = 1_000_000
POLICIES = ('include_export', 'export_containing', 'export_synonyms', 'is_person')
CSV_HEADER = ('Include On Export', 'Export Containing Keywords', 'Export Synonyms', 'Person Type Keyword', '')


def migrate(db):
    if db.execute('PRAGMA user_version').fetchone()[0] >= 12:
        return
    with db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('ALTER TABLE keywords ADD COLUMN is_person INTEGER NOT NULL DEFAULT 0 CHECK(is_person IN (0,1))')
        db.execute('PRAGMA user_version=12')


def identity(value):
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns


def copy_input(source, destination):
    source = Path(source).resolve(strict=True)
    digest = hashlib.sha256()
    descriptor = os.open(source, os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0))
    with os.fdopen(descriptor, 'rb') as stream, destination.open('xb') as output:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_BYTES:
            raise ValueError('Choose a regular keyword file no larger than 64 MiB')
        size = 0
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_BYTES:
                raise ValueError('Keyword file exceeds 64 MiB')
            digest.update(chunk); output.write(chunk)
        if identity(before) != identity(os.fstat(stream.fileno())) or identity(before) != identity(source.stat()):
            raise ValueError('Keyword file changed while reading; select it again')
    return digest.hexdigest(), size


class Document:
    def __init__(self, root):
        self.db = sqlite3.connect(root / 'staging.sqlite')
        self.db.row_factory = sqlite3.Row
        self.db.executescript('PRAGMA journal_mode=OFF; PRAGMA cache_size=-4096; '
            'CREATE TABLE tags(id INTEGER PRIMARY KEY,parent_id INTEGER,name TEXT,normalized TEXT,'
            'include_export INTEGER,export_containing INTEGER,export_synonyms INTEGER,is_person INTEGER,target_id INTEGER);'
            'CREATE UNIQUE INDEX sibling ON tags(COALESCE(parent_id,0),normalized);'
            'CREATE TABLE aliases(tag_id INTEGER,name TEXT,normalized TEXT,PRIMARY KEY(tag_id,normalized));')
        self.format = 'text'
        self.count = 0
        self.synonym_count = 0

    def parse(self, path):
        stack = []
        first_content = True
        with path.open('r', encoding='utf-8-sig', newline=None) as stream, self.db:
            line_number = 0
            while line := stream.readline(8193):
                line_number += 1
                if len(line) > 8192:
                    raise ValueError(f'Keyword line {line_number} is too long')
                line = line.rstrip('\r\n')
                if not line.strip():
                    continue
                try:
                    if first_content and line.startswith(CSV_HEADER[0]+','):
                        if tuple(next(csv.reader([line], strict=True))) != CSV_HEADER:
                            raise ValueError('Unsupported keyword CSV header')
                        self.format = 'csv'
                        first_content = False
                        continue
                    first_content = False
                    flags = (1, 1, 1, 0)
                    if self.format == 'csv':
                        fields = next(csv.reader([line], strict=True))
                        if len(fields) != 5:
                            raise ValueError('Keyword CSV requires four option columns and one tab-indented name')
                        raw = fields[4]
                        if any(value not in ('Y', 'N', '') for value in fields[:4]):
                            raise ValueError('Keyword CSV options must be Y or N')
                        flags = tuple(int(value == 'Y') for value in fields[:4])
                    else:
                        raw = line
                    depth = len(raw) - len(raw.lstrip('\t'))
                    word = raw[depth:].strip()
                    synonym = word.startswith('{') and word.endswith('}')
                    if synonym:
                        if depth == 0 or depth > len(stack):
                            raise ValueError('Synonym must be nested beneath a keyword')
                        word = valid_name(word[1:-1])
                        tag_id = stack[depth-1]
                        self.db.execute('INSERT OR IGNORE INTO aliases VALUES(?,?,?)', (tag_id, word, folded(word)))
                        if self.db.execute('SELECT COUNT(*) FROM aliases WHERE tag_id=?', (tag_id,)).fetchone()[0] > 30:
                            raise ValueError('A keyword cannot have more than 30 synonyms')
                        stack = stack[:depth]
                        continue
                    if depth > len(stack) or depth >= 32:
                        raise ValueError('Keyword indentation skips a parent or exceeds 32 levels')
                    if self.format == 'text' and word.startswith('[') and word.endswith(']'):
                        word = word[1:-1]; flags = (0, 1, 1, 0)
                    if self.format == 'csv' and any(value == '' for value in fields[:4]):
                        raise ValueError('Keyword CSV requires all four options for each keyword')
                    word = valid_name(word)
                    parent = stack[depth-1] if depth else None
                    existing = self.db.execute('SELECT * FROM tags WHERE COALESCE(parent_id,0)=? AND normalized=?', (parent or 0, folded(word))).fetchone()
                    if existing:
                        if tuple(existing[key] for key in POLICIES) != flags:
                            raise ValueError('Duplicate keyword has conflicting options')
                        tag_id = existing['id']
                    else:
                        self.count += 1
                        if self.count > MAX_TAGS:
                            raise ValueError('Keyword file exceeds one million tags')
                        tag_id = self.db.execute('INSERT INTO tags(parent_id,name,normalized,include_export,export_containing,export_synonyms,is_person) '
                            'VALUES(?,?,?,?,?,?,?)', (parent, word, folded(word), *flags)).lastrowid
                    stack = [*stack[:depth], tag_id]
                except (ValueError, csv.Error) as error:
                    raise ValueError(f'Keyword line {line_number}: {error}') from error
        self.synonym_count = self.db.execute('SELECT COUNT(*) FROM aliases').fetchone()[0]

    def apply(self, catalog, expected_revision):
        db = catalog.db
        created = existing = 0
        with db, self.db:
            db.execute('BEGIN IMMEDIATE')
            Keywords(catalog).check_revision(expected_revision)
            for row in self.db.execute('SELECT * FROM tags ORDER BY id'):
                parent = self.db.execute('SELECT target_id FROM tags WHERE id=?', (row['parent_id'],)).fetchone() if row['parent_id'] else None
                parent_id = parent[0] if parent else None
                match = db.execute('SELECT id FROM keywords WHERE parent_id IS ? AND normalized=?', (parent_id, row['normalized'])).fetchone()
                if match:
                    target = match[0]; existing += 1
                else:
                    target = db.execute('INSERT INTO keywords(parent_id,name,normalized,include_export,export_containing,export_synonyms,is_person) '
                        'VALUES(?,?,?,?,?,?,?)', (parent_id, row['name'], row['normalized'], *(row[key] for key in POLICIES))).lastrowid
                    db.executemany('INSERT INTO keyword_synonyms VALUES(?,?,?)',
                        ((target, alias['normalized'], alias['name']) for alias in self.db.execute('SELECT * FROM aliases WHERE tag_id=?', (row['id'],))))
                    created += 1
                self.db.execute('UPDATE tags SET target_id=? WHERE id=?', (target, row['id']))
            if created:
                db.execute('UPDATE keyword_state SET revision=revision+1')
        return {'created':created, 'existing':existing, 'keywords':self.count,
                'input_synonyms':self.synonym_count, 'format':self.format,
                'keyword_revision':Keywords(catalog).revision()}


@contextmanager
def read_document(path):
    with tempfile.TemporaryDirectory(prefix='lumaraw-keywords-') as folder:
        root = Path(folder)
        digest, size = copy_input(path, root/'input')
        document = Document(root)
        try:
            try:
                document.parse(root/'input')
            except UnicodeError as error:
                raise ValueError('Keyword files must use UTF-8 encoding') from error
            yield document, digest, size
        finally:
            document.db.close()


def import_file(service, path, expected_revision):
    with read_document(path) as (document, digest, size):
        with service.catalog() as catalog:
            result = document.apply(catalog, expected_revision)
        return {**result, 'sha256':digest, 'bytes':size}


def write_dictionary(catalog, output, format, expected_revision):
    tags = Keywords(catalog)
    tags.check_revision(expected_revision)
    writer = csv.writer(output, lineterminator='\n') if format == 'csv' else None
    if writer:
        writer.writerow(CSV_HEADER)
    count = synonyms = omitted_options = 0

    def walk(parent=None, depth=0):
        nonlocal count, synonyms, omitted_options
        if depth >= 32:
            raise ValueError('Keyword hierarchy exceeds 32 levels')
        for row in catalog.db.execute('SELECT k.*,EXISTS(SELECT 1 FROM keywords c WHERE c.parent_id=k.id) AS children '
                'FROM keywords k WHERE parent_id IS ? ORDER BY normalized,id', (parent,)):
            name = row['name']
            if valid_name(name) != name or (name.startswith('{') and name.endswith('}')) or (
                    format == 'text' and name.startswith('[') and name.endswith(']')):
                raise ValueError(f'Keyword {row["id"]} cannot be represented without changing its name')
            value = '\t'*depth + (f'[{name}]' if format == 'text' and not row['include_export'] else name)
            if writer:
                writer.writerow([*('Y' if row[key] else 'N' for key in POLICIES), value])
            else:
                output.write(value+'\n')
                omitted_options += int(not row['export_containing'] or not row['export_synonyms'] or row['is_person'])
            count += 1
            for alias in tags.synonyms(row['id']):
                if valid_name(alias) != alias:
                    raise ValueError(f'Keyword {row["id"]} has an unrepresentable synonym')
                value = '\t'*(depth+1)+'{'+alias+'}'
                if writer:
                    writer.writerow(['', '', '', '', value])
                else:
                    output.write(value+'\n')
                synonyms += 1
            if row['children']:
                walk(row['id'], depth+1)
    walk()
    if count != catalog.db.execute('SELECT COUNT(*) FROM keywords').fetchone()[0]:
        raise ValueError('Keyword hierarchy contains unreachable or cyclic entries')
    return {'keywords':count, 'synonyms':synonyms, 'omitted_options':omitted_options,
            'format':format, 'keyword_revision':expected_revision}


def export_file(service, path, format, expected_revision):
    destination = Path(path).absolute()
    if destination.suffix.lower() != ('.csv' if format == 'csv' else '.txt'):
        raise ValueError('Choose a .csv or .txt filename matching the export format')
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('Keyword export already exists; choose a new filename')
    with tempfile.TemporaryFile(mode='w+', encoding='utf-8', newline='') as snapshot:
        with service.catalog() as catalog:
            result = write_dictionary(catalog, snapshot, format, expected_revision)
        snapshot.flush(); snapshot.seek(0)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='', prefix='.lumaraw-keywords-', dir=destination.parent, delete=False) as output:
                temporary = Path(output.name)
                shutil.copyfileobj(snapshot, output, length=64*1024)
                output.flush(); os.fsync(output.fileno())
            os.link(temporary, destination)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return {**result, 'path':str(destination), 'bytes':destination.stat().st_size}
