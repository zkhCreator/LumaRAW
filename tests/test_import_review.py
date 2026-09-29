"""Reviewed Add import behavior using isolated originals and durable plans.

Tests verify selection/duplicate semantics, source snapshots, original safety,
atomic metadata import, cancellation/recovery, migrations and bounded service work.
Generated EXIF examples establish exact contracts, not every camera or Adobe UI.
"""
import json
from pathlib import Path
import shutil
import sqlite3
import threading

from PIL import Image
import pytest

from lumaraw.catalog import Catalog
from lumaraw.import_review import ImportReview
from lumaraw.runtime import CATALOG_VERSION
from lumaraw.service import Service
from test_folder_sync import counts
from test_xmp_read import packet


def picture(path,clock=True,color='navy'):
    path.parent.mkdir(parents=True,exist_ok=True)
    exif=Image.Exif()
    if clock:exif[34665]={36867:'2026:09:28 12:00:01',37521:'123456789',36881:'+00:00'}
    Image.new('RGB',(12,8),color).save(path,exif=exif)
    return path


@pytest.fixture
def library(tmp_path):
    s=Service(tmp_path/'catalog',presets_root=tmp_path/'presets')
    s.dispatch('queue_control',{'action':'pause'})
    yield s,tmp_path
    s.close()


def prepare(s,paths,**options):
    return s.dispatch('prepare_import',{'paths':list(map(str,paths)),**options})['plan']


def scan(s,plan):
    while plan['state'] in ('planning','interrupted'):
        plan=s.dispatch('scan_import',{'plan_id':plan['id'],'expected_revision':plan['revision']})['plan']
    return plan


def apply(s,plan):
    return s.dispatch('apply_import',{'plan_id':plan['id'],'expected_revision':plan['revision']})['plan']


def test_review_selection_xmp_and_atomic_add_preserve_existing_photos(library):
    s,root=library
    a=picture(root/'photos/a.jpg');b=picture(root/'photos/b.jpg');c=picture(root/'photos/nested/c.jpg')
    s.dispatch('import_photos',{'paths':[str(a)]})
    s.dispatch('edit_photo',{'photo_id':1,'expected_revision':0,'patch':{'exposure':2}})
    before=s.dispatch('get_photo',{'photo_id':1})
    b.with_suffix('.xmp').write_bytes(packet('<dc:title>Imported title</dc:title><lr:hierarchicalSubject><rdf:Bag><rdf:li>Places|Coast</rdf:li></rdf:Bag></lr:hierarchicalSubject>','xmp:Rating="4"'))
    originals={p:p.read_bytes() for p in (a,b,c,b.with_suffix('.xmp'))}
    plan=scan(s,prepare(s,[a.parent]))
    assert plan['counts']=={'existing':1,'new':2} and plan['selected_count']==2
    assert s.dispatch('list_photos')['total']==1
    items=s.dispatch('get_import')['items'];third=next(r for r in items if r['path']==str(c))
    existing=next(r for r in items if r['state']=='existing')
    with pytest.raises(ValueError,match='not selectable'):
        s.dispatch('select_import_items',{'plan_id':plan['id'],'expected_revision':plan['revision'],'item_ids':[existing['id']],'selected':True})
    plan=s.dispatch('select_import_items',{'plan_id':plan['id'],'expected_revision':plan['revision'],'item_ids':[third['id']],'selected':False})['plan']
    assert plan['selected_count']==1 and plan['selected_bytes']==b.stat().st_size
    assert apply(s,plan)['imported']==1
    assert s.dispatch('get_photo',{'photo_id':1})==before
    new=s.dispatch('get_photo',{'photo_id':2})
    assert new['title']=='Imported title' and new['keywords']==['Places | Coast'] and new['rating']==4
    assert new['original_name']=='b.jpg' and new['taken_submicro']=='789'
    assert all(path.read_bytes()==value for path,value in originals.items())
    counts(s)
    completed=s.dispatch('get_import')['plan']
    assert s.dispatch('cancel_import',{'plan_id':completed['id']})['plan']['state']=='applied'
    with pytest.raises(ValueError,match='changed'):apply(s,plan)


