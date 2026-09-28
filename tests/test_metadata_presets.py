"""Selective metadata presets, shared scope and atomic photo application.

Isolated generated originals verify clearing versus omission, additive keywords,
rating conflicts independent of metadata revision, no-op reapplication and bounded
storage/IPC. Tests do not establish Adobe preset-file or desktop interaction parity.
"""
import json
from pathlib import Path
import sqlite3

from PIL import Image
import pytest

from lumaraw.catalog import Catalog
from lumaraw.service import Service
from lumaraw.runtime import CATALOG_VERSION


@pytest.fixture
def library(tmp_path):
    paths=[]
    for i in range(3):
        path=tmp_path/f'{i}.png'
        Image.new('RGB',(24,16),('navy','teal','orange')[i]).save(path)
        paths.append(path)
    s=Service(tmp_path/'catalog',presets_root=tmp_path/'presets')
    s.dispatch('queue_control',{'action':'pause'})
    s.dispatch('import_photos',{'paths':list(map(str,paths))})
    yield s,paths
    s.close()


def state(s,**query):
    return s.dispatch('list_metadata_presets',query)


def photo(s,id_):
    return s.dispatch('get_photo',{'photo_id':id_})


def save(s,patch,name='Metadata',**options):
    return s.dispatch('save_metadata_preset',{'name':name,'patch':patch,'expected_revision':state(s)['revision'],**options})


def action(s,kind,**options):
    return s.dispatch('metadata_preset_action',{'action':kind,'expected_revision':state(s)['revision'],**options})


def get(s,id_):
    return s.dispatch('get_metadata_preset',{'preset_id':id_,'expected_revision':state(s)['revision']})['preset']


def targets(s,ids=(1,2,3)):
    return [{'photo_id':id_,'expected_metadata_revision':photo(s,id_)['metadata_revision'],
             'expected_rating':photo(s,id_)['rating']} for id_ in ids]


def metadata_targets(s,ids=(1,2,3)):
    return [{key:value for key,value in row.items() if key!='expected_rating'} for row in targets(s,ids)]


def apply(s,id_,**options):
    return s.dispatch('apply_metadata_preset',{'preset_id':id_,'expected_revision':state(s)['revision'],
        'targets':targets(s),**options})


def test_checked_scalars_clear_keywords_append_and_noop_preserves_everything_else(library,tmp_path):
    s,paths=library
    originals=[path.read_bytes() for path in paths]
    s.dispatch('edit_metadata',{'targets':metadata_targets(s),'patch':{'title':'Keep','caption':'Clear me',
        'keywords':['Existing'],'iptc':{'city':'Keep city','creator':['Alice']}}})
    s.dispatch('edit_photo',{'photo_id':1,'expected_revision':0,'patch':{'exposure':1.25}})
    s.dispatch('orient_photos',{'action':'rotate_left','targets':[{'photo_id':1,'expected_revision':1}]})
    job=s.dispatch('enqueue_exports',{'photo_ids':[1],'destination':str(tmp_path/'exports'),
        'format':'jpeg','request_key':'before'})['job_ids'][0]
    before=photo(s,1);frozen=s.dispatch('get_job',{'job_id':job})
    patch={'caption':'','rating':4,'color_label':'purple','keywords':['Places | Coast'],
           'iptc':{'creator':[],'rights_usage_terms':'Editorial use'}}
    keyword_revision=s.dispatch('list_keywords')['keyword_revision']
    id_=save(s,patch)['preset_id']
    assert s.dispatch('list_keywords')['keyword_revision']==keyword_revision and photo(s,1)==before
    assert apply(s,id_)['updated']==[1,2,3]
    after=photo(s,1)
    assert after['title']=='Keep' and after['caption']=='' and after['rating']==4 and after['color_label']=='purple'
    assert set(after['keywords'])=={'Existing','Places | Coast'}
    assert after['iptc']=={'city':'Keep city','creator':[],'rights_usage_terms':'Editorial use'}
    assert (after['recipe'],after['revision'],after['orientation'])==(before['recipe'],before['revision'],before['orientation'])
    assert after['metadata_revision']==before['metadata_revision']+1
    assert apply(s,id_)['updated']==[] and photo(s,1)==after
    assert s.dispatch('get_job',{'job_id':job})==frozen and [p.read_bytes() for p in paths]==originals


