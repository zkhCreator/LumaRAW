"""Partial presets, cross-catalog storage and transactional application contracts.

Generated photographs and isolated user directories verify captured revisions,
selected fields, bounded lists/history, original/job safety and retained LUT assets.
Legacy migration uses the actual schema-15 chain. No Adobe rendering, preset-file
compatibility or native desktop acceptance is established here.
"""
import json
from pathlib import Path
import sqlite3
import threading

from PIL import Image
import pytest

from lumaraw.catalog import Catalog
from lumaraw.develop_presets import migrate
from lumaraw.model import Recipe
from lumaraw.service import Service


@pytest.fixture
def library(tmp_path):
    paths=[]
    for i in range(3):
        path=tmp_path/f'{i}.png'
        Image.new('RGB',(24,16),('navy','orange','teal')[i]).save(path)
        paths.append(path)
    s=Service(tmp_path/'catalog',presets_root=tmp_path/'presets')
    s.dispatch('queue_control',{'action':'pause'})
    s.dispatch('import_photos',{'paths':list(map(str,paths))})
    yield s,paths
    s.close()


def state(s,**options):
    return s.dispatch('list_develop_presets',options)


def photo(s,id_=1):
    return s.dispatch('get_photo',{'photo_id':id_})


def edit(s,patch,id_=1):
    return s.dispatch('edit_photo',{'photo_id':id_,'expected_revision':photo(s,id_)['revision'],'patch':patch})


def save(s,name='Custom',fields=('exposure','contrast'),**options):
    return s.dispatch('save_develop_preset',{'photo_id':1,'expected_photo_revision':photo(s)['revision'],
        'fields':list(fields),'name':name,'group_name':'User Presets','expected_revision':state(s)['revision'],**options})


def action(s,kind,**options):
    return s.dispatch('develop_preset_action',{'action':kind,'expected_revision':state(s)['revision'],**options})


def get(s,id_):
    return s.dispatch('get_develop_preset',{'preset_id':id_,'expected_revision':state(s)['revision']})['preset']


def apply(s,id_,ids=(2,3),**options):
    return s.dispatch('apply_develop_preset',{'preset_id':id_,'expected_revision':state(s)['revision'],
        'targets':[{'photo_id':i,'expected_revision':photo(s,i)['revision']} for i in ids],**options})


def test_partial_application_preserves_unchecked_state_jobs_originals_and_undo(library,tmp_path):
    s,paths=library
    originals=[p.read_bytes() for p in paths]
    edit(s,{'exposure':1.2,'contrast':13,'crop':'4:5','masks':[{'kind':'radial','exposure':.8}]})
    edit(s,{'temperature':22,'crop_box':[.1,.2,.9,.95],'masks':[{'kind':'linear','exposure':-.4}]},2)
    s.dispatch('orient_photos',{'action':'rotate_right','targets':[{'photo_id':2,'expected_revision':photo(s,2)['revision']}]})
    before=photo(s,2)
    job=s.dispatch('enqueue_exports',{'photo_ids':[2],'destination':str(tmp_path/'exports'),
        'format':'jpeg','request_key':'frozen'})['job_ids'][0]
    frozen=s.dispatch('get_job',{'job_id':job})
    id_=save(s)['preset_id']
    assert get(s,id_)['patch']=={'exposure':1.2,'contrast':13}
    result=apply(s,id_)
    after=photo(s,2)
    assert result['updated']==[2,3] and result['targeted']==2
    assert after['recipe']=={**before['recipe'],'exposure':1.2,'contrast':13}
    assert after['orientation']==1 and after['metadata_revision']==before['metadata_revision']
    assert s.dispatch('get_job',{'job_id':job})==frozen
    with s.catalog() as c:
        assert c.db.execute('SELECT label FROM history WHERE photo_id=2 ORDER BY id DESC LIMIT 1').fetchone()[0]=='Preset: Custom'
        count=c.db.execute('SELECT COUNT(*) FROM history').fetchone()[0]
    assert apply(s,id_)['updated']==[]
    with s.catalog() as c:
        assert c.db.execute('SELECT COUNT(*) FROM history').fetchone()[0]==count
    s.dispatch('undo_photo',{'photo_id':2,'expected_revision':after['revision']})
    assert photo(s,2)['recipe']==before['recipe'] and photo(s,2)['orientation']==1
    assert [p.read_bytes() for p in paths]==originals


