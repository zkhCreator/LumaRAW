"""Keyword shortcut and Painter transaction regressions with generated originals.

Inputs: captured identities/revisions, synthetic photos and genuine v13 catalogs.
Outputs: preserved recipes/originals/jobs, complete bounded pages, rollback and
shortcut persistence. Mouse gestures and desktop presentation are not simulated.
"""
import json
import sqlite3

from PIL import Image
import pytest

from lumaraw.catalog import Catalog
from lumaraw.library_painter import migrate
from lumaraw.service import Service
from test_keywords import photo,targets,save,assign,edit


@pytest.fixture
def library(tmp_path):
    paths=[tmp_path/f'{i}.png' for i in range(3)]
    for path in paths:Image.new('RGB',(8,8),'navy').save(path)
    s=Service(tmp_path/'catalog',presets_root=tmp_path/'presets')
    s.dispatch('queue_control',{'action':'pause'})
    s.dispatch('import_photos',{'paths':list(map(str,paths))})
    yield s,paths
    s.close()


def shortcut(s):return s.dispatch('get_keyword_shortcut')


def set_shortcut(s,ids=(),additions=(),**kwargs):
    return s.dispatch('set_keyword_shortcut',{'keyword_ids':list(ids),'keyword_additions':list(additions),
        'expected_revision':shortcut(s)['revision'],**kwargs})


def paint(s,ids=(1,2),kind='keywords',**kwargs):
    params={'targets':targets(s,ids),'kind':kind}
    if kind=='keywords':params['expected_shortcut_revision']=shortcut(s)['revision']
    return s.dispatch('paint_library',{**params,**kwargs})


def test_shortcut_setting_and_atomic_add_erase_preserve_recipes_jobs_originals(library,tmp_path):
    s,paths=library;originals=[p.read_bytes() for p in paths]
    keep=save(s,'Keep');assign(s,keep,[1,2])
    before=[photo(s,id_) for id_ in (1,2,3)]
    queued=s.dispatch('enqueue_exports',{'photo_ids':[1],'destination':str(tmp_path/'exports'),
        'format':'jpeg','request_key':'frozen'})['job_ids'][0]
    job=s.dispatch('get_job',{'job_id':queued})
    state=set_shortcut(s,additions=['Places | Coast','Portrait','places > coast'])
    assert state['total']==2 and [photo(s,id_) for id_ in (1,2,3)]==before
    assert s.dispatch('list_keyword_sets')['selected']['slots'][0]=='Keep'
    result=paint(s)
    assert result['updated']==[1,2] and result['keyword_ids']==state['keyword_ids']
    for index,id_ in enumerate((1,2)):
        row=photo(s,id_)
        assert row['keywords']==['Keep','Places | Coast','Portrait'] and row['revision']==before[index]['revision']
        assert row['metadata_revision']==before[index]['metadata_revision']+1
    assert photo(s,3)==before[2]
    recent=s.dispatch('list_keyword_sets')['selected']['slots']
    paint(s,ids=[2],erase=True)
    assert photo(s,2)['keywords']==['Keep'] and photo(s,1)['keyword_count']==3
    assert s.dispatch('list_keyword_sets')['selected']['slots']==recent
    assert s.dispatch('get_job',{'job_id':queued})==job
    assert originals==[p.read_bytes() for p in paths] and s.peak==0


@pytest.mark.parametrize('kind,value,column,clear',[('rating',5,'rating',0),('flag',-1,'flag',0),('label','purple','color_label','none')])
def test_painter_attributes_and_clear_are_one_metadata_change(library,kind,value,column,clear):
    s,_=library;tag=save(s,'Preserved');assign(s,tag,[1,2,3])
    before=[photo(s,id_) for id_ in (1,2,3)]
    result=paint(s,ids=[1,3],kind=kind,value=value)
    assert result['updated']==[1,3]
    for index,id_ in enumerate((1,3)):
        row=photo(s,id_);old=before[id_-1]
        assert row[column]==value and row['metadata_revision']==old['metadata_revision']+1
        assert row['revision']==old['revision'] and row['keyword_ids']==old['keyword_ids']
    assert photo(s,2)==before[1]
    paint(s,ids=[1],kind=kind,value=clear)
    assert photo(s,1)[column]==clear and photo(s,3)[column]==value


