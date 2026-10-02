"""Catalog-wide import/image sequence numbers across every photo intake path.

Inputs: isolated originals, reviewed Add/Copy plans, folder-sync changes and
counter revisions. Outputs: durable per-photo numbering and collision-safe Copy
names with explicit recovery. Test assets are disposable; no desktop or Adobe
pixel-equivalence claim is made.
"""
import sqlite3
from pathlib import Path

import pytest
from jsonschema import ValidationError

from lumaraw import import_copy_io as copy_io
from lumaraw.import_sequence import MAX_NUMBER, migrate as migrate_sequence
from lumaraw.catalog import Catalog
from legacy_catalog import migrate_to, seed_photo
from test_folder_sync import apply as apply_folder_sync
from test_folder_sync import prepare as prepare_folder_sync
from test_folder_sync import scan as scan_folder_sync
from test_import_review import apply as apply_review
from test_import_review import library, packet, picture, prepare as prepare_import, scan as scan_import


def sequence(service):
    return service.dispatch('get_import_sequence')


def set_sequence(service, next_import, next_image):
    current = sequence(service)
    return service.dispatch('set_import_sequence', {
        'expected_revision': current['revision'],
        'next_import': next_import,
        'next_image': next_image,
    })


def photo_numbers(service, path):
    with service.catalog() as catalog:
        row = catalog.db.execute('SELECT import_number,image_number FROM photos WHERE path=? AND is_virtual=0',
                                 (str(path),)).fetchone()
    assert row is not None
    return row['import_number'], row['image_number']


def tokenized_copy(service, root, paths, *, destination=None, second_copy_destination=None):
    destination = destination or root/'destination'
    destination.mkdir(exist_ok=True)
    options = {'mode':'copy', 'destination':str(destination)}
    if second_copy_destination is not None:
        second_copy_destination.mkdir(exist_ok=True)
        options['second_copy_destination'] = str(second_copy_destination)
    plan = scan_import(service, prepare_import(service, paths, **options))
    naming = service.dispatch('get_import_naming', {'plan_id':plan['id']})
    settings = dict(naming['settings'])
    settings.update({
        'enabled':True,
        'template':[
            {'kind':'import_number','digits':3},
            {'kind':'literal','text':'-'},
            {'kind':'image_number','digits':4},
            {'kind':'literal','text':'-'},
            {'kind':'filename'},
        ],
    })
    service.dispatch('set_import_naming', {
        'plan_id':plan['id'], 'expected_revision':naming['revision'], 'settings':settings,
    })
    return service.dispatch('get_import')['plan'], destination, settings


def apply_counter_copy(service, plan):
    current = service.dispatch('get_import')['plan']
    return service.dispatch('apply_import', {
        'plan_id':plan['id'],
        'expected_revision':current['revision'],
        'expected_sequence_revision':current['sequence']['revision'],
    })['plan']


def test_schema_29_sequence_migration_is_atomic_idempotent_and_does_not_invent_history(tmp_path, monkeypatch):
    from lumaraw import catalog as catalog_module
    with monkeypatch.context() as context:
        context.setattr(catalog_module,'migrate',lambda db:migrate_to(db,29))
        catalog = Catalog(tmp_path/'schema-29')
    old_photo = picture(tmp_path/'existing.jpg')
    photo_id = seed_photo(catalog.db,old_photo)
    with catalog.db:
        plan_id = catalog.db.execute("INSERT INTO import_plans(state,include_subfolders,created) "
                                     "VALUES('ready',1,1)").lastrowid
    catalog.db.set_authorizer(lambda action,a,b,d,t: sqlite3.SQLITE_DENY
                               if action == sqlite3.SQLITE_CREATE_TABLE and a == 'import_sequence_plans'
                               else sqlite3.SQLITE_OK)
    with pytest.raises(sqlite3.DatabaseError):
        migrate_sequence(catalog.db)
    assert catalog.db.execute('PRAGMA user_version').fetchone()[0] == 29
    assert not catalog.db.execute("SELECT 1 FROM sqlite_master WHERE name='import_sequence_state'").fetchone()
    assert 'import_number' not in {row[1] for row in catalog.db.execute('PRAGMA table_info(photos)')}
    catalog.db.set_authorizer(None)

    migrate_sequence(catalog.db)
    migrate_sequence(catalog.db)
    assert catalog.db.execute('PRAGMA user_version').fetchone()[0] == 30
    assert tuple(catalog.db.execute('SELECT revision,next_import,next_image FROM import_sequence_state WHERE id=1').fetchone()) == (0,1,1)
    assert catalog.db.execute('SELECT import_number,image_number FROM photos WHERE id=?',(photo_id,)).fetchone()[:] == (None,None)
    assert catalog.db.execute('SELECT state FROM import_plans WHERE id=?',(plan_id,)).fetchone()[0] == 'ready'
    assert catalog.db.execute('SELECT count(*) FROM import_sequence_plans').fetchone()[0] == 0
    catalog.close()


