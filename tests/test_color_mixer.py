"""Eight-band mixer contracts, legacy pixels and non-destructive persistence.

Synthetic color rings and frozen pre-expansion output verify channel direction,
neutral protection, hue wrap and compatibility. Real worker/bundle probes cover
camera files separately; these tests do not claim Adobe pixel equivalence.
"""
from dataclasses import replace
import hashlib
import json

import numpy as np
from PIL import Image
import pytest

from lumaraw.color import MIXER_CENTERS,from_oklab,oklab,mix_hues,mix_monochrome
from lumaraw.imaging import LUMA
from lumaraw.model import Recipe,MIXER_BANDS,MIXER_FIELDS,BW_FIELDS,ExportOptions
from lumaraw.render import grade_tile,RenderPlan,render_strip
from lumaraw.service import Service,ConflictError
from lumaraw.library import save_recipe,load_recipe,backup_catalog,restore_catalog
from lumaraw.catalog import Catalog
from lumaraw import accelerators as accel


def ring():
    angle=np.radians(np.array(MIXER_CENTERS,np.float32))
    lab=np.stack([np.full(8,.55,np.float32),.09*np.cos(angle),.09*np.sin(angle)],axis=-1)[None,:,:]
    return from_oklab(lab)


@pytest.mark.parametrize('band',MIXER_BANDS)
def test_each_band_has_independent_hue_saturation_luminance_and_bw(band):
    a=ring();index=MIXER_BANDS.index(band);before=oklab(a)
    hue=oklab(mix_hues(a,Recipe(**{band+'_hue':12})))
    angle=np.degrees(np.arctan2(hue[0,index,2],hue[0,index,1]))%360
    assert abs((angle-MIXER_CENTERS[index]-12+180)%360-180)<.001
    saturation=oklab(mix_hues(a,Recipe(**{band+'_sat':50})))
    assert np.hypot(*saturation[0,index,1:])==pytest.approx(np.hypot(*before[0,index,1:])*1.5,rel=1e-5)
    for value,factor in [(50,2),(-50,.5)]:
        light=mix_hues(a,Recipe(**{band+'_lum':value}))
        assert (light@LUMA)[0,index]==pytest.approx((a@LUMA)[0,index]*factor,rel=2e-5)
        gray=mix_monochrome(a,Recipe(monochrome=True,**{band+'_bw':value}),LUMA)
        assert gray[0,index,0]==pytest.approx((a@LUMA)[0,index]*factor,rel=2e-5)
        np.testing.assert_array_equal(gray[:,:,0],gray[:,:,1])
        opposite=(index+4)%8
        assert gray[0,opposite,0]==pytest.approx((a@LUMA)[0,opposite],rel=1e-6)


def test_zero_controls_are_exact_noops_and_new_gains_protect_neutrals():
    a=ring();assert mix_hues(a,Recipe()) is a
    np.testing.assert_array_equal(mix_monochrome(a,Recipe(monochrome=True),LUMA),np.repeat((a@LUMA)[:,:,None],3,axis=2))
    gray=np.repeat(np.linspace(0,1,20,dtype=np.float32)[None,:,None],3,axis=2)
    controls={key:100 for key in (*[b+'_lum' for b in MIXER_BANDS],*BW_FIELDS)}
    r=Recipe(monochrome=True,**controls)
    np.testing.assert_allclose(mix_hues(gray,r),gray,atol=3e-6,rtol=1e-5)
    np.testing.assert_allclose(mix_monochrome(gray,r,LUMA),np.repeat((gray@LUMA)[:,:,None],3,axis=2),atol=3e-6,rtol=1e-5)


def test_bw_values_are_retained_but_inactive_in_color_treatment():
    a=ring();r=Recipe(red_bw=70,blue_bw=-70,yellow_hue=12,aqua_sat=-20)
    np.testing.assert_array_equal(grade_tile(a,r),grade_tile(a,replace(r,red_bw=0,blue_bw=0)))
    assert not np.allclose(grade_tile(a,replace(r,monochrome=True)),grade_tile(a,replace(r,red_bw=0,blue_bw=0,monochrome=True)))