def test_stale_shortcut_and_photo_targets_fail_without_partial_writes(library):
    s,_=library
    captured=set_shortcut(s,additions=['First'])
    set_shortcut(s,additions=['Second'])
    with pytest.raises(ValueError,match='changed'):paint(s,expected_shortcut_revision=captured['revision'])
    bad=targets(s,[1,2]);bad[1]['expected_metadata_revision']+=1
    for kind,params in (('keywords',{}),('rating',{'value':4}),('flag',{'value':1}),('label',{'value':'red'})):
        before=[photo(s,id_) for id_ in (1,2)]
        with pytest.raises(ValueError,match='conflict'):paint(s,kind=kind,targets=bad,**params)
        assert [photo(s,id_) for id_ in (1,2)]==before
    with pytest.raises(ValueError,match='changed'):
        set_shortcut(s,additions=['Unwanted'],expected_revision=captured['revision'])
    assert s.dispatch('list_keywords',{'search':'Unwanted'})['total']==0


def test_capacity_missing_target_and_injected_sql_abort_rollback(library):
    s,_=library
    edit(s,[2],[f'Full {i}' for i in range(100)])
    set_shortcut(s,additions=['New'])
    before=[photo(s,id_) for id_ in (1,2)];state=shortcut(s)
    with pytest.raises(ValueError,match='100'):paint(s)
    assert shortcut(s)==state and [photo(s,id_) for id_ in (1,2)]==before
    with pytest.raises(ValueError,match='does not exist'):
        paint(s,targets=[*targets(s,[1]),{'photo_id':999,'expected_metadata_revision':0}])
    assert photo(s,1)==before[0]
    with s.catalog() as c,c.db:
        c.db.execute("CREATE TRIGGER injected BEFORE UPDATE OF metadata_revision ON photos WHEN NEW.id=3 BEGIN SELECT RAISE(ABORT,'injected'); END")
    with pytest.raises(sqlite3.IntegrityError,match='injected'):paint(s,ids=[1,3])
    assert photo(s,1)==before[0] and photo(s,3)['keyword_count']==0 and shortcut(s)==state


def test_legacy_identity_rename_subtree_delete_and_clear(library):
    s,_=library;parent=save(s,'Root')
    with s.catalog() as c,c.db:
        id_=c.db.execute("INSERT INTO keywords(parent_id,name,normalized) VALUES(?,'Literal, comma | tag','literal, comma | tag')",(parent,)).lastrowid
        c.db.execute('UPDATE keyword_state SET revision=revision+1')
    captured=set_shortcut(s,[id_]);paint(s,ids=[1])
    assert photo(s,1)['keyword_ids']==[id_]
    save(s,'Renamed',keyword_id=parent)
    renamed=shortcut(s)
    assert renamed['keywords'][0]['path']=='Renamed | Literal, comma | tag'
    with pytest.raises(ValueError,match='changed'):paint(s,ids=[2],expected_shortcut_revision=captured['revision'])
    paint(s,ids=[2])
    s.dispatch('delete_keyword',{'keyword_id':parent,'expected_revision':s.dispatch('library_state')['keyword_revision']})
    assert shortcut(s)['keyword_ids']==[]
    with pytest.raises(ValueError,match='Set a keyword shortcut'):paint(s)
    set_shortcut(s,additions=['Another']);set_shortcut(s)
    assert shortcut(s)['total']==0 and s.dispatch('list_keywords')['total']==1


