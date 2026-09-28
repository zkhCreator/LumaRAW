"""Precision and bounded-source evidence for capture-time indexing.

Generated JPEG/PNG and TIFF-family metadata exercise endian, offset and fractional
clock behavior without decoding RAW pixels. Synthetic NEF-shaped TIFF headers do
not establish metadata coverage for a real Nikon camera file.
"""
from datetime import datetime, timezone
import hashlib
import io
import os
import struct
import time

from PIL import Image
import pytest

from lumaraw.capture_time import Reader, MAX_READ, clock_from_tags, read_capture_time, tiff_tags
from lumaraw.catalog import Catalog
from lumaraw.library import index_library


def photo(path, date='2026:09:26 12:00:00', fraction='123456789', offset='+08:00'):
    exif=Image.Exif();exif[272]='Test Nikon'
    exif[34665]={36867:date,37521:fraction,36881:offset}
    Image.new('RGB',(20,16),(70,100,130)).save(path,exif=exif)
    return path


@pytest.mark.parametrize('extension',['jpg','png'])
def test_exact_fraction_and_offset_from_generated_headers(tmp_path,extension):
    path=photo(tmp_path/f'photo.{extension}')
    before=hashlib.sha256(path.read_bytes()).digest()
    result=read_capture_time(path)
    expected=int(datetime(2026,9,26,4,tzinfo=timezone.utc).timestamp())*1000000+123456
    assert result=={'camera':'Test Nikon','taken_us':expected,'taken_submicro':'789','capture_clock':'utc','taken':expected//1000000}
    assert hashlib.sha256(path.read_bytes()).digest()==before


@pytest.mark.skipif(not hasattr(time, 'tzset'), reason='Host does not expose POSIX timezone switching')
def test_camera_wall_clock_is_independent_of_host_timezone(monkeypatch):
    tags={36867:'2026:09:26 12:00:00',37521:'7'}
    previous=os.environ.get('TZ')
    try:
        monkeypatch.setenv('TZ','America/Los_Angeles');time.tzset();first=clock_from_tags(tags)
        monkeypatch.setenv('TZ','Asia/Shanghai');time.tzset();second=clock_from_tags(tags)
        assert first==second and first['capture_clock']=='camera'
        assert first['taken_us']%1000000==700000
    finally:
        if previous is None:monkeypatch.delenv('TZ',raising=False)
        else:monkeypatch.setenv('TZ',previous)
        time.tzset()


@pytest.mark.parametrize('order', ['<','>'])
def test_tiff_family_reader_follows_exif_ifd_with_bounded_io(tmp_path,order):
    marker=b'II' if order=='<' else b'MM'
    data=bytearray(marker+struct.pack(order+'HI',42,8))
    # IFD0 points to one Exif IFD, whose ASCII timestamp lives after its entries.
    data+=struct.pack(order+'H',1)+struct.pack(order+'HHII',34665,4,1,26)+struct.pack(order+'I',0)
    data+=struct.pack(order+'H',1)+struct.pack(order+'HHII',36867,2,20,44)+struct.pack(order+'I',0)
    data+=b'2026:09:26 12:00:00\0'
    path=tmp_path/'synthetic.nef';path.write_bytes(data)
    result=read_capture_time(path)
    assert result['capture_clock']=='camera' and result['taken_us'] is not None
    reader=Reader(io.BytesIO(data),len(data));assert tiff_tags(reader)[36867]=='2026:09:26 12:00:00'
    assert reader.read_bytes<100 and reader.read_bytes<=MAX_READ


def test_invalid_dates_offsets_and_malformed_files_remain_unknown(tmp_path):
    assert clock_from_tags({36867:'2026:99:26 12:00:00'})['taken_us'] is None
    assert clock_from_tags({36867:'2026:09:26 12:00:00',36881:'+25:00'})['taken_us'] is None
    assert clock_from_tags({36867:'2026:09:26 12:00:00',37521:'oops'})['taken_us'] is None
    path=tmp_path/'bad.nef'
    for payload in (b'',b'II*\x00\xff\xff\xff\x7f',b'\xff\xd8\xff\xe1\xff\xffExif\0\0'):
        path.write_bytes(payload);assert read_capture_time(path)['taken_us'] is None
    image=tmp_path/'untagged.jpg';Image.new('RGB',(16,16)).save(image)
    assert read_capture_time(image)['taken_us'] is None


def test_epoch_and_pre_epoch_are_known_not_missing_dates():
    assert clock_from_tags({36867:'1970:01:01 00:00:00',36881:'+00:00'})['taken_us']==0
    assert clock_from_tags({36867:'1969:12:31 23:59:59',37521:'9',36881:'+00:00'})['taken_us']==-100000
    assert clock_from_tags({36867:'2026:09:26 12:00:00',37521:'1234560000'})['taken_submicro']==''


def test_import_populates_clock_and_index_preserves_fraction_for_family(tmp_path):
    path=photo(tmp_path/'photo.jpg');c=Catalog(tmp_path/'catalog')
    assert c.import_paths([str(path)])==(1,0)
    row=c.photo(1);expected=read_capture_time(path)
    assert row['taken_us']==expected['taken_us'] and row['taken_submicro']=='789'
    from lumaraw.virtual_copies import VirtualCopies
    copy=VirtualCopies(c).create([{'photo_id':1,'expected_revision':0,'expected_metadata_revision':0}])['photos'][0]['id']
    assert c.photo(copy)['taken_us']==row['taken_us']
    index_library(c)
    assert c.photo(copy)['taken_submicro']=='789' and c.photo(copy)['camera']=='Test Nikon'
    assert c.import_paths([str(path)])==(0,1)
    c.close()