def test_sequence_settings_use_captured_revision_and_reject_invalid_starts(library):
    service, _ = library
    initial = sequence(service)
    assert (initial['next_import'],initial['next_image']) == (1,1)
    changed = service.dispatch('set_import_sequence', {
        'expected_revision':initial['revision'],'next_import':17,'next_image':900,
    })
    assert (changed['next_import'],changed['next_image']) == (17,900)
    assert changed['revision'] == initial['revision']+1
    with pytest.raises(ValueError, match='changed|revision'):
        service.dispatch('set_import_sequence', {
            'expected_revision':initial['revision'],'next_import':18,'next_image':901,
        })
    with pytest.raises((ValueError,ValidationError)):
        service.dispatch('set_import_sequence', {
            'expected_revision':changed['revision'],'next_import':MAX_NUMBER+1,'next_image':901,
        })
    with pytest.raises((ValueError,ValidationError)):
        service.dispatch('set_import_sequence', {
            'expected_revision':changed['revision'],'next_import':0,'next_image':901,
        })
    assert sequence(service) == changed


def test_add_direct_and_folder_sync_share_sequences_and_noops_or_virtual_copies_do_not_advance(library):
    service, root = library
    album = root/'album'
    first = picture(album/'a.jpg')
    second = picture(album/'b.jpg')
    add = scan_import(service, prepare_import(service, [first,second]))
    assert apply_review(service,add)['imported'] == 2
    assert sequence(service)['next_import'] == 2
    assert sequence(service)['next_image'] == 3
    assert {photo_numbers(service,path) for path in (first,second)} == {(1,1),(1,2)}

    master = service.dispatch('get_photo', {'photo_id':1})
    service.dispatch('create_virtual_copies', {'targets':[{
        'photo_id':master['id'], 'expected_revision':master['revision'],
        'expected_metadata_revision':master['metadata_revision'],
    }]})
    assert (sequence(service)['next_import'],sequence(service)['next_image']) == (2,3)

    direct = picture(album/'direct.jpg')
    assert service.dispatch('import_photos', {'paths':[str(direct)]})['imported'] == 1
    assert photo_numbers(service,direct) == (2,3)
    duplicate = service.dispatch('import_photos', {'paths':[str(direct)]})
    assert duplicate['imported'] == 0
    assert (sequence(service)['next_import'],sequence(service)['next_image']) == (3,4)

    # A reviewed item already in the catalog is a no-op and must not reserve a
    # batch or image number even though it appears in a completed review.
    duplicate_review = scan_import(service, prepare_import(service,[first]))
    assert duplicate_review['selected_count'] == 0
    with pytest.raises(ValueError, match='Check at least one'):
        apply_review(service,duplicate_review)
    service.dispatch('cancel_import', {'plan_id':duplicate_review['id']})
    assert (sequence(service)['next_import'],sequence(service)['next_image']) == (3,4)

    synced = picture(album/'sync.jpg')
    plan = scan_folder_sync(service,prepare_folder_sync(service,metadata=False))
    result = apply_folder_sync(service,plan,read_metadata=False)
    assert result['imported'] == 1
    assert photo_numbers(service,synced) == (3,4)
    assert (sequence(service)['next_import'],sequence(service)['next_image']) == (4,5)


