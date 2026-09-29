"""Import-time preset snapshots, metadata unions and asset/recovery contracts.

Generated files and isolated preset repositories prove persistence, revision and
all-or-nothing writes, including full-value wire limits. Real worker previews are
tested separately from catalog performance; no Adobe pixel equivalence is claimed.
"""
import json
from pathlib import Path
import sqlite3

from PIL import Image
import pytest

from lumaraw.catalog import Catalog
from lumaraw.import_processing import migrate, settings
from lumaraw.runtime import CATALOG_VERSION
from lumaraw.service import Service
from test_import_review import picture, prepare, scan, apply
from test_xmp_read import packet


@pytest.fixture
def library(tmp_path):
    s=Service(tmp_path/'catalog',presets_root=tmp_path/'presets')
    s.dispatch('queue_control',{'action':'pause'})
    source=picture(tmp_path/'template.jpg')
    s.dispatch('import_photos',{'paths':[str(source)]})
    yield s,tmp_path
    s.close()


def current(s):
    return s.dispatch('get_import')['plan']


def set_processing(s,**changes):
    plan=current(s)
    return s.dispatch('set_import_processing',{'plan_id':plan['id'],'expected_revision':plan['revision'],**changes})


def choice(s,kind,id_):
    return {'preset_id':id_,'expected_revision':s.dispatch('list_'+kind+'_presets')['revision']}


def metadata(s,patch,name='Import metadata'):
    return s.dispatch('save_metadata_preset',{'name':name,'patch':patch,
        'expected_revision':s.dispatch('list_metadata_presets')['revision']})['preset_id']


def develop(s,patch):
    p=s.dispatch('get_photo',{'photo_id':1})
    s.dispatch('edit_photo',{'photo_id':1,'expected_revision':p['revision'],'patch':patch})
    return s.dispatch('save_develop_preset',{'name':'Import Develop','group_name':'User Presets','photo_id':1,
        'expected_photo_revision':p['revision']+1,'fields':list(patch),
        'expected_revision':s.dispatch('list_develop_presets')['revision']})['preset_id']


def test_frozen_presets_apply_only_to_checked_new_photos_with_additive_keywords(library):
    s,root=library
    d=develop(s,{'exposure':1.25,'contrast':13})
    m=metadata(s,{'title':'Chosen title','caption':'','rating':4,'keywords':['Tags | Preset'],
                  'iptc':{'headline':'Captured headline'}})
    a=picture(root/'new/a.jpg');b=picture(root/'new/b.jpg')
    a.with_suffix('.xmp').write_bytes(packet('<dc:title>File title</dc:title><dc:description>File caption</dc:description>'
        '<dc:subject><rdf:Bag><rdf:li>Existing</rdf:li></rdf:Bag></dc:subject>','xmp:Rating="2"'))
    originals={p:p.read_bytes() for p in (a,b,a.with_suffix('.xmp'))}
    before=s.dispatch('get_photo',{'photo_id':1})
    plan=scan(s,prepare(s,[a,b]))
    second=s.dispatch('get_import')['items'][1]
    s.dispatch('select_import_items',{'plan_id':plan['id'],'expected_revision':plan['revision'],'selected':False,'item_ids':[second['id']]})
    set_processing(s,develop_preset=choice(s,'develop',d),metadata_preset=choice(s,'metadata',m),keywords=['Additional','Tags | Preset'])
    assert s.dispatch('list_keywords')['total']==0 and s.dispatch('status')['photos']==1
    s.dispatch('metadata_preset_action',{'action':'delete',**choice(s,'metadata',m)})
    s.dispatch('develop_preset_action',{'action':'delete',**choice(s,'develop',d)})
    result=apply(s,current(s))
    assert result['state']=='applied' and result['imported']==1
    p=s.dispatch('get_photo',{'photo_id':2})
    assert p['title']=='Chosen title' and p['caption']=='' and p['rating']==4
    assert p['iptc']['headline']=='Captured headline'
    assert set(p['keywords'])=={'Existing','Additional','Tags | Preset'}
    assert p['recipe']['exposure']==1.25 and p['recipe']['contrast']==13 and p['revision']==0
    assert s.dispatch('get_photo',{'photo_id':1})==before
    with s.catalog() as c:
        assert c.db.execute('SELECT count(*) FROM history WHERE photo_id=2').fetchone()[0]==0
        assert c.db.execute('SELECT count(*) FROM import_processing').fetchone()[0]==0
    assert all(p.read_bytes()==data for p,data in originals.items())