def test_lifecycle_group_visibility_favorites_and_duplicate_policy(library):
    s,_=library
    assert len(state(s)['presets'])==5
    id_=save(s,name='色彩 %_ Look',group_name='旅行')['preset_id']
    assert state(s,search='%_')['total']==1 and state(s,search='旅行')['total']==1
    action(s,'favorite',preset_id=id_,favorite=True)
    assert [r['id'] for r in state(s,favorites=True)['presets']]==[id_]
    action(s,'rename',preset_id=id_,name='Renamed')
    action(s,'move',preset_id=id_,group_name='Other')
    row=get(s,id_)
    assert row['name']=='Renamed' and row['group_name']=='Other' and row['favorite']==1
    action(s,'group_rename',group_id=row['group_id'],name='Different')
    action(s,'group_visibility',group_id=row['group_id'],visible=False)
    assert state(s,search='Different')['total']==0
    assert state(s,search='Different',include_hidden=True)['total']==1
    copied=action(s,'duplicate',preset_id=id_,name='Copy',group_name='User Presets')['preset_id']
    assert copied!=id_ and get(s,copied)['patch']==row['patch']
    with pytest.raises(ValueError,match='already exists'):
        save(s,name='Copy')
    edit(s,{'exposure':2})
    assert save(s,name='Copy',duplicate_policy='replace')['preset_id']==copied
    assert get(s,copied)['patch']['exposure']==2
    another=save(s,name='Copy',duplicate_policy='duplicate')['preset_id']
    assert another!=copied and state(s,search='Copy')['total']==2
    with pytest.raises(ValueError,match='already exists'):
        save(s,name='Copy',duplicate_policy='replace')
    action(s,'delete',preset_id=copied)
    with pytest.raises(ValueError,match='does not exist'):
        get(s,copied)
    assert photo(s)['recipe']['exposure']==2
    for method in ('delete','rename','move'):
        options={'name':'Oops'} if method=='rename' else {'group_name':'Other'} if method=='move' else {}
        with pytest.raises(ValueError,match='Built-in'):
            action(s,method,preset_id='builtin-0',**options)
    with pytest.raises(ValueError,match='Built-in'):
        save(s,preset_id='builtin-0')
    action(s,'favorite',preset_id='builtin-0',favorite=True)
    assert get(s,'builtin-0')['favorite']==1


def test_shared_and_catalog_storage_never_move_presets(library,tmp_path):
    a,paths=library
    b=Service(tmp_path/'other',presets_root=tmp_path/'presets')
    try:
        b.dispatch('import_photos',{'paths':[str(paths[0])]})
        shared=save(a,name='Shared')['preset_id']
        assert get(b,shared)['name']=='Shared'
        old=state(a)['revision']
        action(b,'storage',store_with_catalog=True)
        assert state(a)['store_with_catalog'] and state(a,search='Shared')['total']==0
        with pytest.raises(ValueError,match='storage changed'):
            apply(a,shared,expected_revision=old)
        local=save(a,name='Only A')['preset_id']
        assert state(b,search='Only A')['total']==0
        action(a,'storage',store_with_catalog=False)
        assert get(a,shared)['name']=='Shared' and state(a,search='Only A')['total']==0
        action(a,'storage',store_with_catalog=True)
        assert get(a,local)['name']=='Only A'
    finally:
        b.close()


def test_captured_library_source_and_all_target_revisions(library):
    s,_=library
    edit(s,{'exposure':1})
    id_=save(s)['preset_id']
    token=state(s)['revision']
    action(s,'favorite',preset_id=id_,favorite=True)
    with pytest.raises(ValueError,match='presets or storage changed'):
        apply(s,id_,expected_revision=token)
    with pytest.raises(ValueError,match='Source photo changed'):
        save(s,expected_photo_revision=0)
    before=[photo(s,i) for i in (2,3)]
    for targets in ([{'photo_id':2,'expected_revision':0},{'photo_id':3,'expected_revision':9}],
                    [{'photo_id':2,'expected_revision':0},{'photo_id':999,'expected_revision':0}],
                    [{'photo_id':2,'expected_revision':0}]*2):
        with pytest.raises(ValueError):
            apply(s,id_,targets=targets)
    assert [photo(s,i) for i in (2,3)]==before
    with s.catalog() as c:
        c.db.execute("CREATE TRIGGER fail_preset BEFORE UPDATE OF recipe ON photos WHEN NEW.id=3 BEGIN SELECT RAISE(ABORT,'preset fault'); END")
        c.db.commit()
    with pytest.raises(sqlite3.IntegrityError,match='preset fault'):
        apply(s,id_)
    assert [photo(s,i) for i in (2,3)]==before
    with s.catalog() as c:
        assert c.db.execute('SELECT COUNT(*) FROM history WHERE photo_id IN (2,3)').fetchone()[0]==0


