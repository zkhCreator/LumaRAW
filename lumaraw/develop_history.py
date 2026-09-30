"""Durable per-photo Develop timeline with bounded, payload-free history pages.

Inputs: a catalog-owned SQLite connection and validated recipes/step identities.
Outputs: recipe states, cursor moves and summaries. Callers own transactions and
revision checks. A new edit after an older state replaces only its future branch;
navigation never deletes states. Baselines retain imported/virtual-copy settings.
No pixels, original writes, metadata/orientation undo or global application undo.
"""
import json
import time

from .model import Recipe

PAGE = 60


def migrate(db):
    if db.execute('PRAGMA user_version').fetchone()[0] >= 22:
        return
    db.execute('BEGIN IMMEDIATE')
    try:
        db.execute('ALTER TABLE photos ADD COLUMN history_base_recipe TEXT')
        db.execute("ALTER TABLE photos ADD COLUMN history_base_label TEXT NOT NULL DEFAULT 'Import'")
        db.execute("UPDATE photos SET history_base_label='Virtual Copy' WHERE is_virtual=1")
        db.execute('ALTER TABLE photos ADD COLUMN history_base_created REAL')
        db.execute('ALTER TABLE photos ADD COLUMN history_cursor INTEGER NOT NULL DEFAULT 0')
        # Old rows hold the state BEFORE their named action. Preserve every ID,
        # timestamp and label, shifting recipes to AFTER with a disk-backed SQL
        # staging table. Already discarded legacy states cannot be reconstructed.
        db.execute('UPDATE photos SET history_base_recipe=(SELECT recipe FROM history WHERE photo_id=photos.id ORDER BY id LIMIT 1),'
                   "history_base_label='Initial retained state',history_base_created=(SELECT created FROM history WHERE photo_id=photos.id ORDER BY id LIMIT 1),"
                   'history_cursor=COALESCE((SELECT max(id) FROM history WHERE photo_id=photos.id),0) '
                   'WHERE EXISTS(SELECT 1 FROM history WHERE photo_id=photos.id)')
        db.execute('CREATE TABLE history_migration AS SELECT h.id,COALESCE(lead(h.recipe) OVER '
                   '(PARTITION BY h.photo_id ORDER BY h.id),p.recipe) AS recipe FROM history h JOIN photos p ON p.id=h.photo_id')
        db.execute('CREATE UNIQUE INDEX history_migration_id ON history_migration(id)')
        db.execute('UPDATE history SET recipe=(SELECT recipe FROM history_migration WHERE id=history.id) '
                   'WHERE id IN (SELECT id FROM history_migration)')
        db.execute('DROP TABLE history_migration')
        db.execute('CREATE TABLE history_identity(id INTEGER PRIMARY KEY CHECK(id=1),next_id INTEGER NOT NULL)')
        db.execute('INSERT INTO history_identity SELECT 1,COALESCE(max(id),0)+1 FROM history')
        db.execute('PRAGMA user_version=22')
        db.commit()
    except BaseException:
        db.rollback()
        raise