def test_omission_none_and_keyword_clearing_are_independent(library):
    s,root=library;d=develop(s,{'exposure':1});m=metadata(s,{'copyright':'Preset'})
    scan(s,prepare(s,[picture(root/'new.jpg')]))
    set_processing(s,develop_preset=choice(s,'develop',d),metadata_preset=choice(s,'metadata',m),keywords=['One'])
    a=set_processing(s,develop_preset=None)
    assert a['develop_id']=='' and a['metadata_id']==m and a['keywords']==['One']
    b=set_processing(s,metadata_preset=None,keywords=[])
    assert b['metadata_id']=='' and b['keywords']==[]
    assert apply(s,current(s))['state']=='applied'
    p=s.dispatch('get_photo',{'photo_id':2})
    assert p['recipe']['exposure']==0 and not p['copyright'] and not p['keywords']


def test_captured_keyword_root_does_not_retarget_to_later_xmp_leaf(library):
    s,root=library;a=picture(root/'new.jpg')
    a.with_suffix('.xmp').write_bytes(packet('<lr:hierarchicalSubject><rdf:Bag>'
        '<rdf:li>Places|Coast</rdf:li></rdf:Bag></lr:hierarchicalSubject>'))
    scan(s,prepare(s,[a]));set_processing(s,keywords=['Coast'])
    assert apply(s,current(s))['state']=='applied'
    assert set(s.dispatch('get_photo',{'photo_id':2})['keywords'])=={'Coast','Places | Coast'}


def test_ambiguous_leaf_capture_and_keyword_transport_overflow_are_atomic(library):
    from lumaraw.keywords import Keywords
    s,root=library
    with s.catalog() as c,c.db:
        Keywords(c).resolve('North | Bird');Keywords(c).resolve('South | Bird')
    scan(s,prepare(s,[picture(root/'new.jpg')]))
    plan=current(s);before=s.dispatch('list_keywords')
    with pytest.raises(ValueError,match='Ambiguous'):
        set_processing(s,keywords=['Bird'])
    oversized=[' | '.join(['界'*119+str(i%10)]*31+[str(i)]) for i in range(100)]
    with pytest.raises(ValueError,match='128 KiB'):
        set_processing(s,keywords=oversized)
    assert current(s)==plan and s.dispatch('list_keywords')==before


def test_metadata_keyword_meaning_is_frozen_at_preset_read_not_later_plan_write(library,monkeypatch):
    from lumaraw.import_processing import ImportProcessing
    from lumaraw.keywords import Keywords
    s,root=library
    with s.catalog() as c,c.db:Keywords(c).resolve('North | Bird')
    m=metadata(s,{'keywords':['Bird']})
    scan(s,prepare(s,[picture(root/'new.jpg')]))
    actual=ImportProcessing.capture_metadata
    def raced(self,choice):
        captured=actual(self,choice)
        with s.catalog() as c,c.db:
            c.db.execute("INSERT INTO keywords(name,normalized) VALUES('Bird','bird')")
            c.db.execute('UPDATE keyword_state SET revision=revision+1')
        return captured
    monkeypatch.setattr(ImportProcessing,'capture_metadata',raced)
    set_processing(s,metadata_preset=choice(s,'metadata',m))
    assert apply(s,current(s))['state']=='applied'
    assert s.dispatch('get_photo',{'photo_id':2})['keywords']==['North | Bird']


def test_stale_plan_preset_or_ambiguous_keyword_leaves_settings_and_vocabulary_unchanged(library):
    s,root=library;m=metadata(s,{'title':'First'})
    scan(s,prepare(s,[picture(root/'new.jpg')]))
    original=current(s)
    set_processing(s,keywords=['Uncommitted | New'])
    before=s.dispatch('get_import_processing',{'plan_id':original['id']})
    with pytest.raises(ValueError,match='changed'):
        s.dispatch('set_import_processing',{'plan_id':original['id'],'expected_revision':original['revision'],'keywords':['Wrong']})
    stale=choice(s,'metadata',m)
    metadata(s,{'title':'Second'},name='Another')
    with pytest.raises(ValueError,match='changed'):
        set_processing(s,metadata_preset=stale)
    with pytest.raises(ValueError):
        set_processing(s,keywords=['Valid new tag','Invalid,tag'])
    assert s.dispatch('get_import_processing',{'plan_id':original['id']})==before
    assert s.dispatch('list_keywords')['total']==0


