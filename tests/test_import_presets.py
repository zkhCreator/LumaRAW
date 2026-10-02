"""Source-neutral import snapshots, atomic rescans and migration/revision safety.

Disposable photos and isolated libraries exercise Copy/Add, metadata and naming,
all-or-nothing replacement across unlocked filesystem checks, and bounded listing.
No Adobe preset interchange or desktop interaction acceptance is implied.
"""
import json
import sqlite3

import pytest

from lumaraw import import_presets
from lumaraw.service import Service
from lumaraw.catalog import Catalog
from test_import_review import library, picture, prepare, scan, apply
from test_import_copy import ready
from test_import_naming import configure
from test_import_backup import backup_ready, folder
from test_import_processing import metadata, choice, set_processing, develop
from legacy_catalog import migrate_to, seed_photo


def save(s, name='Travel', preset_id=None, plan=None, revision=None):
    plan = plan or s.dispatch('get_import')['plan']
    params = {'name':name, 'plan_id':plan['id'], 'expected_plan_revision':plan['revision'],
              'expected_revision':s.dispatch('list_import_presets')['revision'] if revision is None else revision}
    if preset_id: params['preset_id'] = preset_id
    return s.dispatch('save_import_preset', params)


def ref(result):
    return {'preset_id':result['preset_id'], 'expected_revision':result['revision']}


def restart(s, plan, preset):
    return s.dispatch('restart_import_with_preset', {'plan_id':plan['id'], 'expected_revision':plan['revision'], 'preset':preset})['plan']


def test_snapshot_survives_library_edits_deletion_and_plan_cleanup(library):
    s, root = library
    s.dispatch('import_photos', {'paths':[str(picture(root/'template.jpg'))]})
    d = develop(s, {'exposure':1.25})
    m = metadata(s, {'title':'Frozen title','keywords':['Locations | Coast']})
    a = picture(root/'first/a.jpg'); b = picture(root/'second/b.jpg')
    plan = configure(s, backup_ready(s, root, [a]), custom_text='Trip')
    set_processing(s, develop_preset=choice(s,'develop',d), metadata_preset=choice(s,'metadata',m), keywords=['Additional'])
    saved = save(s)
    value = s.dispatch('get_import_preset', ref(saved))
    assert value['processing']['keyword_count'] == 1 and value['renaming']
    assert 'value' not in value and 'sources' not in value and 'develop_patch' not in value['processing']
    with s.catalog() as c:
        snapshot = c.db.execute('SELECT value FROM import_presets').fetchone()[0]
        assert str(a) not in snapshot and 'destination_identity' not in snapshot and 'Imported on ' not in snapshot
    s.dispatch('develop_preset_action', {'action':'delete', **choice(s,'develop',d)})
    s.dispatch('metadata_preset_action', {'action':'delete', **choice(s,'metadata',m)})
    current = s.dispatch('get_import')['plan']
    s.dispatch('cancel_import', {'plan_id':current['id']})
    plan = scan(s, prepare(s, [b], preset=ref(saved)))
    assert plan['preset_name'] == 'Travel' and plan['mode'] == 'copy'
    assert s.dispatch('get_import')['items'][0]['destination'].endswith('Trip-0001.jpg')
    s.dispatch('import_preset_action', {'action':'delete', **ref(saved)})
    done = apply(s, plan)
    assert done['state'] == 'applied' and (folder(done)/b.name).read_bytes() == b.read_bytes()
    new = s.dispatch('get_photo', {'photo_id':2})
    assert new['title'] == 'Frozen title' and new['recipe']['exposure'] == 1.25
    assert set(new['keywords']) == {'Additional','Locations | Coast'}
    assert not (folder(done)/a.name).exists()


def test_rename_update_delete_conflicts_and_normalized_names(library):
    s,root = library; plan = scan(s,prepare(s,[picture(root/'a.jpg')]))
    saved = save(s,'Café'); old = ref(saved)
    with pytest.raises(ValueError,match='already has'): save(s,'CAFE\u0301')
    renamed = s.dispatch('import_preset_action',{'action':'rename','name':'Trips',**old})
    with pytest.raises(ValueError,match='changed'): s.dispatch('get_import_preset',old)
    plan = s.dispatch('set_import_options',{'plan_id':plan['id'],'expected_revision':plan['revision'],'skip_duplicates':False})['plan']
    with pytest.raises(ValueError,match='changed'): save(s,preset_id=saved['preset_id'],revision=saved['revision'])
    updated = save(s,'Trips',preset_id=saved['preset_id'])
    assert not s.dispatch('get_import_preset',ref(updated))['options']['skip_duplicates']
    assert updated['preset_id'] == saved['preset_id'] and updated['total'] == 1
    with pytest.raises(ValueError,match='changed'):
        s.dispatch('import_preset_action',{'action':'delete',**old})
    assert s.dispatch('import_preset_action',{'action':'delete',**ref(updated)})['total'] == 0


