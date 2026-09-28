"""Shared-original virtual copies across migration, catalog and service boundaries.

Use generated images and disposable catalogs. Verify independent edits, shared
snapshots, atomic conflicts, physical indexing and durable export/backup state.
These contracts do not establish Lightroom pixel equivalence or rendered Mac UI.
"""
import hashlib
import json
import sqlite3
import time

from PIL import Image
import pytest

from lumaraw.catalog import Catalog
from lumaraw.library import backup_catalog, restore_catalog
from lumaraw.model import Recipe
from lumaraw.service import Service


@pytest.fixture
def library(tmp_path):
    s = Service(tmp_path/'catalog')
    s.dispatch('queue_control', {'action':'pause'})
    paths = []
    for i in range(2):
        p = tmp_path/f'{i}.png'
        Image.new('RGB', (64,48), (40+i*30,70,110)).save(p)
        paths.append(p)
    s.dispatch('import_photos', {'paths':list(map(str, paths))})
    yield s, paths
    s.close()


def photo(s, id_):
    return s.dispatch('get_photo', {'photo_id':id_})


def target(s, id_, source=False):
    row = photo(s, id_)
    result = {'photo_id':id_, 'expected_revision':row['revision'],
              'expected_metadata_revision':row['metadata_revision']}
    if source:
        result['expected_source_revision'] = row['source_revision']
    return result


def copy(s, id_=1, **extra):
    return s.dispatch('create_virtual_copies', {'targets':[target(s,id_)], **extra})['photos'][0]['id']


def test_copies_inherit_state_then_edit_independently(library):
    s, paths = library
    before = hashlib.sha256(paths[0].read_bytes()).hexdigest()
    s.dispatch('edit_photo', {'photo_id':1,'expected_revision':0,'patch':{'exposure':1}})
    s.dispatch('edit_metadata', {'targets':[{'photo_id':1,'expected_metadata_revision':0}],
                                  'patch':{'title':'Original', 'keywords':['Night'], 'color_label':'red'}})
    s.dispatch('rate_photo', {'photo_id':1,'rating':4,'flag':1})
    first = copy(s); second = copy(s, first)
    a, b = photo(s,first), photo(s,second)
    assert a['path']==b['path']==str(paths[0]) and a['source_id']==b['source_id']==1
    assert a['copy_name']=='Copy 1' and b['copy_name']=='Copy 2'
    assert a['master_id']==1 and a['is_virtual']==1
    assert a['recipe']['exposure']==1 and a['revision']==0
    assert a['keywords']==['Night'] and a['rating']==4 and a['flag']==1
    s.dispatch('edit_photo', {'photo_id':first,'expected_revision':0,'patch':{'exposure':-1}})
    s.dispatch('edit_metadata', {'targets':[{'photo_id':first,'expected_metadata_revision':0}],
                                  'patch':{'copy_name':'Moody','keywords':['Copy']}})
    assert photo(s,1)['recipe']['exposure']==photo(s,second)['recipe']['exposure']==1
    assert photo(s,1)['keywords']==['Night'] and photo(s,first)['keywords']==['Copy']
    s.dispatch('undo_photo', {'photo_id':first,'expected_revision':1})
    assert photo(s,first)['recipe']['exposure']==1 and photo(s,1)['revision']==1
    with s.catalog() as c:
        assert c.db.execute('SELECT count(*) FROM history WHERE photo_id=?',(second,)).fetchone()[0]==0
    assert hashlib.sha256(paths[0].read_bytes()).hexdigest()==before
    assert s.dispatch('import_photos', {'paths':[str(paths[0])]})['imported']==0


