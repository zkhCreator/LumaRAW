"""Keyword preset persistence, concurrent catalogs and atomic assignment evidence.

Inputs: isolated shared stores, generated originals and a genuine schema-twelve
catalog. Outputs: bounded nine-slot/page contracts, revision conflicts, rollback,
legacy identity safety and backup preservation. No personal preset directory,
Adobe preset parsing, rendered UI or camera processing acceptance is claimed.
"""
import json
import sqlite3
import threading

from PIL import Image
import pytest

from lumaraw.catalog import Catalog
from lumaraw.keyword_sets import migrate
from lumaraw.service import Service
from test_keywords import save, assign, edit, targets, photo


@pytest.fixture
def library(tmp_path):
    paths=[tmp_path/f'{i}.png' for i in range(2)]
    for path in paths:Image.new('RGB',(8,8),'navy').save(path)
    s=Service(tmp_path/'catalog',presets_root=tmp_path/'shared')
    s.dispatch('import_photos',{'paths':list(map(str,paths))})
    yield s,paths
    s.close()


def state(s):
    return s.dispatch('list_keyword_sets')


def preset(s,name='Travel',values=None,**kwargs):
    values=['Places | Coast','海岸 🌊'] if values is None else values
    return s.dispatch('save_keyword_set',{'name':name,'slots':values+['']*(9-len(values)),
        'expected_revision':state(s)['revision'],**kwargs})


def action(s,action,**kwargs):
    return s.dispatch('keyword_set_action',{'action':action,'expected_revision':state(s)['revision'],**kwargs})


def apply(s,slot=1,ids=(1,2),**kwargs):
    return s.dispatch('apply_keyword_set',{'slot':slot,'targets':targets(s,ids),'expected_revision':state(s)['revision'],**kwargs})


def test_create_apply_draft_rename_delete_preserves_originals_recipes(library):
    s,paths=library;originals=[p.read_bytes() for p in paths]
    old=save(s,'Keep');assign(s,old,[1,2])
    initial=[photo(s,id_) for id_ in (1,2)]
    saved=preset(s);set_id=saved['selected']['id']
    assert saved['selected']['slots']==['Places | Coast','海岸 🌊']+['']*7
    assert s.dispatch('list_keywords')['total']==1  # Saving doesn't create words.
    result=apply(s)
    assert result['updated']==[1,2]
    for index,id_ in enumerate((1,2)):
        row=photo(s,id_)
        assert row['keywords']==['Keep','Places | Coast'] and row['revision']==initial[index]['revision']
        assert row['metadata_revision']==initial[index]['metadata_revision']+1
    draft=['Draft']+['']*8
    apply(s,draft_slots=draft)
    assert state(s)['selected']['slots'][0]=='Places | Coast'
    assert 'Draft' in photo(s,1)['keywords']
    updated=preset(s,'Renamed',['Other'],set_id=set_id)
    assert updated['selected']['id']==set_id and updated['selected']['name']=='Renamed'
    before=photo(s,1)
    action(s,'delete',set_id=set_id)
    assert state(s)['selected']['id']=='recent' and state(s)['total']==0
    assert before==photo(s,1) and originals==[p.read_bytes() for p in paths]


def test_shared_and_local_presets_scope_does_not_move_or_copy(library,tmp_path):
    first,_=library;second=Service(tmp_path/'other',presets_root=tmp_path/'shared')
    try:
        shared=preset(first)['selected']['id']
        assert state(second)['selected']['id']==shared
        action(first,'storage',store_with_catalog=True)
        assert state(first)['total']==state(second)['total']==0
        local=preset(first,'Local')['selected']['id']
        assert state(second)['total']==0
        action(second,'storage',store_with_catalog=False)
        assert state(first)['selected']['id']==state(second)['selected']['id']==shared
        action(second,'storage',store_with_catalog=True)
        assert state(first)['selected']['id']==local and state(second)['total']==0
    finally:second.close()
    reopened=Service(first.root,presets_root=tmp_path/'shared')
    try:assert state(reopened)['selected']['id']==local
    finally:reopened.close()


