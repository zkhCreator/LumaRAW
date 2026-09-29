"""Durable folder synchronization with generated files and real catalog semantics.

Inputs: isolated nested images, sidecars, plan selections and injected failures.
Outputs: atomic imports/removal/read-metadata, consistent folder counts, preserved
edits/exports and responsive cancellation. All file mutations affect fixtures only.
"""
import hashlib
from pathlib import Path
import shutil
import sqlite3
import threading

from PIL import Image
import pytest

from lumaraw.catalog import Catalog
from lumaraw.folder_sync import FolderSync,migrate
from lumaraw.service import Service
from test_xmp_read import packet


@pytest.fixture
def library(tmp_path):
    root=tmp_path/'Photos';root.mkdir()
    paths=[root/name for name in ('a.png','b.png','Child/c.png')]
    for path in paths:
        path.parent.mkdir(exist_ok=True);Image.new('RGB',(12,8),'navy').save(path)
    s=Service(tmp_path/'catalog');s.dispatch('queue_control',{'action':'pause'})
    s.dispatch('import_photos',{'paths':list(map(str,paths))})
    yield s,root,paths
    s.close()


def prepare(s,metadata=True):
    folder=s.dispatch('get_folder',{'photo_id':1})
    return s.dispatch('prepare_folder_sync',{'folder_id':folder['id'],'expected_revision':folder['folder_revision'],'scan_metadata':metadata})['plan']


def scan(s,plan):
    while plan['state'] in ('planning','interrupted'):
        plan=s.dispatch('scan_folder_sync',{'plan_id':plan['id'],'expected_revision':plan['revision']})['plan']
    return plan


def apply(s,plan,**options):
    return s.dispatch('apply_folder_sync',{'plan_id':plan['id'],'expected_revision':plan['revision'],**options})['plan']


def counts(s):
    with s.catalog() as c:
        paths=[Path(row[0]).parent for row in c.db.execute('SELECT path FROM photos')]
        for row in c.db.execute('SELECT * FROM catalog_folders'):
            path=Path(row['path'])
            assert row['direct_count']==sum(p==path for p in paths)
            assert row['total_count']==sum(p==path or path in p.parents for p in paths)
        assert c.db.execute('SELECT enabled FROM folder_maintenance').fetchone()[0]==1
        assert c.db.execute('SELECT count(*) FROM folder_photos').fetchone()[0]==len(paths)


def photo(s,id_):
    return s.dispatch('get_photo',{'photo_id':id_})


def copy(s,id_):
    p=photo(s,id_)
    return s.dispatch('create_virtual_copies',{'targets':[{'photo_id':id_,'expected_revision':p['revision'],
        'expected_metadata_revision':p['metadata_revision']}]})['photos'][0]['id']


