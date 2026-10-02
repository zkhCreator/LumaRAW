"""Portable filename templates for explicit Copy imports.

Inputs: bounded tokens, captured clocks, selected ordinals and allocated counters.
Outputs: a single validated basename with its original extension. No filesystem,
catalog access, implicit sanitization, pixel reads or inferred capture metadata.
Counter allocation and Adobe template-file translation are outside this module.
Sequence is batch-local; Import/Image tokens require explicit catalog snapshots.
"""
from pathlib import Path
import re


TOKENS = ('literal', 'filename', 'original_number', 'folder', 'custom_text',
          'shoot_name', 'sequence', 'index', 'total', 'year', 'month', 'day',
          'hour', 'minute', 'second', 'camera', 'import_number', 'image_number')
TOKEN_SCHEMA = {'type':'object', 'properties':{
    'kind':{'enum':list(TOKENS)}, 'text':{'type':'string','maxLength':120},
    'digits':{'type':'integer','minimum':1,'maximum':10}},
    'required':['kind'], 'additionalProperties':False}
TEMPLATE_SCHEMA = {'type':'array','items':TOKEN_SCHEMA,'minItems':1,'maxItems':48}
SETTINGS_SCHEMA = {'type':'object', 'properties':{
    'enabled':{'type':'boolean'}, 'template':TEMPLATE_SCHEMA,
    'custom_text':{'type':'string','maxLength':120}, 'shoot_name':{'type':'string','maxLength':120},
    'start':{'type':'integer','minimum':1,'maximum':9999999999},
    'extension':{'enum':['preserve','lower','upper']}},
    'required':['enabled','template','custom_text','shoot_name','start','extension'],
    'additionalProperties':False}


def token(kind, **values):
    return {'kind':kind, **values}


def builtins():
    dash = token('literal', text='-')
    sequence = token('sequence', digits=4)
    custom, shoot, name, number = (token(k) for k in ('custom_text','shoot_name','filename','original_number'))
    choices = [
        ('Custom Name (x of y)', [custom, token('literal',text=' ('), token('index'),
                                token('literal',text=' of '), token('total'), token('literal',text=')')]),
        ('Custom Name - Original File Number', [custom,dash,number]),
        ('Custom Name - Sequence', [custom,dash,sequence]), ('Custom Name', [custom]),
        ('Date - Filename', [token('year'),token('month'),token('day'),dash,name]),
        ('Filename - Sequence', [name,dash,sequence]), ('Filename', [name]),
        ('Shoot Name - Original File Number', [shoot,dash,number]),
        ('Shoot Name - Sequence', [shoot,dash,sequence]),
    ]
    return [{'id':'builtin-'+str(i),'name':name,'template':parts} for i,(name,parts) in enumerate(choices)]


def defaults():
    return {'enabled':False,'template':[token('filename')],'custom_text':'','shoot_name':'',
            'start':1,'extension':'preserve'}


def safe_text(value):
    if any(c in '/\\:' or ord(c)<32 or ord(c)==127 for c in value):
        raise ValueError('Filename text cannot contain separators, colons or control characters')
    return value


def validate(template):
    import jsonschema
    jsonschema.validate(template,TEMPLATE_SCHEMA)
    for part in template:
        kind = part['kind']
        if kind == 'literal':
            if set(part) != {'kind','text'} or not part['text']:
                raise ValueError('Literal tokens require nonempty text only')
            safe_text(part['text'])
        elif kind in ('sequence','index','total','import_number','image_number'):
            if set(part)-{'kind','digits'}:
                raise ValueError('Number tokens accept only optional padding digits')
        elif set(part) != {'kind'}:
            raise ValueError('This filename token accepts no options')
    return template


def validate_settings(value):
    import jsonschema
    jsonschema.validate(value,SETTINGS_SCHEMA)
    validate(value['template'])
    safe_text(value['custom_text']); safe_text(value['shoot_name'])
    return value


def render(value, row, ordinal, total, sequence=None):
    source = Path(row['path'])
    if not value['enabled']:
        return source.name
    clock = row['clock']
    values = {'filename':source.stem,'folder':source.parent.name,
              'custom_text':value['custom_text'],'shoot_name':value['shoot_name'],
              'camera':clock.get('camera','')}
    numbers = re.findall(r'[0-9]+',source.stem)
    values['original_number'] = numbers[-1] if numbers else ''
    civil = clock.get('capture_civil',{})
    if not civil and re.fullmatch(r'\d{4}/\d{4}-\d{2}-\d{2}',clock.get('capture_date','')):
        civil = dict(zip(('year','month','day'),clock['capture_date'][5:].split('-')))
    values.update({k:civil.get(k,'') for k in ('year','month','day','hour','minute','second')})
    parts = []
    for part in value['template']:
        kind = part['kind']
        if kind == 'literal':
            item = part['text']
        elif kind in ('sequence','index','total'):
            number = {'sequence':value['start']+ordinal-1,'index':ordinal,'total':total}[kind]
            item = str(number).zfill(part.get('digits',1))
        elif kind in ('import_number','image_number'):
            if sequence is None or kind not in sequence or ordinal < 1:
                raise ValueError('Catalog numbering requires a captured sequence and checked item rank')
            number = sequence[kind] + (ordinal-1 if kind == 'image_number' else 0)
            if not 1 <= number <= 9999999999:
                raise ValueError('Import sequence exhausted; set new starting numbers before importing')
            item = str(number).zfill(part.get('digits',1))
        else:
            item = values[kind]
            if not item:
                raise ValueError('Missing filename value: '+kind)
        parts.append(safe_text(item))
    stem = ''.join(parts)
    if not stem.strip() or stem in ('.','..') or stem.startswith('.') or stem.endswith((' ','.')):
        raise ValueError('Filename must be visible and cannot end in a space or period')
    extension = source.suffix
    if value['extension'] != 'preserve':
        extension = getattr(extension,value['extension'])()
    result = stem+extension
    if len(result.encode('utf-8')) > 255:
        raise ValueError('Renamed filename exceeds 255 UTF-8 bytes')
    return result
