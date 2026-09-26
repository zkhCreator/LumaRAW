"""End-to-end v2 contracts: pixels, halo seams, color tags, files and catalog recovery.

Synthetic charts test algorithm behavior; they do not establish Nikon accuracy.
Tests use disposable local fixtures and never mutate user-owned originals.
"""
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import zipfile

import numpy as np
from PIL import Image,ImageCms
import pytest
import tifffile
from PySide6.QtGui import QColorSpace

from lumaraw.model import Recipe,ExportOptions
from lumaraw.render import RenderPlan,render_strip,detail_filter,grade_tile,make_preview,export_image,validate_camera
from lumaraw.color import output_matrix,icc_profile,apply_lut,read_cube,to_output,WORK_FROM_SRGB,decode
from lumaraw.calibration import fit_matrix
from lumaraw.catalog import Catalog
from lumaraw.library import index_library,backup_catalog,restore_catalog,save_recipe,load_recipe

@pytest.fixture
def photograph(tmp_path):
    x=np.linspace(.08,.9,360,dtype=np.float32)[None,:];y=np.linspace(.1,.8,240,dtype=np.float32)[:,None]
    data=np.stack(np.broadcast_arrays(x,y,.2+x*.3+y*.1),axis=-1)
    file=tmp_path/'test.png';Image.fromarray(np.rint(data*255).astype(np.uint8)).save(file,icc_profile=icc_profile('srgb'))
    return file


def test_migrates_legacy_recipe_and_rejects_invalid_extended_values():
    assert Recipe.parse({'version':1,'exposure':1}).version==2
    for value in [dict(sharpen=float('nan')),dict(straighten=99),dict(crop_box=[.8,0,.1,1]),dict(curve_points=[[0,0],[.7,.8],[.5,.9],[1,1]]),dict(masks=[{'kind':'arbitrary'}]),dict(lut={'path':'x','sha256':'short'})]:
        with pytest.raises((ValueError,TypeError)):Recipe.parse(value)


def test_identity_pixels_and_free_crop_coordinates():
    a=np.arange(40*60*3,dtype=np.uint16).reshape(40,60,3)
    plan=RenderPlan(a,Recipe());np.testing.assert_array_equal(plan.sample(8,9,6,5),a[9:14,8:14].astype(np.float32)/65535)
    crop=RenderPlan(a,Recipe(crop_box=[.1,.2,.8,.9]))
    assert (crop.width,crop.height)==(42,28)
    np.testing.assert_allclose(crop.sample(0,0,42,28),a[8:36,6:48]/65535,atol=2e-7)


def test_geometry_has_real_effect_without_unbounded_dimensions():
    a=np.ones((200,300,3),np.float32)*.2;a[50:150,80:220]=.6
    base=RenderPlan(a,Recipe());edited=RenderPlan(a,Recipe(distortion=30,straighten=8,perspective_v=10,geometry_scale=1.2))
    assert edited.sample(0,0,300,200).shape==a.shape
    assert np.mean(np.abs(base.sample(0,0,300,200)-edited.sample(0,0,300,200)))>.005


def test_full_and_strips_have_no_detail_or_mask_seams():
    rng=np.random.default_rng(22);a=rng.uniform(.05,.8,(400,340,3)).astype(np.float32)
    recipe=Recipe(luma_noise=70,chroma_noise=65,sharpen=110,sharpen_radius=3,detail_protect=15,
                  distortion=4,vignette=12,straighten=1,curve_points=[[0,0],[.4,.44],[1,1]],
                  masks=[{'kind':'radial','x':.4,'y':.5,'radius':.3,'exposure':.7},
                         {'kind':'brush','points':[[.1,.1],[.8,.8]],'radius':.04,'exposure':-.5}])
    plan=RenderPlan(a,recipe);full,_=render_strip(plan,0,0,340,400)
    pieces=[render_strip(plan,0,y,340,min(97,400-y))[0] for y in range(0,400,97)]
    np.testing.assert_allclose(np.concatenate(pieces),full,atol=1e-6)
    viewport,_=render_strip(plan,45,108,170,160)
    np.testing.assert_allclose(viewport,full[108:268,45:215],atol=1e-6)