def test_keyword_capacity_and_sql_failure_roll_back_all_new_photos(library):
    s,root=library
    a=picture(root/'new/a.jpg');b=picture(root/'new/b.jpg')
    terms=''.join(f'<rdf:li>Tag {i}</rdf:li>' for i in range(100))
    b.with_suffix('.xmp').write_bytes(packet('<dc:subject><rdf:Bag>'+terms+'</rdf:Bag></dc:subject>'))
    scan(s,prepare(s,[a,b]));set_processing(s,keywords=['Extra'])
    assert apply(s,current(s))['state']=='failed'
    assert s.dispatch('status')['photos']==1 and s.dispatch('list_keywords')['total']==0
    b.with_suffix('.xmp').unlink()
    scan(s,prepare(s,[a,b]));set_processing(s,metadata_preset=choice(s,'metadata',metadata(s,{'title':'Set'})))
    with s.catalog() as c,c.db:
        c.db.execute("CREATE TRIGGER fail_import_metadata BEFORE UPDATE OF title ON photos WHEN NEW.name='b.jpg' BEGIN SELECT RAISE(ABORT,'import metadata fault'); END")
    result=apply(s,current(s))
    assert result['state']=='failed' and 'import metadata fault' in result['error']
    assert s.dispatch('status')['photos']==1
    with s.catalog() as c:
        assert c.db.execute('SELECT enabled FROM folder_maintenance').fetchone()[0]==1
        assert c.db.execute('SELECT sum(direct_count) FROM catalog_folders').fetchone()[0]==1


def test_camera_compatibility_is_rechecked_after_selection_changes(library):
    s,root=library
    profile={'camera':'Nikon Test','space':'LibRaw-ProPhoto-D65-linear','matrix':[[1,0,0],[0,1,0],[0,0,1]]}
    d=develop(s,{'camera_profile':profile})
    scan(s,prepare(s,[picture(root/'new.jpg')]))
    with pytest.raises(ValueError,match='incompatible'):
        set_processing(s,develop_preset=choice(s,'develop',d))
    plan=current(s)
    s.dispatch('select_import_items',{'plan_id':plan['id'],'expected_revision':plan['revision'],'selected':False})
    set_processing(s,develop_preset=choice(s,'develop',d))
    plan=current(s)
    s.dispatch('select_import_items',{'plan_id':plan['id'],'expected_revision':plan['revision'],'selected':True})
    result=apply(s,current(s))
    assert result['state']=='failed' and 'incompatible' in result['error'] and s.dispatch('status')['photos']==1


def test_lut_snapshot_backup_rebind_and_corruption_rejection(library):
    s,root=library;lut=root/'identity.cube'
    lut.write_text('LUT_3D_SIZE 2\n'+'\n'.join(f'{r} {g} {b}' for b in (0,1) for g in (0,1) for r in (0,1)))
    asset=s.dispatch('import_asset',{'kind':'lut','path':str(lut)})['asset']
    d=develop(s,{'lut':asset})
    scan(s,prepare(s,[picture(root/'new.jpg')]))
    set_processing(s,develop_preset=choice(s,'develop',d),keywords=['Restored'])
    backup=root/'backup.sqlite';s.dispatch('backup_catalog',{'path':str(backup)})
    restored=root/'restored';s.dispatch('restore_catalog',{'path':str(backup),'destination':str(restored)})
    other=Service(restored,presets_root=root/'isolated-presets')
    try:
        with other.catalog() as c:
            captured=settings(c,current(other)['id'])
        assert Path(captured['develop_patch']['lut']['path']).parent==restored/'assets'
        assert apply(other,current(other))['state']=='applied'
        assert other.dispatch('get_photo',{'photo_id':2})['keywords']==['Restored']
    finally:other.close()
    Path(asset['path']).write_text('changed asset')
    result=apply(s,current(s))
    assert result['state']=='failed' and 'LUT' in result['error'] and s.dispatch('status')['photos']==1


