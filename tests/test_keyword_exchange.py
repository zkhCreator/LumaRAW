"""Atomic keyword dictionary exchange, migration and resource-bound evidence.

Inputs: generated UTF-8 dictionaries, photographs and genuine schema-eleven data.
Outputs: complete catalog/file round trips, preserved existing identities/policies,
rollback and no-overwrite behavior over service and real IPC. Generated CSVs are
format fixtures, not claimed reference-application interoperability receipts.
"""
import hashlib
from pathlib import Path
import sqlite3
import threading

from PIL import Image
import pytest

from lumaraw.catalog import Catalog
from lumaraw.keyword_exchange import migrate, CSV_HEADER, MAX_BYTES
from lumaraw.service import Service
from test_keyword_details import broker
from test_keywords import save, assign, photo


@pytest.fixture
def library(tmp_path):
    path=tmp_path/'original.png';Image.new('RGB',(8,8),'navy').save(path)
    s=Service(tmp_path/'catalog');s.dispatch('queue_control',{'action':'pause'})
    s.dispatch('import_photos',{'paths':[str(path)]})
    yield s,path
    s.close()


def revision(s):
    return s.dispatch('library_state')['keyword_revision']


def import_text(s,path,text):
    path.write_text(text,encoding='utf-8')
    return s.dispatch('import_keywords',{'path':str(path),'expected_revision':revision(s)})


def tree(s):
    with s.catalog() as c:
        ids=[r[0] for r in c.db.execute('SELECT id FROM keywords')]
    tags=[s.dispatch('get_keyword',{'keyword_id':id_,'expected_revision':revision(s)})['keyword'] for id_ in ids]
    return {r['path']:(r['synonyms'],r['include_export'],r['export_containing'],r['export_synonyms'],r['is_person']) for r in tags}


def test_text_import_preserves_existing_metadata_assignments_and_frozen_jobs(library,tmp_path):
    s,path=library
    parent=save(s,'Places',synonyms=['Original'],include_export=True,export_containing=False,is_person=True)
    coast=save(s,'Coast',parent_id=parent,export_synonyms=False);assign(s,coast,[1])
    before=photo(s,1);original=path.read_bytes()
    job=s.dispatch('enqueue_exports',{'photo_ids':[1],'destination':str(tmp_path/'exports'),'format':'jpeg','request_key':'frozen'})['job_ids'][0]
    before_job=s.dispatch('get_job',{'job_id':job})
    result=import_text(s,tmp_path/'words.txt','\ufeff[Places]\r\n\t{New alias}\r\n\tCoast\r\n\t\t{Added alias}\r\n\t海岸 🌊\r\n\t\t{Shore}\r\nOther\r\n\tCoast\r\n')
    assert (result['created'],result['existing'],result['keywords'])==(3,2,5)
    assert result['sha256']==hashlib.sha256((tmp_path/'words.txt').read_bytes()).hexdigest()
    values=tree(s)
    assert values['Places']==(['Original'],1,0,1,1)
    assert values['Places | Coast']==([],1,1,0,0)
    assert values['Places | 海岸 🌊']==(['Shore'],1,1,1,0)
    assert 'Other | Coast' in values
    assert photo(s,1)==before and path.read_bytes()==original
    assert s.dispatch('get_job',{'job_id':job})==before_job
    now=revision(s)
    again=s.dispatch('import_keywords',{'path':str(tmp_path/'words.txt'),'expected_revision':now})
    assert again['created']==0 and again['existing']==5 and revision(s)==now
    with pytest.raises(ValueError,match='changed'):
        s.dispatch('import_keywords',{'path':str(tmp_path/'words.txt'),'expected_revision':now-1})