def test_full_sync_preview_selection_and_catalog_only_removal(library):
    s,root,paths=library
    variant=copy(s,2)
    s.dispatch('edit_photo',{'photo_id':1,'expected_revision':0,'patch':{'exposure':1.5}})
    s.dispatch('edit_metadata',{'targets':[{'photo_id':1,'expected_metadata_revision':0}], 'patch':{'title':'Old'}})
    s.dispatch('save_version',{'photo_id':2,'name':'Missing family snapshot'})
    album=s.dispatch('save_collection',{'name':'Keep','kind':'regular','photo_ids':[1,2,variant]})
    s.dispatch('enqueue_exports',{'photo_ids':[1,2,variant],'destination':str(root.parent/'exports'),'format':'jpeg','request_key':'sync-frozen'})
    with s.catalog() as c:
        jobs=[tuple(row) for row in c.db.execute('SELECT * FROM jobs ORDER BY id')]
    paths[1].unlink()
    paths[0].with_suffix('.xmp').write_bytes(packet('<dc:title>海边</dc:title><lr:hierarchicalSubject><rdf:Bag><rdf:li>Places|Coast</rdf:li></rdf:Bag></lr:hierarchicalSubject>','xmp:Rating="4"'))
    new=root/'New'/'quote"\\.png';new.parent.mkdir();Image.new('RGB',(8,8),'red').save(new)
    excluded=root/'New'/'exclude.png';Image.new('RGB',(8,8),'blue').save(excluded)
    before={p:hashlib.sha256(p.read_bytes()).digest() for p in root.rglob('*') if p.is_file()}
    plan=scan(s,prepare(s))
    assert plan['state']=='ready',plan
    assert plan['counts']=={'updated':1,'missing':1,'unchanged':1,'new':2}
    assert photo(s,1)['title']=='Old' and s.dispatch('list_photos',{'stacked':False})['total']==4
    rows=s.dispatch('get_folder_sync',{'kind':'new'})['items']
    target=next(row['id'] for row in rows if row['path']==str(excluded))
    plan=s.dispatch('select_folder_sync_items',{'plan_id':plan['id'],'expected_revision':plan['revision'],
        'selected':False,'item_ids':[target]})['plan']
    assert plan['selected_counts']['new']==1
    result=apply(s,plan,remove_missing=True)
    assert result['state']=='applied',result
    assert (result['imported'],result['removed'],result['modified'])==(1,2,1)
    p=photo(s,1)
    assert p['recipe']['exposure']==1.5 and p['title']=='海边' and p['rating']==4
    assert p['keywords']==['Places | Coast']
    with pytest.raises(ValueError,match='does not exist'):photo(s,variant)
    with s.catalog() as c:
        assert [tuple(row) for row in c.db.execute('SELECT * FROM jobs ORDER BY id')]==jobs
        assert c.db.execute('SELECT count(*) FROM versions').fetchone()[0]==0
        assert c.db.execute('SELECT count(*) FROM collection_photos WHERE collection_id=?',(album['id'],)).fetchone()[0]==1
        assert c.db.execute('SELECT count(*) FROM photos WHERE path=?',(str(new),)).fetchone()[0]==1
        assert c.db.execute('SELECT count(*) FROM photos WHERE path=?',(str(excluded),)).fetchone()[0]==0
    assert before=={p:hashlib.sha256(p.read_bytes()).digest() for p in before}
    assert s.dispatch('cancel_folder_sync',{'plan_id':plan['id']})['plan']['state']=='applied'
    counts(s)


def test_default_sync_marks_missing_without_removing_and_preserves_copy_metadata(library):
    s,root,paths=library
    variant=copy(s,1)
    paths[0].with_suffix('.xmp').write_bytes(packet('<dc:title>External</dc:title>'))
    paths[1].unlink()
    plan=scan(s,prepare(s));result=apply(s,plan)
    assert result['state']=='applied' and result['removed']==0
    assert photo(s,2)['missing']==1 and photo(s,1)['title']=='External'
    assert photo(s,variant)['title']=='' and photo(s,variant)['recipe']==photo(s,1)['recipe']
    counts(s)


def test_metadata_opt_out_and_changed_original_invalidates_hash(library):
    s,root,paths=library
    s.dispatch('index_library');original=photo(s,1)
    paths[0].with_suffix('.xmp').write_bytes(b'invalid XML')
    Image.new('RGB',(12,8),'orange').save(paths[0])
    plan=scan(s,prepare(s,metadata=False))
    assert plan['state']=='ready' and plan['counts']['updated']==1
    with pytest.raises(ValueError,match='not scanned'):apply(s,plan)
    assert apply(s,plan,read_metadata=False)['state']=='applied'
    updated=photo(s,1)
    assert updated['sha256']=='' and updated['source_revision']==original['source_revision']+1
    assert updated['title']==original['title']