def test_lifecycle_unicode_search_and_scope_are_independent(library,tmp_path):
    a,paths=library
    id_=save(a,{'title':'Shared'},name='旅行 %_')['preset_id']
    b=Service(tmp_path/'other',presets_root=tmp_path/'presets')
    try:
        b.dispatch('import_photos',{'paths':[str(paths[0])]})
        assert get(b,id_)['name']=='旅行 %_' and state(a,search='%_')['total']==1
        action(a,'rename',preset_id=id_,name='Renamed')
        copied=action(a,'duplicate',preset_id=id_,name='Copy')['preset_id']
        assert copied!=id_ and get(b,copied)['patch']=={'title':'Shared'}
        with pytest.raises(ValueError,match='already exists'):
            save(a,{'caption':'x'},name='COPY')
        stale=state(a)['revision']
        action(b,'storage',store_with_catalog=True)
        assert state(a)['store_with_catalog'] and state(a)['total']==0
        assert not a.dispatch('list_develop_presets')['store_with_catalog']
        assert not a.dispatch('list_keyword_sets')['store_with_catalog']
        with pytest.raises(ValueError,match='storage or keywords changed'):
            apply(a,id_,expected_revision=stale)
        local=save(a,{'title':'Local'})['preset_id']
        assert state(b)['total']==0
        action(a,'storage',store_with_catalog=False)
        assert get(a,id_)['patch']=={'title':'Shared'}
        action(a,'delete',preset_id=copied)
        with pytest.raises(ValueError,match='does not exist'):
            get(a,copied)
        action(a,'storage',store_with_catalog=True)
        assert get(a,local)['patch']=={'title':'Local'}
    finally:
        b.close()


def test_stale_preset_vocabulary_metadata_or_rating_rejects_entire_batch(library):
    s,_=library
    id_=save(s,{'rating':2,'title':'Applied','keywords':['New Tag']})['preset_id']
    captured=targets(s)
    s.dispatch('rate_photo',{'photo_id':2,'rating':3})
    assert photo(s,2)['metadata_revision']==captured[1]['expected_metadata_revision']
    with pytest.raises(ValueError,match='Rating conflict'):
        apply(s,id_,targets=captured)
    assert photo(s,1)['title']=='' and s.dispatch('list_keywords')['total']==0
    token=state(s)['revision']
    s.dispatch('save_keyword',{'name':'External','expected_revision':s.dispatch('list_keywords')['keyword_revision']})
    with pytest.raises(ValueError,match='keywords changed'):
        apply(s,id_,expected_revision=token)
    token=state(s)['revision']
    save(s,{'title':'Updated'},preset_id=id_)
    with pytest.raises(ValueError,match='presets, storage'):
        apply(s,id_,expected_revision=token)
    captured=targets(s)
    s.dispatch('edit_metadata',{'targets':metadata_targets(s,(3,)),'patch':{'copyright':'New'}})
    with pytest.raises(ValueError,match='Metadata conflict'):
        apply(s,id_,targets=captured)
    assert photo(s,1)['title']==''


def test_keyword_capacity_and_sql_failure_roll_back_fields_and_vocabulary(library):
    s,_=library
    s.dispatch('edit_metadata',{'targets':metadata_targets(s,(3,)),
        'patch':{'keywords':[f'Tag {i}' for i in range(100)]}})
    id_=save(s,{'keywords':['Extra'],'iptc':{'country':'New'},'title':'New'})['preset_id']
    before=[photo(s,i) for i in (1,2,3)]
    with pytest.raises(ValueError,match='100 directly'):
        apply(s,id_)
    assert [photo(s,i) for i in (1,2,3)]==before
    assert s.dispatch('list_keywords',{'search':'Extra'})['total']==0
    with s.catalog() as c,c.db:
        c.db.execute("CREATE TRIGGER fail_metadata BEFORE UPDATE ON photos WHEN NEW.id=2 BEGIN SELECT RAISE(ABORT,'preset fault'); END")
    with pytest.raises(sqlite3.IntegrityError,match='preset fault'):
        apply(s,id_,targets=targets(s,(1,2)))
    assert [photo(s,i) for i in (1,2,3)]==before
    assert s.dispatch('list_keywords',{'search':'Extra'})['total']==0