def test_atomic_create_stale_metadata_and_collection_context(library):
    s,_ = library
    stale = target(s,2)
    s.dispatch('edit_metadata', {'targets':[{'photo_id':2,'expected_metadata_revision':0}], 'patch':{'title':'Changed'}})
    with pytest.raises(ValueError,match='Metadata conflict'):
        s.dispatch('create_virtual_copies', {'targets':[target(s,1),stale]})
    assert s.dispatch('list_photos')['total']==2
    collection = s.dispatch('save_collection', {'name':'Album','kind':'regular','photo_ids':[1]})
    id_ = copy(s, collection_id=collection['id'], expected_collection_revision=0)
    assert {r['id'] for r in s.dispatch('list_photos',{'collection_id':collection['id']})['photos']}=={1,id_}
    with pytest.raises(ValueError,match='Collection conflict'):
        copy(s, collection_id=collection['id'], expected_collection_revision=0)
    assert s.dispatch('list_photos')['total']==3


def test_promote_preserves_identity_recipe_and_shared_snapshots(library):
    s,_ = library
    a = copy(s); b = copy(s)
    s.dispatch('edit_photo', {'photo_id':a,'expected_revision':0,'patch':{'exposure':2}})
    s.dispatch('save_version', {'photo_id':a,'name':'Bright'})
    version = s.dispatch('list_versions', {'photo_id':1})['versions'][0]
    stale = target(s,b,True)
    promoted = s.dispatch('set_copy_as_master', target(s,a,True))
    assert promoted['id']==a and promoted['recipe']['exposure']==2 and promoted['is_virtual']==0
    assert photo(s,1)['is_virtual']==1 and photo(s,1)['recipe']['exposure']==0
    assert photo(s,b)['master_id']==a and photo(s,1)['master_id']==a
    with pytest.raises(ValueError,match='Source conflict'):
        s.dispatch('set_copy_as_master',stale)
    s.dispatch('restore_version', {'photo_id':b,'version_id':version['id'],'expected_revision':0})
    assert photo(s,b)['recipe']['exposure']==2
    with pytest.raises(ValueError,match='does not exist'):
        s.dispatch('restore_version', {'photo_id':2,'version_id':version['id'],'expected_revision':0})
    with s.catalog() as c:
        assert c.db.execute('SELECT count(*) FROM photos WHERE source_id=1 AND is_virtual=0').fetchone()[0]==1


def test_remove_is_catalog_only_and_keeps_export_and_shared_snapshots(library,tmp_path):
    s, paths = library
    a = copy(s)
    s.dispatch('edit_photo', {'photo_id':a,'expected_revision':0,'patch':{'exposure':1}})
    s.dispatch('save_version', {'photo_id':a,'name':'Keep after removal'})
    album = s.dispatch('save_collection', {'name':'Album','kind':'regular','photo_ids':[1,a]})
    job = s.dispatch('enqueue_exports', {'photo_ids':[a], 'destination':str(tmp_path/'exports'),
        'format':'jpeg','request_key':'copy-export'})['job_ids'][0]
    with pytest.raises(ValueError,match='Only virtual'):
        s.dispatch('remove_virtual_copies', {'targets':[target(s,a,True),target(s,1,True)]})
    s.dispatch('remove_virtual_copies', {'targets':[target(s,a,True)]})
    assert paths[0].is_file() and photo(s,1)['recipe']['exposure']==0
    assert s.dispatch('get_collection',{'collection_id':album['id']})['revision']==1
    assert s.dispatch('list_photos',{'collection_id':album['id']})['total']==1
    assert s.dispatch('list_versions',{'photo_id':1})['versions'][0]['name']=='Keep after removal'
    queued = s.dispatch('get_job',{'job_id':job})
    assert queued['photo_id']==a and queued['recipe']['exposure']==1 and queued['source_id']==1
    assert copy(s)>a  # Deleted photo IDs are never reused for another variant.
    s.dispatch('queue_control', {'action':'resume'})
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        queued=s.dispatch('get_job',{'job_id':job})
        if queued['state'] in ('done','failed'): break
        time.sleep(.05)
    assert queued['state']=='done', queued['error']


