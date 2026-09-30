"""Durable Develop timeline, legacy recovery and revision safety regressions.

Inputs: generated originals and genuine schema-21 catalogs. Outputs: assertions
on history states, SQL rollback, bounded pages, backups and frozen exports. No
Adobe pixel-equivalence or desktop interaction claims are made by these tests.
"""
import json
import sqlite3
from pathlib import Path

from PIL import Image
import pytest

from lumaraw.catalog import Catalog
from lumaraw.develop_history import DevelopHistory, migrate
from lumaraw.model import Recipe
from lumaraw.service import Service, ConflictError
from legacy_catalog import migrate_to, seed_photo


def test_history_tool_effect_annotations():
    from lumaraw.api import TOOLS
    assert TOOLS['clear_history']['annotations']['destructiveHint'] is True
    assert TOOLS['clear_history']['annotations']['readOnlyHint'] is False
    assert TOOLS['list_history']['annotations']['readOnlyHint'] is True


@pytest.fixture
def library(tmp_path):
    paths=[]
    for index in range(2):
        path=tmp_path/f'{index}.png'
        Image.new('RGB',(48,32),('navy','orange')[index]).save(path)
        paths.append(path)
    service=Service(tmp_path/'catalog',presets_root=tmp_path/'presets')
    service.dispatch('queue_control',{'action':'pause'})
    service.dispatch('import_photos',{'paths':list(map(str,paths))})
    yield service,paths
    service.close()


def photo(s,id_=1):
    return s.dispatch('get_photo',{'photo_id':id_})


def command(s,method,id_=1,**args):
    return s.dispatch(method,{'photo_id':id_,'expected_revision':photo(s,id_)['revision'],**args})


def edit(s,exposure,id_=1):
    return command(s,'edit_photo',id_,patch={'exposure':exposure})


def test_navigation_redo_reopen_and_branching(library):
    s,_=library
    assert command(s,'list_history')['steps']==[{'id':0,'label':'Import','created':photo(s)['created'],'current':True}]
    edit(s,1);edit(s,2);edit(s,3)
    page=command(s,'list_history');ids=[item['id'] for item in page['steps']]
    assert len(ids)==4 and page['can_undo'] and not page['can_redo']
    assert command(s,'undo_photo')['recipe']['exposure']==2
    assert len(command(s,'list_history')['steps'])==4
    # A second service opens a new catalog connection and observes the cursor.
    other=Service(s.root,presets_root=s.root/'other-presets')
    try:
        assert command(other,'list_history')['can_redo']
        assert command(other,'redo_photo')['recipe']['exposure']==3
    finally:other.close()
    command(s,'select_history',step_id=ids[2])
    assert photo(s)['recipe']['exposure']==1
    revision=photo(s)['revision']
    edit(s,1)  # No-op leaves future steps and the revision intact.
    assert photo(s)['revision']==revision and len(command(s,'list_history')['steps'])==4
    edit(s,-1)
    branched=command(s,'list_history')
    assert len(branched['steps'])==3 and not branched['can_redo']
    assert branched['cursor']>max(ids)
    with pytest.raises(ValueError,match='does not exist'):
        command(s,'select_history',step_id=ids[0])
    command(s,'select_history',step_id=0)
    assert photo(s)['recipe']['exposure']==0
    assert command(s,'redo_photo')['recipe']['exposure']==1
    assert command(s,'redo_photo')['recipe']['exposure']==-1


@pytest.mark.parametrize('method,args',[('undo_photo',{}),('redo_photo',{}),('select_history',{'step_id':0}),
    ('list_history',{}),('rename_history',{'step_id':0,'name':'Initial'}),('clear_history',{})])
def test_all_history_commands_reject_stale_revision(library,method,args):
    s,_=library
    edit(s,1);before=command(s,'list_history')
    with pytest.raises(ConflictError):
        s.dispatch(method,{'photo_id':1,'expected_revision':0,**args})
    assert command(s,'list_history')==before and photo(s)['recipe']['exposure']==1