def test_csv_roundtrip_retains_all_options_and_text_reports_omitted_options(library,tmp_path):
    s,_=library
    parent=save(s,'Group "A"',include_export=False,export_containing=False,is_person=True)
    save(s,'海岸',parent_id=parent,synonyms=['Shore','{Literal}'],export_synonyms=False)
    target=Service(tmp_path/'second')
    try:
        path=tmp_path/'dictionary.csv'
        exported=s.dispatch('export_keywords',{'path':str(path),'format':'csv','expected_revision':revision(s)})
        assert exported['keywords']==2 and exported['synonyms']==2 and exported['omitted_options']==0
        assert path.read_text().splitlines()[0]==','.join(CSV_HEADER)
        imported=target.dispatch('import_keywords',{'path':str(path),'expected_revision':0})
        assert imported['format']=='csv' and tree(target)==tree(s)
        text=tmp_path/'dictionary.txt'
        result=s.dispatch('export_keywords',{'path':str(text),'format':'text','expected_revision':revision(s)})
        assert result['omitted_options']==2 and '[Group "A"]' in text.read_text()
        assert '\t\t{{Literal}}' in text.read_text()
    finally:target.close()


@pytest.mark.parametrize('content',[
    'Okay\n\t\tSkipped\n', '\tOrphan\n', '{Orphan alias}\n',
    'Okay\n'+''.join('\t'*i+f'Depth{i}\n' for i in range(1,33)),
    'Okay\n'+''.join('\t{Alias'+str(i)+'}\n' for i in range(31)),
    'Same\n[Same]\n', 'Okay\nBad,keyword\n', 'Okay\n'+('X'*8193),
    ','.join(CSV_HEADER)+'\nY,Y,,N,Incomplete\n',
    ','.join(CSV_HEADER)+'\nY,Y,Z,N,Invalid\n',
    ','.join(CSV_HEADER)+'\n"Y,Y,Y,N,Quoted whole row"\n',
    ','.join(CSV_HEADER)+'\nY,Y,Y,N,"Unclosed\n',
])
def test_invalid_dictionary_never_partially_imports(library,tmp_path,content):
    s,_=library;save(s,'Existing');before=tree(s);rev=revision(s)
    with pytest.raises(ValueError,match='Keyword line'):
        import_text(s,tmp_path/'bad.txt',content)
    assert tree(s)==before and revision(s)==rev


def test_file_limits_and_complete_transaction_rollback(library,tmp_path):
    s,_=library
    path=tmp_path/'bad.txt';path.write_bytes(b'Good\n\xff')
    with pytest.raises(ValueError,match='UTF-8'):
        s.dispatch('import_keywords',{'path':str(path),'expected_revision':0})
    with path.open('wb') as stream:stream.truncate(MAX_BYTES+1)
    with pytest.raises(ValueError,match='64 MiB'):
        s.dispatch('import_keywords',{'path':str(path),'expected_revision':0})
    with s.catalog() as c,c.db:
        c.db.execute("CREATE TRIGGER deny_keyword BEFORE INSERT ON keywords WHEN NEW.name='Fail' BEGIN SELECT RAISE(ABORT,'Denied insertion'); END")
    with pytest.raises(sqlite3.IntegrityError,match='Denied'):
        import_text(s,path,'First\nFail\n')
    assert tree(s)=={} and revision(s)==0
    # A keyword whose ordinary name resembles a CSV column is still plain text.
    result=import_text(s,path,'Include On Export\n')
    assert result['created']==1 and result['format']=='text'


def test_export_never_replaces_files_or_publishes_partial_invalid_output(library,tmp_path,monkeypatch):
    import lumaraw.keyword_exchange as module
    s,original=library
    save(s,'Valid')
    destination=tmp_path/'saved.txt';destination.write_bytes(b'Preserve')
    with pytest.raises(FileExistsError):
        s.dispatch('export_keywords',{'path':str(destination),'format':'text','expected_revision':revision(s)})
    assert destination.read_bytes()==b'Preserve'
    alias=tmp_path/'link.txt';alias.symlink_to(original)
    before=original.read_bytes()
    with pytest.raises(FileExistsError):
        s.dispatch('export_keywords',{'path':str(alias),'format':'text','expected_revision':revision(s)})
    assert original.read_bytes()==before
    with monkeypatch.context() as patch:
        patch.setattr(module.os,'link',lambda *args:(_ for _ in ()).throw(OSError('Publication failed')))
        with pytest.raises(OSError,match='Publication'):
            s.dispatch('export_keywords',{'path':str(tmp_path/'failure.txt'),'format':'text','expected_revision':revision(s)})
    assert not (tmp_path/'failure.txt').exists() and not list(tmp_path.glob('.lumaraw-keywords-*'))
    save(s,'{Ambiguous}')
    with pytest.raises(ValueError,match='represented'):
        s.dispatch('export_keywords',{'path':str(tmp_path/'invalid.txt'),'format':'text','expected_revision':revision(s)})
    assert not (tmp_path/'invalid.txt').exists()


