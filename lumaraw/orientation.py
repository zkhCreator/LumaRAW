"""Independent catalog orientation and exact orthogonal coordinate transforms.

Inputs: captured photo revisions, explicit rotate/flip actions and bounded tiles.
Outputs: atomic catalog orientation, separate batch undo, and lossless array views.
Orientation is a horizontal mirror followed by 0–3 clockwise quarter turns; it
acts after Develop geometry/masks and after decoder EXIF orientation. Never changes
Develop recipes/history, originals or existing export snapshots. No decoder, NumPy
import, platform UI or file writes. Array helpers preserve dtype and use views.
"""
import json

ACTIONS = ('rotate_left', 'rotate_right', 'flip_horizontal', 'flip_vertical')


def validate(value):
    if type(value) is not int or not 0 <= value <= 7:
        raise ValueError('Photo orientation must be an integer from 0 to 7')
    return value


def compose(value, action):
    validate(value)
    turns, mirror = value % 4, value // 4
    if action == 'rotate_right':
        turns = (turns + 1) % 4
    elif action == 'rotate_left':
        turns = (turns - 1) % 4
    elif action == 'flip_horizontal':
        turns, mirror = (-turns) % 4, 1 - mirror
    elif action == 'flip_vertical':
        turns, mirror = (2 - turns) % 4, 1 - mirror
    else:
        raise ValueError('Choose a supported rotation or flip')
    return turns + 4 * mirror


def apply_array(array, value):
    validate(value)
    if value >= 4:
        array = array[:, ::-1]
    turns = value % 4
    if turns == 1:
        return array[::-1].swapaxes(0, 1)
    if turns == 2:
        return array[::-1, ::-1]
    if turns == 3:
        return array.swapaxes(0, 1)[::-1]
    return array


def inverse_point(x, y, width, height, value):
    """Map oriented pixel edges to canonical pixel edges (also works on unit UV)."""
    validate(value)
    turns = value % 4
    if turns == 1:
        x, y = y, height - x
    elif turns == 2:
        x, y = width - x, height - y
    elif turns == 3:
        x, y = width - y, x
    if value >= 4:
        x = width - x
    return x, y


def inverse_rect(x, y, width, height, full_width, full_height, value):
    corners = [inverse_point(px, py, full_width, full_height, value)
               for px in (x, x + width) for py in (y, y + height)]
    left, top = map(min, zip(*corners))
    right, bottom = map(max, zip(*corners))
    return left, top, right - left, bottom - top


def migrate(db):
    if db.execute('PRAGMA user_version').fetchone()[0] >= 15:
        return
    db.execute('BEGIN IMMEDIATE')
    try:
        db.execute('ALTER TABLE photos ADD COLUMN orientation INTEGER NOT NULL DEFAULT 0 CHECK(orientation BETWEEN 0 AND 7)')
        db.execute('ALTER TABLE jobs ADD COLUMN orientation INTEGER NOT NULL DEFAULT 0 CHECK(orientation BETWEEN 0 AND 7)')
        db.execute('CREATE TABLE orientation_state(id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL)')
        db.execute('INSERT INTO orientation_state VALUES(1,0)')
        db.execute('CREATE TABLE orientation_history(id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL, changes TEXT NOT NULL)')
        db.execute('PRAGMA user_version=15')
        db.commit()
    except BaseException:
        db.rollback()
        raise


class Orientations:
    def __init__(self, catalog):
        self.db = catalog.db

    def state(self):
        latest = self.db.execute('SELECT id,action FROM orientation_history ORDER BY id DESC LIMIT 1').fetchone()
        return {'revision':self.db.execute('SELECT revision FROM orientation_state').fetchone()[0],
                'latest':dict(latest) if latest else None}

    def apply(self, targets, action):
        if not 1 <= len(targets) <= 60 or len({t['photo_id'] for t in targets}) != len(targets):
            raise ValueError('Choose between 1 and 60 distinct photos')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            changes = []
            for target in targets:
                row = self.db.execute('SELECT id,revision,orientation FROM photos WHERE id=?', (target['photo_id'],)).fetchone()
                if row is None:
                    raise ValueError('Photo does not exist')
                if row['revision'] != target['expected_revision']:
                    raise ValueError('Orientation edit conflict; refresh the photos')
                changes.append({'photo_id':row['id'], 'before':row['orientation'], 'after':compose(row['orientation'],action)})
            self.db.executemany('UPDATE photos SET orientation=?,revision=revision+1 WHERE id=?',
                                ((c['after'],c['photo_id']) for c in changes))
            self.db.execute('INSERT INTO orientation_history(action,changes) VALUES(?,?)', (action,json.dumps(changes)))
            self.db.execute('DELETE FROM orientation_history WHERE id NOT IN (SELECT id FROM orientation_history ORDER BY id DESC LIMIT 50)')
            self.db.execute('UPDATE orientation_state SET revision=revision+1')
        return {'updated':[c['photo_id'] for c in changes], **self.state()}

    def undo(self, action_id, expected_revision):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            state = self.state()
            if state['revision'] != expected_revision or state['latest'] is None or state['latest']['id'] != action_id:
                raise ValueError('Orientation history changed; refresh before undoing')
            row = self.db.execute('SELECT changes FROM orientation_history WHERE id=?', (action_id,)).fetchone()
            changes = json.loads(row[0])
            for change in changes:
                photo = self.db.execute('SELECT orientation FROM photos WHERE id=?', (change['photo_id'],)).fetchone()
                if photo is None or photo[0] != change['after']:
                    raise ValueError('Orientation undo conflict; a target is missing or changed')
            self.db.executemany('UPDATE photos SET orientation=?,revision=revision+1 WHERE id=?',
                                ((c['before'],c['photo_id']) for c in changes))
            self.db.execute('DELETE FROM orientation_history WHERE id=?', (action_id,))
            self.db.execute('UPDATE orientation_state SET revision=revision+1')
        return {'updated':[c['photo_id'] for c in changes], **self.state()}