def test_noise_reduction_preserves_mean_and_sharpen_is_effective():
    rng=np.random.default_rng(6);a=np.full((180,200,3),.3,np.float32)+rng.normal(0,.012,(180,200,3)).astype(np.float32)
    reduced=detail_filter(a,Recipe(luma_noise=100,chroma_noise=100,detail_protect=0))
    assert reduced.std()<a.std()*.85
    assert abs(reduced.mean()-a.mean())<.003
    gradient=np.full((100,100,3),.2,np.float32);gradient[:,50:]=.7
    initial=gradient[:,50:52].mean()
    sharp=detail_filter(gradient,Recipe(sharpen=100,detail_protect=0))
    assert sharp[:,50:52].mean()>initial


def test_local_mask_scope_and_continuous_brush_segment():
    a=np.full((100,100,3),.2,np.float32)
    r=Recipe(masks=[{'kind':'radial','radius':.2,'x':.5,'y':.5,'exposure':1}])
    result=grade_tile(a,r)
    np.testing.assert_allclose(result[0,0],a[0,0],atol=1e-6)
    assert result[50,50].mean()>.38
    brush=Recipe(masks=[{'kind':'brush','points':[[.1,.5],[.9,.5]],'radius':.03,'exposure':1}])
    assert grade_tile(a,brush)[50,50].mean()>.38


@pytest.mark.parametrize('space',['srgb','adobe','p3','prophoto'])
def test_icc_profiles_match_encoded_output(photograph,tmp_path,space):
    output=export_image(photograph,Recipe(),tmp_path,'tiff16',1024,4,options={'space':space,'max_edge':160})
    with tifffile.TiffFile(output['output']) as tf:
        array=tf.asarray();profile=tf.pages[0].tags[34675].value
        assert array.dtype==np.uint16 and max(array.shape[:2])==160
    assert QColorSpace.fromIccProfile(profile).isValid()
    encoded=(array/257).round().astype(np.uint8)
    converted=ImageCms.profileToProfile(Image.fromarray(encoded),ImageCms.ImageCmsProfile(io.BytesIO(profile)),ImageCms.createProfile('sRGB'),outputMode='RGB')
    baseline=export_image(photograph,Recipe(),tmp_path,'tiff16',1024,5,options={'space':'srgb','max_edge':160})
    expected=(tifffile.imread(baseline['output'])/257).round().astype(np.int32)
    assert np.mean(np.abs(np.asarray(converted).astype(np.int32)-expected))<1.2


def test_wide_gamut_not_clipped_before_output():
    # A Display P3 green lies outside sRGB; retain it until the chosen output boundary.
    green=np.array([[[0,1,0]]],np.float32) @ np.linalg.inv(output_matrix('p3')).T
    graded=grade_tile(green,Recipe());p3,gamut=to_output(graded,'p3')
    np.testing.assert_allclose(p3,[[[0,1,0]]],atol=.001)
    assert to_output(graded,'srgb')[1].item()


def test_detail_view_matches_full_export_pixels(photograph,tmp_path):
    r=Recipe(exposure=.2,chroma_noise=20,sharpen=30,crop_box=[.1,.1,.9,.9])
    output=export_image(photograph,r,tmp_path,'tiff16',1024,8)
    full=tifffile.imread(output['output'])
    detail=make_preview(photograph,r,tmp_path/'cache',1024,detail={'cx':.62,'cy':.51,'width':90,'height':70})
    x,y,w,h=detail['roi'];tile=np.asarray(Image.open(detail['preview']))
    expected=np.rint(full[y:y+h,x:x+w]/257).astype(np.int32)
    assert np.max(np.abs(tile.astype(np.int32)-expected))<=1
    assert detail['detail'] is True


def cube_file(path):
    lines=['LUT_3D_SIZE 2']
    for b in (0,1):
        for g in (0,1):
            for r in (0,1):lines.append(f'{b} {g} {r}')
    path.write_text('\n'.join(lines)+'\n');return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'title':path.name}


def test_lut_channel_order_and_portable_asset(photograph,tmp_path):
    lut=cube_file(tmp_path/'swap.cube');a=decode(np.array([[[.8,.4,.2]]],np.float32))@WORK_FROM_SRGB.T
    result=to_output(apply_lut(a,lut,100))[0]
    np.testing.assert_allclose(result,[[[.2,.4,.8]]],atol=1e-5)
    r=Recipe(lut=lut,exposure=.3);file=tmp_path/'look.luma';save_recipe(file,r)
    dest=tmp_path/'new-catalog';dest.mkdir();restored=load_recipe(file,dest)
    assert restored.exposure==.3 and Path(restored.lut['path']).exists()
    assert restored.lut['path']!=lut['path']
    with pytest.raises(FileExistsError):save_recipe(file,r)


