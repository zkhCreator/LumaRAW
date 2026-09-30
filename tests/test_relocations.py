"""Missing-folder plans, content checks, atomic remaps and responsive cancellation.

Inputs: disposable nested image folders, real catalog state and injected I/O/write
failures. Outputs: preserved source identities, counts and rollback evidence. All
filesystem moves/deletions affect generated fixtures only; no desktop automation.
"""
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import threading

from PIL import Image
import pytest

from lumaraw.catalog import Catalog
from lumaraw.relocations import Relocations, migrate
from lumaraw.service import Service


@pytest.fixture
def library(tmp_path):
    old = tmp_path/'Originals'
    names = ('a.png', 'b.png', 'Child/c.png', 'Child/海边.png')
    paths = [old/name for name in names]
    for i,path in enumerate(paths):
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', (12, 8), (i*30,80,120)).save(path)
    s = Service(tmp_path/'catalog')
    s.dispatch('queue_control', {'action':'pause'})
    s.dispatch('import_photos', {'paths':list(map(str, paths))})
    yield s,old,tmp_path/'Located'
    s.close()


def photo(s, id_):
    return s.dispatch('get_photo', {'photo_id':id_})


def prepare(s, new, folder_id=None):
    if folder_id is None:
        folder_id = s.dispatch('get_folder', {'photo_id':1})['id']
    return s.dispatch('prepare_folder_relocation', {'folder_id':folder_id, 'destination':str(new),
        'expected_revision':s.dispatch('library_state')['folder_revision']})['plan']


def scan(s, plan):
    while plan['state'] in ('planning','interrupted'):
        plan = s.dispatch('scan_folder_relocation', {'plan_id':plan['id'], 'expected_revision':plan['revision']})['plan']
    return plan


def apply(s, plan):
    return s.dispatch('apply_folder_relocation', {'plan_id':plan['id'], 'expected_revision':plan['revision']})['plan']


def counts(s):
    with s.catalog() as c:
        paths = [Path(r[0]).parent for r in c.db.execute('SELECT path FROM photos')]
        for row in c.db.execute('SELECT * FROM catalog_folders'):
            path = Path(row['path'])
            assert row['direct_count'] == sum(p == path for p in paths)
            assert row['total_count'] == sum(p == path or path in p.parents for p in paths)
        assert c.db.execute('SELECT enabled FROM folder_maintenance').fetchone()[0] == 1
        assert c.db.execute('SELECT count(*) FROM folder_photos f JOIN photos p ON p.id=f.photo_id '
                            'WHERE f.folder_path!=folder_path(p.path)').fetchone()[0] == 0


