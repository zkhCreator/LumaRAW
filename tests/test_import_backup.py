"""Original-state second copies across filesystem, SQL and interruption boundaries.

Generated photographs/XMP establish byte and naming safety, pinned independent
roots, all-destination preflight, explicit recovery and bounded control access.
No physical-drive redundancy, removable-media or desktop acceptance is implied.
"""
import json
from pathlib import Path
import sqlite3
import threading

import pytest

from lumaraw.catalog import Catalog
from lumaraw.service import Service
from lumaraw.import_copy import ImportCopy,settings
from lumaraw import import_backup
from lumaraw import import_copy_io as io
from lumaraw.library import backup_catalog,restore_catalog
from test_import_review import library,picture,prepare,scan,apply
from test_import_copy import ready,resume,transfers
from test_import_naming import configure
from test_xmp_read import packet
from test_folder_sync import counts
from legacy_catalog import migrate_to,seed_photo


def backup_ready(s,root,paths,**options):
    backup=root/'backup';backup.mkdir(exist_ok=True)
    return ready(s,root,paths,second_copy_destination=str(backup),**options)


def folder(plan):
    value=plan['copy']['backup']
    return Path(value['destination'])/value['subfolder']


def set_backup(s,plan,path):
    return s.dispatch('set_import_backup',{'plan_id':plan['id'],'expected_revision':plan['revision'],
                                        'destination':str(path) if path else None})['plan']


def test_original_names_and_bytes_survive_renaming_and_import_presets(library):
    from test_import_processing import metadata,choice,set_processing
    s,root=library;paths=[picture(root/'source/DSC001.jpg'),picture(root/'source/DSC002.jpg')]
    xmp=paths[0].with_suffix('.xmp');xmp.write_bytes(packet('<dc:title>Original description</dc:title>'))
    original={p:(p.read_bytes(),p.stat().st_mtime_ns) for p in (*paths,xmp)}
    preset=metadata(s,{'title':'Catalog description'})
    plan=configure(s,backup_ready(s,root,[paths[0].parent]),custom_text='Trip')
    set_processing(s,metadata_preset=choice(s,'metadata',preset))
    plan=s.dispatch('get_import')['plan'];backup=folder(plan)
    assert not backup.exists() and plan['copy']['backup']['same_volume']
    previews=s.dispatch('get_import')['items']
    assert previews[0]['second_destination']==str(backup/'DSC001.jpg')
    assert previews[0]['destination'].endswith('Trip-0001.jpg')
    done=apply(s,plan)
    assert done['imported']==2 and done['copy']['copied']==6 and done['copy']['backup']['copied']==3
    assert done['copy']['backup']['copied_bytes']==sum(p.stat().st_size for p in original)
    assert {p.name for p in backup.iterdir()}=={'DSC001.jpg','DSC002.jpg','DSC001.xmp'}
    for path,data in original.items():
        assert (path.read_bytes(),path.stat().st_mtime_ns)==data
        copy=backup/path.name;assert (copy.read_bytes(),copy.stat().st_mtime_ns)==data
    assert s.dispatch('status')['photos']==2
    assert s.dispatch('get_photo',{'photo_id':1})['title']=='Catalog description'
    assert not any(str(backup) in p['path'] for p in s.dispatch('list_photos')['photos'])
    assert [r['role'] for r in transfers(s,done)].count('second')==3
    assert s.dispatch('list_photos',{'mode':'previous_import'})['total']==2
    counts(s)


def test_ready_choice_clear_revision_conflict_and_add_rejection(library):
    s,root=library;photo=picture(root/'a.jpg');backup=root/'backup';backup.mkdir()
    plan=scan(s,prepare(s,[photo]))
    with pytest.raises(ValueError,match='Copy mode'):set_backup(s,plan,backup)
    s.dispatch('cancel_import',{'plan_id':plan['id']})
    with pytest.raises(ValueError,match='Copy mode'):
        prepare(s,[photo],second_copy_destination=str(backup))
    plan=ready(s,root,[photo]);changed=set_backup(s,plan,backup)
    assert changed['copy']['backup'] and not list(backup.iterdir())
    with pytest.raises(ValueError,match='changed'):set_backup(s,plan,None)
    cleared=set_backup(s,changed,None)
    assert cleared['copy']['backup'] is None
    assert apply(s,cleared)['state']=='applied' and not list(backup.iterdir())