def test_use_refreshes_destinations_and_accepts_explicit_overrides(library):
    s,root = library;a=picture(root/'a.jpg')
    plan = backup_ready(s,root,[a]); saved=save(s)
    s.dispatch('cancel_import',{'plan_id':plan['id']})
    destination = root/'alternate';destination.mkdir()
    plan=scan(s,prepare(s,[a],preset=ref(saved),destination=str(destination),second_copy_destination=None))
    assert plan['copy']['destination']==str(destination) and plan['copy']['backup'] is None
    s.dispatch('cancel_import',{'plan_id':plan['id']})
    plan=scan(s,prepare(s,[a],preset=ref(saved),mode='add'))
    assert plan['mode']=='add' and 'copy' not in plan
    assert apply(s,plan)['state']=='applied'


def test_stale_choice_before_scan_creates_no_plan(library):
    s,root=library;a=picture(root/'a.jpg');plan=scan(s,prepare(s,[a]));saved=save(s)
    s.dispatch('cancel_import',{'plan_id':plan['id']})
    s.dispatch('import_preset_action',{'action':'delete',**ref(saved)})
    with pytest.raises(ValueError,match='changed'):prepare(s,[a],preset=ref(saved))
    with s.catalog() as c:
        assert c.db.execute('SELECT count(*) FROM import_plans').fetchone()[0]==1
        assert not c.db.execute("SELECT 1 FROM import_plans WHERE state='planning'").fetchone()


def test_explicit_rescan_changes_mode_and_recursion_preserves_sources(library):
    s,root=library; a=picture(root/'sources/a.jpg');picture(root/'sources/child/b.jpg')
    plan=ready(s,root,[a.parent],include_subfolders=False);saved=save(s)
    s.dispatch('cancel_import',{'plan_id':plan['id']})
    previous=scan(s,prepare(s,[a.parent]));assert previous['file_count']==2
    previous=s.dispatch('select_import_items',{'plan_id':previous['id'],'expected_revision':previous['revision'],'selected':False})['plan']
    plan=restart(s,previous,ref(saved))
    assert plan['id'] != previous['id'] and plan['state']=='planning' and plan['mode']=='copy'
    assert s.dispatch('get_import',{'plan_id':previous['id']})['plan']['state']=='cancelled'
    plan=scan(s,plan);assert plan['file_count']==1 and plan['selected_count']==1
    assert s.dispatch('status')['photos']==0 and apply(s,plan)['imported']==1


@pytest.mark.parametrize('failure',['missing','symlink','inside_source','stale_plan','stale_library','sql'])
def test_failed_restart_preserves_old_review_and_checked_rows(library,monkeypatch,failure):
    from lumaraw import import_copy_io
    s,root=library;a=picture(root/'sources/a.jpg');plan=ready(s,root,[a.parent]);saved=save(s)
    original=plan
    if failure=='missing':
        from pathlib import Path
        Path(plan['copy']['destination']).rmdir()
    if failure=='symlink':
        from pathlib import Path
        dest=Path(plan['copy']['destination']);dest.rmdir();dest.symlink_to(a.parent,target_is_directory=True)
    if failure=='inside_source':
        with s.catalog() as c,c.db:
            value=json.loads(c.db.execute('SELECT value FROM import_presets').fetchone()[0]);value['options']['destination']=str(a.parent)
            c.db.execute('UPDATE import_presets SET value=?',(json.dumps(value),))
    if failure in ('stale_plan','stale_library'):
        validate=import_copy_io.validate_destination
        def changed(*args,**kwargs):
            value=validate(*args,**kwargs)
            if failure=='stale_plan':
                s.dispatch('set_import_options',{'plan_id':plan['id'],'expected_revision':plan['revision'],'skip_duplicates':False})
            else:save(s,'New')
            return value
        monkeypatch.setattr(import_copy_io,'validate_destination',changed)
    if failure=='sql':
        def failed(*args):raise sqlite3.OperationalError('injected install failure')
        monkeypatch.setattr(import_presets,'install',failed)
    with pytest.raises((ValueError,OSError,sqlite3.Error)): restart(s,plan,ref(saved))
    current=s.dispatch('get_import')['plan']
    assert current['id']==original['id'] and current['state']=='ready' and current['selected_count']==1
    assert s.dispatch('status')['photos']==0
    with s.catalog() as c:assert c.db.execute('SELECT count(*) FROM import_plans').fetchone()[0]==1