def test_wrap_and_extreme_mixer_values_are_finite_without_mutating_input():
    a=np.random.default_rng(334).uniform(-.03,1.5,(18,25,3)).astype(np.float32);before=a.copy()
    for sign in (-1,1):
        r=Recipe(monochrome=True,**{key:sign*(30 if key.endswith('_hue') else 100) for key in (*MIXER_FIELDS,*BW_FIELDS)})
        assert np.isfinite(grade_tile(a,r)).all()
    np.testing.assert_array_equal(a,before)
    angles=np.radians(np.array([359.999,.001],np.float32))
    wrapped=from_oklab(np.stack([np.full(2,.55),.09*np.cos(angles),.09*np.sin(angles)],axis=-1).astype(np.float32)[None,:,:])
    output=mix_hues(wrapped,Recipe(red_hue=12,magenta_sat=50,red_lum=30))
    np.testing.assert_allclose(output[:,0],output[:,1],atol=2e-5)


def test_new_controls_validate_and_old_recipe_versions_default_to_zero():
    for version in (1,2):
        r=Recipe.parse({'version':version,'red_hue':15,'blue_sat':-20,'monochrome':True})
        assert r.red_hue==15 and r.blue_sat==-20 and r.red_bw==r.yellow_hue==r.magenta_lum==0
    for key in (*MIXER_FIELDS,*BW_FIELDS):
        for value in (True,float('nan'),float('inf'),101,-101):
            with pytest.raises(ValueError):Recipe.parse({key:value})


def test_four_band_recipe_keeps_frozen_pre_expansion_pixels():
    # Captured from a330eab's color mixer; contains neutral, HDR and negative-channel
    # samples as well as saturated colors. This reference does not call new code.
    a=np.array([[[.07,.12,.21],[.4,.06,.03],[.18,.32,.04],[.4,.03,.42],[.25,.25,.25],[1.1,.4,-.01]]],np.float32)
    expected=np.array([[[.0690981746,.120593451,.209936649],[.330389082,.098908022,.015850410],
        [.177758113,.319343001,.089041092],[.399999976,.030000031,.420000017],
        [.249999866,.250000149,.249999970],[1.081117630,.410388738,-.006453392]]],np.float32)
    r=Recipe(red_hue=21,red_sat=-33,orange_hue=-12,orange_sat=18,green_hue=11,green_sat=-28,blue_hue=-24,blue_sat=38)
    np.testing.assert_allclose(mix_hues(a,r),expected,atol=1e-8,rtol=0)


def test_mixer_strips_and_detail_share_pixels():
    accel.configure('cpu')
    a=np.tile(ring(),(193,19,1))
    r=Recipe(yellow_hue=14,aqua_sat=-45,purple_lum=30,magenta_bw=-22,red_bw=25,monochrome=True)
    plan=RenderPlan(a,r)
    whole,_=render_strip(plan,0,0,plan.width,plan.height)
    pieces=np.concatenate([render_strip(plan,0,y,plan.width,min(57,plan.height-y))[0] for y in range(0,plan.height,57)])
    np.testing.assert_array_equal(whole,pieces)
    view,_=render_strip(plan,11,29,65,100)
    np.testing.assert_array_equal(view,whole[29:129,11:76])