def test_complete_tree_preserves_copies_metadata_stacks_and_export_snapshots(library):
    s,old,new = library
    s.dispatch('index_library')
    p = photo(s, 1)
    s.dispatch('edit_photo', {'photo_id':1, 'expected_revision':p['revision'], 'patch':{'exposure':1.5}})
    s.dispatch('edit_metadata', {'targets':[{'photo_id':1,'expected_metadata_revision':0}], 'patch':{'keywords':['Places | Coast'], 'title':'Keep'}})
    p = photo(s, 1)
    copy_id = s.dispatch('create_virtual_copies', {'targets':[{'photo_id':1,'expected_revision':p['revision'],
        'expected_metadata_revision':p['metadata_revision']}]})['photos'][0]['id']
    album = s.dispatch('save_collection', {'name':'Keep', 'kind':'regular', 'photo_ids':[1,3,copy_id]})
    s.dispatch('stack_photos', {'action':'group','photo_ids':[1,3], 'collection_id':album['id'],
                              'expected_revision':s.dispatch('stack_state')['revision']})
    with s.catalog() as c:
        before_stacks = [tuple(r) for r in c.db.execute('SELECT * FROM stack_members ORDER BY stack_id,position')]
    folder = s.dispatch('get_folder', {'photo_id':1})
    s.dispatch('edit_folder', {'folder_id':folder['id'], 'expected_revision':folder['revision'], 'patch':{'favorite':True,'color_label':'red'}})
    s.dispatch('save_version', {'photo_id':1, 'name':'Before relocation'})
    s.dispatch('enqueue_exports', {'photo_ids':[1,copy_id], 'destination':str(new.parent/'out'),
        'format':'jpeg', 'request_key':'relink-snapshot'})
    with s.catalog() as c:
        job_snapshots = [tuple(r) for r in c.db.execute('SELECT id,recipe,options,destination FROM jobs ORDER BY id')]
    before = {id_:photo(s, id_) for id_ in (1,2,3,4,copy_id)}
    old.rename(new)
    hashes = {str(p.relative_to(new)):hashlib.sha256(p.read_bytes()).digest() for p in new.rglob('*.png')}
    plan = scan(s, prepare(s,new))
    assert (plan['verified'],plan['physical_count'],plan['photo_count']) == (4,4,5)
    result = apply(s,plan)
    assert result['state'] == 'applied' and result['result_folder_id'] == folder['id']
    receipt = s.dispatch('cancel_folder_relocation', {'plan_id':plan['id']})
    assert receipt['plan']['state'] == 'applied' and receipt['total'] == 0 and receipt['items'] == []
    for id_,original in before.items():
        after = photo(s,id_)
        for field in ('id','source_id','recipe','revision','metadata_revision','keyword_tags','title','is_virtual','copy_name'):
            assert after[field] == original[field]
        assert after['source_revision'] == original['source_revision']+1
        assert after['path'] == str(new/Path(original['path']).relative_to(old))
    with s.catalog() as c:
        assert [tuple(r) for r in c.db.execute('SELECT * FROM stack_members ORDER BY stack_id,position')] == before_stacks
        assert c.db.execute("SELECT folder FROM photo_stacks WHERE scope='folder'").fetchone()[0] == str(new)
        assert all(Path(r[0]).is_relative_to(new) for r in c.db.execute('SELECT source FROM jobs'))
        assert [tuple(r) for r in c.db.execute('SELECT id,recipe,options,destination FROM jobs ORDER BY id')] == job_snapshots
        assert c.db.execute('SELECT count(*) FROM relocation_files').fetchone()[0] == 0
    assert s.dispatch('get_folder', {'folder_id':folder['id']})['color_label'] == 'red'
    assert s.dispatch('get_folder', {'folder_id':folder['id']})['favorite'] == 1
    assert len(s.dispatch('list_versions', {'photo_id':copy_id})['versions']) == 1
    assert hashes == {str(p.relative_to(new)):hashlib.sha256(p.read_bytes()).digest() for p in new.rglob('*.png')}
    counts(s)


def test_partial_relocation_preserves_missing_members_and_unindexed_paths(library):
    s,old,new = library
    old.rename(new);(new/'Child/c.png').unlink()
    plan = scan(s,prepare(s,new))
    assert (plan['missing'],plan['unverified'],plan['conflicts']) == (1,3,0)
    issues = s.dispatch('get_folder_relocation', {'plan_id':plan['id']})
    assert issues['items'][0]['source_id'] == photo(s,3)['source_id'] and issues['total'] == 1
    assert apply(s,plan)['state'] == 'applied'
    assert photo(s,3)['missing'] == 1 and photo(s,3)['path'] == str(new/'Child/c.png')
    assert photo(s,1)['missing'] == 0 and photo(s,1)['sha256'] == ''
    assert s.dispatch('list_photos', {'mode':'missing','stacked':False})['total'] == 1
    counts(s)


def test_hash_mismatch_blocks_without_relinking_any_member(library):
    s,old,new = library
    s.dispatch('index_library');old.rename(new)
    (new/'a.png').write_bytes(b'not the indexed original')
    plan = scan(s,prepare(s,new))
    assert plan['state'] == 'ready' and plan['conflicts'] == 1
    with pytest.raises(ValueError, match='file conflicts'):
        apply(s,plan)
    assert photo(s,1)['path'] == str(old/'a.png')
    assert 'differs' in s.dispatch('get_folder_relocation', {'plan_id':plan['id']})['items'][0]['error']
    s.dispatch('cancel_folder_relocation', {'plan_id':plan['id']})
    counts(s)


def test_changed_file_and_reappearing_source_invalidate_ready_plans(library):
    s,old,new = library
    old.rename(new);plan = scan(s,prepare(s,new))
    (new/'a.png').write_bytes((new/'a.png').read_bytes()+b'changed')
    result = apply(s,plan)
    assert result['state'] == 'failed' and 'changed after scanning' in result['error']
    assert photo(s,1)['path'] == str(old/'a.png')
    plan = scan(s,prepare(s,new));old.mkdir()
    result = apply(s,plan)
    assert result['state'] == 'failed' and 'available again' in result['error']
    counts(s)


