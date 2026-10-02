"""Captured Copy naming, indexed ordinals and catalog-local template library.

Inputs: ready-plan revisions, template-library revisions and explicit drafts.
Outputs: bounded previews, immutable per-plan settings and frozen selected ranks.
SQL owns no original writes. Filename order is NOCASE then stable import item ID;
UI sort/page never defines the sequence. Range counts scan disjoint index spans,
not a complete prefix once per visible item. Templates affect only future choices.
"""
import json
import sqlite3
import uuid

from . import filename_templates as names


def migrate(db):
    if db.execute('PRAGMA user_version').fetchone()[0] >= 27:
        return
    db.execute('BEGIN IMMEDIATE')
    try:
        db.execute("ALTER TABLE import_copy_plans ADD COLUMN naming TEXT NOT NULL DEFAULT '{}'")
        db.execute('ALTER TABLE import_files ADD COLUMN naming_index INTEGER NOT NULL DEFAULT 0')
        db.execute('CREATE INDEX import_naming_order ON import_files(plan_id,selected,name COLLATE NOCASE,id,state)')
        db.execute('CREATE TABLE filename_templates(id TEXT PRIMARY KEY,name TEXT NOT NULL,normalized TEXT NOT NULL UNIQUE,template TEXT NOT NULL)')
        db.execute('CREATE INDEX filename_template_names ON filename_templates(normalized,id)')
        db.execute('CREATE TABLE filename_template_state(id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER NOT NULL)')
        db.execute('INSERT INTO filename_template_state VALUES(1,0)')
        db.execute('PRAGMA user_version=27')
        db.commit()
    except BaseException:
        db.rollback()
        raise


def settings(copy):
    return json.loads(copy['naming']) or names.defaults()


