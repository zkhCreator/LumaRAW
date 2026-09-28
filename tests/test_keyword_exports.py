"""Keyword export flags, frozen metadata and additive schema-eleven migration.

Inputs: generated images and catalog edits only. Outputs: metadata projection,
immutable queued snapshots, bounded public receipts and rollback guarantees.
Adobe checkbox-combination equivalence still requires reference-app acceptance.
"""
import json
import sqlite3

from PIL import Image
import pytest

from lumaraw.catalog import Catalog
from lumaraw.keyword_exports import migrate
from lumaraw.library import backup_catalog,restore_catalog
from lumaraw.service import Service
from test_keywords import save,assign,photo,targets


@pytest.fixture
def library(tmp_path):
    source=tmp_path/'photo.png';Image.new('RGB',(16,12),'navy').save(source)
    s=Service(tmp_path/'catalog');s.dispatch('queue_control',{'action':'pause'})
    s.dispatch('import_photos',{'paths':[str(source)]})
    yield s,source
    s.close()


def preview(s,**kwargs):
    return s.dispatch('preview_export_metadata',{'photo_id':1,**kwargs})


def enqueue(s,destination,key='first',**options):
    return s.dispatch('enqueue_exports',{'photo_ids':[1],'destination':str(destination),
        'format':'jpeg','request_key':key,'options':options})['job_ids'][0]


def test_nested_export_policies_synonyms_and_duplicate_leaf_paths(library):
    s,_=library
    private=save(s,'Private category',synonyms=['Hidden alias'],include_export=False)
    parent=save(s,'Places',parent_id=private,synonyms=['Locations'])
    leaf=save(s,'Coast',parent_id=parent,synonyms=['Shore','COAST'])
    other=save(s,'People')
    alternate=save(s,'Coast',parent_id=other,export_synonyms=False)
    assign(s,leaf,[1]);assign(s,alternate,[1])
    assert preview(s)['items']==['Coast','Locations','People','Places','Shore']
    assert preview(s,kind='hierarchy')['items']==['People|Coast','Places|Coast']
    save(s,'Coast',keyword_id=leaf,parent_id=parent,synonyms=['Shore'],export_containing=False,export_synonyms=False)
    assert preview(s)['items']==['Coast','People']
    assert preview(s,kind='hierarchy')['items']==['Coast','People|Coast']
    assert photo(s,1)['keywords']==['People | Coast','Private category | Places | Coast']


def test_containing_policy_stops_at_an_intermediate_parent(library):
    s,_=library
    grandparent=save(s,'Country')
    parent=save(s,'City',parent_id=grandparent,export_containing=False)
    leaf=save(s,'Street',parent_id=parent)
    assign(s,leaf,[1])
    assert preview(s)['items']==['City','Street']
    assert preview(s,kind='hierarchy')['items']==['City|Street']
    assign(s,grandparent,[1])
    assert preview(s)['items']==['City','Country','Street']
    assert preview(s,kind='hierarchy')['items']==['City|Street','Country']


def test_disabled_leaf_can_export_containing_keywords_but_not_its_synonyms(library):
    s,_=library
    parent=save(s,'Public')
    leaf=save(s,'Private',parent_id=parent,synonyms=['Secret'],include_export=False)
    assign(s,leaf,[1])
    assert preview(s)['items']==['Public']
    assert preview(s,kind='hierarchy')['items']==['Public']
    save(s,'Private',keyword_id=leaf,parent_id=parent,synonyms=['Secret'],export_containing=False)
    assert preview(s)['items']==[]


def test_old_keyword_editor_preserves_policies_and_revision_conflicts(library):
    s,_=library
    tag=save(s,'One',include_export=False,export_containing=False,export_synonyms=False)
    assign(s,tag,[1]);revision=photo(s,1)['metadata_revision']
    expected=s.dispatch('library_state')['keyword_revision']
    save(s,'Two',keyword_id=tag)
    row=s.dispatch('list_keywords')['keywords'][0]
    assert all(row[key]==0 for key in ('include_export','export_containing','export_synonyms'))
    assert photo(s,1)['metadata_revision']==revision+1
    with pytest.raises(ValueError,match='Keyword list changed'):
        s.dispatch('save_keyword',{'keyword_id':tag,'name':'Stale','expected_revision':expected,'include_export':True})
    assert preview(s)['items']==[]


def test_metadata_policies_and_paged_expansion(library):
    s,_=library
    s.dispatch('edit_metadata',{'targets':targets(s,[1]),'patch':{'title':'海边','caption':'Caption','copyright':'© Owner','color_label':'blue'}})
    for number in range(3):
        tag=save(s,f'Word {number}',synonyms=[f'Alias {number}-{i:02}' for i in range(30)])
        assign(s,tag,[1])
    result=preview(s)
    assert result['total']==93 and len(result['items'])==60 and result['fields']['title']=='海边'
    assert preview(s,offset=9999)['offset']==60 and len(preview(s,offset=60)['items'])==33
    assert preview(s,metadata='copyright')['fields']=={'copyright':'© Owner'}
    assert preview(s,metadata='copyright')['items']==[]
    assert preview(s,metadata='none')['fields']=={} and preview(s,metadata='none')['items']==[]
    assert preview(s,kind='hierarchy',keyword_hierarchy=False)['items']==[]