def test_suspected_duplicates_require_filename_size_and_known_capture_time(library):
    s,root=library
    original=picture(root/'original/one.jpg');unknown=picture(root/'original/unknown.jpg',clock=False)
    s.dispatch('import_photos',{'paths':[str(original),str(unknown)]})
    folder=root/'new';folder.mkdir()
    same=folder/'one.jpg';shutil.copy2(original,same)
    different=folder/'different.jpg';shutil.copy2(original,different)
    uncertain=folder/'unknown.jpg';shutil.copy2(unknown,uncertain)
    plan=scan(s,prepare(s,[folder]))
    assert plan['counts']=={'duplicate':1,'new':2} and plan['selected_count']==2
    plan=s.dispatch('set_import_options',{'plan_id':plan['id'],'expected_revision':plan['revision'],'skip_duplicates':False})['plan']
    assert plan['selected_count']==3
    assert apply(s,plan)['imported']==3 and s.dispatch('list_photos')['total']==5
    counts(s)


def test_nonrecursive_sources_and_duplicate_overlapping_paths_are_bounded(library):
    s,root=library
    direct=picture(root/'photos/direct.jpg');picture(root/'photos/child/nested.jpg')
    plan=scan(s,prepare(s,[direct.parent,direct],include_subfolders=False))
    assert plan['file_count']==1 and plan['selected_count']==1
    assert apply(s,plan)['imported']==1


@pytest.mark.parametrize('kind',['source','sidecar','directory','catalog'])
def test_changed_sources_or_catalog_cannot_silently_change_review(library,kind):
    s,root=library
    a=picture(root/'photos/a.jpg');b=picture(root/'photos/b.jpg')
    plan=scan(s,prepare(s,[a.parent]))
    if kind=='source':a.write_bytes(a.read_bytes()+b'changed')
    elif kind=='sidecar':a.with_suffix('.xmp').write_bytes(packet('<dc:title>Late</dc:title>'))
    elif kind=='directory':picture(a.parent/'new.jpg')
    else:s.dispatch('import_photos',{'paths':[str(b)]})
    result=apply(s,plan)
    assert result['state']=='failed' and result['error']
    assert s.dispatch('list_photos')['total']==(1 if kind=='catalog' else 0)
    counts(s)


def test_missing_duplicate_time_is_not_file_modification_time(library):
    s,root=library
    a=picture(root/'one/unknown.jpg',clock=False)
    b=root/'two/unknown.jpg';b.parent.mkdir();shutil.copy2(a,b)
    plan=scan(s,prepare(s,[a,b]))
    assert plan['counts']=={'new':2} and apply(s,plan)['imported']==2


def test_sql_failure_rolls_back_photos_keywords_and_folder_counts(library):
    s,root=library
    a=picture(root/'photos/a.jpg');b=picture(root/'photos/b.jpg')
    a.with_suffix('.xmp').write_bytes(packet('<dc:subject><rdf:Bag><rdf:li>New tag</rdf:li></rdf:Bag></dc:subject>'))
    plan=scan(s,prepare(s,[a,b]))
    with s.catalog() as c,c.db:
        c.db.execute("CREATE TRIGGER fail_import BEFORE INSERT ON photos WHEN NEW.name='b.jpg' BEGIN SELECT RAISE(ABORT,'import fault'); END")
    result=apply(s,plan)
    assert result['state']=='failed' and 'import fault' in result['error']
    assert s.dispatch('list_photos')['total']==0 and s.dispatch('list_keywords')['total']==0
    counts(s)


def test_scan_releases_catalog_lock_and_cancel_discards_staged_rows(library,monkeypatch):
    from lumaraw import import_runner
    s,root=library;a=picture(root/'a.jpg');plan=prepare(s,[a])
    entered=threading.Event();release=threading.Event();result=[]
    original=import_runner.inspect_file
    def slow(*args):
        entered.set();assert release.wait(5);return original(*args)
    monkeypatch.setattr(import_runner,'inspect_file',slow)
    thread=threading.Thread(target=lambda:result.append(s.dispatch('scan_import',{'plan_id':plan['id'],'expected_revision':plan['revision']})))
    thread.start()
    try:
        assert entered.wait(3)
        assert s.dispatch('status')['photos']==0
        assert s.dispatch('cancel_import',{'plan_id':plan['id']})['plan']['state']=='cancelled'
    finally:release.set();thread.join(5)
    assert not thread.is_alive() and result[0]['plan']['state']=='cancelled'
    with s.catalog() as c:assert c.db.execute('SELECT count(*) FROM import_files').fetchone()[0]==0