@pytest.mark.parametrize('mutation',['file','sidecar','directory','root'])
def test_late_filesystem_changes_block_complete_application(library,mutation):
    s,root,paths=library
    new=root/'new.png';Image.new('RGB',(8,8)).save(new)
    plan=scan(s,prepare(s))
    if mutation=='file':paths[0].write_bytes(paths[0].read_bytes()+b'changed')
    elif mutation=='sidecar':paths[0].with_suffix('.xmp').write_bytes(packet('<dc:title>Late</dc:title>'))
    elif mutation=='directory':(root/'Child'/'late.txt').write_text('late')
    else:root.rename(root.with_name('Elsewhere'));root.mkdir()
    result=apply(s,plan)
    assert result['state']=='failed' and 'changed' in result['error']
    assert s.dispatch('list_photos',{'stacked':False})['total']==3
    counts(s)


@pytest.mark.parametrize('kind',['recipe','rating','metadata','membership'])
def test_late_catalog_edits_protect_missing_family_removal(library,kind):
    s,root,paths=library
    paths[1].unlink();plan=scan(s,prepare(s))
    if kind=='recipe':s.dispatch('edit_photo',{'photo_id':2,'expected_revision':0,'patch':{'exposure':2.0}})
    elif kind=='rating':s.dispatch('rate_photo',{'photo_id':2,'rating':5})
    elif kind=='metadata':s.dispatch('edit_metadata',{'targets':[{'photo_id':2,'expected_metadata_revision':0}],'patch':{'title':'Keep'}})
    else:copy(s,2)
    if kind=='membership':
        with pytest.raises(ValueError,match='membership changed'):apply(s,plan,remove_missing=True)
    else:assert apply(s,plan,remove_missing=True)['state']=='failed'
    assert photo(s,2)['id']==2
    counts(s)


def test_deselected_metadata_does_not_overwrite_catalog(library):
    s,root,paths=library
    paths[0].with_suffix('.xmp').write_bytes(packet('<dc:title>External</dc:title>'))
    plan=scan(s,prepare(s));row=s.dispatch('get_folder_sync',{'kind':'updated'})['items'][0]
    plan=s.dispatch('select_folder_sync_items',{'plan_id':plan['id'],'expected_revision':plan['revision'],
        'kind':'updated','selected':False,'item_ids':[row['id']]})['plan']
    s.dispatch('edit_metadata',{'targets':[{'photo_id':1,'expected_metadata_revision':0}],'patch':{'title':'Local'}})
    assert apply(s,plan)['state']=='applied' and photo(s,1)['title']=='Local'


def test_scan_is_cancellable_without_catalog_lock(library,monkeypatch):
    import lumaraw.folder_sync_runner as module
    s,root,paths=library;plan=prepare(s)
    while plan['phase']=='directories':
        plan=s.dispatch('scan_folder_sync',{'plan_id':plan['id'],'expected_revision':plan['revision']})['plan']
    entered,release=threading.Event(),threading.Event();outcome=[];original=module.inspect_file
    def slow(row,scan_metadata,cancelled):
        entered.set();assert release.wait(3);return original(row,scan_metadata,cancelled)
    monkeypatch.setattr(module,'inspect_file',slow)
    worker=threading.Thread(target=lambda:outcome.append(scan(s,plan)));worker.start()
    try:
        assert entered.wait(3)
        assert s.dispatch('list_photos',{'stacked':False})['total']==3
        assert s.dispatch('cancel_folder_sync',{'plan_id':plan['id']})['plan']['state']=='cancelled'
    finally:release.set();worker.join(3)
    assert not worker.is_alive() and outcome[0]['state']=='cancelled'
    counts(s)


