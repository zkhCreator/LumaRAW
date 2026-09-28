"""Complete vocabulary browsing remains bounded without losing editable values.

Inputs: valid maximal Unicode tags created through a real broker and isolated
legacy literals. Outputs: bounded tree/search pages, full revision-bound details,
preserved synonyms/export policies and visible stale/removed-keyword failures.
No image processing, personal data or rendered desktop claims.
"""
import json

from PIL import Image

from test_keyword_details import broker, library
from test_keywords import save


def response_bytes(value):
    return len(json.dumps({'ok':True,'result':value},ensure_ascii=False).encode())


def test_maximal_vocabulary_pages_and_edits_through_real_broker(broker,tmp_path):
    rpc=broker
    image=tmp_path/'original.png';Image.new('RGB',(4,4)).save(image)
    before=image.read_bytes()
    rpc('import_photos',{'paths':[str(image)]})
    revision=0
    def create(name,**kwargs):
        nonlocal revision
        result=rpc('save_keyword',{'name':name,'expected_revision':revision,**kwargs})
        revision=result['keyword_revision']
        return result['keyword_id']
    parent=None;ancestors=[]
    for i in range(31):
        name=f'{i:02}'+('🌊'*118);ancestors.append(name)
        parent=create(name,parent_id=parent)
    synonyms=[f'{i:02}'+('🐳'*118) for i in range(30)]
    ids=[create(f'{i:02}'+('🌴'*118),parent_id=parent,synonyms=synonyms,
                include_export=False,export_containing=False,export_synonyms=False) for i in range(67)]
    result=rpc('keyword_membership',{'keyword_id':ids[0],'action':'add','expected_revision':revision,
        'targets':[{'photo_id':1,'expected_metadata_revision':0}]})
    revision=result['keyword_revision']
    pages=[rpc('list_keywords',{'parent_id':parent,'offset':offset,'photo_ids':[1]}) for offset in (0,60)]
    assert [len(p['keywords']) for p in pages]==[60,7]
    assert all(p['total']==67 and p['page_size']==60 and response_bytes(p)<512*1024 for p in pages)
    rows=pages[0]['keywords']+pages[1]['keywords']
    assert [r['id'] for r in rows]==ids
    assert rows[0]['photo_count']==rows[0]['selected_count']==1 and rows[1]['photo_count']==0
    for row in rows:
        assert row['details_deferred'] and row['path'] is None and row['synonyms'] is None
        assert '…' in row['path_preview'] and row['name'] in row['path_preview']
        detail=rpc('get_keyword',{'keyword_id':row['id'],'expected_revision':revision})
        assert response_bytes(detail)<64*1024
        full=detail['keyword']
        assert full['path']==' | '.join(ancestors+[row['name']])
        assert full['parent_path']==' | '.join(ancestors) and full['synonyms']==synonyms
        assert not full['details_deferred'] and full['parent_id']==parent
        assert full['include_export']==full['export_containing']==full['export_synonyms']==0
    search=rpc('list_keywords',{'search':'🐳','offset':9999})
    assert search['total']==67 and search['offset']==60 and len(search['keywords'])==7
    assert response_bytes(search)<512*1024
    first=rpc('get_keyword',{'keyword_id':ids[0],'expected_revision':revision})['keyword']
    result=rpc('save_keyword',{'keyword_id':first['id'],'parent_id':first['parent_id'],'name':'Renamed',
        'synonyms':first['synonyms'],'expected_revision':revision,'include_export':True})
    stale={'keyword_id':ids[0],'expected_revision':revision}
    assert 'changed' in rpc('get_keyword',stale,ok=False)['error']
    revision=result['keyword_revision']
    fresh=rpc('get_keyword',{'keyword_id':ids[0],'expected_revision':revision})['keyword']
    assert fresh['synonyms']==synonyms and fresh['include_export']==1
    assert fresh['export_containing']==fresh['export_synonyms']==0
    rpc('delete_keyword',{'keyword_id':ids[0],'expected_revision':revision})
    revision=rpc('library_state')['keyword_revision']
    assert 'does not exist' in rpc('get_keyword',{'keyword_id':ids[0],'expected_revision':revision},ok=False)['error']
    assert image.read_bytes()==before


def test_small_rows_keep_inline_values_and_legacy_parent_identity(library):
    s=library
    root=save(s,'Parent',synonyms=['Alias']);child=save(s,'Child',parent_id=root)
    page=s.dispatch('list_keywords')
    row=page['keywords'][0]
    assert not row['details_deferred'] and row['path']=='Parent' and row['synonyms']==['Alias']
    with s.catalog() as c,c.db:
        c.db.execute("UPDATE keywords SET name='Literal | Parent',normalized='literal | parent' WHERE id=?",(root,))
        c.db.execute('UPDATE keyword_state SET revision=revision+1')
    revision=s.dispatch('library_state')['keyword_revision']
    detail=s.dispatch('get_keyword',{'keyword_id':child,'expected_revision':revision})['keyword']
    assert detail['parent_path']=='Literal | Parent' and detail['parent_id']==root
    assert detail['path']=='Literal | Parent | Child'
    large=save(s,'Short',synonyms=[f'{i:02}'+('🐳'*118) for i in range(30)])
    row=next(r for r in s.dispatch('list_keywords')['keywords'] if r['id']==large)
    assert row['details_deferred'] and row['path_preview']=='Short'
    revision=s.dispatch('library_state')['keyword_revision']
    assert len(s.dispatch('get_keyword',{'keyword_id':large,'expected_revision':revision})['keyword']['synonyms'])==30
