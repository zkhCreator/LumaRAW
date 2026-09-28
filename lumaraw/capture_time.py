"""Bounded, read-only EXIF capture clocks for catalog organization.

Inputs: TIFF-family, JPEG or PNG headers. Outputs: camera model, integer
microseconds and clock provenance; no pixel decoder, hash, original writes or
host-timezone dependence. Explicit offsets normalize to UTC. Without an offset,
camera wall time is compared as-is, not claimed to be an absolute UTC instant.
Only IFD0 and its Exif IFD are read; maker notes and embedded previews are ignored.
Unsupported containers/malformed metadata remain unknown instead of using mtime.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import struct

MAX_READ = 1024*1024
DATE_TAGS = {272,306,36867,36868,36880,36881,36882,37520,37521,37522}


def migrate(db):
    if db.execute('PRAGMA user_version').fetchone()[0] >= 6:
        return
    with db:
        db.execute('BEGIN IMMEDIATE')
        columns={row[1] for row in db.execute('PRAGMA table_info(photos)')}
        if 'taken_us' not in columns:
            db.execute('ALTER TABLE photos ADD COLUMN taken_us INTEGER')
            db.execute("ALTER TABLE photos ADD COLUMN taken_submicro TEXT NOT NULL DEFAULT ''")
            db.execute("ALTER TABLE photos ADD COLUMN capture_clock TEXT NOT NULL DEFAULT 'unknown'")
            # Old integer seconds depended on the indexing host's timezone. Keep
            # that field intact; explicit metadata refresh supplies the new clock.
        db.execute('CREATE INDEX IF NOT EXISTS photo_capture_us ON photos(taken_us,taken_submicro,id)')
        db.execute('PRAGMA user_version=6')


class Reader:
    def __init__(self, stream, size):
        self.stream=stream;self.size=size;self.read_bytes=0

    def read(self, offset, count):
        if offset<0 or count<0 or offset+count>self.size or self.read_bytes+count>MAX_READ:
            raise ValueError('EXIF read exceeds header bounds')
        self.read_bytes+=count
        self.stream.seek(offset)
        data=self.stream.read(count)
        if len(data)!=count:raise ValueError('Truncated EXIF metadata')
        return data


def tiff_tags(reader, base=0, length=None):
    """Read bounded classic TIFF IFDs; offsets are relative to their TIFF header."""
    length=reader.size-base if length is None else length
    def read(offset,count):
        if offset<0 or offset+count>length:raise ValueError('Invalid TIFF offset')
        return reader.read(base+offset,count)
    header=read(0,8)
    if header[:2] not in (b'II',b'MM'):return {}
    order='<' if header[:2]==b'II' else '>'
    if struct.unpack(order+'H',header[2:4])[0]!=42:return {}
    tags={}
    def directory(offset):
        count=struct.unpack(order+'H',read(offset,2))[0]
        if count>4096:raise ValueError('Too many EXIF entries')
        data=read(offset+2,count*12);child=None
        for i in range(count):
            entry=data[i*12:(i+1)*12]
            tag,kind,size=struct.unpack(order+'HHI',entry[:8])
            if tag==34665 and kind in (4,13) and size==1:
                child=struct.unpack(order+'I',entry[8:12])[0]
            elif tag in DATE_TAGS and kind==2 and 0<size<=512:
                value=entry[8:8+size] if size<=4 else read(struct.unpack(order+'I',entry[8:12])[0],size)
                tags[tag]=value.rstrip(b'\0 ').decode('ascii',errors='replace')
        return child
    first=struct.unpack(order+'I',header[4:8])[0]
    child=directory(first)
    if child and child!=first:directory(child)
    return tags


def read_tags(reader):
    head=reader.read(0,min(8,reader.size))
    if head[:2] in (b'II',b'MM'):return tiff_tags(reader)
    if head[:2]==b'\xff\xd8':
        offset=2
        for _ in range(4096):
            marker=reader.read(offset,2);offset+=2
            if marker[0]!=255:return {}
            while marker[1]==255:
                marker=b'\xff'+reader.read(offset,1);offset+=1
            code=marker[1]
            if code in (0xda,0xd9):return {}
            if code==1 or 0xd0<=code<=0xd7:continue
            size=int.from_bytes(reader.read(offset,2),'big')
            if size<2:raise ValueError('Invalid JPEG segment')
            if code==0xe1 and size>=8 and reader.read(offset+2,6)==b'Exif\0\0':
                return tiff_tags(reader,offset+8,size-8)
            offset+=size
        raise ValueError('Too many JPEG segments')
    if head==b'\x89PNG\r\n\x1a\n':
        offset=8
        for _ in range(4096):
            chunk=reader.read(offset,8);size=int.from_bytes(chunk[:4],'big')
            if chunk[4:]==b'eXIf':return tiff_tags(reader,offset+8,size)
            if chunk[4:]==b'IEND':return {}
            offset+=size+12
        raise ValueError('Too many PNG chunks')
    return {}


def clock_from_tags(tags):
    result={'camera':tags.get(272,'')[:100],'taken_us':None,'taken_submicro':'','capture_clock':'unknown','taken':0}
    for date,subsec,offset in ((36867,37521,36881),(36868,37522,36882),(306,37520,36880)):
        if not tags.get(date):continue
        try:
            value=datetime.strptime(tags[date],'%Y:%m:%d %H:%M:%S')
            fraction=tags.get(subsec,'').strip()
            if fraction and not re.fullmatch(r'\d+',fraction):raise ValueError('Invalid subsecond time')
            # Keep any finer residual as exact digits, never silently round it.
            micros=int((fraction+'000000')[:6])
            residual=fraction[6:].rstrip('0')
            value=value.replace(microsecond=micros,tzinfo=timezone.utc)
            zone=tags.get(offset,'').strip();basis='camera'
            if zone:
                match=re.fullmatch(r'([+-])(\d{2}):(\d{2})',zone)
                if not match:raise ValueError('Invalid EXIF offset')
                hours,minutes=int(match[2]),int(match[3])
                if hours>23 or minutes>59:raise ValueError('Invalid EXIF offset')
                delta=timedelta(hours=hours,minutes=minutes)*(1 if match[1]=='+' else -1)
                value=value.replace(tzinfo=timezone(delta)).astimezone(timezone.utc);basis='utc'
            delta=value-datetime(1970,1,1,tzinfo=timezone.utc)
            us=(delta.days*86400+delta.seconds)*1000000+delta.microseconds
            result.update(taken_us=us,taken_submicro=residual,capture_clock=basis,taken=us//1000000)
            break
        except (ValueError,OverflowError):continue
    return result


def read_capture_time(path):
    path=Path(path);before=path.stat()
    with path.open('rb') as stream:
        try:tags=read_tags(Reader(stream,before.st_size))
        except (ValueError,struct.error):tags={}
    after=path.stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
        raise OSError('The source changed while reading capture metadata; refresh again')
    return clock_from_tags(tags)