def test_image_admission_defers_and_failed_commit_rolls_back(library,monkeypatch):
    s,root,paths=library
    paths[1].unlink();Image.new('RGB',(8,8)).save(root/'new.png')
    plan=scan(s,prepare(s))
    with s.image_lock:waiting=apply(s,plan,remove_missing=True)
    assert waiting['state']=='ready' and 'Image processing' in waiting['error']
    original=FolderSync.apply
    def fail(self,*args):
        self.db.set_authorizer(lambda action,table,column,*rest:sqlite3.SQLITE_DENY
            if action==sqlite3.SQLITE_UPDATE and table=='folder_state' else sqlite3.SQLITE_OK)
        try:return original(self,*args)
        finally:self.db.set_authorizer(None)
    monkeypatch.setattr(FolderSync,'apply',fail)
    result=apply(s,waiting,remove_missing=True)
    assert result['state']=='failed'
    assert s.dispatch('list_photos',{'stacked':False})['total']==3 and photo(s,2)['id']==2
    counts(s)


def test_wide_directory_restart_replays_without_duplicates_and_paginates(library):
    s,root,paths=library
    for i in range(300):shutil.copyfile(paths[0],root/f'new-{i}.png')
    plan=prepare(s)
    first=s.dispatch('scan_folder_sync',{'plan_id':plan['id'],'expected_revision':plan['revision']})['plan']
    assert first['phase']=='directories' and first['directories_done']==0 and first['file_count']<=258
    saved=s.root;s.close();reopened=Service(saved)
    try:
        plan=scan(reopened,reopened.dispatch('get_folder_sync')['plan'])
        assert plan['state']=='ready' and plan['file_count']==303 and plan['counts']['new']==300
        page=reopened.dispatch('get_folder_sync',{'kind':'new','offset':9999})
        assert page['offset']==240 and len(page['items'])==60
        plan=reopened.dispatch('select_folder_sync_items',{'plan_id':plan['id'],'expected_revision':plan['revision'],
            'selected':False,'folder':str(root)})['plan']
        assert plan['selected_counts'].get('new',0)==0
        assert apply(reopened,plan)['state']=='applied' and reopened.dispatch('list_photos')['total']==3
    finally:reopened.close()


def test_invalid_plan_request_does_not_strand_runner(library):
    s,root,paths=library
    with pytest.raises(ValueError,match='does not exist'):
        s.dispatch('scan_folder_sync',{'plan_id':9999,'expected_revision':0})
    assert scan(s,prepare(s))['state']=='ready'


def test_interrupted_apply_retains_explicit_file_deselection(library):
    s,root,paths=library
    Image.new('RGB',(8,8)).save(root/'new.png')
    plan=scan(s,prepare(s))
    plan=s.dispatch('select_folder_sync_items',{'plan_id':plan['id'],'expected_revision':plan['revision'],'selected':False})['plan']
    with s.catalog() as c:FolderSync(c).start_apply(plan['id'],plan['revision'],True)
    saved=s.root;s.close();reopened=Service(saved)
    try:
        recovered=reopened.dispatch('get_folder_sync')['plan']
        assert recovered['state']=='interrupted'
        ready=scan(reopened,recovered)
        assert ready['selected_counts'].get('new',0)==0
        assert apply(reopened,ready)['imported']==0
    finally:reopened.close()


def test_syncing_hidden_parent_makes_new_subfolders_visible(tmp_path):
    root=tmp_path/'Photos';old=root/'Old';old.mkdir(parents=True)
    source=old/'old.png';Image.new('RGB',(8,8)).save(source)
    s=Service(tmp_path/'catalog')
    try:
        s.dispatch('queue_control',{'action':'pause'});s.dispatch('import_photos',{'paths':[str(source)]})
        with s.catalog() as c:
            folder_id=c.db.execute('SELECT id FROM catalog_folders WHERE path=?',(str(root),)).fetchone()[0]
        new=root/'New';new.mkdir();Image.new('RGB',(8,8)).save(new/'new.png')
        plan=s.dispatch('prepare_folder_sync',{'folder_id':folder_id,'expected_revision':s.dispatch('library_state')['folder_revision'],'scan_metadata':False})['plan']
        plan=scan(s,plan)
        assert apply(s,plan,read_metadata=False)['state']=='applied'
        assert s.dispatch('list_folders',{'search':'New'})['total']==1
        assert s.dispatch('list_folders')['folders'][0]['path']==str(root)
        counts(s)
    finally:s.close()