def test_bounded_lists_exclude_payloads_and_application_avoids_full_photo_details(library,monkeypatch):
    s,_=library
    edit(s,{'exposure':1})
    id_=save(s)['preset_id']
    with s.develop_presets.transaction() as (_,_,db,_):
        db.executemany('INSERT INTO develop_presets VALUES(?,?,?,?,?,?,0,0)',
            [(f'test-{i}',f'Test {i:03}',f'test {i:03}','user','{"exposure":1}',1) for i in range(95)])
    first=state(s,search='Test')
    last=state(s,search='Test',offset=999)
    assert first['total']==95 and len(first['presets'])==30 and last['offset']==90 and len(last['presets'])==5
    assert all('patch' not in row for row in first['presets'])
    assert len(json.dumps(first).encode())<25000
    monkeypatch.setattr(Catalog,'photo',lambda *args: (_ for _ in ()).throw(AssertionError('Full details forbidden')))
    assert s.dispatch('apply_develop_preset',{'preset_id':id_,'expected_revision':first['revision'],
        'targets':[{'photo_id':2,'expected_revision':0}]})['updated']==[2]


def test_lut_is_retained_across_catalogs_and_local_backup(library,tmp_path):
    s,paths=library
    lut=tmp_path/'identity.cube'
    lut.write_text('LUT_3D_SIZE 2\n'+'\n'.join(f'{r} {g} {b}' for b in (0,1) for g in (0,1) for r in (0,1)))
    asset=s.dispatch('import_asset',{'kind':'lut','path':str(lut)})['asset']
    edit(s,{'lut':asset,'lut_amount':40})
    id_=save(s,fields=('lut','lut_amount'))['preset_id']
    saved=get(s,id_)['patch']['lut']
    assert Path(saved['path']).parent!=Path(asset['path']).parent
    Path(asset['path']).unlink()
    other=Service(tmp_path/'other',presets_root=tmp_path/'presets')
    try:
        other.dispatch('import_photos',{'paths':[str(paths[0])]})
        apply(other,id_,ids=(1,))
        copied=photo(other)['recipe']['lut']
        assert Path(copied['path']).parent==other.root/'assets'
        assert Path(copied['path']).read_bytes()==lut.read_bytes()
        action(other,'storage',store_with_catalog=True)
        local=save(other,name='Local LUT',fields=('lut','lut_amount'))['preset_id']
        backup=tmp_path/'backup.sqlite'
        other.dispatch('backup_catalog',{'path':str(backup)})
        restored=other.dispatch('restore_catalog',{'path':str(backup),'destination':str(tmp_path/'restored')})
        r=Service(restored['catalog'],presets_root=tmp_path/'presets')
        try:
            rebound=get(r,local)['patch']['lut']
            assert Path(rebound['path']).parent==r.root/'assets' and Path(rebound['path']).read_bytes()==lut.read_bytes()
        finally:
            r.close()
    finally:
        other.close()


def test_asset_staging_releases_lock_and_rechecks_captured_state(library,monkeypatch):
    s,_=library
    from lumaraw import develop_presets as module
    actual=module.stage_lut
    def staged(patch,root):
        done=threading.Event()
        def concurrent():
            try:
                s.dispatch('list_photos')
            finally:
                done.set()
        thread=threading.Thread(target=concurrent,daemon=True)
        thread.start()
        assert done.wait(3),'Catalog lock held during asset staging'
        edit(s,{'exposure':2})
        return actual(patch,root)
    monkeypatch.setattr(module,'stage_lut',staged)
    with pytest.raises(ValueError,match='Source photo changed'):
        save(s)
    assert state(s,search='Custom')['total']==0


def test_camera_compatibility_and_history_limit(library):
    s,_=library
    profile={'camera':'Nikon Test','space':'LibRaw-ProPhoto-D65-linear','matrix':[[1,0,0],[0,1,0],[0,0,1]]}
    edit(s,{'camera_profile':profile})
    id_=save(s,fields=('camera_profile',))['preset_id']
    with s.catalog() as c,c.db:
        c.db.execute("UPDATE photos SET camera='Nikon Test' WHERE id=2")
    with pytest.raises(ValueError,match='incompatible'):
        apply(s,id_)
    assert photo(s,2)['recipe']['camera_profile']=={}
    assert apply(s,id_,ids=(2,))['updated']==[2]
    edit(s,{'exposure':1})
    light=save(s,name='Light',fields=('exposure',))['preset_id']
    for _ in range(26):
        edit(s,{'exposure':0},2)
        apply(s,light,ids=(2,))
    with s.catalog() as c:
        assert c.db.execute('SELECT COUNT(*) FROM history WHERE photo_id=2').fetchone()[0]==50


