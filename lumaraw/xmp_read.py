"""Bounded, read-only XMP metadata for explicit folder synchronization.

Inputs: a photo and optional adjacent XMP sidecar. Outputs: supported descriptive
fields, exact keyword paths, source fingerprints and unsupported-feature notes.
Reads sidecars and TIFF/JPEG/PNG packets, including verified extended JPEG XMP,
without decoding pixels. Sidecar
properties override embedded properties. Never writes files or catalog rows and
never translates Adobe Develop/ACR settings into a different rendering engine.
Absent properties are omitted, not interpreted as permission to clear a catalog.
"""
from pathlib import Path
import struct
import xml.etree.ElementTree as ET
import zlib

from .keywords import valid_name
from .organization import COLORS, folded
from .relocations import identity

MAX_PACKET = 2 * 1024 * 1024
MAX_READ = 4 * 1024 * 1024
NS = {'rdf':'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
      'dc':'http://purl.org/dc/elements/1.1/', 'xmp':'http://ns.adobe.com/xap/1.0/',
      'lr':'http://ns.adobe.com/lightroom/1.0/', 'crs':'http://ns.adobe.com/camera-raw-settings/1.0/'}


class PacketReader:
    def __init__(self, stream, size):
        self.stream, self.size, self.used = stream, size, 0

    def read(self, offset, count):
        if offset < 0 or count < 0 or offset+count > self.size or self.used+count > MAX_READ:
            raise ValueError('XMP header exceeds bounded read limits')
        self.used += count
        self.stream.seek(offset)
        value = self.stream.read(count)
        if len(value) != count:
            raise ValueError('Truncated XMP header')
        return value


class BoundedTree(ET.TreeBuilder):
    def __init__(self):
        super().__init__()
        self.depth = self.nodes = 0

    def start(self, tag, attrs):
        self.depth += 1
        self.nodes += 1
        if self.depth > 64 or self.nodes > 10000:
            raise ValueError('XMP XML structure exceeds supported limits')
        return super().start(tag, attrs)

    def end(self, tag):
        self.depth -= 1
        return super().end(tag)

    def doctype(self, name, pubid, system):
        raise ValueError('XMP document types and entities are not supported')


def parse_packet(data):
    if len(data) > MAX_PACKET:
        raise ValueError('XMP packet exceeds 2 MiB')
    try:
        root = ET.fromstring(data, parser=ET.XMLParser(target=BoundedTree()))
    except ET.ParseError as error:
        raise ValueError('Malformed XMP XML') from error
    descriptions = root.findall('.//rdf:Description', NS)
    if root.tag == '{'+NS['rdf']+'}Description':
        descriptions.insert(0, root)
    if not descriptions:
        raise ValueError('XMP has no RDF description')
    def property_values(prefix, name):
        key = '{'+NS[prefix]+'}'+name
        values = []
        for description in descriptions:
            if key in description.attrib:
                values.append(description.attrib[key])
            for child in description.findall(key):
                entries = child.findall('./rdf:Alt/rdf:li', NS)
                if entries:
                    selected = next((entry for entry in entries if entry.get('{http://www.w3.org/XML/1998/namespace}lang') == 'x-default'), entries[0])
                    values.append(selected.text or '')
                elif child.find('./rdf:Bag', NS) is not None or child.find('./rdf:Seq', NS) is not None:
                    values.append([entry.text or '' for entry in child.findall('./*/rdf:li', NS)])
                else:
                    values.append(child.text or '')
        if values and any(value != values[0] for value in values[1:]):
            raise ValueError('Conflicting XMP properties: '+prefix+':'+name)
        return values[0] if values else None
    patch, notes = {}, []
    for name, field, limit in (('title','title',500), ('description','caption',5000), ('rights','copyright',500)):
        value = property_values('dc', name)
        if value is not None:
            if not isinstance(value, str) or len(value) > limit:
                raise ValueError('Unsupported XMP '+name+' value or length')
            patch[field] = value
    rating = property_values('xmp','Rating')
    if rating is not None:
        try:
            number = float(rating)
            if not number.is_integer() or number not in range(-1,6):
                raise ValueError()
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError('XMP rating must be -1 or an integer from 0 to 5') from error
        if number == -1:
            patch['flag'] = -1
        else:
            patch['rating'] = int(number)
    label = property_values('xmp','Label')
    if label is not None:
        if not isinstance(label,str):
            raise ValueError('Unsupported XMP color label')
        color = label.casefold().strip() or 'none'
        if color in COLORS:
            patch['color_label'] = color
        else:
            notes.append('Custom XMP color label is not mapped: '+label[:120])
    flat = property_values('dc','subject')
    hierarchy = property_values('lr','hierarchicalSubject')
    if flat is not None or hierarchy is not None:
        if any(value is not None and not isinstance(value,list) for value in (flat,hierarchy)):
            raise ValueError('XMP keywords must be RDF arrays')
        paths = [[valid_name(part) for part in value.split('|')] for value in hierarchy or []]
        leaves = {folded(path[-1]) for path in paths}
        paths += [[valid_name(value)] for value in flat or [] if folded(value.strip()) not in leaves]
        unique = {tuple(folded(part) for part in path):path for path in paths}
        if len(unique) > 100 or any(len(path)>32 for path in unique):
            raise ValueError('XMP keywords exceed 100 assignments or 32 hierarchy levels')
        patch['keyword_paths'] = list(unique.values())
    if any(element.tag.startswith('{'+NS['crs']+'}') or any(key.startswith('{'+NS['crs']+'}') for key in element.attrib) for element in root.iter()):
        notes.append('Adobe Develop settings are present and are not imported')
    return patch, notes


