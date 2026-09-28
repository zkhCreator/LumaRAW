"""IPTC partial edits, independent XMP fixtures and catalog safety.

Generated files verify named namespaces/RDF containers, extended JPEG packets,
sidecar precedence, absence versus clearing, virtual copies, snapshots and genuine
schema-16 upgrades. No original metadata rewriting or Adobe UI acceptance is claimed.
"""
import io
import json
import sqlite3
import xml.etree.ElementTree as ET

from PIL import Image
import pytest

from lumaraw import iptc
from lumaraw.catalog import Catalog
from lumaraw.export_metadata import xmp_packet,jpeg_segments
from lumaraw.model import Recipe
from lumaraw.runtime import CATALOG_VERSION
from lumaraw.service import Service
from lumaraw.xmp_read import parse_packet,read_xmp,PacketReader,embedded_packets


def snapshot(values):
    return {'version':1,'mode':'catalog','fields':{'iptc':values},'keywords':[],'hierarchy':[]}


def all_fields():
    values={key:['Author One','Author Two'] if field['kind']=='array' else 'Text & <Unicode 海>'
            for key,field in iptc.FIELDS.items()}
    values.update(country_code='USA',subject_codes=['01000000','02000000'],scene_codes=['010100'],
        date_created='2026-09-28T10:11:12.123456789-07:00',copyright_status='copyrighted',
        rights_url='https://example.test/rights?q=one&lang=en')
    return values


def test_all_fields_roundtrip_with_independent_namespace_and_container_assertions():
    values=all_fields()
    data=xmp_packet(snapshot(values))
    parsed,notes=parse_packet(data)
    assert parsed['iptc']==values and not notes
    root=ET.fromstring(data)
    ns={'rdf':'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
        'dc':'http://purl.org/dc/elements/1.1/','ps':'http://ns.adobe.com/photoshop/1.0/',
        'core':'http://iptc.org/std/Iptc4xmpCore/1.0/xmlns/','rights':'http://ns.adobe.com/xap/1.0/rights/'}
    assert [e.text for e in root.findall('.//dc:creator/rdf:Seq/rdf:li',ns)]==values['creator']
    assert root.find('.//ps:City',ns).text==values['city']
    assert root.find('.//ps:TransmissionReference',ns).text==values['job_identifier']
    assert root.find('.//core:CreatorContactInfo/core:CiAdrCtry',ns).text==values['creator_country']
    assert root.find('.//rights:UsageTerms/rdf:Alt/rdf:li',ns).text==values['rights_usage_terms']
    assert root.find('.//rights:WebStatement',ns).get('{'+ns['rdf']+'}resource')==values['rights_url']


def test_independent_contact_forms_empty_arrays_boolean_and_partial_dates():
    packet=b'''<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
      xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:c="http://iptc.org/std/Iptc4xmpCore/1.0/xmlns/"
      xmlns:r="http://ns.adobe.com/xap/1.0/rights/" xmlns:p="http://ns.adobe.com/photoshop/1.0/">
      <rdf:Description r:Marked="False" p:DateCreated="2026-02">
       <dc:creator><rdf:Seq/></dc:creator><c:CreatorContactInfo><rdf:Description c:CiEmailWork="a@example.test">
        <c:CiAdrCity>Paris</c:CiAdrCity></rdf:Description></c:CreatorContactInfo>
       <r:WebStatement rdf:resource="https://example.test/rights"/>
      </rdf:Description></rdf:RDF>'''
    assert parse_packet(packet)[0]['iptc']=={'creator':[],'creator_email':'a@example.test','creator_city':'Paris',
        'copyright_status':'public_domain','date_created':'2026-02','rights_url':'https://example.test/rights'}
    for value in ('2026','2026-02','2024-02-29','2026-02-01T15:00Z'):
        assert iptc.validate({'date_created':value})['date_created']==value
    assert parse_packet(xmp_packet(snapshot({'copyright_status':'unknown'})))[0]=={}
    for values in ({'date_created':'2026-02-29'},{'date_created':'2026-13'},{'country_code':'USAX'},
                   {'subject_codes':['abc']},{'scene_codes':['12345']},{'creator':['']},
                   {'rights_url':'\x00'},{'copyright_status':'maybe'},{'city':'x'*501},{'unsupported':'x'}):
        with pytest.raises(ValueError):
            iptc.validate(values)
    with pytest.raises(ValueError,match='Conflicting XMP contact'):
        parse_packet(packet.replace(b'<c:CiAdrCity>',b'<c:CiEmailWork>b@example.test</c:CiEmailWork><c:CiAdrCity>'))


