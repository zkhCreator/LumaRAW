"""Copy import safety across real filesystem, catalog and crash boundaries.

Generated photos/sidecars and fresh destinations prove exact byte preservation,
exclusive publication, bounded service work, recovery and transaction behavior.
These tests do not establish camera coverage or desktop interaction acceptance.
"""
import json
import os
from pathlib import Path
import sqlite3
import threading

from PIL import Image
import pytest

from lumaraw import import_copy_io as io
from lumaraw.import_copy import ImportCopy, settings
from lumaraw.service import Service
from lumaraw.catalog import Catalog
from lumaraw.library import backup_catalog, restore_catalog
from test_import_review import library, picture, prepare, scan, apply
from test_xmp_read import packet
from test_folder_sync import counts


def ready(s, root, paths, **options):
    destination=root/'destination'
    destination.mkdir(exist_ok=True)
    return scan(s, prepare(s, paths, mode='copy', destination=str(destination), **options))


def resume(s, plan):
    return s.dispatch('resume_import_copy', {'plan_id':plan['id'],'expected_revision':plan['revision']})['plan']


def transfers(s, plan):
    return s.dispatch('get_import_copies', {'plan_id':plan['id']})['items']


@pytest.mark.parametrize('organization,relative', [('flat','Album/a.jpg'), ('source','Album/source/child/a.jpg'),
                                                  ('date','Album/2026/2026-09-28/a.jpg')])
def test_copy_modes_xmp_metadata_previous_import_and_original_safety(library, organization, relative):
    s,root=library
    a=picture(root/'source/child/a.jpg')
    xmp=a.with_suffix('.xmp');xmp.write_bytes(packet('<dc:title>Copied title</dc:title>','xmp:Rating="4"'))
    original={p:(p.read_bytes(),p.stat().st_mtime_ns) for p in (a,xmp)}
    plan=ready(s,root,[root/'source'],organization=organization,subfolder='Album')
    assert plan['mode']=='copy' and not list((root/'destination').iterdir())
    assert s.dispatch('get_import')['items'][0]['destination']==str(root/'destination'/relative)
    result=apply(s,plan)
    assert result['state']=='applied' and result['imported']==1 and result['copy']['copied']==2
    p=s.dispatch('get_photo',{'photo_id':1})
    assert p['path']==str(root/'destination'/relative) and p['title']=='Copied title' and p['rating']==4
    assert p['original_name']=='a.jpg' and p['taken_submicro']=='789'
    assert s.dispatch('list_photos',{'mode':'previous_import'})['total']==1
    for source,expected in original.items():
        assert (source.read_bytes(),source.stat().st_mtime_ns)==expected
        copied=(root/'destination'/relative).with_name(source.name)
        assert (copied.read_bytes(),copied.stat().st_mtime_ns)==expected
    assert all(row['state']=='published' for row in transfers(s,plan))
    assert not list((root/'destination').rglob('*.part'))
    counts(s)


def test_local_capture_date_and_unknown_are_independent_of_utc_and_mtime(library):
    s,root=library
    a=root/'a.jpg';exif=Image.Exif();exif[34665]={36867:'2026:09:28 00:05:00',36881:'+14:00'}
    Image.new('RGB',(8,6)).save(a,exif=exif)
    b=picture(root/'unknown.jpg',clock=False)
    plan=ready(s,root,[a,b],organization='date')
    paths={item['name']:item['destination'] for item in s.dispatch('get_import')['items']}
    assert paths['a.jpg'].endswith('/2026/2026-09-28/a.jpg')
    assert paths['unknown.jpg'].endswith('/Unknown Date/unknown.jpg')
    assert apply(s,plan)['state']=='applied'


@pytest.mark.parametrize('collision',['existing','symlink','selected','casefold','sidecar'])
def test_all_destination_collisions_reject_before_any_copy(library, collision):
    s,root=library;a=picture(root/'source/a.jpg');b=picture(root/'other/b.jpg')
    destination=root/'destination';destination.mkdir()
    if collision=='existing':(destination/'b.jpg').write_bytes(b'keep')
    if collision=='symlink':(destination/'b.jpg').symlink_to(b)
    if collision in ('selected','casefold'):
        b=picture(root/'other'/('a.jpg' if collision=='selected' else 'A.JPG'))
    if collision=='sidecar':
        a.with_suffix('.xmp').write_bytes(packet('<dc:title>A</dc:title>'))
        (destination/'a.xmp').write_bytes(b'keep')
    plan=ready(s,root,[a,b],skip_duplicates=False);before={p.name:os.lstat(p).st_ino for p in destination.iterdir()}
    result=apply(s,plan)
    assert result['state']=='interrupted' and result['copy']['copied']==0
    assert {p.name:os.lstat(p).st_ino for p in destination.iterdir()}==before
    assert s.dispatch('status')['photos']==0
    assert s.dispatch('cancel_import',{'plan_id':plan['id']})['plan']['state']=='cancelled'