def test_mixer_history_presets_sync_exports_and_backup(tmp_path):
    s=Service(tmp_path/'catalog',presets_root=tmp_path/'presets')
    s.dispatch('queue_control',{'action':'pause'})
    paths=[]
    for i in range(2):
        p=tmp_path/f'{i}.png';Image.new('RGB',(32,24),(70,100,150)).save(p);paths.append(p)
    hashes=[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
    try:
        s.dispatch('import_photos',{'paths':list(map(str,paths))})
        patch={'yellow_hue':15,'aqua_sat':-30,'purple_lum':20,'red_bw':55,'blue_bw':-40,'monochrome':True}
        s.dispatch('edit_photo',{'photo_id':1,'expected_revision':0,'patch':patch})
        s.dispatch('enqueue_exports',{'photo_ids':[1],'destination':str(tmp_path/'exports'),'format':'tiff16','request_key':'mixer-export'})
        fields=list(s.dispatch('recipe_schema')['defaults']);fields.remove('version')
        assert len(fields)>64
        preset=s.dispatch('save_develop_preset',{'photo_id':1,'expected_photo_revision':1,'fields':fields,'name':'Complete mixer','group_name':'Tests',
            'expected_revision':s.dispatch('list_develop_presets')['revision']})
        s.dispatch('apply_develop_preset',{'preset_id':preset['preset_id'],'expected_revision':preset['revision'],'targets':[{'photo_id':2,'expected_revision':0}]})
        assert s.dispatch('get_photo',{'photo_id':2})['recipe']==s.dispatch('get_photo',{'photo_id':1})['recipe']
        s.dispatch('edit_photo',{'photo_id':1,'expected_revision':1,'patch':{'red_bw':-20,'aqua_sat':50}})
        second=s.dispatch('get_photo',{'photo_id':2})
        s.dispatch('sync_photos',{'source_id':1,'targets':[{'photo_id':2,'expected_revision':second['revision']}],'groups':['Black & White Mix']})
        copied=s.dispatch('get_photo',{'photo_id':2})['recipe']
        assert copied['red_bw']==-20 and copied['aqua_sat']==-30
        undo=s.dispatch('undo_photo',{'photo_id':2,'expected_revision':2})
        assert undo['recipe']['red_bw']==55 and undo['recipe']['purple_lum']==20
        s.dispatch('sync_photos',{'source_id':1,'targets':[{'photo_id':2,'expected_revision':undo['revision']}],'groups':['Black & White Mix']})
        with s.catalog() as c:
            frozen=json.loads(c.db.execute('SELECT recipe FROM jobs').fetchone()[0])
            assert frozen['red_bw']==55 and frozen['aqua_sat']==-30
            save_recipe(tmp_path/'mixer.lumarecipe',c.recipe(1))
            assert load_recipe(tmp_path/'mixer.lumarecipe',c.root).red_bw==-20
            backup_catalog(c,tmp_path/'backup.sqlite')
        restored=Catalog(restore_catalog(tmp_path/'backup.sqlite',tmp_path/'restored'))
        try:assert restored.recipe(2).red_bw==-20
        finally:restored.close()
        assert hashes==[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
    finally:s.close();accel.configure('auto')


def test_old_stored_json_sync_defaults_and_all_target_conflicts(tmp_path):
    s=Service(tmp_path/'catalog',presets_root=tmp_path/'presets')
    s.dispatch('queue_control',{'action':'pause'})
    try:
        paths=[]
        for i in range(3):
            path=tmp_path/f'{i}.png';Image.new('RGB',(8,8),(100,120,140)).save(path);paths.append(str(path))
        s.dispatch('import_photos',{'paths':paths})
        legacy=Recipe(red_hue=12,blue_sat=-20,monochrome=True).dict()
        old_fields={'red_hue','red_sat','orange_hue','orange_sat','green_hue','green_sat','blue_hue','blue_sat'}
        for key in set(MIXER_FIELDS+BW_FIELDS)-old_fields:legacy.pop(key)
        with s.catalog() as c:
            c.db.execute('UPDATE photos SET recipe=? WHERE id=1',(json.dumps(legacy),));c.db.commit()
        s.dispatch('edit_photo',{'photo_id':2,'expected_revision':0,'patch':{'yellow_lum':40,'red_bw':20,'crop':'1:1'}})
        with pytest.raises(ConflictError):
            s.dispatch('sync_photos',{'source_id':1,'groups':['Color','Black & White Mix'],
                'targets':[{'photo_id':2,'expected_revision':1},{'photo_id':3,'expected_revision':99}]})
        assert s.dispatch('get_photo',{'photo_id':2})['revision']==1
        s.dispatch('sync_photos',{'source_id':1,'groups':['Color','Black & White Mix'],
            'targets':[{'photo_id':2,'expected_revision':1},{'photo_id':3,'expected_revision':0}]})
        target=s.dispatch('get_photo',{'photo_id':2})
        assert target['recipe']['red_hue']==12 and target['recipe']['blue_sat']==-20
        assert target['recipe']['yellow_lum']==target['recipe']['red_bw']==0
        assert target['recipe']['crop']=='1:1' and target['recipe']['monochrome']
        undo=s.dispatch('undo_photo',{'photo_id':2,'expected_revision':target['revision']})
        assert undo['recipe']['yellow_lum']==40 and undo['recipe']['red_bw']==20
        assert s.dispatch('get_photo',{'photo_id':1})['recipe']==legacy
        s.dispatch('sync_photos',{'source_id':1,'groups':list(s.dispatch('recipe_schema')['groups']),
            'targets':[{'photo_id':2,'expected_revision':undo['revision']}]})
        assert s.dispatch('get_photo',{'photo_id':2})['recipe']==Recipe.parse(legacy).dict()
    finally:s.close()