def test_backup_choice_rechecks_revision_after_filesystem_inspection(library,monkeypatch):
    s,root=library;plan=ready(s,root,[picture(root/'a.jpg')]);backup=root/'backup';backup.mkdir()
    original=import_backup.capture
    def changed(*args):
        value=original(*args)
        s.dispatch('set_import_options',{'plan_id':plan['id'],'expected_revision':plan['revision'],'skip_duplicates':False})
        return value
    monkeypatch.setattr(import_backup,'capture',changed)
    with pytest.raises(ValueError,match='changed'):set_backup(s,plan,backup)
    current=s.dispatch('get_import')['plan']
    assert not current['skip_duplicates'] and current['copy']['backup'] is None
    assert not list(backup.iterdir())


def test_second_copy_target_cannot_enter_catalog_through_dated_folder(tmp_path):
    from datetime import datetime
    backup=tmp_path/'backup';backup.mkdir()
    s=Service(backup/('Imported on '+datetime.now().astimezone().strftime('%Y-%m-%d')),presets_root=tmp_path/'presets')
    try:
        a=picture(tmp_path/'a.jpg');plan=ready(s,tmp_path,[a],second_copy_destination=str(backup))
        pending=apply(s,plan)
        assert pending['state']=='interrupted' and 'active catalog' in pending['error']
        assert pending['copy']['copied']==0 and not (s.root/'a.jpg').exists()
    finally:s.close()


@pytest.mark.parametrize('which',['same','inside','parent','catalog','source','symlink'])
def test_backup_destination_boundaries(library,which):
    s,root=library;photo=picture(root/'source/a.jpg');destination=root/'destination';destination.mkdir()
    if which=='same':backup=destination
    elif which=='inside':backup=destination/'backup';backup.mkdir()
    elif which=='parent':backup=root
    elif which=='catalog':backup=s.root
    elif which=='source':backup=photo.parent
    else:backup=root/'backup-link';backup.symlink_to(destination)
    with pytest.raises((ValueError,OSError)):
        prepare(s,[photo.parent],mode='copy',destination=str(destination),second_copy_destination=str(backup))
    assert s.dispatch('get_import')['plan'] is None and s.dispatch('status')['photos']==0


@pytest.mark.parametrize('collision',['primary','second','second_sidecar','duplicate_name','casefold'])
def test_all_destinations_preflight_before_any_publication(library,collision):
    s,root=library;a=picture(root/'source/a.jpg');b=picture(root/'other/b.jpg')
    if collision=='duplicate_name':b=picture(root/'other/a.jpg')
    if collision=='casefold':b=picture(root/'other/A.JPG')
    if collision=='second_sidecar':a.with_suffix('.xmp').write_bytes(packet('<dc:title>Photo</dc:title>'))
    plan=configure(s,backup_ready(s,root,[a,b],skip_duplicates=False))
    backup=folder(plan)
    existing=None
    if collision=='primary':existing=root/'destination/Trip-0002.jpg'
    elif collision=='second':existing=backup/'b.jpg'
    elif collision=='second_sidecar':existing=backup/'a.xmp'
    if existing:
        existing.parent.mkdir(exist_ok=True);existing.write_bytes(b'keep')
    pending=apply(s,plan)
    assert pending['state']=='interrupted' and pending['copy']['copied']==0 and s.dispatch('status')['photos']==0
    files=[p for base in (root/'destination',root/'backup') for p in base.rglob('*') if p.is_file()]
    assert files==([existing] if existing else [])
    if existing:assert existing.read_bytes()==b'keep'