def test_large_escaped_descriptive_fields_use_verified_extended_jpeg():
    values={key:'&'*5000 for key in ('instructions','rights_usage_terms','extended_description','alt_text')}
    payload=jpeg_segments(snapshot(values))
    data=b'\xff\xd8'+payload+b'\xff\xd9'
    packets=embedded_packets(PacketReader(io.BytesIO(data),len(data)))
    combined={}
    for packet in packets:
        combined.update(parse_packet(packet)[0])
    assert combined['iptc']==values and len(packets)==2
    assert b'http://ns.adobe.com/xmp/extension/' in payload


def test_sidecar_merges_iptc_fields_without_losing_embedded_values(tmp_path):
    source=tmp_path/'photo.jpg'
    data=io.BytesIO();Image.new('RGB',(12,8),'navy').save(data,format='JPEG')
    original=data.getvalue()
    embedded=jpeg_segments(snapshot({'creator':['Alice'],'creator_email':'keep@example.test','city':'Old'}))
    source.write_bytes(original[:2]+embedded+original[2:])
    source.with_suffix('.xmp').write_bytes(xmp_packet(snapshot({'city':'New','creator':[]})))
    before=source.read_bytes()
    assert read_xmp(source)['patch']['iptc']=={'creator':[],'creator_email':'keep@example.test','city':'New'}
    assert source.read_bytes()==before


def test_partial_catalog_fields_variants_and_frozen_export_policies(tmp_path):
    path=tmp_path/'image.png';Image.new('RGB',(12,8),'navy').save(path)
    original=path.read_bytes()
    s=Service(tmp_path/'catalog',presets_root=tmp_path/'presets')
    try:
        s.dispatch('queue_control',{'action':'pause'})
        s.dispatch('import_photos',{'paths':[str(path)]})
        def photo(id_=1):return s.dispatch('get_photo',{'photo_id':id_})
        def edit(values,id_=1):
            return s.dispatch('edit_metadata',{'targets':[{'photo_id':id_,'expected_metadata_revision':photo(id_)['metadata_revision']}],
                'patch':{'iptc':values}})
        edit({'city':'Paris','creator':['Alice'],'creator_email':'private@example.test','rights_usage_terms':'Editorial'})
        before=photo()
        target={'photo_id':1,'expected_revision':before['revision'],'expected_metadata_revision':before['metadata_revision']}
        copy=s.dispatch('create_virtual_copies',{'targets':[target]})['photos'][0]['id']
        assert photo(copy)['iptc']==before['iptc']
        edit({'city':''},copy)
        assert photo()['iptc']['city']=='Paris' and photo(copy)['iptc']['creator']==['Alice']
        assert photo(copy)['revision']==0
        result=edit({'rights_url':'https://example.test/rights'})
        assert result['patch']['iptc']=={'rights_url':'https://example.test/rights'}
        assert photo()['iptc']['city']=='Paris' and photo()['taken']==before['taken']
        copyright=s.dispatch('preview_export_metadata',{'photo_id':1,'metadata':'copyright'})['fields']
        assert copyright['iptc']=={'rights_usage_terms':'Editorial','rights_url':'https://example.test/rights'}
        assert s.dispatch('preview_export_metadata',{'photo_id':1,'metadata':'none'})['fields']=={}
        job=s.dispatch('enqueue_exports',{'photo_ids':[1],'destination':str(tmp_path/'out'),
            'format':'jpeg','request_key':'frozen'})['job_ids'][0]
        with s.catalog() as c:
            frozen=c.db.execute('SELECT metadata_snapshot FROM jobs WHERE id=?',(job,)).fetchone()[0]
        edit({'creator_email':'new@example.test'})
        with s.catalog() as c:
            assert c.db.execute('SELECT metadata_snapshot FROM jobs WHERE id=?',(job,)).fetchone()[0]==frozen
        assert json.loads(frozen)['fields']['iptc']['creator_email']=='private@example.test'
        assert path.read_bytes()==original and 'iptc' not in s.dispatch('list_photos')['photos'][0]
    finally:
        s.close()


