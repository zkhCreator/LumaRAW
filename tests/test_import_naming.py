"""Filename templates across selection, Copy journals and catalog migration.

Real disposable photos prove destination/original/XMP identity and recovery.
Synthetic large plans verify indexed rank work independently of filesystem speed.
No desktop or Adobe filename byte-equivalence claim is made.
"""
import json
from pathlib import Path
import sqlite3

import pytest
import jsonschema
from PIL import Image

from lumaraw import filename_templates as names
from lumaraw.import_copy import ImportCopy
from lumaraw.import_naming import ImportNaming, migrate, ordinals
from lumaraw.import_review import ImportReview
from lumaraw.service import Service
from lumaraw.catalog import Catalog
from test_import_review import library, picture, prepare, scan, apply
from test_import_copy import ready, resume, transfers
from test_xmp_read import packet
from legacy_catalog import migrate_to, seed_photo


def draft(**values):
    return {**names.defaults(),'enabled':True,'template':names.builtins()[2]['template'],
            'custom_text':'Trip',**values}


def configure(s,plan,**values):
    s.dispatch('set_import_naming',{'plan_id':plan['id'],'expected_revision':plan['revision'],'settings':draft(**values)})
    return s.dispatch('get_import')['plan']


def test_checked_sequence_page_sort_and_original_identity(library):
    s,root=library
    paths=[picture(root/'source'/name) for name in ('z003.JPG','A001.jpg','b002.jpg')]
    paths[1].with_suffix('.XMP').write_bytes(packet('<dc:title>Retained title</dc:title>'))
    originals={p:p.read_bytes() for p in [*paths,paths[1].with_suffix('.XMP')]}
    plan=configure(s,ready(s,root,paths),custom_text='旅行',start=41,extension='lower')
    items=s.dispatch('get_import')['items']
    assert [Path(r['destination']).name for r in items]==['旅行-0041.jpg','旅行-0042.jpg','旅行-0043.jpg']
    plan=s.dispatch('select_import_items',{'plan_id':plan['id'],'expected_revision':plan['revision'],'selected':False,'item_ids':[items[1]['id']]})['plan']
    reverse=s.dispatch('get_import',{'descending':True})['items']
    assert Path(reverse[0]['destination']).name=='旅行-0042.jpg' and 'destination' not in reverse[1]
    assert apply(s,plan)['imported']==2
    photos=s.dispatch('list_photos',{'descending':False,'stacked':False})['photos']
    assert {p['name'] for p in photos}=={'旅行-0041.jpg','旅行-0042.jpg'}
    assert s.dispatch('get_photo',{'photo_id':photos[0]['id']})['original_name'] in ('A001.jpg','z003.JPG')
    assert (root/'destination/旅行-0041.XMP').read_bytes()==originals[paths[1].with_suffix('.XMP')]
    assert all(path.read_bytes()==data for path,data in originals.items())
    again=ready(s,root,paths)
    assert again['counts']=={'duplicate':2,'new':1}


def test_capture_tokens_are_local_camera_time_not_utc_or_mtime(library):
    s,root=library;path=root/'DSC0099.JPG'
    exif=Image.Exif();exif[272]='Camera';exif[34665]={36867:'2026:09:28 00:05:07',36881:'+14:00'}
    Image.new('RGB',(8,6)).save(path,exif=exif)
    template=[names.token(k) for k in ('year','month','day')]+[names.token('literal',text='-')]+[
        names.token(k) for k in ('hour','minute','second')]+[names.token('literal',text='-'),names.token('original_number')]
    plan=configure(s,ready(s,root,[path]),template=template,extension='upper')
    assert Path(s.dispatch('get_import')['items'][0]['destination']).name=='20260928-000507-0099.JPG'
    assert apply(s,plan)['state']=='applied'


@pytest.mark.parametrize('kind',['year','hour','camera','original_number','custom_text','shoot_name'])
def test_missing_token_rejects_all_before_destination_writes(library,kind):
    s,root=library;a=picture(root/'plain.jpg',clock=False)
    plan=configure(s,ready(s,root,[a]),template=[names.token(kind)],custom_text='')
    item=s.dispatch('get_import')['items'][0]
    assert 'Missing filename value' in item['naming_error'] and 'destination' not in item
    pending=apply(s,plan)
    assert pending['state']=='interrupted' and pending['copy']['copied']==0
    assert not list((root/'destination').iterdir()) and s.dispatch('status')['photos']==0


@pytest.mark.parametrize('text',['../outside','bad/name','bad\\name','bad:name','bad\nname','\0'])
def test_invalid_literal_is_rejected_before_revision_change(library,text):
    s,root=library;plan=ready(s,root,[picture(root/'a.jpg')])
    with pytest.raises(ValueError):configure(s,plan,template=[names.token('literal',text=text)])
    assert s.dispatch('get_import')['plan']['revision']==plan['revision']