def test_interrupted_scan_resumes_without_losing_selection(library):
    s,root=library;a=picture(root/'a.jpg');b=picture(root/'b.jpg')
    plan=scan(s,prepare(s,[a,b]))
    item=s.dispatch('get_import')['items'][0]
    plan=s.dispatch('select_import_items',{'plan_id':plan['id'],'expected_revision':plan['revision'],'item_ids':[item['id']],'selected':False})['plan']
    with s.catalog() as c:ImportReview(c).start_apply(plan['id'],plan['revision'])
    s.close();reopened=Service(s.root,presets_root=root/'presets')
    try:
        saved=reopened.dispatch('get_import')['plan']
        assert saved['state']=='interrupted'
        ready=scan(reopened,saved)
        assert ready['selected_count']==1 and apply(reopened,ready)['imported']==1
    finally:reopened.close()


def test_genuine_schema18_upgrade_and_failure_are_atomic(tmp_path,monkeypatch):
    from lumaraw import catalog as module
    from lumaraw.import_review import migrate
    from legacy_catalog import migrate_to
    with monkeypatch.context() as context:
        context.setattr(module,'migrate',lambda db:migrate_to(db,18))
        c=Catalog(tmp_path/'old')
        with c.db:c.db.execute("INSERT INTO photos(path,name,bytes,mtime,recipe,created) VALUES('old.jpg','old.jpg',1,0,'{}',0)")
        c.db.set_authorizer(lambda action,a,b,d,t:sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_CREATE_TABLE and a=='import_plans' else sqlite3.SQLITE_OK)
        with pytest.raises(sqlite3.DatabaseError):migrate(c.db)
        c.db.set_authorizer(None)
        assert c.db.execute('PRAGMA user_version').fetchone()[0]==18
        assert 'original_name' not in [r[1] for r in c.db.execute('PRAGMA table_info(photos)')]
        c.close()
    c=Catalog(tmp_path/'old')
    try:
        assert c.db.execute('PRAGMA user_version').fetchone()[0]==CATALOG_VERSION
        assert c.db.execute('SELECT original_name,recipe FROM photos').fetchone()[:]==('old.jpg','{}')
    finally:c.close()


def test_large_directory_replays_after_restart_without_duplicate_rows(library):
    import os
    s,root=library
    source=picture(root/'template.jpg',clock=False)
    folder=root/'many';folder.mkdir()
    for i in range(601):os.link(source,folder/f'{i:04}.jpg')
    plan=prepare(s,[folder])
    first=s.dispatch('scan_import',{'plan_id':plan['id'],'expected_revision':plan['revision']})['plan']
    assert first['file_count']==256 and first['phase']=='directories'
    s.close();other=Service(s.root,presets_root=root/'presets')
    try:
        ready=scan(other,other.dispatch('get_import')['plan'])
        assert ready['file_count']==601 and ready['scanned']==601 and ready['selected_count']==601
        page=other.dispatch('get_import',{'offset':600})
        assert page['total']==601 and len(page['items'])==1
        assert all('patch' not in r and 'fingerprints' not in r for r in page['items'])
        assert len(json.dumps(page).encode())<20000
        plan=other.dispatch('select_import_items',{'plan_id':ready['id'],'expected_revision':ready['revision'],'selected':False})['plan']
        plan=other.dispatch('select_import_items',{'plan_id':plan['id'],'expected_revision':plan['revision'],
            'selected':True,'item_ids':[page['items'][0]['id']]})['plan']
        assert apply(other,plan)['imported']==1
    finally:other.close()