def ordinals(db, plan, items):
    """Count each index interval at most once, returning only visible selected IDs."""
    from .import_review import ImportReview
    keys = sorted(((item['name'].translate(str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')),item['id'])
                   for item in items if item['selected'] and item['eligible']))
    result, previous, count = {}, None, 0
    base = 'SELECT count(*) FROM import_files WHERE plan_id=? AND selected=1 AND '+ImportReview.eligible(plan)
    def span(clause,args):
        return db.execute(base+' AND '+clause,(plan['id'],*args)).fetchone()[0]
    for key in keys:
        # SQLite does not turn a collated row-value comparison into a composite
        # index range. Split at filename boundaries so even equal-name imports
        # seek directly into the ID range instead of rescanning their prefix.
        if previous is not None and previous[0] == key[0]:
            count += span('name COLLATE NOCASE=? AND id>? AND id<=?',(key[0],previous[1],key[1]))
        else:
            if previous is None:
                count += span('name COLLATE NOCASE<?',(key[0],))
            else:
                count += span('name COLLATE NOCASE=? AND id>?',previous)
                count += span('name COLLATE NOCASE>? AND name COLLATE NOCASE<?',(previous[0],key[0]))
            count += span('name COLLATE NOCASE=? AND id<=?',key)
        result[key[1]] = count
        previous = key
    return result


def freeze(db, plan, cancelled=lambda:False):
    from .import_review import ImportReview
    # The selection is immutable in verifying/copying states. Ranking is done
    # once before transfer staging; interrupted staging may safely reconstruct it.
    db.set_progress_handler(lambda:int(cancelled()),2000)
    try:
        db.execute('WITH ranks AS (SELECT id,row_number() OVER (ORDER BY name COLLATE NOCASE,id) AS n '
                   'FROM import_files WHERE plan_id=? AND selected=1 AND '+ImportReview.eligible(plan)+') '
                   'UPDATE import_files SET naming_index=r.n FROM ranks r WHERE import_files.id=r.id', (plan['id'],))
    except sqlite3.OperationalError:
        if cancelled():
            raise InterruptedError('Import cancelled')
        raise
    finally:
        db.set_progress_handler(None,0)


class ImportNaming:
    def __init__(self,catalog):
        self.catalog,self.db = catalog,catalog.db

    def get(self,plan_id):
        from .import_copy import settings as copy_settings
        from .import_review import ImportReview
        plan = ImportReview(self.catalog).row(plan_id)
        copy = copy_settings(self.db,plan_id)
        if copy is None:
            raise ValueError('File renaming requires Copy mode; Add preserves originals')
        return {'plan_id':plan_id,'revision':plan['revision'],'state':plan['state'],
                'settings':settings(copy),'order':'filename','builtins':names.builtins(),'tokens':list(names.TOKENS)}

    def set(self,plan_id,expected_revision,settings):
        from .import_review import ImportReview
        names.validate_settings(settings)
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            ImportReview(self.catalog).check(plan_id,expected_revision,('ready',))
            self.get(plan_id)
            self.db.execute('UPDATE import_copy_plans SET naming=? WHERE plan_id=?',(json.dumps(settings),plan_id))
            self.db.execute('UPDATE import_plans SET revision=revision+1 WHERE id=?',(plan_id,))
        return self.get(plan_id)

    def preview(self,plan_id,expected_revision,settings,offset=0):
        from .import_review import ImportReview
        from .import_copy import settings as copy_settings, target
        names.validate_settings(settings)
        plan = ImportReview(self.catalog).check(plan_id,expected_revision,('ready',))
        copy = copy_settings(self.db,plan_id)
        if copy is None:
            raise ValueError('File renaming requires Copy mode; Add preserves originals')
        copy['naming'] = json.dumps(settings)
        items = [dict(row) for row in self.db.execute('SELECT id,path,name,clock,selected FROM import_files '
            'WHERE plan_id=? AND selected=1 AND '+ImportReview.eligible(plan)+
            ' ORDER BY name COLLATE NOCASE,id LIMIT 60 OFFSET ?',(plan_id,offset))]
        for item in items:
            item['clock'] = json.loads(item['clock']); item['eligible'] = True
        ranks = ordinals(self.db,plan,items)
        previews = []
        for item in items:
            result = {'id':item['id'],'source':item['path'],'index':ranks[item['id']]}
            try:result['destination'] = target(copy,item,ranks[item['id']],plan['selected_count'])
            except ValueError as error:result['error'] = str(error)
            previews.append(result)
        return {'items':previews,'total':plan['selected_count'],'offset':offset,'page_size':60,'revision':plan['revision']}

    def library_revision(self):
        return self.db.execute('SELECT revision FROM filename_template_state WHERE id=1').fetchone()[0]

    def check_library(self,expected_revision):
        if expected_revision != self.library_revision():
            raise ValueError('Filename templates changed; refresh before continuing')

    def list(self,offset=0):
        rows = self.db.execute('SELECT id,name FROM filename_templates ORDER BY normalized,id LIMIT 30 OFFSET ?',(offset,))
        return {'items':[dict(r) for r in rows],'total':self.db.execute('SELECT count(*) FROM filename_templates').fetchone()[0],
                'offset':offset,'page_size':30,'revision':self.library_revision(),'storage':'catalog'}

    def read(self,template_id,expected_revision):
        self.check_library(expected_revision)
        row = self.db.execute('SELECT id,name,template FROM filename_templates WHERE id=?',(template_id,)).fetchone()
        if row is None:
            raise ValueError('Filename template no longer exists')
        result = dict(row); result['template'] = json.loads(result['template'])
        return result

    def save(self,name,template,expected_revision,template_id=None):
        from .develop_presets import title
        from .organization import folded
        name = title(name); names.validate(template)
        with self.db:
            self.db.execute('BEGIN IMMEDIATE'); self.check_library(expected_revision)
            if template_id:
                self.read(template_id,expected_revision)
            else:
                template_id = str(uuid.uuid4())
            if self.db.execute('SELECT 1 FROM filename_templates WHERE normalized=? AND id!=?',(folded(name),template_id)).fetchone():
                raise ValueError('A filename template already has that name')
            self.db.execute('INSERT INTO filename_templates VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET '
                            'name=excluded.name,normalized=excluded.normalized,template=excluded.template',
                            (template_id,name,folded(name),json.dumps(template)))
            self.db.execute('UPDATE filename_template_state SET revision=revision+1')
        return {**self.list(),'template_id':template_id}

    def delete(self,template_id,expected_revision):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE'); self.read(template_id,expected_revision)
            self.db.execute('DELETE FROM filename_templates WHERE id=?',(template_id,))
            self.db.execute('UPDATE filename_template_state SET revision=revision+1')
        return self.list()