def test_merge_disjoint_destination_keeps_existing_identity_and_combines_counts(library):
    s,old,new = library
    new.mkdir();extra = new/'existing.png';Image.new('RGB',(8,8)).save(extra)
    s.dispatch('import_photos', {'paths':[str(extra)]})
    original = s.dispatch('get_folder', {'photo_id':1});destination = s.dispatch('get_folder', {'photo_id':5})
    child = s.dispatch('get_folder', {'photo_id':3})
    s.dispatch('edit_folder', {'folder_id':original['id'],'expected_revision':original['revision'],'patch':{'favorite':True,'color_label':'red'}})
    s.dispatch('edit_folder', {'folder_id':destination['id'],'expected_revision':destination['revision'],'patch':{'color_label':'blue'}})
    shutil.copytree(old,new,dirs_exist_ok=True);shutil.rmtree(old)
    plan = scan(s,prepare(s,new));assert plan['merge_count'] == 1
    result = apply(s,plan);assert result['state'] == 'applied'
    merged = s.dispatch('get_folder', {'folder_id':destination['id']})
    assert result['result_folder_id'] == destination['id']
    assert merged['total_count'] == 5 and merged['favorite'] == 1 and merged['color_label'] == 'blue'
    assert s.dispatch('get_folder', {'photo_id':3})['id'] == child['id']
    with pytest.raises(ValueError, match='does not exist'):
        s.dispatch('get_folder', {'folder_id':original['id']})
    counts(s)


def test_existing_photo_destination_is_reported_as_conflict(library):
    s,old,new = library
    new.mkdir();Image.new('RGB',(8,8),'red').save(new/'a.png')
    s.dispatch('import_photos', {'paths':[str(new/'a.png')]})
    old.rename(old.with_name('Elsewhere'))
    plan = scan(s,prepare(s,new))
    assert plan['conflicts'] == 1 and plan['missing'] == 3
    assert 'already uses' in s.dispatch('get_folder_relocation', {'plan_id':plan['id']})['items'][0]['error']
    assert photo(s,1)['path'] == str(old/'a.png')


def test_metadata_only_edits_survive_but_changed_catalog_membership_rejects_plan(library):
    s,old,new = library
    old.rename(new);plan = scan(s,prepare(s,new))
    s.dispatch('edit_metadata', {'targets':[{'photo_id':1,'expected_metadata_revision':0}], 'patch':{'title':'During scan'}})
    assert apply(s,plan)['state'] == 'applied' and photo(s,1)['title'] == 'During scan'
    second = new.with_name('Again');new.rename(second)
    plan = scan(s,prepare(s,second))
    p = photo(s,1)
    s.dispatch('create_virtual_copies', {'targets':[{'photo_id':1,'expected_revision':p['revision'],'expected_metadata_revision':p['metadata_revision']}]})
    with pytest.raises(ValueError, match='folder catalog changed'):
        apply(s,plan)
    assert photo(s,1)['path'] == str(new/'a.png')
    counts(s)


def test_busy_image_worker_retains_verified_plan_for_explicit_retry(library):
    s,old,new = library
    old.rename(new);plan = scan(s,prepare(s,new))
    with s.image_lock:
        waiting = apply(s,plan)
    assert waiting['state'] == 'ready' and 'Image processing' in waiting['error']
    assert waiting['scanned'] == 4 and waiting['revision'] > plan['revision']
    assert apply(s,waiting)['state'] == 'applied'
    with pytest.raises(ValueError, match='relocation changed'):
        apply(s,waiting)


def test_cancellation_and_catalog_reads_continue_during_file_verification(library, monkeypatch):
    import lumaraw.service as module
    s,old,new = library
    old.rename(new);plan = prepare(s,new);entered = threading.Event();outcome=[]
    real = module.inspect_file
    def slow(row, cancelled):
        entered.set()
        assert cancel_requested.wait(3)
        assert cancelled()
        return real(row,cancelled)
    cancel_requested = threading.Event()
    monkeypatch.setattr(module,'inspect_file',slow)
    worker = threading.Thread(target=lambda:outcome.append(scan(s,plan)))
    worker.start()
    try:
        assert entered.wait(3)
        assert s.dispatch('list_photos', {'stacked':False})['total'] == 4
        cancelled = s.dispatch('cancel_folder_relocation', {'plan_id':plan['id']})['plan']
        assert cancelled['state'] == 'cancelled'
    finally:
        cancel_requested.set();worker.join(3)
    assert not worker.is_alive() and outcome[0]['state'] == 'cancelled'
    assert photo(s,1)['path'] == str(old/'a.png')
    counts(s)