@pytest.mark.parametrize('kind',['destination','ancestor','source','sidecar'])
def test_symlink_substitution_cannot_redirect_copy(library,kind):
    s,root=library;a=picture(root/'source/a.jpg');xmp=a.with_suffix('.xmp')
    xmp.write_bytes(packet('<dc:title>A</dc:title>'))
    plan=ready(s,root,[a],subfolder='Album')
    outside=root/'outside';outside.mkdir()
    if kind=='destination':
        (root/'destination').rename(root/'old');(root/'destination').symlink_to(outside)
    elif kind=='ancestor':(root/'destination/Album').symlink_to(outside)
    else:
        path=a if kind=='source' else xmp
        moved=outside/path.name;path.rename(moved);path.symlink_to(moved)
    result=apply(s,plan)
    assert result['state']=='interrupted' and s.dispatch('status')['photos']==0
    assert not list(outside.glob('*.part'))
    assert not (outside/'Album').exists()


@pytest.mark.parametrize('point',['writing','sealed','linked','published'])
def test_restart_recovers_owned_copy_without_duplicate_or_overwrite(library,monkeypatch,point):
    s,root=library;a=picture(root/'a.jpg');plan=ready(s,root,[a])
    original=ImportCopy.save
    fired=False
    def fail(self,row,**patch):
        nonlocal fired
        # 'linked' models loss after exclusive publication, before its SQL receipt.
        if point=='linked' and patch.get('state')=='published' and not fired:
            fired=True;raise SystemExit('injected process death')
        original(self,row,**patch)
        if patch.get('state')==point and not fired:
            fired=True;raise SystemExit('injected process death')
    monkeypatch.setattr(ImportCopy,'save',fail)
    with pytest.raises(SystemExit):apply(s,plan)
    assert s.dispatch('status')['photos']==0
    monkeypatch.setattr(ImportCopy,'save',original)
    s.close()
    restarted=Service(root/'catalog',presets_root=root/'presets')
    try:
        pending=restarted.dispatch('get_import')['plan']
        assert pending['state']=='interrupted' and pending['phase']=='copying'
        with pytest.raises(ValueError,match='Resume Copy'):
            restarted.dispatch('scan_import',{'plan_id':pending['id'],'expected_revision':pending['revision']})
        assert resume(restarted,pending)['state']=='applied'
        assert (root/'destination/a.jpg').read_bytes()==a.read_bytes()
        assert restarted.dispatch('status')['photos']==1
        assert not list((root/'destination').glob('*.part'))
    finally:restarted.close()


def test_unowned_equal_bytes_and_modified_published_copy_are_not_adopted(library,monkeypatch):
    s,root=library;a=picture(root/'a.jpg');plan=ready(s,root,[a])
    original=io.transfer
    def interfere(row,value,save,cancelled):
        Path(row['target']).write_bytes(a.read_bytes())
        return original(row,value,save,cancelled)
    monkeypatch.setattr(io,'transfer',interfere)
    pending=apply(s,plan)
    assert pending['state']=='interrupted' and pending['copy']['copied']==0
    assert (root/'destination/a.jpg').read_bytes()==a.read_bytes()
    monkeypatch.setattr(io,'transfer',original)
    assert resume(s,pending)['state']=='interrupted'
    assert s.dispatch('status')['photos']==0


