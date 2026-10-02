"""Date-folder choices for reviewed Copy imports and their saved snapshots.

Inputs: generated EXIF civil clocks, Copy reviews, presets and a genuine schema-30
catalog. Outputs: stable date paths, matching XMP targets and legacy-safe recovery.
File timestamps, host locale and UTC-day conversion are not date-folder inputs.
These fixtures prove catalog and filesystem contracts, not Adobe UI parity.
"""
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
import sqlite3

from PIL import Image
import pytest

from lumaraw import catalog as catalog_module
from lumaraw import import_copy_io as copy_io
from lumaraw.catalog import Catalog
from lumaraw.import_copy_runner import CopyRunner
from lumaraw.service import Service
from legacy_catalog import migrate_to
from test_import_review import apply, library, picture, prepare, scan
from test_xmp_read import packet


def civil_photo(path, *, offset='+00:00'):
    path.parent.mkdir(parents=True,exist_ok=True)
    exif=Image.Exif()
    exif[34665]={36867:'2026:09:28 00:05:00',36881:offset}
    Image.new('RGB',(12,8),'navy').save(path,exif=exif)
    return path


def prepare_copy(service, paths, destination, *, organization='date', date_format='year_date', **options):
    destination.mkdir(parents=True,exist_ok=True)
    return scan(service,prepare(service,paths,mode='copy',destination=str(destination),
                                organization=organization,date_format=date_format,**options))


