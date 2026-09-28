"""Portable XMP encoding for new derivative images, without touching originals.

Inputs: a validated frozen catalog metadata snapshot. Outputs: bounded UTF-8 XMP
and JPEG APP1 segments / TIFF tag payloads. Large JPEG packets use Adobe Extended
XMP with a matching MD5 identifier; this checksum is format integrity, not security.
Never copies raw EXIF blocks, local paths, processing recipes or unsupported fields.
"""
import hashlib
import struct
import xml.etree.ElementTree as ET
from . import iptc

MAX_PACKET = 2 * 1024 * 1024
NS = {'x': 'adobe:ns:meta/', 'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
      'dc': 'http://purl.org/dc/elements/1.1/', 'xmp': 'http://ns.adobe.com/xap/1.0/',
      'lr': 'http://ns.adobe.com/lightroom/1.0/', 'note': 'http://ns.adobe.com/xmp/note/'}
NS.update(iptc.NAMESPACES)
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)


def tag(prefix, name):
    return '{' + NS[prefix] + '}' + name


def text(value):
    if not isinstance(value, str) or any(
            not (char in '\t\n\r' or 0x20 <= ord(char) <= 0xD7FF
                 or 0xE000 <= ord(char) <= 0xFFFD or 0x10000 <= ord(char) <= 0x10FFFF)
            for char in value):
        raise ValueError('Export metadata contains text that cannot be represented in XML')
    return value


def tree(snapshot, extended=None):
    root = ET.Element(tag('x', 'xmpmeta'))
    rdf = ET.SubElement(root, tag('rdf', 'RDF'))
    description = ET.SubElement(rdf, tag('rdf', 'Description'), {tag('rdf', 'about'): ''})
    if extended:
        description.set(tag('note', 'HasExtendedXMP'), extended)
    fields = snapshot.get('fields', {})
    iptc.write_xmp(description,fields.get('iptc',{}),tag)
    for key, name in (('title', 'title'), ('caption', 'description'), ('copyright', 'rights')):
        if key in fields:
            alt = ET.SubElement(ET.SubElement(description, tag('dc', name)), tag('rdf', 'Alt'))
            ET.SubElement(alt, tag('rdf', 'li'), {'{http://www.w3.org/XML/1998/namespace}lang': 'x-default'}).text = text(fields[key])
    if 'rating' in fields:
        description.set(tag('xmp', 'Rating'), str(-1 if fields.get('flag') == -1 else fields['rating']))
    if 'color_label' in fields:
        label = fields['color_label']
        description.set(tag('xmp', 'Label'), '' if label == 'none' else label.capitalize())
    for key, prefix, name in (('keywords', 'dc', 'subject'), ('hierarchy', 'lr', 'hierarchicalSubject')):
        values = snapshot.get(key, [])
        if values:
            bag = ET.SubElement(ET.SubElement(description, tag(prefix, name)), tag('rdf', 'Bag'))
            for value in values:
                ET.SubElement(bag, tag('rdf', 'li')).text = text(value)
    return ET.tostring(root, encoding='utf-8')


def wrapped(data):
    return b'<?xpacket begin="\xef\xbb\xbf" id="W5M0MpCehiHzreSzNTczkc9d"?>\n' + data + b'\n<?xpacket end="w"?>'


def xmp_packet(snapshot):
    if not snapshot or snapshot.get('mode') == 'none':
        return b''
    packet = wrapped(tree(snapshot))
    if len(packet) > MAX_PACKET:
        raise ValueError('Export metadata exceeds the supported 2 MiB XMP packet size')
    return packet


def jpeg_segments(snapshot):
    packet = xmp_packet(snapshot)
    if not packet:
        return b''
    signature = b'http://ns.adobe.com/xap/1.0/\0'
    extension = b'http://ns.adobe.com/xmp/extension/\0'

    def segment(payload):
        return b'\xff\xe1' + struct.pack('>H', len(payload)+2) + payload

    if len(packet) <= 65502:
        return segment(signature + packet)
    # Keep the most useful descriptive fields in standard XMP, with large
    # keyword arrays in the extension. Each portion is an independent RDF tree.
    large = tree({'keywords': snapshot['keywords'], 'hierarchy': snapshot['hierarchy']})
    guid = hashlib.md5(large, usedforsecurity=False).hexdigest().upper()
    standard = wrapped(tree({'fields': snapshot['fields']}, extended=guid))
    if len(standard) > 65502:
        # Escaped descriptive text can exceed APP1 even when catalog JSON is
        # bounded. Keep the complete RDF tree in the verified extension.
        large=tree(snapshot)
        guid=hashlib.md5(large,usedforsecurity=False).hexdigest().upper()
        standard=wrapped(tree({},extended=guid))
    chunks = [segment(signature + standard)]
    for offset in range(0, len(large), 65458):
        chunks.append(segment(extension + guid.encode('ascii') + struct.pack('>II', len(large), offset)
                              + large[offset:offset+65458]))
    return b''.join(chunks)