@pytest.mark.parametrize('role',['primary','second'])
@pytest.mark.parametrize('point',['writing','sealed','linked','published'])
def test_restart_recovers_each_role_without_retarget_or_double_count(library,monkeypatch,role,point):
    s,root=library;a=picture(root/'a.jpg');plan=configure(s,backup_ready(s,root,[a]),start=7)
    original=ImportCopy.save;fired=False
    def crash(self,row,**patch):
        nonlocal fired
        match=row['role']==role and not fired
        if match and point=='linked' and patch.get('state')=='published':fired=True;raise SystemExit('crash')
        original(self,row,**patch)
        if match and patch.get('state')==point:fired=True;raise SystemExit('crash')
    monkeypatch.setattr(ImportCopy,'save',crash)
    with pytest.raises(SystemExit):apply(s,plan)
    monkeypatch.setattr(ImportCopy,'save',original);s.close()
    restarted=Service(s.root,presets_root=root/'presets')
    try:
        pending=restarted.dispatch('get_import')['plan']
        with pytest.raises(ValueError,match='changed'):set_backup(restarted,pending,None)
        done=resume(restarted,pending)
        assert done['state']=='applied' and done['copy']['copied']==2 and done['copy']['backup']['copied']==1
        assert folder(done)==folder(plan)
        assert (folder(done)/'a.jpg').read_bytes()==(root/'destination/Trip-0007.jpg').read_bytes()==a.read_bytes()
        assert all(r['state']=='published' for r in transfers(restarted,done))
        assert not list(root.rglob('*.part'))
    finally:restarted.close()


def test_cancel_keeps_published_files_on_both_destinations_and_control_responsive(library,monkeypatch):
    s,root=library;paths=[picture(root/'a.jpg'),picture(root/'b.jpg')];plan=backup_ready(s,root,paths)
    original=io.transfer;entered=threading.Event();release=threading.Event();result={}
    def hold(row,value,save,cancelled):
        original(row,value,save,cancelled)
        if row['role']=='primary' and not entered.is_set():entered.set();assert release.wait(5)
    monkeypatch.setattr(io,'transfer',hold)
    thread=threading.Thread(target=lambda:result.update(apply(s,plan)));thread.start()
    try:
        assert entered.wait(5)
        assert s.dispatch('status')['photos']==0
        progress=s.dispatch('get_import')['plan']
        assert progress['copy']['copied']==2 and progress['copy']['backup']['copied']==1
        s.dispatch('cancel_import',{'plan_id':plan['id']})
    finally:release.set();thread.join(5)
    assert not thread.is_alive() and result['state']=='cancelled'
    assert (root/'destination/a.jpg').exists() and (folder(plan)/'a.jpg').exists()
    assert not (root/'destination/b.jpg').exists() and not (folder(plan)/'b.jpg').exists()
    assert len(transfers(s,plan))==4


def test_missing_backup_volume_blocks_preflight_and_explicit_resume_can_recover(library):
    s,root=library;a=picture(root/'a.jpg');plan=backup_ready(s,root,[a])
    (root/'backup').rename(root/'offline')
    pending=apply(s,plan)
    assert pending['state']=='interrupted' and not list((root/'destination').iterdir())
    (root/'offline').rename(root/'backup')
    assert resume(s,pending)['state']=='applied'


def test_swapped_backup_root_or_symlink_is_not_adopted(library):
    s,root=library;a=picture(root/'a.jpg');plan=backup_ready(s,root,[a])
    (root/'backup').rename(root/'old');(root/'backup').mkdir()
    pending=apply(s,plan)
    assert pending['state']=='interrupted' and pending['copy']['copied']==0
    (root/'backup').rmdir();(root/'backup').symlink_to(root/'old')
    assert resume(s,pending)['state']=='interrupted'
    assert not list((root/'destination').iterdir()) and not list((root/'old').iterdir())


def test_catalog_failure_retains_both_verified_copies_for_explicit_retry(library):
    s,root=library;a=picture(root/'a.jpg');plan=backup_ready(s,root,[a])
    with s.catalog() as c,c.db:
        c.db.execute("CREATE TRIGGER fail_import BEFORE INSERT ON photos BEGIN SELECT RAISE(ABORT,'injected failure'); END")
    pending=apply(s,plan)
    assert pending['state']=='interrupted' and pending['copy']['copied']==2 and s.dispatch('status')['photos']==0
    with s.catalog() as c,c.db:c.db.execute('DROP TRIGGER fail_import')
    assert resume(s,pending)['state']=='applied'
    assert len(transfers(s,plan))==2 and s.dispatch('status')['photos']==1