def test_invalid_shortcut_combined_capacity_and_ambiguous_text_rollback(library):
    s,_=library
    a=save(s,'A');b=save(s,'B');save(s,'Same',parent_id=a);save(s,'Same',parent_id=b)
    state=set_shortcut(s,additions=['Keep'])
    with pytest.raises(ValueError,match='Ambiguous'):set_shortcut(s,additions=['Would Be New','Same'])
    assert shortcut(s)==state and s.dispatch('list_keywords',{'search':'Would Be New'})['total']==0
    with pytest.raises(ValueError,match='100'):set_shortcut(s,state['keyword_ids'],[f'New{i}' for i in range(100)])
    assert shortcut(s)==state and s.dispatch('list_keywords',{'search':'New'})['total']==0


@pytest.mark.parametrize('kind,params',[
    ('rating',{'value':-1}),('flag',{'value':5}),('label',{'value':3}),
    ('keywords',{'value':3}),('rating',{'value':4,'erase':True}),
    ('label',{'value':'red','expected_shortcut_revision':'irrelevant'}),
])
def test_invalid_painter_options_commit_nothing(library,kind,params):
    s,_=library;set_shortcut(s,additions=['Keep']);before=photo(s,1)
    with pytest.raises(ValueError):paint(s,kind=kind,**params)
    assert photo(s,1)==before


def test_complete_maximum_paths_are_paged_and_revision_bound(library):
    s,_=library
    with s.catalog() as c,c.db:
        parent=None
        for i in range(31):
            name=f'{i:02}'+('🌊'*118)
            parent=c.db.execute('INSERT INTO keywords(parent_id,name,normalized) VALUES(?,?,?)',(parent,name,name)).lastrowid
        ids=[]
        for i in range(100):
            name=f'{i:02}'+('🐳'*118)
            ids.append(c.db.execute('INSERT INTO keywords(parent_id,name,normalized) VALUES(?,?,?)',(parent,name,name)).lastrowid)
        c.db.execute('UPDATE keyword_state SET revision=revision+1')
    state=set_shortcut(s,ids);paths=[]
    for offset in range(0,100,20):
        page=s.dispatch('get_keyword_shortcut',{'offset':offset,'expected_revision':state['revision']})
        assert page['keyword_ids']==ids and len(page['keywords'])==20
        assert len(json.dumps(page,ensure_ascii=False).encode())<320000
        paths.extend(row['path'] for row in page['keywords'])
    assert len(set(paths))==100 and all(len(p.split(' | '))==32 for p in paths)
    paint(s,ids=[1])
    assert photo(s,1)['keyword_ids']==ids
    with pytest.raises(ValueError,match='changed'):
        s.dispatch('get_keyword_shortcut',{'offset':20,'expected_revision':state['revision']})


def test_genuine_v13_migration_rollback_and_backup(tmp_path,monkeypatch):
    import lumaraw.catalog as module
    from legacy_catalog import migrate_to
    from lumaraw.library import backup_catalog,restore_catalog
    with monkeypatch.context() as patch:
        patch.setattr(module,'migrate',lambda db:migrate_to(db,13))
        c=Catalog(tmp_path/'old')
    c.db.set_authorizer(lambda action,name,*rest:sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_CREATE_TRIGGER else sqlite3.SQLITE_OK)
    with pytest.raises(sqlite3.DatabaseError):migrate(c.db)
    c.db.set_authorizer(None)
    assert c.db.execute('PRAGMA user_version').fetchone()[0]==13
    assert not c.db.execute("SELECT 1 FROM sqlite_master WHERE name='keyword_shortcut'").fetchone()
    migrate(c.db);migrate(c.db);c.close()
    s=Service(tmp_path/'old',presets_root=tmp_path/'presets')
    try:
        saved=set_shortcut(s,additions=['Saved | Shortcut'])
        with s.catalog() as c:backup_catalog(c,tmp_path/'backup')
    finally:s.close()
    restored=Service(restore_catalog(tmp_path/'backup',tmp_path/'restored'),presets_root=tmp_path/'presets')
    try:
        assert shortcut(restored)['keyword_ids']==saved['keyword_ids']
        assert shortcut(restored)['keywords']==saved['keywords']
    finally:restored.close()