def test_active_review_backup_retains_file_selections(library):
    from lumaraw.library import backup_catalog,restore_catalog
    s,root,paths=library
    for name in ('keep.png','skip.png'):
        Image.new('RGB',(8,8)).save(root/name)
    plan=scan(s,prepare(s))
    skipped=next(row for row in s.dispatch('get_folder_sync',{'kind':'new'})['items']
                 if row['path'].endswith('/skip.png'))
    plan=s.dispatch('select_folder_sync_items',{'plan_id':plan['id'],'expected_revision':plan['revision'],
        'item_ids':[skipped['id']],'selected':False})['plan']
    with s.catalog() as c:
        backup_catalog(c,root.parent/'backup')
    restored=Service(restore_catalog(root.parent/'backup',root.parent/'restored'))
    try:
        loaded=restored.dispatch('get_folder_sync')['plan']
        assert loaded['state']=='ready' and loaded['selected_counts']['new']==1
        assert apply(restored,loaded)['imported']==1
        with restored.catalog() as c:
            assert c.db.execute('SELECT 1 FROM photos WHERE path=?',(str(root/'skip.png'),)).fetchone() is None
        counts(restored)
    finally:
        restored.close()
    assert s.dispatch('list_photos',{'stacked':False})['total']==3



def test_metadata_review_keeps_complete_capture_clock_and_updates_family(library):
    s,root,_=library
    path=root/'clock.jpg'
    def write_time(second,fraction):
        exif=Image.Exif()
        exif[272]='Fixture Camera'
        exif[34665]={36867:f'2026:09:26 12:00:{second:02d}',37521:fraction,36881:'+08:00'}
        Image.new('RGB',(12,8)).save(path,exif=exif)
    write_time(1,'123456789')
    s.dispatch('import_photos',{'paths':[str(path)]})
    with s.catalog() as c:
        master=c.db.execute('SELECT id FROM photos WHERE path=?',(str(path),)).fetchone()[0]
    variant=copy(s,master)
    s.dispatch('edit_metadata',{'targets':[{'photo_id':variant,'expected_metadata_revision':0}],
        'patch':{'title':'Independent copy'}})
    write_time(2,'987654321')
    plan=scan(s,prepare(s))
    item=next(row for row in s.dispatch('get_folder_sync',{'kind':'updated'})['items']
              if row['path']==str(path))
    assert item['clock']['capture_clock']=='utc' and item['clock']['camera']=='Fixture Camera'
    assert item['clock']['taken_submicro']=='321' and item['clock']['taken_us'] % 1000000==987654
    assert apply(s,plan)['modified']==1
    assert photo(s,master)['taken_us']==photo(s,variant)['taken_us']==item['clock']['taken_us']
    assert photo(s,variant)['title']=='Independent copy'


def test_genuine_v9_migration_rolls_back_triggers_and_keeps_catalog(tmp_path,monkeypatch):
    import lumaraw.catalog as module
    from legacy_catalog import migrate_to,seed_photo
    with monkeypatch.context() as patch:
        patch.setattr(module,'migrate',lambda db:migrate_to(db,9));c=Catalog(tmp_path/'legacy')
    path=tmp_path/'old.png';Image.new('RGB',(8,8)).save(path);seed_photo(c.db,path)
    before=[tuple(row) for row in c.db.execute('SELECT * FROM photos')]
    trigger=c.db.execute("SELECT sql FROM sqlite_master WHERE name='folder_member_added'").fetchone()[0]
    c.db.set_authorizer(lambda action,name,*rest:sqlite3.SQLITE_DENY
        if action==sqlite3.SQLITE_DROP_TRIGGER and name=='folder_member_removed' else sqlite3.SQLITE_OK)
    with pytest.raises(sqlite3.DatabaseError):migrate(c.db)
    c.db.set_authorizer(None)
    assert c.db.execute('PRAGMA user_version').fetchone()[0]==9
    assert c.db.execute("SELECT sql FROM sqlite_master WHERE name='folder_member_added'").fetchone()[0]==trigger
    assert c.db.execute("SELECT 1 FROM sqlite_master WHERE name='folder_sync_plans'").fetchone() is None
    migrate(c.db)
    assert c.db.execute('PRAGMA user_version').fetchone()[0]==10
    assert [tuple(row) for row in c.db.execute('SELECT * FROM photos')]==before
    c.close()