def test_pages_are_bounded_complete_and_without_recipes(library):
    s,_=library
    for i in range(125):edit(s,(i%19-9)/10)
    first=command(s,'list_history');second=command(s,'list_history',before_id=first['next_before'])
    last=command(s,'list_history',before_id=second['next_before'])
    assert [len(p['steps']) for p in (first,second,last)]==[60,60,6]
    ids=[r['id'] for p in (first,second,last) for r in p['steps']]
    assert len(ids)==len(set(ids)) and ids==sorted(ids,reverse=True) and ids[-1]==0
    assert last['next_before'] is None and not last['has_more']
    assert 'recipe' not in json.dumps(first)
    assert not any(key.startswith('history_') for key in photo(s))
    assert command(s,'list_history',before_id=0)['steps']==[]
    with s.catalog() as c:
        plan=c.db.execute('EXPLAIN QUERY PLAN SELECT id,label,created FROM history WHERE photo_id=1 AND id<100 ORDER BY id DESC LIMIT 61').fetchall()
        assert any('history_photo' in row[3] for row in plan)


def test_summary_read_never_loads_photo_recipe_or_keyword_payloads(library,monkeypatch):
    s,_=library
    edit(s,1)
    def unexpected(*args):raise AssertionError('Full photo payload was loaded for a history summary')
    monkeypatch.setattr(Catalog,'photo',unexpected)
    result=s.dispatch('list_history',{'photo_id':1,'expected_revision':1})
    assert result['cursor']>0 and len(result['steps'])==2


def test_normalized_legacy_noop_preset_preserves_redo(library):
    s,_=library
    presets=s.dispatch('list_develop_presets')
    saved=s.dispatch('save_develop_preset',{'photo_id':1,'expected_photo_revision':0,
        'fields':['exposure'],'name':'Neutral','group_name':'Tests','expected_revision':presets['revision']})
    edit(s,1);command(s,'undo_photo')
    before=command(s,'list_history');revision=photo(s)['revision']
    # A valid old sparse recipe must compare equal after default expansion.
    with s.catalog() as c,c.db:c.db.execute("UPDATE photos SET recipe='{}' WHERE id=1")
    result=s.dispatch('apply_develop_preset',{'preset_id':saved['preset_id'],
        'expected_revision':s.dispatch('list_develop_presets')['revision'],
        'targets':[{'photo_id':1,'expected_revision':revision}]})
    assert result['updated']==[] and command(s,'list_history')==before


def test_rename_clear_snapshots_jobs_and_originals(library,tmp_path):
    s,paths=library;originals=[p.read_bytes() for p in paths]
    edit(s,1);edit(s,2)
    s.dispatch('save_version',{'photo_id':1,'name':'Keep'})
    version=s.dispatch('list_versions',{'photo_id':1})['versions'][0]['id']
    job=s.dispatch('enqueue_exports',{'photo_ids':[1],'destination':str(tmp_path/'out'),'format':'jpeg','request_key':'history'})['job_ids'][0]
    before=s.dispatch('get_job',{'job_id':job})
    page=command(s,'list_history');step=page['cursor']
    command(s,'rename_history',step_id=step,name='  Warmer sunset  ')
    assert command(s,'list_history')['current_label']=='Warmer sunset'
    revision=photo(s)['revision'];command(s,'rename_history',step_id=step,name='Warmer sunset')
    assert photo(s)['revision']==revision
    for name in (' ','A\nB'):
        with pytest.raises(ValueError):command(s,'rename_history',step_id=step,name=name)
    command(s,'undo_photo');command(s,'clear_history')
    page=command(s,'list_history')
    assert len(page['steps'])==1 and not page['can_undo'] and not page['can_redo']
    assert photo(s)['recipe']['exposure']==1
    command(s,'undo_photo');command(s,'redo_photo')
    assert photo(s)['recipe']['exposure']==1
    command(s,'restore_version',version_id=version)
    assert photo(s)['recipe']['exposure']==2
    command(s,'undo_photo');assert photo(s)['recipe']['exposure']==1
    assert s.dispatch('get_job',{'job_id':job})==before
    assert [p.read_bytes() for p in paths]==originals


def test_copy_baseline_is_current_source_recipe_and_history_is_private(library):
    s,_=library
    edit(s,2);p=photo(s)
    copy=s.dispatch('create_virtual_copies',{'targets':[{'photo_id':1,'expected_revision':p['revision'],'expected_metadata_revision':p['metadata_revision']}]})['photos'][0]['id']
    assert command(s,'list_history',copy)['steps'][0]['label']=='Virtual Copy'
    assert len(command(s,'list_history',copy)['steps'])==1
    edit(s,-1,copy);command(s,'undo_photo',copy)
    assert photo(s,copy)['recipe']['exposure']==2 and photo(s)['recipe']['exposure']==2
    with pytest.raises(ValueError,match='this photo'):
        command(s,'select_history',copy,step_id=command(s,'list_history')['cursor'])
    command(s,'clear_history',copy)
    assert len(command(s,'list_history')['steps'])==2