class DevelopHistory:
    def __init__(self, db):
        self.db = db

    def photo(self, photo_id, recipes=True):
        payload = 'recipe,history_base_recipe,' if recipes else ''
        row = self.db.execute('SELECT id,'+payload+'revision,created,is_virtual,'
                              'history_base_label,history_base_created,history_cursor FROM photos WHERE id=?', (photo_id,)).fetchone()
        if row is None:
            raise ValueError('Photo does not exist')
        return row

    def baseline(self, row):
        return {'id': 0, 'label': row['history_base_label'] or ('Virtual Copy' if row['is_virtual'] else 'Import'),
                'created': row['history_base_created'] if row['history_base_created'] is not None else row['created']}

    def page(self, photo_id, before_id=None):
        row = self.photo(photo_id, recipes=False)
        cursor = row['history_cursor']
        query = 'SELECT id,label,created FROM history WHERE photo_id=?'
        params = [photo_id]
        if before_id is not None:
            query += ' AND id<?'
            params.append(before_id)
        rows = [dict(r) for r in self.db.execute(query+' ORDER BY id DESC LIMIT ?', (*params, PAGE+1))]
        if len(rows) <= PAGE and (before_id is None or before_id > 0):
            rows.append(self.baseline(row))
        more = len(rows) > PAGE
        rows = rows[:PAGE]
        for item in rows:
            item['current'] = item['id'] == cursor
        current = self.db.execute('SELECT label FROM history WHERE photo_id=? AND id=?', (photo_id, cursor)).fetchone()
        redo = self.db.execute('SELECT id FROM history WHERE photo_id=? AND id>? ORDER BY id LIMIT 1', (photo_id, cursor)).fetchone()
        return {'photo_id': photo_id, 'revision': row['revision'], 'cursor': cursor,
                'current_label': current['label'] if current else self.baseline(row)['label'],
                'can_undo': cursor != 0, 'can_redo': redo is not None, 'steps': rows,
                'has_more': more, 'next_before': rows[-1]['id'] if more else None}

    def edit(self, photo_id, recipe, label):
        """Append within an existing transaction; never commit a caller's batch."""
        row = self.photo(photo_id)
        values = recipe.dict()
        # Normalize old recipe versions before comparing so a no-op neither
        # increments revisions nor destroys a retained redo branch.
        if Recipe.parse(json.loads(row['recipe'])).dict() == values:
            return False
        if row['history_base_recipe'] is None:
            self.db.execute('UPDATE photos SET history_base_recipe=? WHERE id=?', (row['recipe'], photo_id))
        self.db.execute('DELETE FROM history WHERE photo_id=? AND id>?', (photo_id, row['history_cursor']))
        data = json.dumps(values)
        step = self.db.execute('UPDATE history_identity SET next_id=next_id+1 WHERE id=1 RETURNING next_id-1').fetchone()[0]
        self.db.execute('INSERT INTO history(id,photo_id,recipe,label,created) VALUES(?,?,?,?,?)',
                        (step, photo_id, data, label, time.time()))
        self.db.execute('UPDATE photos SET recipe=?,revision=revision+1,history_cursor=? WHERE id=?', (data, step, photo_id))
        return True

    def value(self, photo_id, step_id):
        row = self.photo(photo_id)
        if step_id == 0:
            data = row['history_base_recipe'] or row['recipe']
        else:
            step = self.db.execute('SELECT recipe FROM history WHERE photo_id=? AND id=?', (photo_id, step_id)).fetchone()
            if step is None:
                raise ValueError('History step does not exist for this photo')
            data = step['recipe']
        return Recipe.parse(json.loads(data))

    def select(self, photo_id, step_id):
        row = self.photo(photo_id, recipes=False)
        recipe = self.value(photo_id, step_id)
        if row['history_cursor'] != step_id:
            self.db.execute('UPDATE photos SET recipe=?,revision=revision+1,history_cursor=? WHERE id=?',
                            (json.dumps(recipe.dict()), step_id, photo_id))
        return recipe

    def move(self, photo_id, redo=False):
        row = self.photo(photo_id)
        comparison, order = ('>', 'ASC') if redo else ('<', 'DESC')
        step = self.db.execute(f'SELECT id FROM history WHERE photo_id=? AND id{comparison}? ORDER BY id {order} LIMIT 1',
                               (photo_id, row['history_cursor'])).fetchone()
        target = step['id'] if step else (row['history_cursor'] if redo else 0)
        return self.select(photo_id, target)

    def rename(self, photo_id, step_id, name):
        name = name.strip()
        if not name or len(name) > 120 or any(ord(c) < 32 for c in name):
            raise ValueError('History name must be 1–120 characters on one line')
        row = self.photo(photo_id)
        if step_id == 0:
            previous = self.baseline(row)['label']
            if previous == name:
                return
            self.db.execute('UPDATE photos SET history_base_label=? WHERE id=?', (name, photo_id))
        else:
            step = self.db.execute('SELECT label FROM history WHERE photo_id=? AND id=?', (photo_id, step_id)).fetchone()
            if step is None:
                raise ValueError('History step does not exist for this photo')
            if step['label'] == name:
                return
            self.db.execute('UPDATE history SET label=? WHERE photo_id=? AND id=?', (name, photo_id, step_id))
        self.db.execute('UPDATE photos SET revision=revision+1 WHERE id=?', (photo_id,))

    def clear(self, photo_id):
        row = self.photo(photo_id)
        self.db.execute('DELETE FROM history WHERE photo_id=?', (photo_id,))
        self.db.execute("UPDATE photos SET history_base_recipe=?,history_base_label='History cleared',"
                        'history_base_created=?,history_cursor=0,revision=revision+1 WHERE id=?', (row['recipe'], time.time(), photo_id))


def adjustment_label(patch):
    keys = [key for key in patch if key != 'version']
    if len(keys) == 1:
        key = keys[0]
        label = key.replace('_', ' ').title()
        value = patch[key]
        if isinstance(value, bool):
            label += ': On' if value else ': Off'
        elif isinstance(value, (int, float)):
            label += f': {value:g}'
        return label[:120]
    return f'Adjustments ({len(keys)} settings)'