def test_cross_catalog_change_and_scope_reject_stale_tokens(library,tmp_path):
    first,_=library;second=Service(tmp_path/'other',presets_root=tmp_path/'shared')
    try:
        preset(first);captured=state(first)
        preset(second,'Other')
        with pytest.raises(ValueError,match='changed'):
            apply(first,expected_revision=captured['revision'])
        with pytest.raises(ValueError,match='changed'):
            first.dispatch('save_keyword_set',{'set_id':captured['selected']['id'],'name':'Late','slots':['']*9,
                'expected_revision':captured['revision']})
        captured=state(first)
        action(second,'storage',store_with_catalog=True)
        with pytest.raises(ValueError,match='changed'):
            apply(first,expected_revision=captured['revision'])
        # Tokens bind the catalog even when both libraries see the same shared set.
        with pytest.raises(ValueError,match='changed'):
            first.dispatch('keyword_set_action',{'action':'storage','store_with_catalog':False,
                'expected_revision':state(second)['revision']})
        assert photo(first,1)['keyword_count']==0
    finally:second.close()


def test_concurrent_shared_writers_have_one_winner(library,tmp_path):
    first,_=library;second=Service(tmp_path/'other',presets_root=tmp_path/'shared')
    barrier=threading.Barrier(2);outcomes=[]
    snapshots=[state(first),state(second)]
    def run(service,snapshot,name):
        barrier.wait()
        try:
            service.dispatch('save_keyword_set',{'name':name,'slots':['']*9,'expected_revision':snapshot['revision']})
            outcomes.append('saved')
        except ValueError as error:outcomes.append(str(error))
    threads=[threading.Thread(target=run,args=(s,snapshot,str(i))) for i,(s,snapshot) in enumerate(zip((first,second),snapshots))]
    try:
        for thread in threads:thread.start()
        for thread in threads:thread.join(10);assert not thread.is_alive()
        assert outcomes.count('saved')==1 and sum('changed' in o for o in outcomes)==1
        assert state(first)['total']==1
    finally:second.close()


def test_recent_is_bounded_tracks_additions_and_preserves_legacy_identity(library):
    s,_=library
    edit(s,[1],[f'Word {i:02}' for i in range(12)])
    recent=state(s)
    assert recent['selected']['slots']==[f'Word {i:02}' for i in range(11,2,-1)]
    edit(s,[1],['Word 01','Word 02'])  # Removing words never counts as recent use.
    assert state(s)['selected']['slots']==recent['selected']['slots']
    # Imported legacy delimiters cannot safely round-trip through a text parser.
    with s.catalog() as c,c.db:
        legacy=c.db.execute("INSERT INTO keywords(name,normalized) VALUES('Literal | Name','literal | name')").lastrowid
        c.db.execute('UPDATE keyword_state SET revision=revision+1')
    assign(s,legacy,[1]);apply(s,ids=[2])
    assert photo(s,2)['keyword_ids']==[legacy]
    s.dispatch('save_keyword',{'keyword_id':legacy,'name':'Renamed','expected_revision':s.dispatch('library_state')['keyword_revision']})
    assert state(s)['selected']['slots'][0]=='Renamed'
    s.dispatch('delete_keyword',{'keyword_id':legacy,'expected_revision':s.dispatch('library_state')['keyword_revision']})
    assert 'Renamed' not in state(s)['selected']['slots']
    with pytest.raises(ValueError,match='cannot be edited'):apply(s,draft_slots=['Unwanted']+['']*8)
    with pytest.raises(ValueError,match='cannot be deleted'):action(s,'delete',set_id='recent')


def test_all_targets_validate_and_capacity_failure_rolls_back_new_word(library):
    s,_=library
    edit(s,[2],[f'Full{i}' for i in range(100)])
    preset(s,values=['Would Be New'])
    before=state(s);photos=[photo(s,id_) for id_ in (1,2)]
    with pytest.raises(ValueError,match='100'):apply(s)
    assert state(s)==before and [photo(s,id_) for id_ in (1,2)]==photos
    assert s.dispatch('list_keywords',{'search':'Would Be New'})['total']==0
    bad=targets(s,[1,2]);bad[1]['expected_metadata_revision']-=1
    with pytest.raises(ValueError,match='conflict'):apply(s,targets=bad)
    assert state(s)==before and [photo(s,id_) for id_ in (1,2)]==photos


def test_empty_ambiguous_invalid_slots_and_duplicate_names_fail_visibly(library):
    s,_=library
    a=save(s,'A');b=save(s,'B');save(s,'Same',parent_id=a);save(s,'Same',parent_id=b)
    preset(s,values=['Same','Invalid,Two'])
    before=state(s)
    for slot,match in ((1,'Ambiguous'),(2,'delimiters'),(3,'empty')):
        with pytest.raises(ValueError,match=match):apply(s,slot)
        assert state(s)==before and photo(s,1)['keyword_count']==0
    with pytest.raises(ValueError,match='already exists'):preset(s,' travel ')
    with pytest.raises(ValueError,match='one line'):preset(s,values=['Bad\nLine'])