def test_changed_preset_during_asset_staging_cannot_change_plan(library,monkeypatch):
    import lumaraw.import_processing as module
    s,root=library;d=develop(s,{'exposure':1})
    scan(s,prepare(s,[picture(root/'new.jpg')]))
    before=current(s);real=module.stage_lut
    def changed(patch,path):
        s.dispatch('develop_preset_action',{'action':'rename','name':'Changed',**choice(s,'develop',d)})
        assert s.dispatch('status')['photos']==1
        return real(patch,path)
    monkeypatch.setattr(module,'stage_lut',changed)
    with pytest.raises(ValueError,match='changed'):
        set_processing(s,develop_preset=choice(s,'develop',d))
    assert current(s)==before


def test_large_metadata_is_not_repeated_in_review_or_processing_replies(library):
    from lumaraw.iptc import FIELDS
    from lumaraw.bridge import MAX_MESSAGE
    s,root=library
    # Use a bounded large valid preset independently of its list description.
    values={key:'界'*FIELDS[key]['limit'] for key in ('headline','alt_text','extended_description')}
    m=metadata(s,{'iptc':values})
    scan(s,prepare(s,[picture(root/'new.jpg')]))
    set_processing(s,metadata_preset=choice(s,'metadata',m))
    for result in (s.dispatch('get_import'),s.dispatch('get_import_processing',{'plan_id':current(s)['id']})):
        encoded=json.dumps({'ok':True,'result':result}).encode()
        assert len(encoded)<MAX_MESSAGE and b'\\u754c' not in encoded
    assert apply(s,current(s))['state']=='applied'
    assert s.dispatch('get_photo',{'photo_id':2})['iptc']==values


def test_develop_preview_changes_before_catalog_import_and_none_restores_source(library):
    s,root=library;d=develop(s,{'exposure':2})
    source=root/'gray.png';Image.new('RGB',(32,20),(70,70,70)).save(source)
    scan(s,prepare(s,[source]))
    item=s.dispatch('get_import')['items'][0]
    def preview(generation):
        p=current(s)
        return s.dispatch('preview_import_item',{'plan_id':p['id'],'item_id':item['id'],
            'expected_revision':p['revision'],'client_id':'processing-test','generation':generation})
    before=preview(1)
    set_processing(s,develop_preset=choice(s,'develop',d))
    after=preview(2)
    assert before['thumbnail']!=after['thumbnail']
    with Image.open(before['thumbnail']) as a,Image.open(after['thumbnail']) as b:
        assert b.getpixel((10,10))[0]>a.getpixel((10,10))[0]+20
    set_processing(s,develop_preset=None)
    assert preview(3)['thumbnail']==before['thumbnail'] and s.dispatch('status')['photos']==1


def test_genuine_schema19_migration_keeps_review_and_rolls_back_failure(tmp_path,monkeypatch):
    from lumaraw import catalog as module
    from legacy_catalog import migrate_to
    with monkeypatch.context() as context:
        context.setattr(module,'migrate',lambda db:migrate_to(db,19))
        c=Catalog(tmp_path/'old')
        with c.db:c.db.execute("INSERT INTO import_plans(include_subfolders,created,state) VALUES(1,0,'ready')")
        c.db.set_authorizer(lambda action,a,b,d,t:sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_CREATE_TRIGGER and a=='import_processing_delete' else sqlite3.SQLITE_OK)
        with pytest.raises(sqlite3.DatabaseError):migrate(c.db)
        c.db.set_authorizer(None)
        assert c.db.execute('PRAGMA user_version').fetchone()[0]==19
        assert not c.db.execute("SELECT 1 FROM sqlite_master WHERE name='import_processing'").fetchone()
        c.close()
    c=Catalog(tmp_path/'old')
    try:
        assert c.db.execute('PRAGMA user_version').fetchone()[0]==CATALOG_VERSION
        assert c.db.execute('SELECT state FROM import_plans').fetchone()[0]=='ready'
        assert settings(c,1)['keywords']==[]
    finally:c.close()