def test_streaming_direct_import_uses_one_batch_number_across_hundred_row_commit(library):
    service, root = library
    paths = [picture(root/'large-batch'/f'{index:03}.jpg') for index in range(101)]
    result = service.dispatch('import_photos', {'paths':[str(path) for path in paths]})
    assert result['imported'] == 101
    assert (sequence(service)['next_import'],sequence(service)['next_image']) == (2,102)
    with service.catalog() as catalog:
        row = catalog.db.execute('SELECT count(*),count(DISTINCT import_number),min(import_number),'
                                 'min(image_number),max(image_number),count(DISTINCT image_number) '
                                 'FROM photos WHERE is_virtual=0').fetchone()
    assert tuple(row) == (101,1,1,1,101,101)


def test_add_sql_failure_rolls_back_number_allocation_with_photo_transaction(library):
    service, root = library
    failing = picture(root/'fail.jpg')
    plan = scan_import(service,prepare_import(service,[failing]))
    before = sequence(service)
    with service.catalog() as catalog:
        catalog.db.execute("CREATE TRIGGER reject_sequence_photo BEFORE INSERT ON photos "
                           "WHEN NEW.name='fail.jpg' BEGIN SELECT RAISE(ABORT,'injected import failure'); END")
    result = apply_review(service,plan)
    assert result['state'] == 'failed'
    assert sequence(service) == before
    assert service.dispatch('status')['photos'] == 0


def test_copy_number_tokens_are_tentative_until_preflight_and_count_only_primary_photos(library):
    service, root = library
    set_sequence(service,40,500)
    source = root/'incoming'
    first = picture(source/'a.jpg')
    second = picture(source/'b.jpg')
    sidecar = first.with_suffix('.xmp')
    sidecar.write_bytes(packet())
    originals = {path:path.read_bytes() for path in (first,second,sidecar)}
    backup = root/'backup'
    plan,destination,settings = tokenized_copy(service,root,[first,second],second_copy_destination=backup)

    before = sequence(service)
    preview = service.dispatch('preview_import_naming', {
        'plan_id':plan['id'],'expected_revision':plan['revision'],
        'settings':settings,'offset':0,
    })
    assert {Path(item['destination']).name for item in preview['items']} == {
        '040-0500-a.jpg','040-0501-b.jpg'}
    assert sequence(service) == before
    assert not list(destination.iterdir()) and not list(backup.iterdir())

    applied = apply_counter_copy(service,plan)
    assert applied['state'] == 'applied' and applied['imported'] == 2
    assert (sequence(service)['next_import'],sequence(service)['next_image']) == (41,502)
    assert (destination/'040-0500-a.jpg').read_bytes() == originals[first]
    assert (destination/'040-0500-a.xmp').read_bytes() == originals[sidecar]
    assert (destination/'040-0501-b.jpg').read_bytes() == originals[second]
    backup_files = {path.name:path.read_bytes() for path in backup.rglob('*') if path.is_file()}
    assert backup_files == {path.name:data for path,data in originals.items()}
    assert photo_numbers(service,destination/'040-0500-a.jpg') == (40,500)
    assert photo_numbers(service,destination/'040-0501-b.jpg') == (40,501)
    assert all(path.read_bytes() == data for path,data in originals.items())
    with service.catalog() as catalog:
        assert catalog.db.execute('SELECT count(*) FROM photos WHERE is_virtual=0').fetchone()[0] == 2