def test_schema16_migration_failure_preserves_original_schema_and_rows(tmp_path,monkeypatch):
    from lumaraw import catalog as module
    from legacy_catalog import migrate_to
    root=tmp_path/'legacy'
    with monkeypatch.context() as context:
        context.setattr(module,'migrate',lambda db:migrate_to(db,16))
        c=Catalog(root)
        recipe=json.dumps(Recipe(exposure=1).dict())
        with c.db:
            c.db.execute("INSERT INTO photos(path,name,bytes,mtime,recipe,created,orientation) VALUES('old.png','old.png',0,0,?,0,3)",(recipe,))
        c.db.set_authorizer(lambda action,a,b,d,t:sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_ALTER_TABLE else sqlite3.SQLITE_OK)
        with pytest.raises(sqlite3.DatabaseError):
            iptc.migrate(c.db)
        c.db.set_authorizer(None)
        assert c.db.execute('PRAGMA user_version').fetchone()[0]==16
        assert 'iptc' not in [r[1] for r in c.db.execute('PRAGMA table_info(photos)')]
        c.close()
    c=Catalog(root)
    try:
        assert c.db.execute('PRAGMA user_version').fetchone()[0]==CATALOG_VERSION
        assert c.db.execute('SELECT recipe,orientation,iptc FROM photos').fetchone()[:]==(recipe,3,'{}')
    finally:
        c.close()


def test_folder_sync_reads_partial_iptc_and_preserves_virtual_copies(tmp_path):
    from test_folder_sync import prepare,scan,apply,copy,photo
    source=tmp_path/'photos'/'image.png';source.parent.mkdir()
    Image.new('RGB',(12,8),'navy').save(source)
    original=source.read_bytes()
    s=Service(tmp_path/'catalog',presets_root=tmp_path/'presets')
    try:
        s.dispatch('import_photos',{'paths':[str(source)]})
        s.dispatch('edit_metadata',{'targets':[{'photo_id':1,'expected_metadata_revision':0}],
            'patch':{'iptc':{'city':'Paris','creator':['Alice']}}})
        variant=copy(s,1)
        source.with_suffix('.xmp').write_bytes(xmp_packet(snapshot({'city':'Rome','creator_email':'a@example.test'})))
        plan=scan(s,prepare(s))
        assert plan['state']=='ready' and plan['counts']=={'updated':1}
        assert apply(s,plan)['modified']==1
        assert photo(s,1)['iptc']=={'city':'Rome','creator':['Alice'],'creator_email':'a@example.test'}
        assert photo(s,variant)['iptc']=={'city':'Paris','creator':['Alice']}
        plan=scan(s,prepare(s))
        assert plan['counts']=={'unchanged':1} and apply(s,plan)['modified']==0
        assert source.read_bytes()==original
    finally:s.close()


def test_iptc_merged_size_failure_rolls_back_all_targets(tmp_path):
    s=Service(tmp_path/'catalog',presets_root=tmp_path/'presets')
    paths=[]
    for i in range(2):
        path=tmp_path/f'{i}.png';Image.new('RGB',(4,4)).save(path);paths.append(str(path))
    try:
        s.dispatch('import_photos',{'paths':paths})
        current={'instructions':'🌊'*5000,'rights_usage_terms':'🌊'*5000,'extended_description':'🌊'*5000}
        s.dispatch('edit_metadata',{'targets':[{'photo_id':2,'expected_metadata_revision':0}],'patch':{'iptc':current}})
        targets=[{'photo_id':1,'expected_metadata_revision':0},{'photo_id':2,'expected_metadata_revision':1}]
        patch={'caption':'Must roll back','iptc':{'alt_text':'🌊'*5000}}
        with pytest.raises(ValueError,match='64 KiB'):
            s.dispatch('edit_metadata',{'targets':targets,'patch':patch})
        state=s.dispatch('list_metadata_presets')
        saved=s.dispatch('save_metadata_preset',{'expected_revision':state['revision'],'name':'Too much','patch':patch})
        with pytest.raises(ValueError,match='64 KiB'):
            s.dispatch('apply_metadata_preset',{'targets':targets,'preset_id':saved['preset_id'],'expected_revision':saved['revision']})
        one=s.dispatch('get_photo',{'photo_id':1});two=s.dispatch('get_photo',{'photo_id':2})
        assert one['iptc']=={} and one['caption']=='' and one['metadata_revision']==0
        assert two['iptc']==current and two['caption']=='' and two['metadata_revision']==1
    finally:s.close()
