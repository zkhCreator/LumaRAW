"""Keyword export policy and frozen descriptive metadata, independent of pixels.

Inputs: one catalog photo and explicit export settings. Outputs: bounded previews
and immutable job snapshots. Policies never alter assignments or source files.
Non-exporting names/synonyms are omitted from hierarchy paths too. This module
does not claim complete EXIF/IPTC/Adobe Develop metadata preservation.
"""
import hashlib
import json

from .keywords import Keywords
from .organization import folded


def migrate(db):
    if db.execute('PRAGMA user_version').fetchone()[0] >= 11:
        return
    with db:
        db.execute('BEGIN IMMEDIATE')
        for name in ('include_export', 'export_containing', 'export_synonyms'):
            db.execute(f'ALTER TABLE keywords ADD COLUMN {name} INTEGER NOT NULL DEFAULT 1 CHECK({name} IN (0,1))')
        # Existing exports retain an empty snapshot; migration never looks up
        # today's metadata to change the meaning of an already-submitted job.
        db.execute("ALTER TABLE jobs ADD COLUMN metadata_snapshot TEXT NOT NULL DEFAULT '{}'")
        db.execute("ALTER TABLE jobs ADD COLUMN export_metadata TEXT NOT NULL DEFAULT '{}'")
        db.execute('PRAGMA user_version=11')


def encode(snapshot):
    return json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def receipt(snapshot):
    if not snapshot:
        return {'mode': 'legacy', 'keyword_count': 0, 'hierarchy_count': 0}
    return {'mode': snapshot['mode'], 'keyword_count': len(snapshot['keywords']),
            'hierarchy_count': len(snapshot['hierarchy']),
            'sha256': hashlib.sha256(encode(snapshot).encode()).hexdigest()}


class KeywordExports:
    def __init__(self, catalog):
        self.catalog = catalog
        self.db = catalog.db

    def project(self, photo_id):
        assigned = [row[0] for row in self.db.execute(
            'SELECT keyword_id FROM keyword_photos WHERE photo_id=? ORDER BY keyword_id', (photo_id,))]
        tags = Keywords(self.catalog)
        names, paths = {}, {}
        cache, aliases = {}, {}

        def ancestry(keyword_id):
            result = []
            while keyword_id is not None:
                if keyword_id not in cache:
                    cache[keyword_id] = tags.get(keyword_id)
                node = cache[keyword_id]
                if len(result) >= 32 or any(item['id'] == keyword_id for item in result):
                    raise ValueError('Keyword hierarchy is too deep or cyclic')
                result.append(node)
                keyword_id = node['parent_id']
            return list(reversed(result))

        for keyword_id in assigned:
            branch = ancestry(keyword_id)
            candidates = []
            for node in reversed(branch):
                candidates.append(node)
                if not node['export_containing']:
                    break
            candidates.reverse()
            exported = [node for node in candidates if node['include_export']]
            for node in exported:
                names.setdefault(folded(node['name']), node['name'])
                if node['export_synonyms']:
                    if node['id'] not in aliases:
                        aliases[node['id']] = [row[0] for row in self.db.execute(
                            'SELECT name FROM keyword_synonyms WHERE keyword_id=? ORDER BY normalized', (node['id'],))]
                    for alias in aliases[node['id']]:
                        names.setdefault(folded(alias), alias)
            if exported:
                path = '|'.join(node['name'] for node in exported)
                paths.setdefault(folded(path), path)
        return [names[key] for key in sorted(names)], [paths[key] for key in sorted(paths)]

    def snapshot(self, photo_id, options):
        row = self.db.execute(
            'SELECT id,title,caption,copyright,rating,flag,color_label,metadata_revision,iptc '
            'FROM photos WHERE id=?', (photo_id,)).fetchone()
        if row is None:
            raise ValueError('Photo does not exist')
        fields, keywords, hierarchy = {}, [], []
        if options.metadata in ('copyright', 'catalog'):
            fields['copyright'] = row['copyright']
            rights={key:value for key,value in json.loads(row['iptc']).items()
                    if key in ('rights_usage_terms','rights_url','copyright_status')}
            if rights:
                fields['iptc']=rights
        if options.metadata == 'catalog':
            fields.update({key: row[key] for key in ('title', 'caption', 'rating', 'flag', 'color_label')})
            if descriptive:=json.loads(row['iptc']):
                fields['iptc']=descriptive
            keywords, paths = self.project(photo_id)
            if options.keyword_hierarchy:
                hierarchy = paths
        snapshot = {'version': 1, 'mode': options.metadata, 'fields': fields,
                    'keywords': keywords, 'hierarchy': hierarchy}
        # Validate representability before a single job is inserted. XML-invalid
        # user text or overlarge metadata must not fail after expensive RAW work.
        from .export_metadata import xmp_packet
        xmp_packet(snapshot)
        return snapshot

    def preview(self, photo_id, kind='keywords', offset=0, metadata='catalog', keyword_hierarchy=True):
        from .model import ExportOptions
        snapshot = self.snapshot(photo_id, ExportOptions(metadata=metadata, keyword_hierarchy=keyword_hierarchy))
        values = snapshot[kind]
        offset = min(offset, max(0, (len(values)-1)//60*60))
        row = self.db.execute('SELECT metadata_revision FROM photos WHERE id=?', (photo_id,)).fetchone()
        return {'photo_id': photo_id, 'metadata_revision': row[0],
                'keyword_revision': Keywords(self.catalog).revision(), 'fields': snapshot['fields'],
                'kind': kind, 'items': values[offset:offset+60], 'offset': offset,
                'total': len(values), 'page_size': 60, 'receipt': receipt(snapshot)}
