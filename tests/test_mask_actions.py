"""Non-AI mask management through pure recipes and the shared service.

Inputs: synthetic masks/rasters and disposable catalogs. Outputs: retained fields,
bounded names/capacity, revision/history and frozen-export/original-safety evidence.
Pixel checks establish existing mask composition, not Lightroom equivalence.
"""
from copy import deepcopy
import hashlib

import numpy as np
from PIL import Image
import pytest

from lumaraw import mask_actions
from lumaraw.model import Recipe
from lumaraw.render import grade_tile
from lumaraw.service import Service, ConflictError


@pytest.fixture
def recipe():
    return Recipe(exposure=.25,masks=[
        {'kind':'brush','name':'Skin 肤色 🐈','points':[[.1,.2],[.8,.7]],'radius':.04,
         'feather':.3,'exposure':.6,'saturation':-20,'enabled':True,'invert':False},
        {'kind':'luminance','name':'Highlights','low':.7,'high':1,'exposure':-.5}])


@pytest.mark.parametrize('action',['rename','duplicate','duplicate_invert','invert','delete'])
def test_actions_preserve_unrelated_values_and_owned_input(recipe,action):
    before=deepcopy(recipe.dict())
    updated,index,label=mask_actions.apply(recipe,0,action,'Portrait 肤色' if action=='rename' else None)
    assert recipe.dict()==before
    assert updated.exposure==recipe.exposure and updated.masks[-1]==recipe.masks[-1]
    assert label==mask_actions.LABELS[action]
    if action.startswith('duplicate'):
        assert index==1 and len(updated.masks)==3
        copy=updated.masks[1]
        assert copy['name']=='Skin 肤色 🐈 Copy'
        assert copy['points']==recipe.masks[0]['points']
        assert copy['invert']==(action=='duplicate_invert')
        assert copy['enabled'] and copy['exposure']==.6 and copy['saturation']==-20
        copy['points'][0][0]=.9
        assert updated.masks[0]['points'][0][0]==recipe.masks[0]['points'][0][0]==.1
    elif action=='rename':
        assert updated.masks[0]['name']=='Portrait 肤色' and index==0
    elif action=='invert':
        assert updated.masks[0]['invert'] and index==0
    else:
        assert len(updated.masks)==1 and index==0


def test_name_limit_counts_unicode_code_points_and_preserves_content():
    name='e\u0301'*40
    recipe=Recipe(masks=[{'kind':'radial','name':name}])
    assert mask_actions.apply(recipe,0,'rename',name)[0].masks[0]['name']==name
    with pytest.raises(ValueError):
        mask_actions.apply(recipe,0,'rename',name+'x')
    duplicated,index,_=mask_actions.apply(recipe,0,'duplicate')
    assert len(duplicated.masks[index]['name'])==80
    assert duplicated.masks[0]['name']==name
    assert mask_actions.apply(recipe,0,'rename','  ')[0].masks[0]['name']=='  '


@pytest.mark.parametrize('index',[-1,2,True,.5,None])
def test_invalid_index_rejects_without_modifying_input(recipe,index):
    before=recipe.dict()
    with pytest.raises(ValueError):
        mask_actions.apply(recipe,index,'delete')
    assert recipe.dict()==before


@pytest.mark.parametrize('action,name',[
    ('missing',None),('rename',None),('rename',123),('rename','x'*81),('delete','extra')])
def test_invalid_action_values_are_visible(recipe,action,name):
    before=recipe.dict()
    with pytest.raises(ValueError):
        mask_actions.apply(recipe,0,action,name)
    assert recipe.dict()==before


def test_capacity_and_delete_selection():
    recipe=Recipe(masks=[{'kind':'radial'} for _ in range(12)])
    for action in ('duplicate','duplicate_invert'):
        with pytest.raises(ValueError,match='12'):
            mask_actions.apply(recipe,0,action)
    updated,index,_=mask_actions.apply(recipe,11,'delete')
    assert len(updated.masks)==11 and index==10
    empty,index,_=mask_actions.apply(Recipe(masks=[{'kind':'radial'}]),0,'delete')
    assert empty.masks==[] and index==0


def test_duplicate_and_invert_retains_complementary_existing_mask_effect():
    pixels=np.full((80,100,3),.15,np.float32)
    recipe=Recipe(masks=[{'kind':'radial','x':.4,'y':.6,'radius':.3,'exposure':.5}])
    renamed,_,_=mask_actions.apply(recipe,0,'rename','Subject')
    np.testing.assert_array_equal(grade_tile(pixels,renamed),grade_tile(pixels,recipe))
    paired,_,_=mask_actions.apply(recipe,0,'duplicate_invert')
    np.testing.assert_allclose(grade_tile(pixels,paired),grade_tile(pixels,Recipe(exposure=.5)),atol=1e-6)


def test_shared_command_preserves_history_exports_and_originals(tmp_path):
    path=tmp_path/'photo.png';Image.new('RGB',(40,30),(80,110,150)).save(path)
    original=hashlib.sha256(path.read_bytes()).hexdigest()
    service=Service(tmp_path/'catalog',presets_root=tmp_path/'presets')
    service.dispatch('queue_control',{'action':'pause'})
    try:
        service.dispatch('import_photos',{'paths':[str(path)]})
        before=service.dispatch('edit_photo',{'photo_id':1,'expected_revision':0,
            'patch':{'exposure':.25,'masks':[{'kind':'brush','name':'Skin','points':[[.2,.3],[.5,.6]],'exposure':.5}]}})
        export=service.dispatch('enqueue_exports',{'photo_ids':[1],'format':'tiff16',
            'destination':str(tmp_path/'exports'),'request_key':'mask-actions'})
        def action(kind,revision,index=0,**extra):
            return service.dispatch('mask_action',{'photo_id':1,'expected_revision':revision,
                'mask_index':index,'action':kind,**extra})
        renamed=action('rename',1,name='Subject 肤色')
        assert renamed['revision']==2 and renamed['mask_index']==0
        same=action('rename',2,name='Subject 肤色')
        assert same['revision']==2
        duplicated=action('duplicate_invert',2)
        assert duplicated['revision']==3 and duplicated['mask_index']==1
        assert duplicated['recipe']['masks'][1]['invert'] and duplicated['recipe']['exposure']==.25
        with pytest.raises(ConflictError):
            action('delete',2,index=1)
        assert service.dispatch('get_photo',{'photo_id':1})['recipe']==duplicated['recipe']
        undo=service.dispatch('undo_photo',{'photo_id':1,'expected_revision':3})
        assert undo['recipe']==renamed['recipe']
        restored=service.dispatch('redo_photo',{'photo_id':1,'expected_revision':undo['revision']})
        assert restored['recipe']==duplicated['recipe']
        deleted=action('delete',restored['revision'],index=1)
        assert deleted['recipe']==renamed['recipe'] and deleted['mask_index']==0
        frozen=service.dispatch('get_job',{'job_id':export['job_ids'][0]})
        assert frozen['recipe']==before['recipe'] and frozen['state']=='pending'
        assert original==hashlib.sha256(path.read_bytes()).hexdigest()
    finally:
        service.close()