def test_apply_verification_cancel_keeps_catalog(library,monkeypatch):
    import lumaraw.folder_sync_runner as module
    s,root,paths=library
    paths[1].unlink();Image.new('RGB',(8,8)).save(root/'new.png')
    plan=scan(s,prepare(s))
    entered,release=threading.Event(),threading.Event();outcome=[];original=module.identity
    def blocked(path):
        entered.set()
        assert release.wait(3)
        return original(path)
    monkeypatch.setattr(module,'identity',blocked)
    worker=threading.Thread(target=lambda:outcome.append(apply(s,plan,remove_missing=True)))
    worker.start()
    try:
        assert entered.wait(3)
        assert s.dispatch('list_photos',{'stacked':False})['total']==3
        assert s.dispatch('cancel_folder_sync',{'plan_id':plan['id']})['plan']['state']=='cancelled'
    finally:
        release.set();worker.join(3)
    assert not worker.is_alive() and outcome[0]['state']=='cancelled'
    assert photo(s,2)['missing']==0
    counts(s)


def test_running_export_defers_sync_until_explicit_retry(library):
    s,root,paths=library
    paths[0].with_suffix('.xmp').write_bytes(packet('<dc:title>External</dc:title>'))
    s.dispatch('enqueue_exports',{'photo_ids':[1],'destination':str(root.parent/'exports'),
        'format':'jpeg','request_key':'sync-admission'})
    plan=scan(s,prepare(s))
    with s.catalog() as c,c.db:
        c.db.execute("UPDATE jobs SET state='running'")
    deferred=apply(s,plan)
    assert deferred['state']=='ready' and 'exports' in deferred['error']
    assert photo(s,1)['title']==''
    with s.catalog() as c,c.db:
        c.db.execute("UPDATE jobs SET state='cancelled'")
    assert apply(s,deferred)['state']=='applied' and photo(s,1)['title']=='External'


def test_read_failure_blocks_missing_removal_without_classifying_it_missing(library,monkeypatch):
    import lumaraw.folder_sync_io as module
    s,root,paths=library
    paths[1].unlink()
    original=module.identity
    def denied(path):
        if Path(path)==paths[0]:
            raise PermissionError('Fixture access denied')
        return original(path)
    monkeypatch.setattr(module,'identity',denied)
    plan=scan(s,prepare(s))
    assert plan['state']=='ready' and plan['counts']['error']==1 and plan['counts']['missing']==1
    with pytest.raises(ValueError,match='scan errors'):
        apply(s,plan,remove_missing=True)
    assert s.dispatch('list_photos',{'stacked':False})['total']==3
    counts(s)


def test_discovery_skips_symlinks_and_rejects_replaced_catalog_paths(library):
    s,root,paths=library
    (root/'linked.png').symlink_to(paths[0])
    (root/'linked-directory').symlink_to(root/'Child',target_is_directory=True)
    plan=scan(s,prepare(s))
    assert plan['counts']=={'unchanged':3} and plan['file_count']==3
    s.dispatch('cancel_folder_sync',{'plan_id':plan['id']})
    paths[1].unlink();paths[1].symlink_to(paths[0])
    plan=scan(s,prepare(s))
    assert plan['counts']['error']==1 and plan['counts'].get('missing',0)==0
    with pytest.raises(ValueError,match='scan errors'):
        apply(s,plan,remove_missing=True)