def test_cancel_during_copy_releases_catalog_and_preserves_completed_outputs(library,monkeypatch):
    s,root=library;a=picture(root/'a.jpg');b=picture(root/'b.jpg');plan=ready(s,root,[a,b])
    entered=threading.Event();release=threading.Event();result=[];original=io.transfer
    def slow(row,*args):
        if Path(row['source']).name=='b.jpg':entered.set();assert release.wait(5)
        return original(row,*args)
    monkeypatch.setattr(io,'transfer',slow)
    thread=threading.Thread(target=lambda:result.append(apply(s,plan)));thread.start()
    try:
        assert entered.wait(3)
        assert s.dispatch('status')['photos']==0
        s.dispatch('cancel_import',{'plan_id':plan['id']})
    finally:release.set();thread.join(5)
    assert not thread.is_alive() and result[0]['state']=='cancelled'
    assert (root/'destination/a.jpg').read_bytes()==a.read_bytes() and not (root/'destination/b.jpg').exists()
    assert s.dispatch('get_import')['items']==[]
    assert transfers(s,plan)[0]['state']=='published'
    assert not list((root/'destination').glob('*.part'))


def test_sql_failure_retains_copies_for_explicit_resume(library):
    s,root=library;a=picture(root/'a.jpg');plan=ready(s,root,[a])
    with s.catalog() as c,c.db:
        c.db.execute("CREATE TRIGGER copy_fault BEFORE INSERT ON photos BEGIN SELECT RAISE(ABORT,'copy fault'); END")
    pending=apply(s,plan)
    assert pending['state']=='interrupted' and pending['copy']['copied']==1
    assert s.dispatch('status')['photos']==0
    with s.catalog() as c,c.db:c.db.execute('DROP TRIGGER copy_fault')
    before=(root/'destination/a.jpg').stat().st_ino
    assert resume(s,pending)['state']=='applied'
    assert (root/'destination/a.jpg').stat().st_ino==before
    counts(s)


def test_backup_cannot_resume_or_clean_original_catalog_transfer(library,monkeypatch):
    s,root=library;a=picture(root/'a.jpg');plan=ready(s,root,[a])
    original=ImportCopy.save
    def die(self,row,**patch):
        original(self,row,**patch)
        if patch.get('state')=='sealed':raise SystemExit()
    monkeypatch.setattr(ImportCopy,'save',die)
    with pytest.raises(SystemExit):apply(s,plan)
    scratch=next((root/'destination').glob('*.part'));before=scratch.read_bytes()
    monkeypatch.setattr(ImportCopy,'save',original)
    with s.catalog() as c:backup_catalog(c,root/'backup.sqlite')
    restore_catalog(root/'backup.sqlite',root/'restored')
    restored=Service(root/'restored',presets_root=root/'presets')
    try:
        pending=restored.dispatch('get_import')['plan']
        result=resume(restored,pending)
        assert result['state']=='interrupted' and 'another catalog' in result['error']
        restored.dispatch('cancel_import',{'plan_id':plan['id']})
        assert scratch.read_bytes()==before and not (root/'destination/a.jpg').exists()
    finally:restored.close()


def test_additive_schema_25_upgrade_is_atomic_and_keeps_existing_review(tmp_path,monkeypatch):
    from lumaraw import import_copy
    from lumaraw import catalog as module
    from legacy_catalog import migrate_to
    migration=import_copy.migrate
    with monkeypatch.context() as context:
        context.setattr(module,'migrate',lambda db:migrate_to(db,25))
        c=Catalog(tmp_path/'old')
    c.db.execute("INSERT INTO import_plans(include_subfolders,created) VALUES(1,1)");c.db.commit()
    assert c.db.execute('PRAGMA user_version').fetchone()[0]==25
    c.db.set_authorizer(lambda action,a,b,d,t:sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_CREATE_TABLE and a=='import_copy_plans' else sqlite3.SQLITE_OK)
    with pytest.raises(sqlite3.DatabaseError):migration(c.db)
    assert c.db.execute('PRAGMA user_version').fetchone()[0]==25
    assert 'catalog_path' not in {r[1] for r in c.db.execute('PRAGMA table_info(import_files)')}
    c.db.set_authorizer(None);migration(c.db);migration(c.db)
    assert c.db.execute('PRAGMA user_version').fetchone()[0]==26
    assert c.db.execute('SELECT count(*) FROM import_plans').fetchone()[0]==1
    c.close()


