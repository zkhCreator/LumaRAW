"""Catalog import/image numbering with tentative previews and durable Copy ranges.

Inputs: explicit starting values, catalog revisions and successful import scopes.
Outputs: monotonic allocations and per-plan values for the pure filename renderer.
Callers own import transactions. Copy reserves only after complete preflight, before
filesystem writes; reservations survive crashes/cancellation and are never reclaimed.
Add/sync/direct imports count new originals only. No source writes, pixel work,
historic-number inference or live counter values inside saved presets/templates.
"""

MAX_NUMBER = 9999999999


class SequenceChanged(ValueError):
    pass


def migrate(db):
    if db.execute('PRAGMA user_version').fetchone()[0] >= 30:
        return
    db.execute('BEGIN IMMEDIATE')
    try:
        db.execute('CREATE TABLE import_sequence_state(id INTEGER PRIMARY KEY CHECK(id=1), '
                   'revision INTEGER NOT NULL,next_import INTEGER NOT NULL,next_image INTEGER NOT NULL)')
        db.execute('INSERT INTO import_sequence_state VALUES(1,0,1,1)')
        db.execute('CREATE TABLE import_sequence_plans(plan_id INTEGER PRIMARY KEY,revision INTEGER NOT NULL,'
                   'import_number INTEGER NOT NULL,image_number INTEGER NOT NULL,image_count INTEGER NOT NULL,'
                   'frozen INTEGER NOT NULL DEFAULT 0)')
        db.execute('CREATE TRIGGER import_sequence_delete AFTER DELETE ON import_plans BEGIN '
                   'DELETE FROM import_sequence_plans WHERE plan_id=OLD.id; END')
        db.execute('ALTER TABLE photos ADD COLUMN import_number INTEGER')
        db.execute('ALTER TABLE photos ADD COLUMN image_number INTEGER')
        db.execute('PRAGMA user_version=30')
        db.commit()
    except BaseException:
        db.rollback()
        raise


def state(db):
    return dict(db.execute('SELECT revision,next_import,next_image FROM import_sequence_state WHERE id=1').fetchone())


def set_state(catalog, expected_revision, next_import, next_image):
    if any(type(value) is not int or not 1 <= value <= MAX_NUMBER for value in (next_import,next_image)):
        raise ValueError('Import sequence starts must be integers from 1 to 9999999999')
    db = catalog.db
    with db:
        db.execute('BEGIN IMMEDIATE')
        if state(db)['revision'] != expected_revision:
            raise SequenceChanged('Import sequence numbers changed; reload before saving')
        if db.execute("SELECT 1 FROM import_sequence_plans s JOIN import_plans p ON p.id=s.plan_id "
                      "WHERE s.frozen=1 AND p.state IN ('verifying','interrupted') LIMIT 1").fetchone():
            raise ValueError('Finish or cancel the reserved Copy import before changing sequence starts')
        db.execute('UPDATE import_sequence_state SET next_import=?,next_image=?,revision=revision+1 WHERE id=1',
                   (next_import,next_image))
    return state(db)


def uses_numbers(copy):
    if not copy:
        return False
    from .import_naming import settings
    naming = settings(copy)
    return naming['enabled'] and any(part['kind'] in ('import_number','image_number') for part in naming['template'])


def for_plan(db, plan_id):
    row = db.execute('SELECT revision,import_number,image_number,image_count,frozen FROM import_sequence_plans WHERE plan_id=?',
                     (plan_id,)).fetchone()
    if row:
        result = dict(row)
        result['frozen'] = bool(result['frozen'])
        return result
    value = state(db)
    return {'revision':value['revision'],'import_number':value['next_import'],
            'image_number':value['next_image'],'frozen':False}


def capture(db, plan, copy, expected_revision=None):
    # Add reserves only inside its final transaction. An interrupted Add may
    # return to scanning/review before applying again, without a tentative row.
    if not copy:
        return
    value = state(db)
    if uses_numbers(copy) and expected_revision != value['revision']:
        raise SequenceChanged('Import sequence numbers changed; refresh the review and inspect filenames before importing')
    db.execute('INSERT INTO import_sequence_plans VALUES(?,?,?,?,?,0)',
               (plan['id'],value['revision'],value['next_import'],value['next_image'],plan['selected_count']))


def allocate(db, count, import_number=None):
    """Advance inside the caller's transaction; streaming batches reuse their import number."""
    if count <= 0:
        return None
    value = state(db)
    number = value['next_import'] if import_number is None else import_number
    if number > MAX_NUMBER or value['next_image']+count-1 > MAX_NUMBER:
        raise ValueError('Import sequence exhausted; set new starting numbers before importing')
    db.execute('UPDATE import_sequence_state SET next_import=next_import+?,next_image=next_image+?,revision=revision+1 WHERE id=1',
               (int(import_number is None),count))
    return {'import_number':number,'image_number':value['next_image'],'image_count':count}


def reserve_copy(db, plan, copy):
    row = for_plan(db,plan['id'])
    if row['frozen']:
        return row
    value = state(db)
    if uses_numbers(copy) and value['revision'] != row['revision']:
        raise SequenceChanged('Import sequence numbers changed during verification. Review the refreshed filenames and import again.')
    allocation = allocate(db,plan['selected_count'])
    db.execute('INSERT INTO import_sequence_plans VALUES(?,?,?,?,?,1) ON CONFLICT(plan_id) DO UPDATE SET '
               'revision=excluded.revision,import_number=excluded.import_number,image_number=excluded.image_number,'
               'image_count=excluded.image_count,frozen=1',
               (plan['id'],value['revision'],allocation['import_number'],allocation['image_number'],allocation['image_count']))
    return allocation


def commit_plan(db, plan, count, copy):
    if copy:
        value = for_plan(db,plan['id'])
        if not value['frozen'] or value.get('image_count') != count:
            raise ValueError('Copy import sequence reservation is incomplete')
        return value
    value = allocate(db,count)
    db.execute('INSERT INTO import_sequence_plans VALUES(?,?,?,?,?,1) ON CONFLICT(plan_id) DO UPDATE SET '
               'revision=excluded.revision,import_number=excluded.import_number,image_number=excluded.image_number,'
               'image_count=excluded.image_count,frozen=1',
               (plan['id'],state(db)['revision'],value['import_number'],value['image_number'],count))
    return value