def test_numbered_copy_requires_expected_sequence_revision_and_rejects_stale_review(library):
    service, root = library
    set_sequence(service,7,70)
    source = picture(root/'incoming'/'reviewed.jpg')
    destination = root/'reviewed-destination'
    plan,_,_ = tokenized_copy(service,root,[source],destination=destination)
    captured_revision = plan['sequence']['revision']
    before = sequence(service)

    with pytest.raises(ValueError, match='Import sequence'):
        service.dispatch('apply_import', {
            'plan_id':plan['id'],'expected_revision':plan['revision'],
        })
    assert service.dispatch('get_import')['plan']['state'] == 'ready'
    assert sequence(service) == before
    assert list(destination.iterdir()) == []

    changed = set_sequence(service,8,80)
    with pytest.raises(ValueError, match='Import sequence'):
        service.dispatch('apply_import', {
            'plan_id':plan['id'],'expected_revision':plan['revision'],
            'expected_sequence_revision':captured_revision,
        })
    assert service.dispatch('get_import')['plan']['state'] == 'ready'
    assert sequence(service) == changed
    assert list(destination.iterdir()) == []
    assert service.dispatch('status')['photos'] == 0


def test_plain_copy_uses_latest_provenance_after_preflight_import(library, monkeypatch):
    service, root = library
    source = picture(root/'copy-source'/'copy.jpg')
    direct = picture(root/'interleaved'/'direct.jpg')
    destination = root/'plain-copy-destination'
    destination.mkdir()
    plan = scan_import(service,prepare_import(service,[source],mode='copy',destination=str(destination)))
    original_preflight = copy_io.preflight
    fired = False

    def interleaved_preflight(row, target):
        nonlocal fired
        if not fired:
            fired = True
            assert service.dispatch('import_photos', {'paths':[str(direct)]})['imported'] == 1
        return original_preflight(row,target)

    monkeypatch.setattr(copy_io,'preflight',interleaved_preflight)
    applied = apply_review(service,plan)
    assert fired and applied['state'] == 'applied'
    assert (destination/'copy.jpg').is_file()
    assert photo_numbers(service,direct) == (1,1)
    assert photo_numbers(service,destination/'copy.jpg') == (2,2)
    assert (sequence(service)['next_import'],sequence(service)['next_image']) == (3,3)


def test_copy_collision_consumes_no_numbers_and_counter_race_returns_ready_without_writes(library, monkeypatch):
    service, root = library
    set_sequence(service,7,70)
    first = picture(root/'incoming'/'a.jpg')
    collision_destination = root/'collision-destination'
    plan,destination,_ = tokenized_copy(service,root,[first],destination=collision_destination)
    collision = destination/'007-0070-a.jpg'
    collision.write_bytes(b'keep')
    before = sequence(service)
    result = apply_counter_copy(service,plan)
    assert result['state'] == 'interrupted'
    assert sequence(service) == before
    assert collision.read_bytes() == b'keep'
    assert service.dispatch('status')['photos'] == 0
    service.dispatch('cancel_import', {'plan_id':plan['id']})

    # Repeat with a free target. A direct import can commit during filesystem
    # preflight; the CAS must reject the stale tentative range before writes.
    set_sequence(service,10,90)
    source = picture(root/'incoming2'/'copy.jpg')
    race_source = picture(root/'elsewhere'/'direct.jpg')
    race_destination = root/'race-destination'
    next_plan,destination,_ = tokenized_copy(service,root,[source],destination=race_destination)
    original_preflight = copy_io.preflight
    fired = False

    def interleaved_preflight(row, target):
        nonlocal fired
        if not fired:
            fired = True
            assert service.dispatch('import_photos', {'paths':[str(race_source)]})['imported'] == 1
        return original_preflight(row,target)

    monkeypatch.setattr(copy_io,'preflight',interleaved_preflight)
    before_copy = sequence(service)
    raced = apply_counter_copy(service,next_plan)
    assert fired
    assert raced['state'] == 'ready' and raced['error']
    assert sequence(service) == before_copy | {
        'revision':before_copy['revision']+1,
        'next_import':11,'next_image':91,
    }
    assert list(destination.iterdir()) == []
    refreshed = service.dispatch('get_import')
    assert Path(refreshed['items'][0]['destination']).name == '011-0091-copy.jpg'

    monkeypatch.setattr(copy_io,'preflight',original_preflight)
    applied = apply_counter_copy(service,refreshed['plan'])
    assert applied['state'] == 'applied'
    assert (destination/'011-0091-copy.jpg').is_file()
    assert (sequence(service)['next_import'],sequence(service)['next_image']) == (12,92)


