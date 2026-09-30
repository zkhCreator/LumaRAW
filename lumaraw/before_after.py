"""Persistent per-photo comparison snapshots, separate from Develop history.

Inputs: revision-checked actions and a catalog-owned transaction. Outputs: a
frozen Before recipe or ordinary undoable After edits. Import/copy triggers seed
the initial snapshot; history clear/branching cannot retarget it. Geometry stays
aligned to After during preview, while copy/swap transfers the complete recipe.
No pixels, original writes, metadata, orientation or global application undo.
"""
import json

from .develop_history import DevelopHistory
from .model import Recipe
from .snapshots import Snapshots


def migrate(db):
    if db.execute('PRAGMA user_version').fetchone()[0] >= 23:
        return
    db.execute('BEGIN IMMEDIATE')
    try:
        db.execute('CREATE TABLE photo_before(photo_id INTEGER PRIMARY KEY,recipe TEXT NOT NULL,label TEXT NOT NULL)')
        db.execute('INSERT INTO photo_before SELECT id,COALESCE(history_base_recipe,recipe),history_base_label FROM photos')
        db.execute("CREATE TRIGGER photo_before_created AFTER INSERT ON photos BEGIN "
                   "INSERT INTO photo_before VALUES(NEW.id,NEW.recipe,CASE WHEN NEW.is_virtual=1 THEN 'Virtual Copy' ELSE 'Import' END); END")
        db.execute('CREATE TRIGGER photo_before_deleted AFTER DELETE ON photos BEGIN DELETE FROM photo_before WHERE photo_id=OLD.id; END')
        db.execute('PRAGMA user_version=23')
        db.commit()
    except BaseException:
        db.rollback()
        raise


class BeforeAfter:
    def __init__(self, db):
        self.db = db

    def read(self, photo_id):
        row = self.db.execute('SELECT recipe,label FROM photo_before WHERE photo_id=?', (photo_id,)).fetchone()
        if row is None:
            raise ValueError('Before state does not exist for this photo')
        return Recipe.parse(json.loads(row['recipe'])), row['label']

    def write(self, photo_id, recipe, label):
        previous, old_label = self.read(photo_id)
        if previous.dict() == recipe.dict() and old_label == label:
            return False
        self.db.execute('UPDATE photo_before SET recipe=?,label=? WHERE photo_id=?', (json.dumps(recipe.dict()), label, photo_id))
        return True

    def apply(self, photo_id, action, step_id=None, version_id=None, expected_version_revision=None):
        """Use the caller's transaction; swap must never publish only one side."""
        if action == 'history_to_before' and step_id is None:
            raise ValueError('Select a history step to copy to Before')
        if action != 'history_to_before' and step_id is not None:
            raise ValueError('A history step is only valid for copying history to Before')
        if action == 'snapshot_to_before':
            if version_id is None or expected_version_revision is None:
                raise ValueError('Copying a snapshot requires its identity and captured revision')
        elif version_id is not None or expected_version_revision is not None:
            raise ValueError('Snapshot identity is only valid for copying a snapshot to Before')
        history = DevelopHistory(self.db)
        row = history.photo(photo_id)
        after = Recipe.parse(json.loads(row['recipe']))
        before, _ = self.read(photo_id)
        changed_before = changed_after = False
        if action == 'history_to_before':
            value = history.value(photo_id, step_id)
            if step_id == 0:
                label = history.baseline(row)['label']
            else:
                label = self.db.execute('SELECT label FROM history WHERE photo_id=? AND id=?', (photo_id, step_id)).fetchone()[0]
            changed_before = self.write(photo_id, value, label)
        elif action == 'snapshot_to_before':
            value,label=Snapshots(self.db).value(photo_id,version_id,expected_version_revision)
            changed_before=self.write(photo_id,value,label)
        elif action == 'after_to_before':
            changed_before = self.write(photo_id, after, 'Copied from After')
        elif action == 'before_to_after':
            changed_after = history.edit(photo_id, before, 'Copy Before to After')
        elif action == 'swap':
            if after.dict() != before.dict():
                changed_before = self.write(photo_id, after, 'Before swap')
                changed_after = history.edit(photo_id, before, 'Swap Before and After')
        else:
            raise ValueError('Unsupported Before/After action')
        # The shared visual revision protects both preview sides and stale forms.
        # Before-only changes do not append Develop steps or truncate redo.
        if changed_before and not changed_after:
            self.db.execute('UPDATE photos SET revision=revision+1 WHERE id=?', (photo_id,))
        return {'changed_before': changed_before, 'changed_after': changed_after}