def test_queue_freezes_metadata_policies_before_edits_and_removal(library,tmp_path):
    s,_=library
    tag=save(s,'First',synonyms=['Original synonym']);assign(s,tag,[1])
    s.dispatch('edit_metadata',{'targets':targets(s,[1]),'patch':{'title':'Submitted'}})
    id_=enqueue(s,tmp_path/'exports',keyword_hierarchy=True)
    with s.catalog() as c:
        snapshot=c.db.execute('SELECT metadata_snapshot FROM jobs WHERE id=?',(id_,)).fetchone()[0]
    public=s.dispatch('get_job',{'job_id':id_})
    assert 'metadata_snapshot' not in public and public['export_metadata']['keyword_count']==2
    assert 'metadata_snapshot' not in s.dispatch('list_jobs')['jobs'][0]
    save(s,'Later',keyword_id=tag,include_export=False)
    s.dispatch('edit_metadata',{'targets':targets(s,[1]),'patch':{'title':'After queue'}})
    assert enqueue(s,tmp_path/'exports',keyword_hierarchy=True)==id_
    with s.catalog() as c:
        assert c.db.execute('SELECT metadata_snapshot FROM jobs WHERE id=?',(id_,)).fetchone()[0]==snapshot
        parsed=json.loads(snapshot)
        assert parsed['fields']['title']=='Submitted' and parsed['keywords']==['First','Original synonym']
        backup_catalog(c,tmp_path/'backup')
    restored=Catalog(restore_catalog(tmp_path/'backup',tmp_path/'restored'))
    try:
        assert restored.db.execute('SELECT metadata_snapshot FROM jobs WHERE id=?',(id_,)).fetchone()[0]==snapshot
    finally:restored.close()


def test_invalid_xml_metadata_rolls_back_entire_batch_and_request(library,tmp_path):
    s,source=library
    second=source.with_name('second.png');Image.new('RGB',(8,8)).save(second)
    s.dispatch('import_photos',{'paths':[str(second)]})
    s.dispatch('edit_metadata',{'targets':targets(s,[2]),'patch':{'title':'Bad\u0001text'}})
    params={'photo_ids':[1,2],'destination':str(tmp_path/'exports'),'format':'jpeg','request_key':'atomic'}
    with pytest.raises(ValueError,match='XML'):s.dispatch('enqueue_exports',params)
    assert s.dispatch('list_jobs')['jobs']==[]
    with s.catalog() as c:assert c.db.execute("SELECT 1 FROM requests WHERE key='atomic'").fetchone() is None
    params['options']={'metadata':'none'}
    assert s.dispatch('enqueue_exports',params)['queued']==2


def test_large_frozen_snapshot_reaches_real_worker_without_bloating_queue(library,tmp_path):
    import hashlib
    from pathlib import Path
    import xml.etree.ElementTree as ET
    from lumaraw.export_metadata import NS
    from lumaraw.xmp_read import PacketReader,embedded_packets
    from test_service import wait_jobs
    s,source=library
    before=hashlib.sha256(source.read_bytes()).digest()
    for number in range(40):
        tag=save(s,f'Word {number}',synonyms=[f'{number}-{i}-'+('海'*100) for i in range(30)])
        assign(s,tag,[1])
    job_id=enqueue(s,tmp_path/'large',keyword_hierarchy=True)
    with s.catalog() as c:
        frozen=c.db.execute('SELECT metadata_snapshot FROM jobs WHERE id=?',(job_id,)).fetchone()[0]
    assert 256*1024 < len(frozen.encode()) < 2*1024*1024
    assert len(json.dumps(s.dispatch('list_jobs')).encode()) < 10000
    s.dispatch('queue_control',{'action':'resume'})
    assert wait_jobs(s)['counts']=={'done':1}
    output=Path(s.dispatch('get_job',{'job_id':job_id})['output'])
    with output.open('rb') as stream:
        packets=embedded_packets(PacketReader(stream,output.stat().st_size))
    assert len(packets)==2
    words=[node.text for data in packets for node in ET.fromstring(data).findall('.//dc:subject/rdf:Bag/rdf:li',NS)]
    assert words==json.loads(frozen)['keywords'] and len(words)==1240
    assert hashlib.sha256(source.read_bytes()).digest()==before


def test_genuine_v10_migration_preserves_old_jobs_and_rolls_back(tmp_path,monkeypatch):
    import lumaraw.catalog as module
    from legacy_catalog import migrate_to
    with monkeypatch.context() as patch:
        patch.setattr(module,'migrate',lambda db:migrate_to(db,10))
        c=Catalog(tmp_path/'legacy')
    with c.db:
        tag=c.db.execute("INSERT INTO keywords(name,normalized) VALUES('Old','old')").lastrowid
        c.db.execute("INSERT INTO jobs(photo_id,source,recipe,destination,format,created) VALUES(1,'old.png','{}','out','jpeg',0)")
    previous=[tuple(row) for row in c.db.execute('SELECT * FROM jobs')]
    c.db.set_authorizer(lambda action,database,table,*rest:sqlite3.SQLITE_DENY
        if action==sqlite3.SQLITE_ALTER_TABLE and table=='jobs' else sqlite3.SQLITE_OK)
    with pytest.raises(sqlite3.DatabaseError):migrate(c.db)
    c.db.set_authorizer(None)
    assert c.db.execute('PRAGMA user_version').fetchone()[0]==10
    assert 'include_export' not in {r[1] for r in c.db.execute('PRAGMA table_info(keywords)')}
    migrate(c.db)
    assert c.db.execute('PRAGMA user_version').fetchone()[0]==11
    row=dict(c.db.execute('SELECT * FROM jobs').fetchone())
    assert row.pop('metadata_snapshot')=='{}' and row.pop('export_metadata')=='{}'
    assert tuple(row.values())==previous[0]
    assert tuple(c.db.execute('SELECT include_export,export_containing,export_synonyms FROM keywords WHERE id=?',(tag,)).fetchone())==(1,1,1)
    c.close()