@pytest.mark.parametrize('date_format,relative',[
    ('year_date',Path('2026/2026-09-28/a.jpg')),
    ('year_month_day',Path('2026/09/28/a.jpg')),
    ('date',Path('2026-09-28/a.jpg')),
])
def test_date_copy_formats_use_captured_civil_day_for_preview_primary_and_xmp(library,date_format,relative):
    service,root=library
    source=civil_photo(root/'source'/'a.jpg',offset='+14:00')
    sidecar=source.with_suffix('.xmp')
    sidecar.write_bytes(packet('<dc:title>Original title</dc:title>'))
    destination=root/'destination'
    plan=prepare_copy(service,[source],destination,date_format=date_format)

    review=service.dispatch('get_import')
    item=review['items'][0]
    expected=destination/relative
    assert review['plan']['copy']['date_format']==date_format
    assert Path(item['destination'])==expected
    assert item['clock']['capture_civil']['year']=='2026'
    assert item['clock']['capture_civil']['month']=='09'
    assert item['clock']['capture_civil']['day']=='28'
    assert datetime.fromtimestamp(item['clock']['taken_us']//1_000_000,timezone.utc).date()==date(2026,9,27)
    assert not list(destination.rglob('*'))

    result=apply(service,plan)
    assert result['state']=='applied'
    receipts=service.dispatch('get_import_copies',{'plan_id':plan['id']})['items']
    targets={Path(row['source']).suffix:Path(row['target']) for row in receipts}
    assert targets['.jpg']==expected and targets['.xmp']==expected.with_suffix('.xmp')
    assert expected.read_bytes()==source.read_bytes()
    assert expected.with_suffix('.xmp').read_bytes()==sidecar.read_bytes()


@pytest.mark.parametrize('date_format',('year_date','year_month_day','date'))
def test_unknown_capture_date_uses_explicit_bucket_not_modification_time(library,date_format):
    service,root=library
    source=picture(root/'no-clock.jpg',clock=False)
    os.utime(source,(0,0))
    destination=root/'destination'
    plan=prepare_copy(service,[source],destination,date_format=date_format)
    item=service.dispatch('get_import')['items'][0]
    expected=destination/'Unknown Date'/'no-clock.jpg'
    assert Path(item['destination'])==expected
    assert item['clock'].get('capture_date') is None
    assert apply(service,plan)['state']=='applied'
    assert expected.is_file()


@pytest.mark.parametrize('organization,relative',[
    ('flat',Path('Album/a.jpg')),
    ('source',Path('Album/source/child/a.jpg')),
])
def test_non_date_organizations_keep_the_selected_format_but_ignore_it_for_paths(library,organization,relative):
    service,root=library
    source_root=root/'source'
    source=picture(source_root/'child'/'a.jpg')
    destination=root/'destination'
    plan=prepare_copy(service,[source_root],destination,organization=organization,
                      date_format='year_month_day',subfolder='Album')
    item=service.dispatch('get_import')['items'][0]
    expected=destination/relative
    assert service.dispatch('get_import')['plan']['copy']['date_format']=='year_month_day'
    assert Path(item['destination'])==expected
    assert apply(service,plan)['state']=='applied'
    assert expected.is_file()


def test_date_collision_preflight_preserves_existing_file_and_writes_no_other_target(library):
    service,root=library
    first=picture(root/'first'/'a.jpg')
    second=picture(root/'second'/'b.jpg')
    destination=root/'destination'
    plan=prepare_copy(service,[first,second],destination,date_format='year_month_day',skip_duplicates=False)
    collision=destination/'2026'/'09'/'28'/'a.jpg'
    collision.parent.mkdir(parents=True)
    collision.write_bytes(b'keep existing bytes')

    result=apply(service,plan)
    assert result['state']=='interrupted'
    assert collision.read_bytes()==b'keep existing bytes'
    assert [path for path in destination.rglob('*') if path.is_file()]==[collision]
    assert service.dispatch('status')['photos']==0


def test_import_preset_round_trip_legacy_default_and_explicit_date_format_override(library):
    service,root=library
    original=picture(root/'preset-source'/'original.jpg')
    original_plan=prepare_copy(service,[original],root/'original-destination',date_format='year_month_day')
    preset_list=service.dispatch('list_import_presets')
    saved=service.dispatch('save_import_preset',{
        'name':'Trip dates','plan_id':original_plan['id'],
        'expected_plan_revision':original_plan['revision'],'expected_revision':preset_list['revision'],
    })
    reference={'preset_id':saved['preset_id'],'expected_revision':saved['revision']}
    options=service.dispatch('get_import_preset',reference)['options']
    assert options['date_format']=='year_month_day'
    service.dispatch('cancel_import',{'plan_id':original_plan['id']})

    saved_source=picture(root/'saved-use'/'saved.jpg')
    saved_destination=root/'saved-destination'
    saved_destination.mkdir()
    saved_plan=scan(service,prepare(service,[saved_source],preset=reference,destination=str(saved_destination)))
    saved_review=service.dispatch('get_import')
    assert saved_review['plan']['copy']['date_format']=='year_month_day'
    assert Path(saved_review['items'][0]['destination'])==saved_destination/'2026'/'09'/'28'/'saved.jpg'
    assert apply(service,saved_plan)['state']=='applied'

    # Emulate a preset written before date_format existed, without lowering the
    # catalog schema or modifying any captured source/transfer identity.
    with service.catalog() as catalog,catalog.db:
        raw=catalog.db.execute('SELECT value FROM import_presets WHERE id=?',(saved['preset_id'],)).fetchone()[0]
        value=json.loads(raw)
        value['options'].pop('date_format')
        catalog.db.execute('UPDATE import_presets SET value=? WHERE id=?',(json.dumps(value),saved['preset_id']))
    assert service.dispatch('get_import_preset',reference)['options']['date_format']=='year_date'

    legacy_source=picture(root/'legacy-use'/'legacy.jpg')
    legacy_destination=root/'legacy-destination'
    legacy_destination.mkdir()
    legacy_plan=scan(service,prepare(service,[legacy_source],preset=reference,destination=str(legacy_destination)))
    legacy_review=service.dispatch('get_import')
    assert legacy_review['plan']['copy']['date_format']=='year_date'
    assert Path(legacy_review['items'][0]['destination'])==legacy_destination/'2026'/'2026-09-28'/'legacy.jpg'
    assert apply(service,legacy_plan)['state']=='applied'

    override_source=picture(root/'override-use'/'override.jpg')
    override_destination=root/'override-destination'
    override_destination.mkdir()
    override_plan=scan(service,prepare(service,[override_source],preset=reference,
                                      destination=str(override_destination),date_format='date'))
    override_review=service.dispatch('get_import')
    assert override_review['plan']['copy']['date_format']=='date'
    assert Path(override_review['items'][0]['destination'])==override_destination/'2026-09-28'/'override.jpg'
    assert apply(service,override_plan)['state']=='applied'


def test_schema_30_upgrade_defaults_existing_copy_and_preserves_old_journal_path(tmp_path,monkeypatch):
    with monkeypatch.context() as context:
        context.setattr(catalog_module,'migrate',lambda db:migrate_to(db,30))
        catalog=Catalog(tmp_path/'schema-30')
    source=picture(tmp_path/'old.jpg')
    destination=tmp_path/'old-destination'
    old_target=destination/'2026'/'2026-09-28'/'old.jpg'
    with catalog.db:
        plan_id=catalog.db.execute("INSERT INTO import_plans(state,phase,include_subfolders,created) "
                                   "VALUES('interrupted','copying',1,1)").lastrowid
        catalog.db.execute('INSERT INTO import_copy_plans(plan_id,destination,destination_identity,organization,'
                           'subfolder,roots,owner) VALUES(?,?,?,?,?,?,?)',
                           (plan_id,str(destination),'[1,2]','date','','[]',str(catalog.root)))
        catalog.db.execute('INSERT INTO import_transfers(plan_id,source,target,target_key,source_identity,temporary) '
                           'VALUES(?,?,?,?,?,?)',
                           (plan_id,str(source),str(old_target),str(old_target).casefold(),'[]','.owned.part'))

    catalog.db.set_authorizer(lambda action,a,b,d,t:
                              sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_ALTER_TABLE else sqlite3.SQLITE_OK)
    with pytest.raises(sqlite3.DatabaseError):
        catalog_module.migrate(catalog.db)
    assert catalog.db.execute('PRAGMA user_version').fetchone()[0]==30
    assert 'date_format' not in {row[1] for row in catalog.db.execute('PRAGMA table_info(import_copy_plans)')}
    catalog.db.set_authorizer(None)

    catalog_module.migrate(catalog.db)
    catalog_module.migrate(catalog.db)
    assert catalog.db.execute('PRAGMA user_version').fetchone()[0]==31
    assert catalog.db.execute('SELECT date_format FROM import_copy_plans WHERE plan_id=?',(plan_id,)).fetchone()[0]=='year_date'
    assert catalog.db.execute('SELECT target FROM import_transfers WHERE plan_id=?',(plan_id,)).fetchone()[0]==str(old_target)
    assert catalog.db.execute('SELECT state,phase FROM import_plans WHERE id=?',(plan_id,)).fetchone()[:]==('interrupted','copying')
    revision=catalog.db.execute('SELECT revision FROM import_plans WHERE id=?',(plan_id,)).fetchone()[0]
    catalog.close()

    service=Service(tmp_path/'schema-30',presets_root=tmp_path/'presets')
    try:
        resumed=CopyRunner(service).resume(plan_id,revision)
        receipt=service.dispatch('get_import_copies',{'plan_id':plan_id})['items'][0]
        assert resumed['state']=='verifying'
        assert Path(receipt['target'])==old_target
    finally:
        service.close()


def test_default_date_copy_resume_keeps_the_previously_published_journal_path(library,monkeypatch):
    service,root=library
    source=picture(root/'resume-source'/'a.jpg')
    destination=root/'destination'
    plan=prepare_copy(service,[source],destination,date_format='year_date')
    old_target=destination/'2026'/'2026-09-28'/'a.jpg'
    original_transfer=copy_io.transfer

    def publish_then_interrupt(row,value,save,cancelled):
        original_transfer(row,value,save,cancelled)
        raise OSError('injected interruption after publication')

    monkeypatch.setattr(copy_io,'transfer',publish_then_interrupt)
    interrupted=apply(service,plan)
    assert interrupted['state']=='interrupted'
    receipt=service.dispatch('get_import_copies',{'plan_id':plan['id']})['items'][0]
    assert Path(receipt['target'])==old_target and old_target.is_file()

    monkeypatch.setattr(copy_io,'transfer',original_transfer)
    resumed=service.dispatch('resume_import_copy',{
        'plan_id':plan['id'],'expected_revision':interrupted['revision'],
    })['plan']
    assert resumed['state']=='applied'
    final_receipt=service.dispatch('get_import_copies',{'plan_id':plan['id']})['items'][0]
    assert Path(final_receipt['target'])==old_target
    assert old_target.read_bytes()==source.read_bytes()