def test_input_and_destination_io_release_catalog_lock(library,tmp_path,monkeypatch):
    import lumaraw.keyword_exchange as module
    s,_=library;path=tmp_path/'input.txt';path.write_text('One\n')
    for operation,attribute,params in (
        ('import_keywords','copy_input',{'path':str(path),'expected_revision':0}),
        ('export_keywords','copyfileobj',{'path':str(tmp_path/'out.txt'),'format':'text','expected_revision':1})):
        owner=module if attribute=='copy_input' else module.shutil
        original=getattr(owner,attribute);started=threading.Event();release=threading.Event();errors=[]
        def paused(*args,**kwargs):
            started.set();assert release.wait(5)
            return original(*args,**kwargs)
        def run():
            try:s.dispatch(operation,params)
            except Exception as error:errors.append(error)
        with monkeypatch.context() as patch:
            patch.setattr(owner,attribute,paused)
            thread=threading.Thread(target=run);thread.start()
            try:
                assert started.wait(5)
                assert s.lock.acquire(blocking=False)
                s.lock.release()
            finally:release.set();thread.join(10)
        assert not thread.is_alive() and errors==[]


def test_genuine_v11_person_flag_migration_and_backup(tmp_path,monkeypatch):
    import lumaraw.catalog as module
    from legacy_catalog import migrate_to
    from lumaraw.library import backup_catalog,restore_catalog
    with monkeypatch.context() as patch:
        patch.setattr(module,'migrate',lambda db:migrate_to(db,11))
        c=Catalog(tmp_path/'old')
    with c.db:
        id_=c.db.execute("INSERT INTO keywords(name,normalized,include_export) VALUES('Old','old',0)").lastrowid
    previous=dict(c.db.execute('SELECT * FROM keywords').fetchone())
    c.db.set_authorizer(lambda action,database,table,*rest:sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_ALTER_TABLE else sqlite3.SQLITE_OK)
    with pytest.raises(sqlite3.DatabaseError):migrate(c.db)
    c.db.set_authorizer(None)
    assert c.db.execute('PRAGMA user_version').fetchone()[0]==11
    migrate(c.db);migrate(c.db)
    row=dict(c.db.execute('SELECT * FROM keywords').fetchone());assert row.pop('is_person')==0 and row==previous
    with c.db:c.db.execute('UPDATE keywords SET is_person=1 WHERE id=?',(id_,))
    backup_catalog(c,tmp_path/'backup');c.close()
    restored=Catalog(restore_catalog(tmp_path/'backup',tmp_path/'restored'))
    assert restored.db.execute('PRAGMA user_version').fetchone()[0]==12
    assert restored.db.execute('SELECT is_person FROM keywords WHERE id=?',(id_,)).fetchone()[0]==1
    restored.close()


def test_exchange_through_real_broker_has_compact_receipts(broker,tmp_path):
    path=tmp_path/'input.txt'
    path.write_text('[Locations]\n'+''.join(f'\tPlace {i:04}\n\t\t{{Alias {i:04}}}\n' for i in range(1000)),encoding='utf-8')
    result=broker('import_keywords',{'path':str(path),'expected_revision':0})
    assert result['created']==1001 and result['input_synonyms']==1000
    output=tmp_path/'output.csv'
    receipt=broker('export_keywords',{'path':str(output),'format':'csv','expected_revision':result['keyword_revision']})
    assert receipt['keywords']==1001 and receipt['synonyms']==1000
    assert broker('list_keywords',{'parent_id':1})['total']==1000