@pytest.mark.parametrize('text',['.', '..', '.hidden','tail.','tail ','字'*90])
def test_unrepresentable_final_name_is_explicit(library,text):
    s,root=library;plan=configure(s,ready(s,root,[picture(root/'a.jpg')]),template=[names.token('literal',text=text)])
    assert s.dispatch('get_import')['items'][0]['naming_error']
    assert apply(s,plan)['copy']['copied']==0
    assert not list((root/'destination').iterdir())


def test_duplicate_renamed_targets_preflight_all_and_keep_existing(library):
    s,root=library;paths=[picture(root/'a.jpg'),picture(root/'b.jpg')]
    plan=configure(s,ready(s,root,paths),template=[names.token('custom_text')])
    pending=apply(s,plan)
    assert pending['state']=='interrupted' and not list((root/'destination').iterdir())
    s.dispatch('cancel_import',{'plan_id':plan['id']})
    (root/'destination/Trip-0002.jpg').write_bytes(b'existing')
    plan=configure(s,ready(s,root,paths))
    assert apply(s,plan)['state']=='interrupted'
    assert sorted(p.name for p in (root/'destination').iterdir())==['Trip-0002.jpg']
    assert (root/'destination/Trip-0002.jpg').read_bytes()==b'existing'


def test_saved_templates_revision_snapshot_deletion_and_backup(library):
    from lumaraw.library import backup_catalog,restore_catalog
    s,root=library;plan=ready(s,root,[picture(root/'a.jpg')]);lib=s.dispatch('list_filename_templates')
    saved=s.dispatch('save_filename_template',{'name':'My sequence','template':draft()['template'],'expected_revision':lib['revision']})
    captured=s.dispatch('get_filename_template',{'template_id':saved['template_id'],'expected_revision':saved['revision']})
    plan=configure(s,plan,template=captured['template'])
    updated=s.dispatch('save_filename_template',{'name':'Renamed','template':[names.token('filename')],
        'template_id':captured['id'],'expected_revision':saved['revision']})
    with pytest.raises(ValueError,match='changed'):
        s.dispatch('delete_filename_template',{'template_id':captured['id'],'expected_revision':saved['revision']})
    s.dispatch('delete_filename_template',{'template_id':captured['id'],'expected_revision':updated['revision']})
    assert s.dispatch('get_import_naming',{'plan_id':plan['id']})['settings']['template']==captured['template']
    with s.catalog() as c:backup_catalog(c,root/'backup.sqlite')
    restore_catalog(root/'backup.sqlite',root/'restored')
    c=Catalog(root/'restored')
    assert ImportNaming(c).get(plan['id'])['settings']==draft()
    c.close()
    assert apply(s,plan)['state']=='applied'


def test_add_rejects_naming_and_stale_drafts_never_rebase(library):
    s,root=library;path=picture(root/'a.jpg');plan=scan(s,prepare(s,[path]))
    with pytest.raises(ValueError,match='Copy mode'):configure(s,plan)
    s.dispatch('cancel_import',{'plan_id':plan['id']})
    plan=ready(s,root,[path]);configure(s,plan)
    with pytest.raises(ValueError,match='changed'):configure(s,plan,custom_text='stale')
    value=s.dispatch('get_import_naming',{'plan_id':plan['id']})['settings']
    assert value['custom_text']=='Trip'
    with pytest.raises(jsonschema.ValidationError):
        s.dispatch('set_import_naming',{'plan_id':plan['id'],'expected_revision':plan['revision'],'settings':{**value,'unknown':True}})


def test_restart_reuses_frozen_names_and_shared_xmp_is_copied_for_each_new_stem(library,monkeypatch):
    s,root=library;paths=[picture(root/'same.jpg'),picture(root/'same.png')]
    xmp=paths[0].with_suffix('.xmp');xmp.write_bytes(packet('<dc:title>Both</dc:title>'))
    plan=configure(s,ready(s,root,paths),start=9)
    original=ImportCopy.save;fired=False
    def crash(self,row,**patch):
        nonlocal fired
        original(self,row,**patch)
        if not fired and patch.get('state')=='published':
            fired=True;raise SystemExit('crash')
    monkeypatch.setattr(ImportCopy,'save',crash)
    with pytest.raises(SystemExit):apply(s,plan)
    monkeypatch.setattr(ImportCopy,'save',original)
    reopened=Service(s.root,presets_root=root/'presets')
    try:
        pending=reopened.dispatch('get_import')['plan']
        with pytest.raises(ValueError,match='changed'):configure(reopened,pending,start=100)
        assert resume(reopened,pending)['state']=='applied'
        assert {p.name for p in (root/'destination').iterdir()}=={'Trip-0009.jpg','Trip-0010.png','Trip-0009.xmp','Trip-0010.xmp'}
        assert all((root/'destination'/name).read_bytes()==xmp.read_bytes() for name in ('Trip-0009.xmp','Trip-0010.xmp'))
        assert len(transfers(reopened,pending))==4
    finally:reopened.close()