def test_bounded_page_wire_size_and_no_full_photo_materialization(library,monkeypatch):
    s,_=library
    with s.metadata_presets.transaction() as (_,_,db,_):
        db.executemany('INSERT INTO metadata_presets VALUES(?,?,?,?,1)',
            [(str(i),f'Preset {i:03}',f'preset {i:03}',json.dumps({'title':'é'*500})) for i in range(95)])
    first=state(s);last=state(s,offset=999)
    assert len(first['presets'])==30 and last['offset']==90 and len(last['presets'])==5
    assert len(json.dumps(first).encode())<20000 and all('patch' not in r for r in first['presets'])
    with pytest.raises(ValueError,match='512 KiB'):
        save(s,{'keywords':['é'*4096]*100})
    monkeypatch.setattr(Catalog,'photo',lambda *a: (_ for _ in ()).throw(AssertionError('Full photo read forbidden')))
    assert s.dispatch('apply_metadata_preset',{'preset_id':'0','expected_revision':first['revision'],
        'targets':[{'photo_id':1,'expected_metadata_revision':0}]})['updated']==[1]


def test_local_presets_and_iptc_survive_backup_and_restore(library,tmp_path):
    s,_=library
    action(s,'storage',store_with_catalog=True)
    id_=save(s,{'iptc':{'creator':['Photographer'],'city':'Paris','rights_url':'https://example.test/rights'}})['preset_id']
    apply(s,id_)
    backup=tmp_path/'backup.sqlite'
    s.dispatch('backup_catalog',{'path':str(backup)})
    restored=s.dispatch('restore_catalog',{'path':str(backup),'destination':str(tmp_path/'restored')})
    other=Service(restored['catalog'],presets_root=tmp_path/'presets')
    try:
        assert get(other,id_)['patch']==get(s,id_)['patch']
        assert photo(other,1)['iptc']==photo(s,1)['iptc']
    finally:
        other.close()


def test_genuine_schema17_preset_migration_rolls_back_and_retries(tmp_path,monkeypatch):
    from lumaraw import catalog as module
    from lumaraw.metadata_presets import migrate
    from legacy_catalog import migrate_to
    root=tmp_path/'old'
    with monkeypatch.context() as context:
        context.setattr(module,'migrate',lambda db:migrate_to(db,17))
        c=Catalog(root)
        with c.db:
            c.db.execute("INSERT INTO photos(path,name,bytes,mtime,recipe,created,iptc) VALUES('old.png','old.png',0,0,'{}',0,?)",(json.dumps({'city':'Keep'}),))
        c.db.set_authorizer(lambda action,a,b,d,t:sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_CREATE_INDEX and a=='metadata_preset_names' else sqlite3.SQLITE_OK)
        with pytest.raises(sqlite3.DatabaseError):
            migrate(c.db)
        c.db.set_authorizer(None)
        assert c.db.execute('PRAGMA user_version').fetchone()[0]==17
        assert not c.db.execute("SELECT name FROM sqlite_master WHERE name='metadata_presets'").fetchone()
        c.close()
    c=Catalog(root)
    try:
        assert c.db.execute('PRAGMA user_version').fetchone()[0]==CATALOG_VERSION
        assert json.loads(c.db.execute('SELECT iptc FROM photos').fetchone()[0])=={'city':'Keep'}
        migrate(c.db)
        assert c.db.execute('SELECT COUNT(*) FROM metadata_preset_state').fetchone()[0]==1
    finally:
        c.close()