def test_sql_failure_rolls_back_entire_assignment_and_recent(library):
    s,_=library;preset(s)
    before=state(s)
    with s.catalog() as c,c.db:
        c.db.execute("CREATE TRIGGER fail_set BEFORE INSERT ON keyword_photos WHEN NEW.photo_id=2 BEGIN SELECT RAISE(ABORT,'injected'); END")
    with pytest.raises(sqlite3.IntegrityError,match='injected'):apply(s)
    assert state(s)==before and photo(s,1)['keyword_count']==photo(s,2)['keyword_count']==0
    assert s.dispatch('list_keywords')['total']==0


def test_large_preset_pages_keep_complete_selected_slots(library):
    s,_=library
    slots=[('🌊'*4096)]*9
    for i in range(65):preset(s,f'Set {i:03}',slots)
    first=state(s)
    last=s.dispatch('list_keyword_sets',{'offset':9999})
    assert len(first['sets'])==30 and first['total']==65 and last['offset']==60 and len(last['sets'])==5
    assert first['selected']['slots']==slots
    assert len(json.dumps(first,ensure_ascii=False).encode())<160000
    assert not any('slots' in row for row in first['sets'])


def test_genuine_v12_migration_rollback_and_catalog_backup(library,tmp_path,monkeypatch):
    import lumaraw.catalog as module
    from legacy_catalog import migrate_to
    from lumaraw.library import backup_catalog,restore_catalog
    with monkeypatch.context() as patch:
        patch.setattr(module,'migrate',lambda db:migrate_to(db,12))
        c=Catalog(tmp_path/'old')
    c.db.set_authorizer(lambda action,name,*rest:sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_CREATE_TRIGGER else sqlite3.SQLITE_OK)
    with pytest.raises(sqlite3.DatabaseError):migrate(c.db)
    c.db.set_authorizer(None)
    assert c.db.execute('PRAGMA user_version').fetchone()[0]==12
    assert not c.db.execute("SELECT 1 FROM sqlite_master WHERE name='keyword_sets'").fetchone()
    migrate(c.db);migrate(c.db);c.close()
    s,_=library
    preset(s,'Shared')
    action(s,'storage',store_with_catalog=True);preset(s,'Catalog')
    apply(s)
    with s.catalog() as c:backup_catalog(c,tmp_path/'backup')
    root=restore_catalog(tmp_path/'backup',tmp_path/'restored')
    restored=Service(root,presets_root=tmp_path/'shared')
    try:
        assert state(restored)['selected']['name']=='Catalog' and state(restored)['total']==1
        action(restored,'select',set_id='recent')
        assert state(restored)['selected']['slots'][0]=='Places | Coast'
        action(restored,'storage',store_with_catalog=False)
        assert state(restored)['selected']['name']=='Shared'
    finally:restored.close()


def test_newer_shared_schema_is_never_modified(library,tmp_path):
    s,_=library;state(s)
    path=tmp_path/'shared/keyword-sets.sqlite'
    with sqlite3.connect(path) as db:db.execute('PRAGMA user_version=2')
    before=path.read_bytes()
    with pytest.raises(ValueError,match='newer'):state(s)
    assert path.read_bytes()==before


def test_replaceable_platform_path_adapter(tmp_path,monkeypatch):
    from lumaraw import preset_paths
    monkeypatch.setenv('LUMARAW_PRESETS_ROOT',str(tmp_path/'override'))
    assert preset_paths.preset_root()==tmp_path/'override'
    monkeypatch.delenv('LUMARAW_PRESETS_ROOT')
    monkeypatch.setattr(preset_paths.sys,'platform','linux');monkeypatch.setenv('XDG_DATA_HOME',str(tmp_path))
    assert preset_paths.preset_root()==tmp_path/'lumaraw/presets'
    monkeypatch.setattr(preset_paths.sys,'platform','win32');monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    assert preset_paths.preset_root()==tmp_path/'LumaRAW/Presets'
    monkeypatch.setattr(preset_paths.sys,'platform','darwin')
    assert str(preset_paths.preset_root()).endswith('/Library/Application Support/LumaRAW/Presets')
