"""Portable descriptive IPTC fields and their XMP representation.

Inputs: explicit partial field values or bounded XMP properties. Outputs: validated
catalog JSON, native form descriptors and XMP elements. Omitted fields are unknown,
not clearing requests; empty checked fields clear only those fields. Date Created
is descriptive metadata and never rewrites EXIF capture time or sorting provenance.
No originals, filesystem, pixels, GPS inference, IIM rewriting or IPTC Extension
structures. Language alternatives currently use x-default, as existing captions do.
"""
from datetime import datetime
import json
import re
import xml.etree.ElementTree as ET

NAMESPACES = {'photoshop':'http://ns.adobe.com/photoshop/1.0/',
              'Iptc4xmpCore':'http://iptc.org/std/Iptc4xmpCore/1.0/xmlns/',
              'xmpRights':'http://ns.adobe.com/xap/1.0/rights/'}

# key, label, group, form kind, XMP prefix, property, RDF representation.
DEFINITIONS = (
    ('creator','Creator','IPTC Creator','array','dc','creator','Seq'),
    ('creator_job_title','Job Title','IPTC Creator','text','photoshop','AuthorsPosition','text'),
    ('creator_address','Address','IPTC Creator','multiline','Iptc4xmpCore','CiAdrExtadr','contact'),
    ('creator_city','City','IPTC Creator','text','Iptc4xmpCore','CiAdrCity','contact'),
    ('creator_region','State / Province','IPTC Creator','text','Iptc4xmpCore','CiAdrRegion','contact'),
    ('creator_postal_code','Postal Code','IPTC Creator','text','Iptc4xmpCore','CiAdrPcode','contact'),
    ('creator_country','Country','IPTC Creator','text','Iptc4xmpCore','CiAdrCtry','contact'),
    ('creator_phone','Phone','IPTC Creator','text','Iptc4xmpCore','CiTelWork','contact'),
    ('creator_email','Email','IPTC Creator','text','Iptc4xmpCore','CiEmailWork','contact'),
    ('creator_website','Website','IPTC Creator','text','Iptc4xmpCore','CiUrlWork','contact'),
    ('headline','Headline','IPTC Content','text','photoshop','Headline','text'),
    ('description_writer','Description Writer','IPTC Content','text','photoshop','CaptionWriter','text'),
    ('alt_text','Alt Text','IPTC Content','multiline','Iptc4xmpCore','AltTextAccessibility','Alt'),
    ('extended_description','Extended Description','IPTC Content','multiline','Iptc4xmpCore','ExtDescrAccessibility','Alt'),
    ('intellectual_genre','Intellectual Genre','IPTC Image','text','Iptc4xmpCore','IntellectualGenre','text'),
    ('subject_codes','Subject Codes','IPTC Content','array','Iptc4xmpCore','SubjectCode','Bag'),
    ('scene_codes','Scene Codes','IPTC Image','array','Iptc4xmpCore','Scene','Bag'),
    ('location','Sublocation','IPTC Image','text','Iptc4xmpCore','Location','text'),
    ('city','City','IPTC Image','text','photoshop','City','text'),
    ('region','State / Province','IPTC Image','text','photoshop','State','text'),
    ('country','Country','IPTC Image','text','photoshop','Country','text'),
    ('country_code','Country Code','IPTC Image','text','Iptc4xmpCore','CountryCode','text'),
    ('date_created','Date Created','IPTC Image','date','photoshop','DateCreated','text'),
    ('credit','Credit Line','IPTC Status','text','photoshop','Credit','text'),
    ('source','Source','IPTC Status','text','photoshop','Source','text'),
    ('instructions','Instructions','IPTC Status','multiline','photoshop','Instructions','text'),
    ('job_identifier','Job Identifier','IPTC Status','text','photoshop','TransmissionReference','text'),
    ('rights_usage_terms','Usage Terms','IPTC Copyright','multiline','xmpRights','UsageTerms','Alt'),
    ('rights_url','Copyright Info URL','IPTC Copyright','text','xmpRights','WebStatement','resource'),
    ('copyright_status','Copyright Status','IPTC Copyright','status','xmpRights','Marked','boolean'),
)
FIELDS = {row[0]:{'key':row[0],'label':row[1],'group':row[2],'kind':row[3],
                  'limit':5000 if row[3]=='multiline' else 500} for row in DEFINITIONS}
MAX_BYTES = 64 * 1024


def value_schema(field):
    kind=field['kind']
    if kind=='array':
        return {'type':'array','items':{'type':'string','minLength':1,'maxLength':500},'maxItems':20}
    if kind=='status':
        return {'enum':['unknown','copyrighted','public_domain']}
    return {'type':'string','maxLength':field['limit']}


SCHEMA = {'type':'object','properties':{key:value_schema(field) for key,field in FIELDS.items()},
          'additionalProperties':False}