def test_camera_fit_has_heldout_improvement_and_camera_gate():
    rng=np.random.default_rng(2);source=rng.uniform(.06,.65,(24,3));matrix=np.array([[1.06,-.03,0],[.01,.98,.01],[0,-.02,1.08]])
    target=source@matrix.T;profile=fit_matrix(source,target,'TEST CAMERA')
    assert profile['measurement']['after_mean']<profile['measurement']['before_mean']*.03
    assert len(profile['measurement']['holdout_indices'])==6
    validate_camera(Recipe(camera_profile=profile),{'camera':'TEST CAMERA'})
    with pytest.raises(ValueError,match='Camera profile'):validate_camera(Recipe(camera_profile=profile),{'camera':'ANOTHER CAMERA'})
    with pytest.raises(ValueError):fit_matrix(np.ones((24,3)),np.ones((24,3)),'CAMERA')


def test_catalog_versions_selective_sync_priority_and_backup(photograph,tmp_path):
    second=tmp_path/'second.png';second.write_bytes(photograph.read_bytes())
    cat=Catalog(tmp_path/'catalog');cat.import_paths([photograph,second]);ids=list(cat.all_ids())
    cat.edit(ids[0],Recipe(exposure=1,crop='1:1'));cat.save_version(ids[0],'Version A');version=cat.versions(ids[0])[0]
    cat.edit(ids[0],Recipe(exposure=2));cat.restore_version(ids[0],version['id'])
    assert cat.recipe(ids[0]).exposure==1
    cat.sync(ids[0],[ids[1]],['Light']);assert cat.recipe(ids[1]).exposure==1 and cat.recipe(ids[1]).crop=='original'
    cat.enqueue(ids,tmp_path/'exports','jpeg',{'max_edge':200,'space':'p3','priority':1})
    jobs=cat.jobs();cat.prioritize(jobs[0]['id'],9);assert cat.next_job()['id']==jobs[0]['id']
    backup=tmp_path/'backup.sqlite';backup_catalog(cat,backup);new=restore_catalog(backup,tmp_path/'restored');clone=Catalog(new)
    assert clone.count()==2 and clone.versions(ids[0])[0]['name']=='Version A'
    assert clone.next_job() is None and clone.job_counts()['interrupted']==2
    assert json.loads(clone.jobs()[0]['options'])['space']=='p3'
    cat.close();clone.close()


def test_duplicate_burst_missing_and_relink(tmp_path):
    paths=[]
    for i,sec in enumerate((0,1,8)):
        path=tmp_path/f'{i}.jpg';exif=Image.Exif();exif[272]='Test Nikon';exif[306]=f'2026:09:26 12:00:{sec:02d}'
        Image.new('RGB',(40,30),(50,100,120)).save(path,exif=exif);paths.append(path)
    duplicate=tmp_path/'duplicate.jpg';duplicate.write_bytes(paths[0].read_bytes())
    cat=Catalog(tmp_path/'catalog');cat.import_paths([*paths,duplicate]);result=index_library(cat)
    assert result['indexed']==4 and cat.filtered_count('duplicates')==2
    assert cat.bursts()[0]['count']==3
    original=cat.filtered_page(mode='duplicates')[0];p=Path(original['path']);content=p.read_bytes();p.unlink();index_library(cat)
    assert cat.filtered_count('missing')==1
    wrong=tmp_path/'wrong.jpg';wrong.write_bytes(paths[2].read_bytes())
    with pytest.raises(ValueError):cat.relink(original['id'],wrong)
    right=tmp_path/'relocated.jpg';right.write_bytes(content);cat.relink(original['id'],right)
    assert cat.photo(original['id'])['missing']==0
    cat.close()


def test_export_template_validation_and_space_check(photograph,tmp_path,monkeypatch):
    for name in ['../escape','{stem.__class__}','{unknown}','{seq:04d}']:
        with pytest.raises(ValueError):ExportOptions(name=name)
    class LowDisk:free=1
    monkeypatch.setattr('lumaraw.render.shutil.disk_usage',lambda p:LowDisk())
    with pytest.raises(OSError,match='Insufficient'):export_image(photograph,Recipe(),tmp_path,'tiff16',1024,10)
    assert not list(tmp_path.glob('*.tif'))