def test_no_rescan_or_preset_edit_after_copy_writes_start(library):
    s,root=library;a=picture(root/'a.jpg');plan=ready(s,root,[a]);saved=save(s)
    from pathlib import Path
    (Path(plan['copy']['destination'])/a.name).write_text('collision')
    plan=apply(s,plan);assert plan['state']=='interrupted'
    with pytest.raises(ValueError,match='changed'): restart(s,plan,ref(saved))
    with pytest.raises(ValueError,match='changed'): save(s,'Interrupted')


def test_plan_and_preset_snapshots_survive_service_restart(library):
    s,root=library;a=picture(root/'a.jpg');plan=ready(s,root,[a]);saved=save(s)
    s.close();next_service=Service(root/'catalog',presets_root=root/'presets')
    try:
        assert next_service.dispatch('get_import_preset',ref(saved))['name']=='Travel'
        plan=scan(next_service,restart(next_service,plan,ref(saved)))
        assert apply(next_service,plan)['imported']==1
    finally:next_service.close()


def test_bounded_name_pages_do_not_project_payloads(library):
    s,root=library;scan(s,prepare(s,[picture(root/'a.jpg')]));saved=save(s)
    with s.catalog() as c,c.db:
        raw=c.db.execute('SELECT value FROM import_presets').fetchone()[0]
        c.db.executemany('INSERT INTO import_presets VALUES(?,?,?,?,?)',((str(i),f'Preset {i:05}',f'preset {i:05}','add',raw) for i in range(5000)))
        sql=[];c.db.set_trace_callback(sql.append)
        page=import_presets.ImportPresets(c).list(4980)
        assert len(page['items'])==21 and page['total']==5001
        assert set(page['items'][0])=={'id','name','mode'}
        assert not any('SELECT value' in q or 'json_extract' in q for q in sql)
    assert len(json.dumps(s.dispatch('list_import_presets',{'offset':2400})))<4000


def test_schema_28_upgrade_is_atomic_and_old_reviews_remain_usable(tmp_path,monkeypatch):
    from lumaraw import catalog as module
    with monkeypatch.context() as context:
        context.setattr(module,'migrate',lambda db:migrate_to(db,28));c=Catalog(tmp_path/'old')
    seed_photo(c.db,picture(tmp_path/'a.jpg'))
    with c.db:c.db.execute("INSERT INTO import_plans(state,include_subfolders,created) VALUES('ready',1,1)")
    c.db.set_authorizer(lambda action,a,b,d,t:sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_ALTER_TABLE else sqlite3.SQLITE_OK)
    with pytest.raises(sqlite3.DatabaseError):import_presets.migrate(c.db)
    assert c.db.execute('PRAGMA user_version').fetchone()[0]==28
    assert not c.db.execute("SELECT 1 FROM sqlite_master WHERE name='import_presets'").fetchone()
    c.db.set_authorizer(None);import_presets.migrate(c.db);import_presets.migrate(c.db)
    assert c.db.execute('SELECT state,preset_name FROM import_plans').fetchone()[:] == ('ready','')
    assert c.db.execute('SELECT name FROM photos').fetchone()[0]=='a.jpg'
    assert c.db.execute('PRAGMA user_version').fetchone()[0]==29
    c.close()


def test_lut_assets_rebind_on_restore_and_corruption_preserves_review(library):
    from pathlib import Path
    from lumaraw.library import backup_catalog,restore_catalog
    s,root=library
    s.dispatch('import_photos',{'paths':[str(picture(root/'template.jpg'))]})
    lut=root/'identity.cube'
    lut.write_text('LUT_3D_SIZE 2\n'+'\n'.join(f'{r} {g} {b}' for b in (0,1) for g in (0,1) for r in (0,1)))
    asset=s.dispatch('import_asset',{'kind':'lut','path':str(lut)})['asset']
    d=develop(s,{'lut':asset});plan=scan(s,prepare(s,[picture(root/'next.jpg')]))
    set_processing(s,develop_preset=choice(s,'develop',d));saved=save(s)
    with s.catalog() as c:backup_catalog(c,root/'copy.sqlite')
    restore_catalog(root/'copy.sqlite',root/'restored')
    other=Service(root/'restored',presets_root=root/'presets-other')
    try:
        with other.catalog() as c:
            payload=import_presets.ImportPresets(c).read(**ref(saved))['value']
        captured=Path(payload['processing']['develop_patch']['lut']['path'])
        assert captured.parent==root/'restored/assets'
        pending=other.dispatch('get_import')['plan']
        fresh=scan(other,restart(other,pending,ref(saved)))
        captured.write_text('corrupt')
        with pytest.raises(ValueError):restart(other,fresh,ref(saved))
        current=other.dispatch('get_import')['plan']
        assert current['id']==fresh['id'] and current['state']=='ready'
        assert Path(asset['path']).read_text()!='corrupt'
    finally:other.close()