def test_restored_catalog_cannot_resume_or_clean_original_backup(library,monkeypatch):
    s,root=library;a=picture(root/'a.jpg');plan=backup_ready(s,root,[a]);original=ImportCopy.save
    def die(self,row,**patch):
        original(self,row,**patch)
        if patch.get('state')=='writing':raise SystemExit('crash')
    monkeypatch.setattr(ImportCopy,'save',die)
    with pytest.raises(SystemExit):apply(s,plan)
    monkeypatch.setattr(ImportCopy,'save',original)
    scratch=next((root/'backup').rglob('*.part'));identity=scratch.stat().st_ino
    with s.catalog() as c:backup_catalog(c,root/'backup.sqlite')
    restore_catalog(root/'backup.sqlite',root/'restored');restored=Service(root/'restored',presets_root=root/'presets')
    try:
        pending=restored.dispatch('get_import')['plan'];failed=resume(restored,pending)
        assert failed['state']=='interrupted' and 'another catalog' in failed['error']
        restored.dispatch('cancel_import',{'plan_id':plan['id']})
        assert scratch.stat().st_ino==identity
    finally:restored.close()


def test_shared_raw_jpeg_sidecar_uses_one_original_backup_and_distinct_primary_stems(library):
    s,root=library;a=picture(root/'same.jpg');b=picture(root/'same.png')
    a.with_suffix('.xmp').write_bytes(packet('<dc:title>Shared</dc:title>'))
    plan=configure(s,backup_ready(s,root,[a,b]));done=apply(s,plan)
    assert done['state']=='applied' and done['copy']['transfer_count']==7 and done['copy']['backup']['transfer_count']==3
    assert {p.name for p in folder(done).iterdir()}=={'same.jpg','same.png','same.xmp'}


def test_schema_27_migration_is_atomic_and_keeps_old_journal_primary(tmp_path,monkeypatch):
    from lumaraw import catalog as module
    with monkeypatch.context() as context:
        context.setattr(module,'migrate',lambda db:migrate_to(db,27));c=Catalog(tmp_path/'old')
    seed_photo(c.db,picture(tmp_path/'a.jpg'))
    with c.db:
        c.db.execute("INSERT INTO import_plans(include_subfolders,created) VALUES(1,1)")
        c.db.execute("INSERT INTO import_copy_plans(plan_id,destination,destination_identity,organization,subfolder,roots,owner) VALUES(1,'target','{}','flat','','[]','owner')")
        c.db.execute("INSERT INTO import_transfers(plan_id,source,target,target_key,source_identity,temporary) VALUES(1,'a','b','b','[]','scratch')")
    c.db.set_authorizer(lambda action,a,b,d,t:sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_ALTER_TABLE and b=='import_transfers' else sqlite3.SQLITE_OK)
    with pytest.raises(sqlite3.DatabaseError):import_backup.migrate(c.db)
    assert c.db.execute('PRAGMA user_version').fetchone()[0]==27
    assert 'backup' not in {r[1] for r in c.db.execute('PRAGMA table_info(import_copy_plans)')}
    c.db.set_authorizer(None);import_backup.migrate(c.db);import_backup.migrate(c.db)
    assert json.loads(c.db.execute('SELECT backup FROM import_copy_plans').fetchone()[0])=={}
    assert c.db.execute('SELECT role FROM import_transfers').fetchone()[0]=='primary'
    assert c.db.execute('SELECT name FROM photos').fetchone()[0]=='a.jpg'
    assert c.db.execute('PRAGMA user_version').fetchone()[0]==28
    module.migrate(c.db)  # Current settings also read the later sequence schema.
    assert import_backup.summary(settings(c.db,1)) is None
    c.close()