def test_frozen_copy_range_survives_interruption_resume_and_partial_cancel(library, monkeypatch):
    service, root = library
    set_sequence(service,20,100)
    first = picture(root/'incoming'/'a.jpg')
    second = picture(root/'incoming'/'b.jpg')
    recovery_destination = root/'recovery-destination'
    plan,destination,_ = tokenized_copy(service,root,[first,second],destination=recovery_destination)
    original_transfer = copy_io.transfer
    attempts = 0

    def interrupted_before_write(row, target, save, cancelled):
        nonlocal attempts
        attempts += 1
        raise OSError('injected interruption after reservation')

    monkeypatch.setattr(copy_io,'transfer',interrupted_before_write)
    interrupted = apply_counter_copy(service,plan)
    assert interrupted['state'] == 'interrupted'
    assert interrupted['sequence']['frozen']
    assert (interrupted['sequence']['import_number'],interrupted['sequence']['image_number']) == (20,100)
    assert (sequence(service)['next_import'],sequence(service)['next_image']) == (21,102)
    with pytest.raises(ValueError, match='reserved Copy'):
        set_sequence(service,30,200)

    monkeypatch.setattr(copy_io,'transfer',original_transfer)
    recovered = service.dispatch('resume_import_copy', {
        'plan_id':interrupted['id'],'expected_revision':interrupted['revision'],
    })['plan']
    assert recovered['state'] == 'applied'
    assert (destination/'020-0100-a.jpg').is_file()
    assert (destination/'020-0101-b.jpg').is_file()
    assert photo_numbers(service,destination/'020-0100-a.jpg') == (20,100)
    assert photo_numbers(service,destination/'020-0101-b.jpg') == (20,101)
    assert (sequence(service)['next_import'],sequence(service)['next_image']) == (21,102)

    # A later partial transfer retains its full reservation even when explicit
    # cancellation keeps only the already-published primary file.
    third = picture(root/'later'/'c.jpg')
    fourth = picture(root/'later'/'d.jpg')
    partial_destination = root/'partial-destination'
    later,destination2,_ = tokenized_copy(service,root,[third,fourth],destination=partial_destination)
    calls = 0

    def publish_one_then_fail(row, target, save, cancelled):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError('injected partial transfer')
        return original_transfer(row,target,save,cancelled)

    monkeypatch.setattr(copy_io,'transfer',publish_one_then_fail)
    partial = apply_counter_copy(service,later)
    assert partial['state'] == 'interrupted'
    assert (sequence(service)['next_import'],sequence(service)['next_image']) == (22,104)
    published = list(destination2.glob('*.jpg'))
    assert [path.name for path in published] == ['021-0102-c.jpg']
    cancelled = service.dispatch('cancel_import', {'plan_id':partial['id']})['plan']
    assert cancelled['state'] == 'cancelled'
    assert (destination2/'021-0102-c.jpg').is_file()
    assert (sequence(service)['next_import'],sequence(service)['next_image']) == (22,104)


def test_last_supported_number_can_be_used_once_then_imports_require_reset(library):
    service, root = library
    set_sequence(service,MAX_NUMBER,MAX_NUMBER)
    last = picture(root/'last.jpg')
    assert service.dispatch('import_photos', {'paths':[str(last)]})['imported'] == 1
    assert photo_numbers(service,last) == (MAX_NUMBER,MAX_NUMBER)
    assert (sequence(service)['next_import'],sequence(service)['next_image']) == (MAX_NUMBER+1,MAX_NUMBER+1)

    extra = picture(root/'extra.jpg')
    with pytest.raises(ValueError, match='exhausted'):
        service.dispatch('import_photos', {'paths':[str(extra)]})
    assert service.dispatch('status')['photos'] == 1
    assert sequence(service)['next_import'] == MAX_NUMBER+1
    reset = set_sequence(service,1,1)
    assert (reset['next_import'],reset['next_image']) == (1,1)
