"""Read-only metadata fixtures for folder synchronization.

Inputs: generated sidecar, JPEG, TIFF and PNG packets. Outputs: exact supported
properties and bounded-parser failures. No external photographs or pixel-equivalence
claims. Hashes prove readers leave both image and metadata files unchanged.
"""
import hashlib
import io
from pathlib import Path

from PIL import Image, PngImagePlugin
import pytest
import tifffile
import numpy as np

from lumaraw.xmp_read import MAX_PACKET, parse_packet, read_xmp


def packet(properties='', attributes=''):
    return (f'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
            f'<rdf:Description xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:xmp="http://ns.adobe.com/xap/1.0/" '
            f'xmlns:lr="http://ns.adobe.com/lightroom/1.0/" xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/" '
            f'{attributes}>{properties}</rdf:Description></rdf:RDF></x:xmpmeta>').encode()


def test_language_alternatives_hierarchy_flat_tags_and_explicit_empty_values():
    patch,notes = parse_packet(packet('''
      <dc:title><rdf:Alt><rdf:li xml:lang="fr">Mer</rdf:li><rdf:li xml:lang="x-default">海边</rdf:li></rdf:Alt></dc:title>
      <dc:description><rdf:Alt><rdf:li xml:lang="x-default"></rdf:li></rdf:Alt></dc:description>
      <lr:hierarchicalSubject><rdf:Bag><rdf:li>Places|Coast</rdf:li><rdf:li>People|Coast</rdf:li></rdf:Bag></lr:hierarchicalSubject>
      <dc:subject><rdf:Bag><rdf:li>Coast</rdf:li><rdf:li>Travel</rdf:li></rdf:Bag></dc:subject>
    ''', 'xmp:Rating="4" xmp:Label="Blue" crs:Exposure2012="1.5"'))
    assert patch == {'title':'海边','caption':'','rating':4,'color_label':'blue',
                     'keyword_paths':[['Places','Coast'],['People','Coast'],['Travel']]}
    assert 'Develop' in notes[0]
    assert 'copyright' not in patch and 'flag' not in patch


@pytest.mark.parametrize('value,expected',[('-1',{'flag':-1}),('0',{'rating':0}),('5.0',{'rating':5})])
def test_rating_rejection_and_unrated_mapping(value,expected):
    assert parse_packet(packet(attributes=f'xmp:Rating="{value}"'))[0] == expected


def test_unknown_labels_are_reported_not_recolored():
    patch,notes = parse_packet(packet(attributes='xmp:Label="Client approved"'))
    assert patch == {} and 'not mapped' in notes[0]


@pytest.mark.parametrize('properties,attrs',[
    ('','xmp:Rating="3.5"'),('','xmp:Rating="NaN"'),('','xmp:Rating="6"'),
    ('<dc:title>One</dc:title><dc:title>Two</dc:title>',''),
    ('<dc:subject>not-an-array</dc:subject>',''),
    ('<dc:title>'+('x'*501)+'</dc:title>',''),
    ('<dc:subject><rdf:Bag>'+''.join(f'<rdf:li>tag{i}</rdf:li>' for i in range(101))+'</rdf:Bag></dc:subject>',''),
])
def test_invalid_or_unrepresentable_properties_fail_without_truncation(properties,attrs):
    with pytest.raises(ValueError):parse_packet(packet(properties,attrs))


@pytest.mark.parametrize('encoding',['utf-8','utf-16'])
def test_document_types_rejected_in_multiple_encodings(encoding):
    value = '<!DOCTYPE x [<!ENTITY name "expanded">]>'+packet('<dc:title>&name;</dc:title>').decode()
    with pytest.raises(ValueError,match='document types'):
        parse_packet(value.encode(encoding))


def test_structure_and_packet_limits():
    with pytest.raises(ValueError,match='structure'):
        parse_packet(packet('<a>'*70+'value'+'</a>'*70))
    with pytest.raises(ValueError,match='2 MiB'):
        parse_packet(b' '*(MAX_PACKET+1))


@pytest.mark.parametrize('fmt',['jpeg','tiff','png','png-compressed'])
def test_embedded_packets_and_sidecar_precedence_leave_files_unchanged(tmp_path,fmt):
    embedded = packet('<dc:title>Embedded title</dc:title>','xmp:Rating="3"')
    path = tmp_path/('image.'+('png' if fmt.startswith('png') else fmt))
    if fmt == 'jpeg':
        stream = io.BytesIO();Image.new('RGB',(12,8),'navy').save(stream,format='JPEG')
        payload = b'http://ns.adobe.com/xap/1.0/\0'+embedded
        path.write_bytes(stream.getvalue()[:2]+b'\xff\xe1'+(len(payload)+2).to_bytes(2,'big')+payload+stream.getvalue()[2:])
    elif fmt == 'tiff':
        tifffile.imwrite(path,np.zeros((8,12,3),dtype=np.uint8),extratags=[(700,'B',len(embedded),embedded,False)])
    else:
        info = PngImagePlugin.PngInfo();info.add_itxt('XML:com.adobe.xmp',embedded.decode(),zip=fmt.endswith('compressed'))
        Image.new('RGB',(12,8),'navy').save(path,pnginfo=info)
    first = read_xmp(path)
    assert first['patch'] == {'title':'Embedded title','rating':3}
    sidecar = path.with_suffix('.xmp');sidecar.write_bytes(packet('<dc:title>Sidecar title</dc:title>'))
    hashes = {p:hashlib.sha256(p.read_bytes()).digest() for p in (path,sidecar)}
    result = read_xmp(path)
    assert result['patch'] == {'title':'Sidecar title','rating':3}
    assert result['fingerprints'][str(sidecar)] is not None
    assert hashes == {p:hashlib.sha256(p.read_bytes()).digest() for p in hashes}


def test_sidecar_only_raw_header_and_empty_keyword_set(tmp_path):
    path = tmp_path/'image.NEF';path.write_bytes(b'not-an-exif-fixture')
    path.with_suffix('.xmp').write_bytes(packet('<dc:subject><rdf:Bag/></dc:subject>'))
    assert read_xmp(path)['patch'] == {'keyword_paths':[]}


def test_sidecar_late_change_is_detected(tmp_path,monkeypatch):
    import lumaraw.xmp_read as module
    path = tmp_path/'image.png';Image.new('RGB',(8,8)).save(path)
    sidecar = path.with_suffix('.xmp');sidecar.write_bytes(packet('<dc:title>One</dc:title>'))
    original = module.parse_packet
    def changed(data):
        result = original(data);sidecar.write_bytes(packet('<dc:title>Different</dc:title>'));return result
    monkeypatch.setattr(module,'parse_packet',changed)
    with pytest.raises(ValueError,match='changed during'):
        read_xmp(path)