def test_shared_sidecar_and_captured_presets_apply_to_destination_references(library):
    from test_import_processing import metadata, develop, choice, set_processing
    s,root=library;template=picture(root/'template.jpg')
    s.dispatch('import_photos',{'paths':[str(template)]})
    d=develop(s,{'exposure':1.5});m=metadata(s,{'title':'Preset','keywords':['Copied | Preset']})
    a=picture(root/'source/same.jpg');b=picture(root/'source/same.png')
    a.with_suffix('.xmp').write_bytes(packet('<dc:title>Sidecar</dc:title>'))
    plan=ready(s,root,[a,b])
    set_processing(s,develop_preset=choice(s,'develop',d),metadata_preset=choice(s,'metadata',m),keywords=['Extra'])
    plan=s.dispatch('get_import')['plan']
    result=apply(s,plan)
    assert result['state']=='applied' and result['copy']['copied']==3 and result['imported']==2
    for id_ in (2,3):
        photo=s.dispatch('get_photo',{'photo_id':id_})
        assert photo['title']=='Preset' and photo['recipe']['exposure']==1.5
        assert set(photo['keywords'])=={'Copied | Preset','Extra'}
        assert str(root/'destination') in photo['path']


def test_published_checksum_damage_with_preserved_stat_blocks_recovery(library,monkeypatch):
    s,root=library;a=picture(root/'a.jpg');plan=ready(s,root,[a]);original=ImportCopy.save
    def die(self,row,**patch):
        original(self,row,**patch)
        if patch.get('state')=='published':raise OSError('lost acknowledgement')
    monkeypatch.setattr(ImportCopy,'save',die)
    pending=apply(s,plan);target=root/'destination/a.jpg';stat=target.stat()
    data=target.read_bytes();target.write_bytes(bytes([data[0]^1])+data[1:]);os.utime(target,ns=(stat.st_atime_ns,stat.st_mtime_ns))
    monkeypatch.setattr(ImportCopy,'save',original)
    result=resume(s,pending)
    assert result['state']=='interrupted' and 'checksum' in result['error'] and s.dispatch('status')['photos']==0
    assert target.read_bytes()!=a.read_bytes()


def test_write_failure_keeps_journal_and_cancel_cleans_only_owned_partial(library,monkeypatch):
    s,root=library;a=picture(root/'a.jpg');plan=ready(s,root,[a]);original=os.write
    def fail(fd,data):raise OSError('No space left on test device')
    monkeypatch.setattr(io.os,'write',fail)
    pending=apply(s,plan)
    assert pending['state']=='interrupted' and 'No space' in pending['error']
    monkeypatch.setattr(io.os,'write',original)
    scratch=next((root/'destination').glob('*.part'))
    s.dispatch('cancel_import',{'plan_id':plan['id']})
    assert not scratch.exists() and not (root/'destination/a.jpg').exists() and a.exists()


def test_unjournalled_temporary_is_preserved_and_reported(library,monkeypatch):
    s,root=library;a=picture(root/'a.jpg');plan=ready(s,root,[a]);original=ImportCopy.save
    def die(self,row,**patch):
        if patch.get('state')=='writing':raise OSError('lost ownership commit')
        original(self,row,**patch)
    monkeypatch.setattr(ImportCopy,'save',die)
    pending=apply(s,plan);scratch=next((root/'destination').glob('*.part'))
    monkeypatch.setattr(ImportCopy,'save',original)
    assert resume(s,pending)['state']=='interrupted'
    cancelled=s.dispatch('cancel_import',{'plan_id':plan['id']})['plan']
    assert scratch.exists() and 'scratch files' in cancelled['error']


def test_large_transfer_journal_and_selection_pages_stay_bounded(library):
    s,root=library
    photos=[picture(root/'source'/f'{i:03}.jpg',clock=False) for i in range(125)]
    plan=ready(s,root,[root/'source'])
    assert len(s.dispatch('get_import')['items'])==60
    result=apply(s,plan);assert result['imported']==125
    first=s.dispatch('get_import_copies',{'plan_id':plan['id']})
    last=s.dispatch('get_import_copies',{'plan_id':plan['id'],'offset':120})
    assert first['total']==125 and len(first['items'])==60 and len(last['items'])==5
    counts(s)


@pytest.mark.parametrize('kind',['nested','catalog','traversal','add_options'])
def test_invalid_destination_contract_never_creates_plan(library,kind):
    s,root=library;a=picture(root/'source/a.jpg');destination=root/'destination';destination.mkdir()
    options={'mode':'copy','destination':str(destination)}
    if kind=='nested':options['destination']=str(a.parent)
    if kind=='catalog':options['destination']=str(s.root)
    if kind=='traversal':options['subfolder']='../escape'
    if kind=='add_options':options['mode']='add'
    with pytest.raises(ValueError):prepare(s,[a.parent],**options)
    assert s.dispatch('get_import')['plan'] is None and not list(destination.iterdir())