def test_backup_restores_ready_review_and_selections(library):
    s,root=library;a=picture(root/'a.jpg');b=picture(root/'b.jpg')
    plan=scan(s,prepare(s,[a,b]))
    first=s.dispatch('get_import')['items'][0]
    plan=s.dispatch('select_import_items',{'plan_id':plan['id'],'expected_revision':plan['revision'],'selected':False,'item_ids':[first['id']]})['plan']
    backup=root/'backup.sqlite';s.dispatch('backup_catalog',{'path':str(backup)})
    restored=s.dispatch('restore_catalog',{'path':str(backup),'destination':str(root/'restored')})
    other=Service(restored['catalog'],presets_root=root/'presets')
    try:
        saved=other.dispatch('get_import')['plan']
        assert saved['revision']==plan['revision'] and saved['selected_count']==1
        assert apply(other,saved)['imported']==1
        assert s.dispatch('status')['photos']==0
    finally:other.close()


def test_active_catalog_cache_is_excluded_from_source_traversal(library):
    s,root=library
    picture(s.root/'cache/generated.jpg');original=picture(root/'original.jpg')
    with pytest.raises(ValueError,match='generated cache'):
        prepare(s,[s.root])
    plan=scan(s,prepare(s,[root]))
    assert plan['file_count']==1 and s.dispatch('get_import')['items'][0]['path']==str(original)


def test_late_duplicate_elsewhere_rejects_review_without_partial_import(library):
    s,root=library
    a=picture(root/'incoming/a.jpg');b=picture(root/'incoming/b.jpg')
    elsewhere=root/'outside/a.jpg';elsewhere.parent.mkdir();shutil.copy2(a,elsewhere)
    plan=scan(s,prepare(s,[a,b]))
    s.dispatch('import_photos',{'paths':[str(elsewhere)]})
    assert apply(s,plan)['state']=='failed' and s.dispatch('status')['photos']==1


def test_cancellation_inside_bulk_sql_rolls_back_folder_maintenance_and_import(library):
    s,root=library
    with s.catalog() as c:
        domain=ImportReview(c);plan=domain.prepare([])['plan']
        with c.db:
            c.db.executemany("INSERT INTO import_files(plan_id,path,name,extension,state) VALUES(?,?,?,'.jpg','new')",
                ((plan['id'],str(root/'bulk'/f'{i}.jpg'),f'{i}.jpg') for i in range(2000)))
            c.db.execute("UPDATE import_plans SET state='verifying',phase='files' WHERE id=?",(plan['id'],))
        writing=threading.Event()
        c.db.set_trace_callback(lambda sql:writing.set() if sql.startswith('INSERT INTO photos(') else None)
        try:
            with pytest.raises(InterruptedError,match='cancelled'):
                domain.apply(plan['id'],plan['revision'],writing.is_set)
        finally:c.db.set_trace_callback(None)
        assert writing.is_set()
        assert c.db.execute('SELECT count(*) FROM photos').fetchone()[0]==0
        assert c.db.execute('SELECT count(*) FROM folder_photos').fetchone()[0]==0
        assert c.db.execute('SELECT enabled FROM folder_maintenance').fetchone()[0]==1
        assert c.db.execute('SELECT count(*) FROM catalog_folders').fetchone()[0]==0
        assert c.db.execute('SELECT count(*) FROM import_files').fetchone()[0]==2000


def test_bulk_import_maintains_source_roots_and_independent_folder_counts(library):
    s,root=library
    first=picture(root/'Photos/One/deep/a.jpg');second=picture(root/'Photos/Two/b.jpg')
    external=picture(root/'Separate/selected.jpg')
    plan=scan(s,prepare(s,[root/'Photos',external]))
    assert apply(s,plan)['imported']==3
    roots=s.dispatch('list_folders')['folders']
    assert {r['path'] for r in roots}=={str(root/'Photos'),str(external.parent)}
    counts(s)


def test_preview_source_change_is_rejected_before_image_worker(library,monkeypatch):
    s,root=library;a=picture(root/'a.jpg')
    plan=scan(s,prepare(s,[a]));item=s.dispatch('get_import')['items'][0]
    a.write_bytes(a.read_bytes()+b'changed')
    monkeypatch.setattr(s,'run_worker',lambda *a:(_ for _ in ()).throw(AssertionError('No image work expected')))
    with pytest.raises(ValueError,match='source changed'):
        s.dispatch('preview_import_item',{'plan_id':plan['id'],'item_id':item['id'],'expected_revision':plan['revision'],
            'client_id':'test-import','generation':1})
    assert s.dispatch('status')['photos']==0