def embedded_packets(reader):
    head = reader.read(0, min(8, reader.size))
    if head[:2] in (b'II',b'MM'):
        if len(head)<8:
            raise ValueError('Truncated TIFF header')
        order = '<' if head[:2] == b'II' else '>'
        if struct.unpack(order+'H',head[2:4])[0] != 42:
            return []
        offset = struct.unpack(order+'I',head[4:8])[0]
        count = struct.unpack(order+'H',reader.read(offset,2))[0]
        if count>4096:
            raise ValueError('Too many TIFF directory entries')
        entries = reader.read(offset+2,count*12)
        packets = []
        for index in range(count):
            entry = entries[index*12:index*12+12]
            tag,kind,size = struct.unpack(order+'HHI',entry[:8])
            if tag == 700:
                if kind not in (1,7) or size>MAX_PACKET:
                    raise ValueError('Unsupported TIFF XMP packet')
                packets.append(entry[8:8+size] if size<=4 else reader.read(struct.unpack(order+'I',entry[8:])[0],size))
        return packets
    if head[:2] == b'\xff\xd8':
        offset, packets, chunks = 2, [], []
        signature = b'http://ns.adobe.com/xap/1.0/\0'
        extended = b'http://ns.adobe.com/xmp/extension/\0'
        for _ in range(4096):
            marker = reader.read(offset,2);offset += 2
            if marker[0] != 255:
                raise ValueError('Invalid JPEG marker')
            while marker[1] == 255:
                marker = b'\xff'+reader.read(offset,1);offset += 1
            if marker[1] in (0xda,0xd9):
                return assemble_jpeg(packets, chunks)
            if marker[1] == 1 or 0xd0 <= marker[1] <= 0xd7:
                continue
            size = int.from_bytes(reader.read(offset,2),'big')
            if size<2 or offset+size>reader.size:
                raise ValueError('Invalid JPEG metadata segment')
            if marker[1] == 0xe1:
                prefix = reader.read(offset+2,min(size-2,len(extended)))
                if prefix.startswith(extended):
                    data = reader.read(offset+2+len(extended),size-2-len(extended))
                    if len(data) <= 40:
                        raise ValueError('Truncated extended JPEG XMP chunk')
                    try:
                        guid = data[:32].decode('ascii').upper()
                    except UnicodeDecodeError as error:
                        raise ValueError('Invalid extended JPEG XMP identifier') from error
                    total,start = struct.unpack('>II',data[32:40])
                    if total>MAX_PACKET or start+len(data)-40>total:
                        raise ValueError('Extended JPEG XMP exceeds packet bounds')
                    chunks.append((guid,total,start,data[40:]))
                if prefix.startswith(signature):
                    packets.append(reader.read(offset+2+len(signature),size-2-len(signature)))
            offset += size
        raise ValueError('Too many JPEG segments')
    if head == b'\x89PNG\r\n\x1a\n':
        offset, packets = 8, []
        for _ in range(4096):
            chunk = reader.read(offset,8);size = int.from_bytes(chunk[:4],'big')
            if chunk[4:] == b'IEND':
                return packets
            if offset+size+12 > reader.size:
                raise ValueError('Invalid PNG chunk bounds')
            if chunk[4:] == b'iTXt':
                prefix = reader.read(offset+8,min(size,80))
                if prefix.startswith(b'XML:com.adobe.xmp\0'):
                    if size>MAX_PACKET:
                        raise ValueError('PNG XMP exceeds 2 MiB')
                    payload = reader.read(offset+8,size)
                    remainder = payload.split(b'\0',1)[1]
                    if len(remainder)<2 or remainder[0] not in (0,1) or remainder[1]!=0:
                        raise ValueError('Unsupported PNG text encoding')
                    fields = remainder[2:].split(b'\0',2)
                    if len(fields)!=3:
                        raise ValueError('Truncated PNG XMP text')
                    data = fields[2]
                    if remainder[0]:
                        decoder = zlib.decompressobj()
                        data = decoder.decompress(data,MAX_PACKET+1)
                        if len(data)>MAX_PACKET or not decoder.eof or decoder.unused_data:
                            raise ValueError('PNG compressed XMP exceeds bounds or is truncated')
                    packets.append(data)
            offset += size+12
        raise ValueError('Too many PNG chunks')
    return []