def test_batch_rollback_restores_timeline_and_redo(library):
    s,_=library
    edit(s,1);edit(s,2);command(s,'undo_photo')
    before=command(s,'list_history');before_photo=photo(s)
    with s.catalog() as c:
        with c.db:c.db.execute("CREATE TRIGGER history_abort BEFORE UPDATE OF recipe ON photos WHEN NEW.id=2 BEGIN SELECT RAISE(ABORT,'injected'); END")
        with pytest.raises(sqlite3.IntegrityError,match='injected'):
            with c.db:
                history=DevelopHistory(c.db)
                history.edit(1,Recipe(exposure=-2),'Batch')
                history.edit(2,Recipe(exposure=-2),'Batch')
    assert command(s,'list_history')==before and photo(s)==before_photo


def test_backup_restores_baseline_cursor_and_future_asset_paths(library,tmp_path):
    s,_=library
    cube=tmp_path/'identity.cube'
    cube.write_text('LUT_3D_SIZE 2\n0 0 0\n1 0 0\n0 1 0\n1 1 0\n0 0 1\n1 0 1\n0 1 1\n1 1 1\n')
    asset=s.dispatch('import_asset',{'path':str(cube),'kind':'lut'})['asset']
    command(s,'edit_photo',patch={'lut':asset})
    command(s,'clear_history');edit(s,1);edit(s,2);command(s,'undo_photo')
    backup=tmp_path/'backup.sqlite'
    s.dispatch('backup_catalog',{'path':str(backup)})
    target=tmp_path/'restored'
    s.dispatch('restore_catalog',{'path':str(backup),'destination':str(target)})
    restored=Service(target,presets_root=target/'presets')
    try:
        assert command(restored,'list_history')['can_redo']
        assert command(restored,'redo_photo')['recipe']['exposure']==2
        baseline=command(restored,'select_history',step_id=0)['recipe']
        assert baseline['exposure']==0 and Path(baseline['lut']['path']).parent==target/'assets'
        assert Path(baseline['lut']['path']).is_file()
    finally:restored.close()


def test_genuine_v21_migration_preserves_labels_recipes_and_rolls_back(tmp_path,monkeypatch):
    from lumaraw import catalog as module
    original=tmp_path/'original.png';Image.new('RGB',(8,8),'red').save(original)
    recipes=[json.dumps(Recipe(exposure=i).dict()) for i in (0,1,2)]
    root=tmp_path/'legacy'
    with monkeypatch.context() as context:
        context.setattr(module,'migrate',lambda db:migrate_to(db,21))
        c=Catalog(root);seed_photo(c.db,original)
        with c.db:
            c.db.execute('UPDATE photos SET recipe=?,revision=9 WHERE id=1',(recipes[2],))
            c.db.executemany('INSERT INTO history VALUES(?,1,?,?,?)',[(41,recipes[0],'First',10),(44,recipes[1],'Second',20)])
        c.db.set_authorizer(lambda action,a,b,d,t:sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_CREATE_TABLE and a=='history_identity' else sqlite3.SQLITE_OK)
        with pytest.raises(sqlite3.DatabaseError):migrate(c.db)
        c.db.set_authorizer(None)
        assert c.db.execute('PRAGMA user_version').fetchone()[0]==21
        assert 'history_cursor' not in {r[1] for r in c.db.execute('PRAGMA table_info(photos)')}
        assert [r[0] for r in c.db.execute('SELECT recipe FROM history ORDER BY id')]==recipes[:2]
        c.close()
    c=Catalog(root)
    try:
        migrate(c.db)
        h=DevelopHistory(c.db);page=h.page(1)
        assert page['cursor']==44 and page['revision']==9
        assert [(r['id'],r['label']) for r in page['steps']]==[(44,'Second'),(41,'First'),(0,'Initial retained state')]
        with c.db:
            assert h.select(1,41).exposure==1
            assert h.select(1,0).exposure==0
            assert h.select(1,44).exposure==2
    finally:c.close()