def test_softproof_validates_asset_and_keeps_srgb_neutral(tmp_path):
    from lumaraw.color import soft_proof
    p=tmp_path/'proof.icc';p.write_bytes(icc_profile('srgb'));sha=hashlib.sha256(p.read_bytes()).hexdigest()
    rgb=np.random.default_rng(2).integers(2,253,(30,40,3),dtype=np.uint8)
    proof=soft_proof(rgb,str(p),sha)
    assert np.max(np.abs(proof.astype(int)-rgb.astype(int)))<=2
    assert soft_proof(rgb,str(p),sha,gamut=True).shape==rgb.shape
    p.write_bytes(icc_profile('p3'))
    with pytest.raises(ValueError,match='changed'):soft_proof(rgb,str(p),sha)


def test_failed_backup_does_not_publish_partial_database(photograph,tmp_path,monkeypatch):
    import lumaraw.library as library
    c=Catalog(tmp_path/'catalog');c.import_paths([photograph]);(c.root/'assets').mkdir()
    (c.root/'assets'/'example.cube').write_text('example')
    def fail(*a,**kw):raise OSError('simulated disk failure')
    monkeypatch.setattr(library.shutil,'copytree',fail)
    path=tmp_path/'backup.sqlite'
    with pytest.raises(OSError):backup_catalog(c,path)
    assert not path.exists() and not path.with_suffix('.sqlite.assets').exists()
    assert not list(tmp_path.glob('.lumaraw-backup-*'))
    c.close()


def test_unknown_camera_cannot_claim_model_bound_profile():
    profile={'camera':'RAW camera','space':'LibRaw-ProPhoto-D65-linear','matrix':np.eye(3).tolist()}
    with pytest.raises(ValueError,match='model'):validate_camera(Recipe(camera_profile=profile),{'camera':'RAW camera'})
    with pytest.raises(ValueError,match='model'):fit_matrix(np.ones((24,3)),np.ones((24,3)),'RAW camera')


def test_chart_sampling_and_end_to_end_calibration(tmp_path):
    from lumaraw.calibration import calibrate
    # A synthetic RAW mosaic and its own developed reference exercise the full
    # calibration file path. This is deliberately not camera colorimetry evidence.
    from lumaraw.color import SRGB_XYZ
    # Identity camera-to-XYZ requires XYZ samples. Arbitrary independent sensor
    # channels would create out-of-sRGB colors and a clipped, invalid reference.
    rng=np.random.default_rng(42);colors=rng.uniform(.08,.4,(24,3))@SRGB_XYZ.T
    mosaic=np.zeros((400,600),np.uint16)
    for row in range(4):
        for col in range(6):
            patch=mosaic[row*100:(row+1)*100,col*100:(col+1)*100];r,g,b=colors[row*6+col]
            patch[0::2,0::2]=512+int(r*15871);patch[0::2,1::2]=512+int(g*15871)
            patch[1::2,0::2]=512+int(g*15871);patch[1::2,1::2]=512+int(b*15871)
    tags=[(50706,'B',4,(1,4,0,0),False),(50708,'s',0,'Synthetic Chart',False),(272,'s',0,'Synthetic Chart',False),
          (33421,'H',2,(2,2),False),(33422,'B',4,(0,1,1,2),False),(50714,'H',1,512,False),(50717,'H',1,16383,False),
          (50721,'2i',9,(10000,10000,0,10000,0,10000,0,10000,10000,10000,0,10000,0,10000,0,10000,10000,10000),False),
          (50728,'2I',3,(1,1,1,1,1,1),False),(50778,'H',1,21,False)]
    raw=tmp_path/'chart.dng';tifffile.imwrite(raw,mosaic,photometric=32803,metadata=None,extratags=tags)
    preview=make_preview(raw,Recipe(),tmp_path/'cache',1024)
    result=calibrate(raw,preview['before'],[0,0,1,1],[0,0,1,1],tmp_path/'cache',1024,'Test only','synthetic')
    assert result['profile']['camera']=='Synthetic Chart'
    assert len(result['measurement']['holdout_indices'])==6
    assert result['measurement']['after_mean']<3