def test_preview_draft_is_readonly_bounded_and_x_of_y_uses_checked_total(library):
    s,root=library;paths=[picture(root/f'p{i:03}.jpg') for i in range(125)]
    plan=ready(s,root,paths);value=draft(template=names.builtins()[0]['template'])
    result=s.dispatch('preview_import_naming',{'plan_id':plan['id'],'expected_revision':plan['revision'],'settings':value,'offset':60})
    assert len(result['items'])==60 and result['items'][0]['destination'].endswith('Trip (61 of 125).jpg')
    assert result['items'][-1]['destination'].endswith('Trip (120 of 125).jpg')
    assert s.dispatch('get_import')['plan']['revision']==plan['revision']
    assert not s.dispatch('get_import_naming',{'plan_id':plan['id']})['settings']['enabled']


def test_library_pages_normalized_names_and_nonreused_identity(library):
    s,root=library;revision=0
    for index in range(32):
        page=s.dispatch('save_filename_template',{'name':f'Template {index:02}','template':[names.token('filename')],'expected_revision':revision})
        revision=page['revision']
    assert len(page['items'])==30 and s.dispatch('list_filename_templates',{'offset':30})['items'][0]['name']=='Template 30'
    with pytest.raises(ValueError,match='already'):
        s.dispatch('save_filename_template',{'name':'TEMPLATE 00','template':[names.token('filename')],'expected_revision':revision})
    old=page['items'][0]['id'];page=s.dispatch('delete_filename_template',{'template_id':old,'expected_revision':revision})
    fresh=s.dispatch('save_filename_template',{'name':'Template 00','template':[names.token('filename')],'expected_revision':page['revision']})
    assert fresh['template_id']!=old


def test_schema_26_upgrade_atomic_existing_copy_and_photo_preserved(tmp_path,monkeypatch):
    from lumaraw import catalog as module
    with monkeypatch.context() as context:
        context.setattr(module,'migrate',lambda db:migrate_to(db,26));c=Catalog(tmp_path/'old')
    photo=picture(tmp_path/'a.jpg');seed_photo(c.db,photo)
    with c.db:
        c.db.execute("INSERT INTO import_plans(include_subfolders,created) VALUES(1,1)")
        c.db.execute("INSERT INTO import_copy_plans(plan_id,destination,destination_identity,organization,subfolder,roots,owner) VALUES(1,'target','{}','flat','','[]','owner')")
    c.db.set_authorizer(lambda action,a,b,d,t:sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_CREATE_TABLE and a=='filename_templates' else sqlite3.SQLITE_OK)
    with pytest.raises(sqlite3.DatabaseError):migrate(c.db)
    assert c.db.execute('PRAGMA user_version').fetchone()[0]==26
    assert 'naming_index' not in {r[1] for r in c.db.execute('PRAGMA table_info(import_files)')}
    c.db.set_authorizer(None);migrate(c.db);migrate(c.db)
    assert ImportNaming(c).get(1)['settings']==names.defaults()
    assert c.db.execute('SELECT name FROM photos').fetchone()[0]=='a.jpg'
    assert c.db.execute('PRAGMA user_version').fetchone()[0]==27
    c.close()


@pytest.mark.parametrize('same_name',[False,True])
def test_ranks_seek_disjoint_index_spans_instead_of_rescanning_per_item(tmp_path,same_name):
    from import_naming_probe import seed
    c=Catalog(tmp_path/'large');seed(c,10000)
    with c.db:
        if same_name:c.db.execute("UPDATE import_files SET name='same.jpg'")
        c.db.execute('UPDATE import_files SET selected=0 WHERE id%3=0')
    items=[dict(row) for row in c.db.execute('SELECT id,name,selected FROM import_files WHERE selected=1 '
          'ORDER BY name COLLATE NOCASE,id LIMIT 60 OFFSET 6500')]
    for item in items:item['eligible']=True
    steps=[0]
    def progress():steps[0]+=1000;return 0
    c.db.set_progress_handler(progress,1000)
    result=ordinals(c.db,{'id':1,'skip_duplicates':1},items)
    c.db.set_progress_handler(None,0)
    assert list(result.values())==list(range(6501,6561))
    # A deterministic VM-work bound detects sixty prefix/full-index scans;
    # it does not impose machine-dependent wall-clock performance thresholds.
    assert steps[0]<250000
    c.close()


def test_cancellation_rolls_back_rank_freeze_before_copy(tmp_path):
    from import_naming_probe import seed
    from lumaraw.import_naming import freeze
    c=Catalog(tmp_path/'cancel');seed(c,10000)
    with pytest.raises(InterruptedError),c.db:
        freeze(c.db,{'id':1,'skip_duplicates':1},lambda:True)
    assert c.db.execute('SELECT count(*) FROM import_files WHERE naming_index!=0').fetchone()[0]==0
    c.close()