def test_failed_sql_apply_rolls_back_paths_counts_and_maintenance_switch(library, monkeypatch):
    s,old,new = library
    old.rename(new);plan = scan(s,prepare(s,new));real = Relocations.apply
    def denied(self, *args):
        self.db.set_authorizer(lambda action,table,*rest:sqlite3.SQLITE_DENY
                              if action == sqlite3.SQLITE_UPDATE and table == 'photo_sources' else sqlite3.SQLITE_OK)
        try:
            return real(self,*args)
        finally:
            self.db.set_authorizer(None)
    monkeypatch.setattr(Relocations,'apply',denied)
    failed = apply(s,plan)
    assert failed['state'] == 'failed'
    assert all(Path(photo(s,i)['path']).is_relative_to(old) for i in range(1,5))
    counts(s)
    with s.catalog() as c:
        assert c.db.execute('SELECT count(*) FROM catalog_folders WHERE path=?',(str(new),)).fetchone()[0] == 0


def test_interrupted_scan_is_recovered_and_resumed_explicitly(library):
    s,old,new = library
    old.rename(new);plan = prepare(s,new)
    with s.catalog() as c:
        Relocations(c).start_scan(plan['id'],plan['revision'])
    root = s.root;s.close();reopened = Service(root)
    try:
        plan = reopened.dispatch('get_folder_relocation')['plan']
        assert plan['state'] == 'interrupted' and plan['scanned'] == 0
        plan = scan(reopened,plan)
        assert apply(reopened,plan)['state'] == 'applied'
        counts(reopened)
    finally:
        reopened.close()