@pytest.mark.parametrize('change',['target','storage'])
def test_apply_revalidates_after_asset_staging(library,monkeypatch,change):
    s,_=library
    from lumaraw import develop_presets as module
    edit(s,{'exposure':1})
    id_=save(s)['preset_id']
    untouched=photo(s,3)
    actual=module.stage_lut
    def staged(patch,root):
        if change=='target':
            edit(s,{'contrast':7},2)
        else:
            action(s,'storage',store_with_catalog=True)
        return actual(patch,root)
    monkeypatch.setattr(module,'stage_lut',staged)
    with pytest.raises(ValueError,match='conflict|storage changed'):
        apply(s,id_)
    assert photo(s,3)==untouched
    assert photo(s,2)['recipe']['exposure']==0
    with s.catalog() as c:
        assert c.db.execute("SELECT COUNT(*) FROM history WHERE label LIKE 'Preset:%'").fetchone()[0]==0


def test_corrupt_or_replaced_lut_never_overwrites_assets_or_applies(library,tmp_path):
    s,_=library
    lut=tmp_path/'identity.cube'
    lut.write_text('LUT_3D_SIZE 2\n'+'\n'.join(f'{r} {g} {b}' for b in (0,1) for g in (0,1) for r in (0,1)))
    asset=s.dispatch('import_asset',{'kind':'lut','path':str(lut)})['asset']
    edit(s,{'lut':asset})
    id_=save(s,fields=('lut',))['preset_id']
    before=[photo(s,i) for i in (2,3)]
    target=Path(asset['path'])
    target.write_text('corrupted destination')
    with pytest.raises(ValueError,match='failed checksum'):
        apply(s,id_)
    assert target.read_text()=='corrupted destination'
    target.unlink()
    target.symlink_to(lut)
    with pytest.raises(ValueError,match='failed checksum'):
        apply(s,id_)
    assert target.is_symlink() and target.read_bytes()==lut.read_bytes()
    target.unlink()
    Path(get(s,id_)['patch']['lut']['path']).write_text('corrupted preset source')
    with pytest.raises(ValueError,match='checksum changed'):
        apply(s,id_)
    assert not target.exists() and [photo(s,i) for i in (2,3)]==before
    assert not list((s.root/'assets').glob('.preset-*'))


def test_genuine_v15_migration_is_atomic_and_preserves_recipes_jobs(tmp_path,monkeypatch):
    from lumaraw import catalog as module
    from legacy_catalog import migrate_to
    root=tmp_path/'old'
    with monkeypatch.context() as context:
        context.setattr(module,'migrate',lambda db:migrate_to(db,15))
        c=Catalog(root)
        recipe=json.dumps(Recipe(exposure=1,rotation=90).dict())
        with c.db:
            c.db.execute('INSERT INTO photos(path,name,bytes,mtime,recipe,created,orientation) VALUES(?,?,0,0,?,0,5)',
                         (str(tmp_path/'old.png'),'old.png',recipe))
            c.db.execute("INSERT INTO jobs(photo_id,source,recipe,destination,format,created,orientation) VALUES(1,?,?,?,'jpeg',0,5)",
                         (str(tmp_path/'old.png'),recipe,str(tmp_path/'out')))
        c.db.set_authorizer(lambda action,a,b,d,t:sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_INSERT and a=='develop_presets' else sqlite3.SQLITE_OK)
        with pytest.raises(sqlite3.DatabaseError):
            migrate(c.db)
        c.db.set_authorizer(None)
        assert c.db.execute('PRAGMA user_version').fetchone()[0]==15
        assert not c.db.execute("SELECT name FROM sqlite_master WHERE name='develop_preset_state'").fetchone()
        c.close()
    c=Catalog(root)
    try:
        migrate(c.db)
        assert c.db.execute('PRAGMA user_version').fetchone()[0]==16
        assert c.db.execute('SELECT COUNT(*) FROM develop_presets').fetchone()[0]==5
        assert c.db.execute('SELECT recipe,orientation FROM photos').fetchone()[:]==(recipe,5)
        assert c.db.execute('SELECT recipe,orientation FROM jobs').fetchone()[:]==(recipe,5)
    finally:
        c.close()
