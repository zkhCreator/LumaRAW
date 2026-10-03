"""Portable management of existing non-AI local masks.

Inputs: validated recipe, captured mask index and explicit action/name. Outputs:
a new recipe, selected index and history label. Caller owns revisions/transactions.
No pixels, I/O, inferred selections, components, ordering changes or stable IDs.
Photo revisions bind indices; stale actions must fail before entering this helper.
Names retain Unicode and the existing 80-code-point limit. Duplication preserves
all mask settings independently; generated copy naming is a LumaRAW convention.
"""
from copy import deepcopy
from dataclasses import replace

from .model import Recipe

LABELS={
    'rename':'Rename Mask',
    'duplicate':'Duplicate Mask',
    'duplicate_invert':'Duplicate and Invert Mask',
    'invert':'Invert Mask',
    'delete':'Delete Mask',
}


def apply(recipe, index, action, name=None):
    if action not in LABELS:
        raise ValueError('Unsupported mask action')
    if type(index) is not int or not 0<=index<len(recipe.masks):
        raise ValueError('The selected mask does not exist')
    if action=='rename':
        if not isinstance(name,str) or len(name)>80:
            raise ValueError('A mask name must contain at most 80 characters')
    elif name is not None:
        raise ValueError('A name is only accepted when renaming a mask')
    masks=deepcopy(recipe.masks)
    selected=index
    if action=='rename':
        masks[index]['name']=name
    elif action in ('duplicate','duplicate_invert'):
        if len(masks)>=12:
            raise ValueError('At most 12 local masks are allowed')
        duplicate=deepcopy(masks[index])
        base=duplicate.get('name') or f'Mask {index+1}'
        duplicate['name']=base[:75]+' Copy'
        if action=='duplicate_invert':
            duplicate['invert']=not duplicate.get('invert',False)
        selected=index+1
        masks.insert(selected,duplicate)
    elif action=='invert':
        masks[index]['invert']=not masks[index].get('invert',False)
    else:
        masks.pop(index)
        selected=min(index,max(0,len(masks)-1))
    return replace(recipe,masks=masks),selected,LABELS[action]