def test_v8_migration_preserves_tables_and_rolls_back_trigger_replacement(tmp_path, monkeypatch):
    import lumaraw.catalog as module
    from lumaraw.model import Recipe
    from legacy_catalog import migrate_to,seed_photo
    with monkeypatch.context() as patch:
        patch.setattr(module,'migrate',lambda db:migrate_to(db,8))
        c = Catalog(tmp_path/'legacy')
    path = tmp_path/'legacy-photo.png';Image.new('RGB',(8,8)).save(path)
    seed_photo(c.db,path)
    # Seed the published before-action history shape, not the current writer.
    with c.db:
        c.db.execute("INSERT INTO history(photo_id,recipe,label,created) SELECT id,recipe,'Adjustments',0 FROM photos WHERE id=1")
        c.db.execute('UPDATE photos SET recipe=?,revision=1 WHERE id=1',(json.dumps(Recipe(exposure=1.25).dict()),))
    c.save_version(1,'Keep')
    # Populate the actual v8 job shape without current export-snapshot methods.
    with c.db:
        c.db.execute('INSERT INTO jobs(photo_id,source,recipe,destination,format,created,source_id) '
                     "SELECT id,path,recipe,?,'jpeg',0,source_id FROM photos WHERE id=1",(str(tmp_path/'legacy-output'),))
    with c.db:
        tag = c.db.execute("INSERT INTO keywords(name,normalized) VALUES('Coast','coast')").lastrowid
        c.db.execute('INSERT INTO keyword_photos VALUES(?,?)',(1,tag))
    tables = [r[0] for r in c.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    snapshots = {table:[tuple(r) for r in c.db.execute(f'SELECT * FROM {table}')] for table in tables}
    before = c.db.execute("SELECT sql FROM sqlite_master WHERE name='folder_photo_relinked'").fetchone()[0]
    c.db.set_authorizer(lambda action,name,*rest:sqlite3.SQLITE_DENY
                        if action == sqlite3.SQLITE_DROP_TRIGGER and name == 'folder_photo_relinked' else sqlite3.SQLITE_OK)
    with pytest.raises(sqlite3.DatabaseError):
        migrate(c.db)
    c.db.set_authorizer(None)
    assert c.db.execute('PRAGMA user_version').fetchone()[0] == 8
    assert c.db.execute("SELECT sql FROM sqlite_master WHERE name='folder_photo_relinked'").fetchone()[0] == before
    assert not c.db.execute("SELECT 1 FROM sqlite_master WHERE name='folder_relocations'").fetchone()
    migrate(c.db)
    assert c.db.execute('PRAGMA user_version').fetchone()[0] == 9
    assert 'folder_maintenance' in c.db.execute("SELECT sql FROM sqlite_master WHERE name='folder_photo_relinked'").fetchone()[0]
    assert {table:[tuple(r) for r in c.db.execute(f'SELECT * FROM {table}')] for table in tables} == snapshots
    c.close()


def test_bounded_pages_and_active_plan_backup_resume(library):
    from lumaraw.library import backup_catalog, restore_catalog
    s,old,new = library
    paths = []
    for i in range(125):
        path = old/f'page-{i}.png';shutil.copyfile(old/'a.png',path);paths.append(str(path))
    s.dispatch('import_photos', {'paths':paths})
    old.rename(new)
    # Missing files exercise the paged issue report too, without whole-tree arrays.
    for path in new.glob('page-*'):path.unlink()
    plan = prepare(s,new)
    first = s.dispatch('scan_folder_relocation', {'plan_id':plan['id'],'expected_revision':plan['revision']})
    assert first['plan']['scanned'] == 60 and first['plan']['state'] == 'planning'
    assert len(first['items']) <= 60
    assert first['total'] == 56
    all_rows = s.dispatch('get_folder_relocation', {'plan_id':plan['id'],'issues_only':False})
    assert all_rows['total'] == 129 and len(all_rows['items']) == 60
    with s.catalog() as c:
        backup_catalog(c,new.parent/'backup')
    restored = Service(restore_catalog(new.parent/'backup',new.parent/'restored'))
    try:
        plan = restored.dispatch('get_folder_relocation')['plan']
        assert plan['scanned'] == 60 and plan['state'] == 'planning'
        plan = scan(restored,plan)
        assert plan['physical_count'] == 129 and plan['scanned'] == 129 and plan['missing'] == 125
        page = restored.dispatch('get_folder_relocation', {'plan_id':plan['id'],'offset':99999})
        assert page['total'] == 125 and page['offset'] == 120 and len(page['items']) == 5
        assert apply(restored,plan)['state'] == 'applied'
        counts(restored)
    finally:
        restored.close()
    assert photo(s,1)['path'] == str(old/'a.png')


def test_running_export_defers_without_changing_snapshots(library):
    s,old,new = library
    s.dispatch('enqueue_exports', {'photo_ids':[1],'destination':str(new.parent/'out'),'format':'jpeg','request_key':'active'})
    old.rename(new);plan = scan(s,prepare(s,new))
    with s.catalog() as c,c.db:
        c.db.execute("UPDATE jobs SET state='running'")
    result = apply(s,plan)
    assert result['state'] == 'ready' and 'export' in result['error']
    assert photo(s,1)['path'] == str(old/'a.png')
    with s.catalog() as c,c.db:
        c.db.execute("UPDATE jobs SET state='interrupted'")
    assert apply(s,result)['state'] == 'applied'


def test_replaced_directory_and_source_hash_updates_reject_plan(library):
    s,old,new = library
    old.rename(new);plan = scan(s,prepare(s,new))
    replaced = new.with_name('Replacement');new.rename(replaced);new.mkdir()
    result = apply(s,plan)
    assert result['state'] == 'failed' and 'directory changed' in result['error']
    new.rmdir();replaced.rename(new)
    plan = scan(s,prepare(s,new))
    with s.catalog() as c,c.db:
        c.db.execute("UPDATE photos SET sha256='changed-by-index' WHERE id=1")
    result = apply(s,plan)
    assert result['state'] == 'failed' and 'Source metadata changed' in result['error']
    counts(s)


def test_cancel_during_final_stat_checks_preserves_all_paths(library, monkeypatch):
    import lumaraw.service as module
    s,old,new = library
    old.rename(new);plan = scan(s,prepare(s,new))
    real = module.relocation_identity;entered = threading.Event();release = threading.Event();outcome=[]
    def slow(path,directory=False):
        if not directory:
            entered.set();assert release.wait(3)
        return real(path,directory)
    monkeypatch.setattr(module,'relocation_identity',slow)
    worker = threading.Thread(target=lambda:outcome.append(apply(s,plan)));worker.start()
    try:
        assert entered.wait(3)
        assert s.dispatch('get_folder_relocation')['plan']['state'] == 'verifying'
        result = s.dispatch('cancel_folder_relocation', {'plan_id':plan['id']})
        assert result['plan']['state'] == 'cancelled'
    finally:
        release.set();worker.join(3)
    assert not worker.is_alive() and outcome[0]['state'] == 'cancelled'
    assert photo(s,1)['path'] == str(old/'a.png')
    counts(s)
