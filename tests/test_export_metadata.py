"""Derivative XMP encoding, JPEG extension integrity and real export metadata.

Inputs: isolated catalog fields and generated raster sources. Outputs: decoded
TIFF/JPEG tags, round-trip supported metadata, exact pixel/ICC preservation and
explicit failures for malformed or overlarge packets. Originals remain unchanged.
"""
import hashlib
import io
import struct
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image
import pytest
import tifffile

from lumaraw.export_metadata import jpeg_segments,xmp_packet,NS
from lumaraw.imaging import export_image
from lumaraw.model import Recipe
from lumaraw.xmp_read import PacketReader,embedded_packets,parse_packet,read_xmp


def snapshot(**overrides):
    return {'version':1,'mode':'catalog','fields':{'title':'海边 & <Coast>','caption':'Line one\nLine two',
        'copyright':'© Photographer','rating':4,'flag':0,'color_label':'blue'},
        'keywords':['Coast','Places','Shore'],'hierarchy':['Places|Coast'],**overrides}


def packets(segments):
    return embedded_packets(PacketReader(io.BytesIO(b'\xff\xd8'+segments+b'\xff\xd9'),len(segments)+4))


def test_exact_supported_text_and_policy_omission():
    value=snapshot()
    patch,notes=parse_packet(xmp_packet(value))
    assert patch['title']==value['fields']['title'] and patch['caption']==value['fields']['caption']
    assert patch['copyright']=='© Photographer' and patch['rating']==4 and patch['color_label']=='blue'
    assert notes==[]
    assert xmp_packet({})==b'' and jpeg_segments(snapshot(mode='none'))==b''
    copyright_only=snapshot(mode='copyright',fields={'copyright':'© Only'},keywords=[],hierarchy=[])
    assert parse_packet(xmp_packet(copyright_only))[0]=={'copyright':'© Only'}
    value['fields']['flag']=-1
    assert parse_packet(xmp_packet(value))[0]['flag']==-1


def test_extended_jpeg_reordered_chunks_reassemble_exactly():
    # 100 valid long hierarchy paths exceed the standard JPEG APP1 payload.
    hierarchy=['|'.join([f'Level {level} '+('x'*105) for level in range(9)]+[f'Leaf {i}']) for i in range(100)]
    value=snapshot(keywords=[f'Leaf {i}' for i in range(100)],hierarchy=hierarchy)
    data=jpeg_segments(value);segments=[];offset=0
    while offset<len(data):
        size=int.from_bytes(data[offset+2:offset+4],'big')
        segments.append(data[offset:offset+size+2]);offset+=size+2
    assert len(segments)>2
    result=packets(b''.join(reversed(segments)))
    combined={}
    for packet in result:combined.update(parse_packet(packet)[0])
    assert combined['title']==value['fields']['title']
    assert combined['keyword_paths']==[path.split('|') for path in hierarchy]


@pytest.mark.parametrize('mutation',['checksum','gap','overlap','missing','oversize','wrong_guid'])
def test_extended_jpeg_rejects_invalid_assembly(mutation):
    value=snapshot(keywords=['x'*100+str(i) for i in range(900)],hierarchy=[])
    data=jpeg_segments(value);segments=[];offset=0
    while offset<len(data):
        size=int.from_bytes(data[offset+2:offset+4],'big')
        segments.append(bytearray(data[offset:offset+size+2]));offset+=size+2
    assert len(segments)>=3
    prefix=4+len(b'http://ns.adobe.com/xmp/extension/\0')
    if mutation=='checksum':segments[-1][-8]^=1
    elif mutation=='gap':segments.pop()
    elif mutation=='overlap':segments.append(segments[-1])
    elif mutation=='missing':segments=segments[:1]
    elif mutation=='oversize':segments[1][prefix+32:prefix+36]=struct.pack('>I',3*1024*1024)
    else:segments[1][prefix:prefix+32]=b'0'*32
    with pytest.raises(ValueError):packets(b''.join(segments))


@pytest.mark.parametrize('bad',['Bad\u0001text','Surrogate\ud800'])
def test_invalid_xml_text_is_rejected(bad):
    with pytest.raises(ValueError,match='XML'):xmp_packet(snapshot(fields={'title':bad}))


def test_large_packet_is_rejected_without_truncation():
    with pytest.raises(ValueError,match='2 MiB'):
        xmp_packet(snapshot(keywords=['a'*1000]*3000))


@pytest.mark.parametrize('fmt',['tiff16','jpeg'])
def test_real_export_roundtrips_metadata_and_retains_exact_pixels(fmt,tmp_path):
    source=tmp_path/'original.png'
    pixels=np.arange(24*32*3,dtype=np.uint8).reshape(24,32,3)
    Image.fromarray(pixels).save(source)
    before=hashlib.sha256(source.read_bytes()).digest()
    value=snapshot()
    with_meta=export_image(source,Recipe(),tmp_path,fmt,512,1,metadata_snapshot=value)
    without_meta=export_image(source,Recipe(),tmp_path,fmt,512,2)
    parsed=read_xmp(with_meta['output'])['patch']
    assert parsed['title']==value['fields']['title'] and parsed['rating']==4
    assert read_xmp(without_meta['output'])['patch']=={}
    with Image.open(with_meta['output']) as a,Image.open(without_meta['output']) as b:
        assert np.array_equal(np.asarray(a),np.asarray(b)) and a.info['icc_profile']==b.info['icc_profile']
    if fmt=='tiff16':
        with tifffile.TiffFile(with_meta['output']) as file:
            assert file.pages[0].dtype==np.uint16 and 700 in file.pages[0].tags
            assert 270 not in file.pages[0].tags
    assert hashlib.sha256(source.read_bytes()).digest()==before
    assert not list(tmp_path.glob('.lumaraw-*'))