def test_index_duplicates_and_relink_operate_on_shared_physical_source(library,tmp_path,monkeypatch):
    import lumaraw.library as lib
    s, paths = library
    a = copy(s); b = copy(s)
    calls=[]; actual=lib.hash_file
    def hashed(path,cancelled=lambda:False):
        calls.append(str(path)); return actual(path,cancelled)
    monkeypatch.setattr(lib,'hash_file',hashed)
    assert s.dispatch('index_library')['indexed']==2 and len(calls)==2
    assert s.dispatch('list_photos',{'mode':'duplicates'})['total']==0
    job=s.dispatch('enqueue_exports',{'photo_ids':[a,b],'destination':str(tmp_path/'out'),
                                      'format':'jpeg','request_key':'relink'})['job_ids']
    s.dispatch('remove_virtual_copies', {'targets':[target(s,b,True)]})
    moved=tmp_path/'moved.png';paths[0].rename(moved)
    s.dispatch('index_library')
    assert photo(s,a)['missing']==photo(s,1)['missing']==1
    s.dispatch('relink_photo', {'photo_id':a,'path':str(moved)})
    assert photo(s,a)['path']==photo(s,1)['path']==str(moved)
    assert all(s.dispatch('get_job',{'job_id':id_})['source']==str(moved) for id_ in job)
    duplicate=tmp_path/'duplicate.png';duplicate.write_bytes(moved.read_bytes())
    s.dispatch('import_photos', {'paths':[str(duplicate)]});s.dispatch('index_library')
    assert s.dispatch('list_photos',{'mode':'duplicates'})['total']==3


def test_variant_filters_and_backup_restore(library,tmp_path):
    s,_=library
    a=copy(s)
    s.dispatch('edit_metadata',{'targets':[{'photo_id':a,'expected_metadata_revision':0}],
                                'patch':{'copy_name':'Café_%'}})
    assert s.dispatch('list_photos',{'filters':{'is_virtual':True}})['total']==1
    assert s.dispatch('list_photos',{'filters':{'source_id':1}})['total']==2
    assert s.dispatch('list_photos',{'search':'CAFÉ_%'})['photos'][0]['id']==a
    assert s.dispatch('list_photos',{'filters':{'copy_name':'café_%'}})['total']==1
    with s.catalog() as c: backup_catalog(c,tmp_path/'backup')
    root=restore_catalog(tmp_path/'backup',tmp_path/'restored')
    c=Catalog(root)
    assert c.photo(a)['copy_name']=='Café_%' and c.photo(a)['master_id']==1
    assert c.db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    c.close()


def test_developed_pixels_share_cache_until_a_copy_recipe_changes(library):
    s,paths=library
    s.dispatch('settings',{'compute_backend':'cpu'})
    a=copy(s)
    base=s.dispatch('thumbnail',{'photo_id':1,'kind':'developed'})
    identical=s.dispatch('thumbnail',{'photo_id':a,'kind':'developed'})
    assert base['thumbnail']==identical['thumbnail']
    s.dispatch('edit_photo',{'photo_id':a,'expected_revision':0,'patch':{'exposure':2}})
    changed=s.dispatch('thumbnail',{'photo_id':a,'kind':'developed'})
    assert changed['thumbnail'] != base['thumbnail']
    with Image.open(base['thumbnail']) as before, Image.open(changed['thumbnail']) as after:
        assert before.getpixel((10,10)) != after.getpixel((10,10))
    assert photo(s,1)['recipe']['exposure']==0 and paths[0].is_file()


def test_promotion_retains_import_dedup_and_stale_family_removal_fails(library):
    s,paths=library
    a=copy(s)
    stale=target(s,a,True)
    b=copy(s)
    with pytest.raises(ValueError,match='Source conflict'):
        s.dispatch('remove_virtual_copies',{'targets':[stale]})
    s.dispatch('set_copy_as_master',target(s,b,True))
    s.dispatch('remove_virtual_copies',{'targets':[target(s,1,True)]})
    assert s.dispatch('import_photos',{'paths':[str(paths[0])]})['imported']==0
    assert photo(s,a)['master_id']==b
    assert s.dispatch('list_photos',{'filters':{'source_id':1}})['total']==2