def assemble_jpeg(packets, chunks):
    """Join only the extension explicitly referenced by standard XMP."""
    import hashlib
    key = '{http://ns.adobe.com/xmp/note/}HasExtendedXMP'
    identifiers = set()
    for packet in packets:
        try:
            root = ET.fromstring(packet, parser=ET.XMLParser(target=BoundedTree()))
        except ET.ParseError as error:
            raise ValueError('Malformed JPEG XMP XML') from error
        for element in root.iter():
            if key in element.attrib:
                identifiers.add(element.attrib[key].upper())
            if element.tag == key and element.text:
                identifiers.add(element.text.upper())
    if not identifiers:
        return packets
    if len(identifiers) != 1:
        raise ValueError('Conflicting extended JPEG XMP identifiers')
    identifier = identifiers.pop()
    if len(identifier) != 32 or any(char not in '0123456789ABCDEF' for char in identifier):
        raise ValueError('Invalid extended JPEG XMP identifier')
    matches = [chunk for chunk in chunks if chunk[0] == identifier]
    if not matches:
        raise ValueError('Extended JPEG XMP is missing')
    total = matches[0][1]
    if not 0 < total <= MAX_PACKET or any(chunk[1] != total for chunk in matches):
        raise ValueError('Invalid extended JPEG XMP size')
    offset, parts = 0, []
    for _, _, start, data in sorted(matches, key=lambda chunk: chunk[2]):
        if start != offset or offset+len(data) > total:
            raise ValueError('Extended JPEG XMP has overlapping or missing chunks')
        parts.append(data)
        offset += len(data)
    combined = b''.join(parts)
    if offset != total or hashlib.md5(combined, usedforsecurity=False).hexdigest().upper() != identifier:
        raise ValueError('Extended JPEG XMP is incomplete or has an invalid checksum')
    return [*packets, combined]


def read_xmp(path):
    path = Path(path)
    fingerprints = {str(path):identity(path)}
    if fingerprints[str(path)] is None:
        raise FileNotFoundError('Original is unavailable')
    with path.open('rb') as stream:
        try:
            packets = embedded_packets(PacketReader(stream, fingerprints[str(path)][2]))
        except (struct.error,zlib.error) as error:
            raise ValueError('Malformed embedded XMP metadata') from error
    candidates = [path.with_suffix('.xmp'),path.with_suffix('.XMP')]
    existing = []
    for sidecar in candidates:
        value = identity(sidecar)
        fingerprints[str(sidecar)] = value
        if value and not any(value[:2] == item[1][:2] for item in existing):
            existing.append((sidecar,value))
    if len(existing)>1:
        raise ValueError('Multiple distinct XMP sidecars exist; choose one before synchronizing')
    if existing:
        sidecar,value = existing[0]
        if value[2]>MAX_PACKET:
            raise ValueError('XMP sidecar exceeds 2 MiB')
        with sidecar.open('rb') as stream:
            packets.append(stream.read(MAX_PACKET+1))
    patch, notes = {}, []
    for packet in packets:
        values, warnings = parse_packet(packet)
        patch.update(values);notes.extend(warnings)
    if any(identity(name) != value for name,value in fingerprints.items()):
        raise ValueError('Metadata changed during reading; scan again')
    return {'patch':patch,'notes':list(dict.fromkeys(notes)),'fingerprints':fingerprints}