def validate(values):
    if not isinstance(values,dict) or set(values)-set(FIELDS):
        raise ValueError('Unsupported IPTC field')
    for key,value in values.items():
        field=FIELDS[key]
        if field['kind']=='array':
            if not isinstance(value,list) or len(value)>20:
                raise ValueError('IPTC lists support at most twenty entries')
            texts=value
            if any(not isinstance(item,str) or not item.strip() or len(item)>500 for item in value):
                raise ValueError('IPTC list entries must be nonblank text up to 500 characters')
        else:
            if not isinstance(value,str) or len(value)>field['limit']:
                raise ValueError('IPTC text exceeds its supported field length')
            texts=[value]
        for text in texts:
            if any(not (c in '\t\n\r' or 0x20<=ord(c)<=0xD7FF or 0xE000<=ord(c)<=0xFFFD or 0x10000<=ord(c)<=0x10FFFF) for c in text):
                raise ValueError('IPTC text contains characters that cannot be represented in XML')
        if key=='copyright_status' and value not in ('unknown','copyrighted','public_domain'):
            raise ValueError('Choose a supported copyright status')
        if key=='country_code' and value and not re.fullmatch(r'[A-Za-z]{2,3}',value):
            raise ValueError('Country code must contain two or three letters')
        if key in ('subject_codes','scene_codes'):
            width=8 if key=='subject_codes' else 6
            if any(not re.fullmatch(r'[0-9]{'+str(width)+'}',item) for item in value):
                raise ValueError(f'{field["label"]} require {width}-digit codes')
        if key=='date_created' and value:
            if not re.fullmatch(r'[0-9]{4}(?:-[0-9]{2}(?:-[0-9]{2}(?:T[0-9]{2}:[0-9]{2}(?::[0-9]{2}(?:\.[0-9]{1,9})?)?(?:Z|[+-][0-9]{2}:[0-9]{2})?)?)?)?',value):
                raise ValueError('Date Created must use ISO 8601, preserving any known timezone')
            try:
                datetime.fromisoformat((value+'-01-01')[:10] if len(value)<=7 else value.replace('Z','+00:00'))
            except ValueError as error:
                raise ValueError('Date Created is not a valid calendar date') from error
    if len(json.dumps(values,ensure_ascii=False).encode())>MAX_BYTES:
        raise ValueError('IPTC fields exceed the 64 KiB catalog limit')
    return values


def merge(db, photo_id, patch):
    """Merge checked fields in the caller's transaction; no revision side effects."""
    current=json.loads(db.execute('SELECT iptc FROM photos WHERE id=?',(photo_id,)).fetchone()[0])
    result=validate({**current,**validate(patch)})
    db.execute('UPDATE photos SET iptc=? WHERE id=?',(json.dumps(result,ensure_ascii=False),photo_id))
    return result


def migrate(db):
    if db.execute('PRAGMA user_version').fetchone()[0]>=17:
        return
    db.execute('BEGIN IMMEDIATE')
    try:
        db.execute("ALTER TABLE photos ADD COLUMN iptc TEXT NOT NULL DEFAULT '{}'")
        db.execute('PRAGMA user_version=17')
        db.commit()
    except BaseException:
        db.rollback()
        raise


def write_xmp(description, values, tag):
    validate(values)
    contact=None
    for key,_,_,_,prefix,name,kind in DEFINITIONS:
        if key not in values:
            continue
        value=values[key]
        if kind=='boolean':
            if value!='unknown':
                description.set(tag(prefix,name),'True' if value=='copyrighted' else 'False')
        elif kind=='contact':
            if contact is None:
                contact=ET.SubElement(description,tag('Iptc4xmpCore','CreatorContactInfo'),{tag('rdf','parseType'):'Resource'})
            ET.SubElement(contact,tag(prefix,name)).text=value
        elif kind in ('Seq','Bag','Alt'):
            container=ET.SubElement(ET.SubElement(description,tag(prefix,name)),tag('rdf',kind))
            if kind=='Alt':
                ET.SubElement(container,tag('rdf','li'),{'{http://www.w3.org/XML/1998/namespace}lang':'x-default'}).text=value
            else:
                for item in value:
                    ET.SubElement(container,tag('rdf','li')).text=item
        elif kind=='resource':
            ET.SubElement(description,tag(prefix,name),{tag('rdf','resource'):value})
        else:
            ET.SubElement(description,tag(prefix,name)).text=value


def read_xmp(root, property_values, namespaces):
    values={}
    for key,_,_,_,prefix,name,kind in DEFINITIONS:
        if kind=='contact':
            qname='{'+namespaces[prefix]+'}'+name
            found=[]
            for contact in root.iter('{'+namespaces['Iptc4xmpCore']+'}CreatorContactInfo'):
                for node in contact.iter():
                    if qname in node.attrib:
                        found.append(node.attrib[qname])
                    if node.tag==qname:
                        if len(node):
                            raise ValueError('XMP contact fields must contain text')
                        found.append(node.text or '')
            if found and any(item!=found[0] for item in found):
                raise ValueError('Conflicting XMP contact information')
            value=found[0] if found else None
        else:
            value=property_values(prefix,name)
        if value is not None:
            if kind=='boolean':
                if not isinstance(value,str) or value.casefold() not in ('true','false','1','0'):
                    raise ValueError('Unsupported XMP copyright status')
                value='copyrighted' if value.casefold() in ('true','1') else 'public_domain'
            values[key]=value
    return validate(values)