def test_v2_rebuild_preserves_ids_indexes_history_jobs_and_memberships(tmp_path):
    # Construct the actual previous schema using the checked-in baseline schema
    # shape, including a custom column/index to catch accidental loss on rebuild.
    root=tmp_path/'legacy';root.mkdir();db=sqlite3.connect(root/'catalog.sqlite')
    db.executescript('''CREATE TABLE photos(id INTEGER PRIMARY KEY,path TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,bytes INTEGER NOT NULL,mtime INTEGER NOT NULL,rating INTEGER DEFAULT 0,
        recipe TEXT NOT NULL,metadata TEXT DEFAULT '{}',error TEXT DEFAULT '',revision INTEGER DEFAULT 0,
        created REAL NOT NULL,custom_note TEXT DEFAULT 'preserved',flag INTEGER DEFAULT 0,
        sha256 TEXT DEFAULT '',taken INTEGER DEFAULT 0,camera TEXT DEFAULT '',
        burst INTEGER DEFAULT 0,missing INTEGER DEFAULT 0);
        CREATE INDEX custom_index ON photos(custom_note);
        CREATE TABLE versions(id INTEGER PRIMARY KEY,photo_id INTEGER,name TEXT,recipe TEXT,created REAL);
        CREATE TABLE history(id INTEGER PRIMARY KEY,photo_id INTEGER,recipe TEXT,label TEXT,created REAL);
        CREATE TABLE jobs(id INTEGER PRIMARY KEY,photo_id INTEGER,source TEXT,recipe TEXT,
            destination TEXT,format TEXT,state TEXT DEFAULT 'pending',error TEXT DEFAULT '',peak_mb REAL DEFAULT 0,created REAL);
        ''')
    recipe=json.dumps(Recipe(exposure=1).dict())
    db.execute('INSERT INTO photos(id,path,name,bytes,mtime,recipe,created,revision) VALUES(17,?,?,?,?,?,0,8)',
               (str(tmp_path/'missing.png'),'missing.png',123,1,recipe))
    db.commit()
    from lumaraw.organization import migrate_metadata
    from lumaraw.collections import migrate as migrate_collections
    migrate_metadata(db);migrate_collections(db)
    db.execute("INSERT INTO versions VALUES(12,17,'Old snapshot',?,0)",(recipe,))
    db.execute("INSERT INTO history VALUES(24,17,?,'Old edit',0)",(recipe,))
    db.execute("INSERT INTO jobs(id,photo_id,source,recipe,destination,format,created) VALUES(31,17,?,?,?,'jpeg',0)",
               (str(tmp_path/'missing.png'),recipe,str(tmp_path/'out')))
    db.execute("INSERT INTO collections(id,name,kind,created) VALUES(9,'Old album','regular',0)")
    db.execute('INSERT INTO collection_photos VALUES(9,17)')
    db.execute("INSERT INTO photo_keywords VALUES(17,'legacy','Legacy')")
    db.commit();db.close()
    c=Catalog(root)
    assert c.photo(17)['revision']==8 and c.photo(17)['source_id']==17
    assert c.photo(17)['custom_note']=='preserved'
    assert c.db.execute("SELECT 1 FROM sqlite_master WHERE name='custom_index'").fetchone()
    assert c.photo(17)['keywords']==['Legacy']
    assert c.db.execute('SELECT photo_id FROM collection_photos WHERE collection_id=9').fetchone()[0]==17
    assert c.db.execute('SELECT photo_id FROM history WHERE id=24').fetchone()[0]==17
    c.edit(17,Recipe(exposure=2))
    from lumaraw.virtual_copies import VirtualCopies
    id_=VirtualCopies(c).create([{'photo_id':17,'expected_revision':9,'expected_metadata_revision':0}])['photos'][0]['id']
    assert c.versions(id_)[0]['name']=='Old snapshot'
    assert c.jobs()[0]['recipe']==recipe and c.jobs()[0]['source_id']==17 and c.jobs()[0]['id']==31
    assert c.versions(id_)[0]['id']==12
    assert c.db.execute('SELECT photo_id FROM history').fetchone()[0]==17
    c.close();c=Catalog(root)
    assert c.photo(id_)['master_id']==17 and c.count()==2
    c.close()
