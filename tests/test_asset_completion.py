import base64
import io
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw
from django.test import SimpleTestCase


class CompleteEntity(SimpleTestCase):
    def test_calibration_cannot_paste_independent_objects_back_when_occlusions_are_missing(self):
        import hashlib
        from asset_completion import calibrate, correct_reviewed_color
        from acceptance import ASSET_CRITERIA
        generated=Image.new('RGBA',(100,100),(40,80,40,255));raw=io.BytesIO();generated.save(raw,'PNG')
        other=dict(name='独立牌面',type='image',x=35,y=35,width=30,height=30)
        node=dict(id='table',name='牌桌',x=0,y=0,width=100,height=100,
                  src='data:image/png;base64,'+base64.b64encode(raw.getvalue()).decode(),sourceAlignment={'inliers':40},
                  completionPlan=dict(bounds=dict(x=10,y=10,width=80,height=80),observed=[[10,10],[89,10],[89,89],[10,89]],
                                      exclusions=[],holes=[],completionRequired=True),_otherLayers=[other])
        quality=dict(status='FAIL',checks=[dict(name=name,status='FAIL' if name=='颜色与光照' else 'PASS',notes='已查看') for name in ASSET_CRITERIA])
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.png';im=Image.new('RGB',(100,100),(60,100,60));ImageDraw.Draw(im).rectangle((35,35,64,64),fill='white');im.save(source)
            node['completionPlan']['sourceSHA256']=hashlib.sha256(source.read_bytes()).hexdigest()
            for adjacent in [other,{**other,'x':float('nan')}]:
                with self.subTest(adjacent=adjacent):
                    candidate={**node,'_otherLayers':[adjacent]};result=calibrate(source,candidate)
                    self.assertEqual(result['src'],node['src'])
                    self.assertIn('遮挡',result['fidelityWarning'])
                    self.assertNotIn('sourceFidelity',result)
                    with patch('acceptance.review_asset') as review:
                        corrected,qa=correct_reviewed_color(source,candidate,quality,root,lambda:False)
                    review.assert_not_called();self.assertEqual(corrected['src'],node['src']);self.assertEqual(qa,quality)
            # A disjoint object must not disable ordinary visible-colour calibration.
            isolated={**node,'_otherLayers':[{**other,'x':95,'y':95,'width':4,'height':4}]}
            result=calibrate(source,isolated)
            pixels=Image.open(io.BytesIO(base64.b64decode(result['src'].split(',')[1])))
            self.assertEqual(pixels.getpixel((25,25)),(60,100,60,255))
            self.assertEqual(pixels.getchannel('A').tobytes(),generated.getchannel('A').tobytes())

    def test_extraction_keeps_independent_layer_ownership_through_planning_generation_and_review(self):
        from incremental_assets import extract_checked
        from acceptance import ASSET_CRITERIA
        node=dict(id='panel',name='面板',type='image',assetKind='panel',x=10,y=10,width=80,height=80)
        other=dict(id='line',name='独立金色横饰',type='image',x=20,y=30,width=40,height=4)
        # An archived layer is not part of the current ownership plan.
        scene=dict(nodes=[node,other,{**other,'id':'archived','name':'旧版横饰','versionArchived':True}])
        plan=dict(bounds=dict(x=10,y=10,width=80,height=80),observed=[[10,10],[89,10],[89,89],[10,89]],
                  exclusions=[[[20,30],[59,30],[59,33],[20,33]]],holes=[],completionRequired=True,notes='移除独立横饰，补齐面板底纹。')
        calls=[]
        def analyze(prompt,images,schema,*args,**kwargs):
            calls.append('plan' if 'bounds' in schema['properties'] else 'review')
            self.assertIn('独立金色横饰',prompt)
            self.assertNotIn('旧版横饰',prompt)
            if 'bounds' in schema['properties']:return plan
            return dict(status='PASS',issues=[],placement=None,checks=[dict(name=n,status='PASS',notes='逐项对照') for n in ASSET_CRITERIA])
        def generate(prompt,images,target,**kwargs):
            calls.append('generate');self.assertIn('独立金色横饰',prompt)
            im=Image.new('RGBA',(100,100));ImageDraw.Draw(im).rectangle((10,10,89,89),fill='#203050');im.save(target)
            return dict(file=str(target),actualImageGeneration=True,transparent=True)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.png';im=Image.new('RGB',(100,100),'#203050');ImageDraw.Draw(im).rectangle((20,30,59,33),fill='gold');im.save(source)
            with patch('codex_client.CLIENT.analyze',side_effect=analyze),patch('codex_client.CLIENT.generate',side_effect=generate):
                result=extract_checked(source,node,root,root,lambda:False,source,None,scene=scene)
        self.assertEqual(calls,['plan','generate','review'])
        self.assertEqual(result['assetReviewStatus'],'PASS')
        self.assertNotIn('_otherLayers',result)
        self.assertNotIn('_otherLayers',node)

    def test_automatic_local_repair_uses_existing_roi_edit_and_preserves_exterior_pixels(self):
        import copy,hashlib
        from asset_completion import repair_local
        from acceptance import ASSET_CRITERIA
        from image_replace import _process as replace
        raw=io.BytesIO();before=Image.new('RGBA',(160,160));ImageDraw.Draw(before).rectangle((5,5,154,154),fill='red');before.save(raw,'PNG')
        node=dict(id='hand',name='角色',type='image',x=10,y=20,width=80,height=80,src='data:image/png;base64,'+base64.b64encode(raw.getvalue()).decode(),completionPlan={'completionRequired':True})
        quality=dict(status='FAIL',issues=['手部姿态错误'],repairRegions=[dict(x=30,y=40,width=20,height=10,confidence=.99,reason='恢复原图中手指向下弯曲的扶台姿势')],checks=[dict(name=name,status='FAIL' if name=='身份与完整实体' else 'PASS',notes='已查看') for name in ASSET_CRITERIA])
        passed=copy.deepcopy(quality);passed.update(status='PASS',issues=[],repairRegions=[])
        for c in passed['checks']:c['status']='PASS'
        def generate(prompt,images,target,**kwargs):
            self.assertFalse(kwargs['allow_identity_change']);self.assertIn('原图证据',prompt);self.assertNotIn('可以依描述和参考图更换指定对象的主体身份',prompt)
            self.assertEqual(len(images),3)
            with Image.open(images[2]) as context:
                self.assertEqual(context.size,before.size);self.assertEqual(context.getpixel((100,100)),before.getpixel((100,100)))
            self.assertIn('完整素材参照',prompt)
            pixels=np.array(Image.open(images[0]).convert('RGBA'));self.assertTrue(np.any(np.all(pixels[:,:,:3]==(0,255,0),axis=2)));self.assertTrue(np.any(np.all(pixels[:,:,:3]==(255,0,0),axis=2)))
            with Image.open(images[0]) as reference:Image.new('RGBA',reference.size,'blue').save(target)
            return dict(actualImageGeneration=True,transparent=True)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.png';Image.new('RGB',(120,120),'#00ff00').save(source)
            with patch('codex_client.CLIENT.generate',side_effect=generate),patch('acceptance.review_asset',return_value=passed):
                result,qa=repair_local(source,node,quality,root,lambda:False,source)
            after=np.array(Image.open(io.BytesIO(base64.b64decode(result['src'].split(',')[1]))))
            changed=np.any(after!=np.array(before),axis=2);self.assertTrue(changed[42:58,42:78].all());self.assertEqual(tuple(after[40,50]),(255,0,0,255));changed[40:60,40:80]=False;self.assertFalse(changed.any())
            self.assertEqual(qa['status'],'PASS');self.assertTrue(result['automaticLocalRepair']['generatedPatchOutsidePixelsUnchanged'])
            self.assertEqual(result['completionBase']['generationRecord']['generatedAssetSHA256'],hashlib.sha256(base64.b64decode(result['src'].split(',')[1])).hexdigest())
            remaining=copy.deepcopy(quality);remaining['repairRegions']=[dict(x=50,y=50,width=10,height=15,confidence=.99,reason='继续修复第二处独立接缝，其他已修复部位保持不变')]
            with patch('codex_client.CLIENT.generate',side_effect=generate) as edits,patch('acceptance.review_asset',side_effect=[remaining,passed]):
                twice,qa=repair_local(source,node,quality,root,lambda:False,source)
            self.assertEqual(edits.call_count,2);self.assertEqual(qa['status'],'PASS')
            im=Image.open(io.BytesIO(base64.b64decode(twice['src'].split(',')[1])))
            self.assertEqual(im.getpixel((50,50)),(0,0,255,255));self.assertEqual(im.getpixel((85,65)),(0,0,255,255));self.assertEqual(im.getpixel((100,100)),(255,0,0,255))
            def escaped(*args,**kwargs):
                scene=replace(*args,**kwargs);im=Image.open(io.BytesIO(base64.b64decode(scene['nodes'][0]['src'].split(',')[1]))).convert('RGBA');im.putpixel((0,0),(255,255,0,255));buf=io.BytesIO();im.save(buf,'PNG');scene['nodes'][0]['src']='data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode();return scene
            with patch('codex_client.CLIENT.generate',side_effect=generate),patch('image_replace._process',side_effect=escaped),self.assertRaisesRegex(ValueError,'越过'):
                repair_local(source,node,quality,root,lambda:False,source)

    def test_automatic_patch_aligns_generated_drift_and_joins_opaque_surface(self):
        import cv2
        from engine import png
        from image_replace import _process
        rng=np.random.default_rng(91);pixels=cv2.GaussianBlur(rng.integers(30,190,(300,360,3),dtype=np.uint8),(3,3),.6)
        before=Image.fromarray(pixels).convert('RGBA');src=png(before)
        scene=dict(format='shijie-scene',version=2,width=360,height=300,source=src,nodes=[dict(id='surface',name='材质',type='image',x=0,y=0,width=360,height=300,src=src)],groups=[],edges=[])
        # Fractional shear resamples texture twice; permit its interpolation
        # loss, while rejecting the observed 23.6 RGB error without alignment.
        for drift,tolerance in [([[1,0,3],[0,1,2]],3),([[1,.005,-.3],[.055,1.008,-2.5]],8)]:
            with self.subTest(drift=drift):
                def generate(prompt,images,target,**kwargs):
                    im=Image.open(images[0]).convert('RGBA');a=np.array(im);a[:,:,:3]=np.minimum(255,a[:,:,:3].astype(int)+12)
                    # Actual model output also shears a context by about three degrees.
                    Image.fromarray(cv2.warpAffine(a,np.float32(drift),im.size)).save(target)
                    return dict(actualImageGeneration=True)
                with tempfile.TemporaryDirectory() as folder,patch('codex_client.CLIENT.generate',side_effect=generate):
                    result=_process(src,'局部返修',lambda *a:None,lambda:False,src,folder,scene,dict(targetId='surface',region=dict(x=90,y=75,width=180,height=150),prompt='保持纹理位置，只校正材质明暗'),preserve_identity=True)['nodes'][0]
                after=np.array(Image.open(io.BytesIO(base64.b64decode(result['src'].split(',')[1]))))
                changed=np.any(after!=np.array(before),axis=2);changed[75:225,90:270]=False;self.assertFalse(changed.any())
                error=after[95:205,110:250,:3].astype(float)-pixels[95:205,110:250]
                self.assertLess(np.abs(error-12).mean(),tolerance)
                self.assertLess(np.abs(after[75,90:270,:3].astype(float)-pixels[75,90:270]).max(),2)
                self.assertEqual(after[:,:,3].tobytes(),np.array(before)[:,:,3].tobytes())

    def test_local_repair_can_cross_source_canvas_but_not_complete_asset(self):
        from asset_completion import validate_repair_region,repair_local
        from acceptance import ASSET_CRITERIA
        raw=io.BytesIO();Image.new('RGBA',(100,190),'red').save(raw,'PNG')
        node=dict(id='body',name='完整人物',type='image',x=-10,y=10,width=100,height=190,src='data:image/png;base64,'+base64.b64encode(raw.getvalue()).decode(),completionPlan={'completionRequired':True})
        region=dict(x=10,y=105,width=20,height=35,confidence=.99,reason='恢复原画板底边上下的腿部自然连续，保留原图可见姿态')
        self.assertEqual(validate_repair_region(region,node,(120,120)),region)
        with self.assertRaises(ValueError):validate_repair_region({**region,'x':90},node,(120,120))
        quality=dict(status='FAIL',issues=['截边接缝'],repairRegions=[region],checks=[dict(name=n,status='FAIL' if n=='透明边缘与孔洞' else 'PASS',notes='实际观察') for n in ASSET_CRITERIA])
        passed={**quality,'status':'PASS','checks':[{**c,'status':'PASS'} for c in quality['checks']]}
        def generate(prompt,images,target,**kwargs):
            ref=Image.open(images[1]);self.assertEqual(ref.size,(20,35));self.assertEqual(ref.getpixel((10,25))[3],0)
            Image.new('RGBA',Image.open(images[0]).size,'blue').save(target);return dict(actualImageGeneration=True)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.png';Image.new('RGB',(120,120),'red').save(source)
            with patch('codex_client.CLIENT.generate',side_effect=generate),patch('acceptance.review_asset',return_value=passed):result,_=repair_local(source,node,quality,root,lambda:False,source)
        im=Image.open(io.BytesIO(base64.b64decode(result['src'].split(',')[1])))
        self.assertEqual(im.getpixel((25,115)),(0,0,255,255));self.assertEqual(im.getpixel((25,140)),(255,0,0,255))

    def test_automatic_color_calibration_cannot_cut_generated_alpha_from_approximate_plan(self):
        from asset_completion import calibrate
        im=Image.new('RGBA',(100,100));ImageDraw.Draw(im).rounded_rectangle((10,10,89,89),radius=10,fill='#d0a040');raw=io.BytesIO();im.save(raw,'PNG')
        node=dict(x=0,y=0,width=100,height=100,src='data:image/png;base64,'+base64.b64encode(raw.getvalue()).decode(),sourceAlignment={'inliers':100},
                  completionPlan=dict(bounds=dict(x=10,y=10,width=80,height=80),observed=[[10,10],[89,10],[89,70],[55,70],[55,89],[10,89]],exclusions=[],holes=[[[65,20],[75,20],[75,30],[65,30]]]))
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.png';im.convert('RGB').save(source);result=calibrate(source,node)
        actual=Image.open(io.BytesIO(base64.b64decode(result['src'].split(',')[1]))).convert('RGBA')
        self.assertEqual(actual.getchannel('A').tobytes(),im.getchannel('A').tobytes())
        self.assertTrue(result['sourceFidelity']['automatic'])

    def test_slight_shear_is_aligned_without_discarding_complete_pixels(self):
        import cv2
        from asset_geometry import align_to_source
        rng=np.random.default_rng(5);rgb=rng.integers(0,256,(240,200,3),dtype=np.uint8)
        rgb=cv2.GaussianBlur(rgb,(3,3),.7);alpha=np.zeros((240,200),np.uint8);alpha[15:225,15:185]=255
        rgba=np.dstack((rgb,alpha));matrix=np.array([[1.05,.07,90],[.01,1.1,35]],float)
        placed=cv2.warpAffine(rgba,matrix,(420,360));source=np.full((360,420,3),(60,30,80),np.uint8);a=placed[:,:,3:]/255
        source=np.rint(source*(1-a)+placed[:,:,:3]*a).astype('uint8');buf=io.BytesIO();Image.fromarray(rgba).save(buf,'PNG')
        node=dict(id='shear',type='image',x=80,y=25,width=210,height=270,src='data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode())
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source.png';Image.fromarray(source).save(path);result=align_to_source(path,node)
        self.assertIsNotNone(result)
        self.assertTrue(result['sourceAlignment']['pixelWarp'])
        self.assertGreaterEqual(result['sourceAlignment']['inliers'],40)
        self.assertLess(result['sourceAlignment']['p90ErrorPx'],4)
        im=Image.open(io.BytesIO(base64.b64decode(result['src'].split(',')[1]))).convert('RGBA')
        self.assertGreater(im.getchannel('A').getbbox()[2],150)

    def test_reviewed_color_restoration_keeps_alpha_and_cannot_regress_passed_checks(self):
        import hashlib,copy
        from asset_completion import correct_reviewed_color
        from acceptance import ASSET_CRITERIA
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.png';im=Image.new('RGB',(80,80),'purple');ImageDraw.Draw(im).rectangle((10,10,69,69),fill='#d0a040');im.save(source)
            generated=Image.new('RGBA',(80,80));ImageDraw.Draw(generated).rectangle((10,10,69,69),fill='#e08010');raw=io.BytesIO();generated.save(raw,'PNG')
            node=dict(id='colour',x=0,y=0,width=80,height=80,src='data:image/png;base64,'+base64.b64encode(raw.getvalue()).decode(),sourceAlignment={'inliers':30},
                      completionPlan=dict(bounds=dict(x=10,y=10,width=60,height=60),observed=[[10,10],[69,10],[69,69],[10,69]],holes=[],exclusions=[],sourceSHA256=hashlib.sha256(source.read_bytes()).hexdigest()),
                      generationRecord=dict(actualImageGeneration=True,generatedAssetSHA256=hashlib.sha256(raw.getvalue()).hexdigest()))
            quality=dict(status='FAIL',issues=['颜色变化'],checks=[dict(name=name,status='FAIL' if name=='颜色与光照' else 'PASS',notes='已查看') for name in ASSET_CRITERIA])
            passed=copy.deepcopy(quality);passed.update(status='PASS',issues=[])
            for c in passed['checks']:c['status']='PASS'
            with patch('acceptance.review_asset',return_value=passed) as review:
                result,qa=correct_reviewed_color(source,node,quality,root,lambda:False)
                review.assert_called_once()
            actual=Image.open(io.BytesIO(base64.b64decode(result['src'].split(',')[1]))).convert('RGBA')
            self.assertEqual(actual.getpixel((40,40)),(208,160,64,255))
            self.assertEqual(actual.getchannel('A').tobytes(),generated.getchannel('A').tobytes())
            self.assertEqual(result['generationRecord']['generatedAssetSHA256'],hashlib.sha256(base64.b64decode(result['src'].split(',')[1])).hexdigest())
            self.assertEqual(qa['status'],'PASS')
            material=copy.deepcopy(quality)
            next(c for c in material['checks'] if c['name']=='材质文字与标识')['status']='FAIL'
            with patch('acceptance.review_asset',return_value=passed):
                restored,qa=correct_reviewed_color(source,node,material,root,lambda:False)
                self.assertEqual(qa['status'],'PASS');self.assertIn('colorCorrectionReview',restored)
            partial=copy.deepcopy(quality);partial['checks'][0]['status']='FAIL'
            improved=copy.deepcopy(partial);next(c for c in improved['checks'] if c['name']=='颜色与光照')['status']='PASS'
            with patch('acceptance.review_asset',return_value=improved) as review:
                fixed,qa=correct_reviewed_color(source,node,partial,root,lambda:False)
                review.assert_called_once();self.assertIsNot(fixed,node);self.assertEqual(qa['status'],'FAIL')
            regressed=copy.deepcopy(passed);regressed['status']='FAIL';next(c for c in regressed['checks'] if c['name']=='透明边缘与孔洞')['status']='FAIL'
            with patch('acceptance.review_asset',return_value=regressed):
                kept,qa=correct_reviewed_color(source,node,partial,root,lambda:False);self.assertIs(kept,node);self.assertEqual(qa,partial)

    def test_targeted_repair_does_not_reapply_the_mask_that_failed_review(self):
        from workflow_assets import complete_asset
        import hashlib
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.png';Image.new('RGB',(80,80),'purple').save(source)
            stream=io.BytesIO();im=Image.new('RGBA',(40,60));ImageDraw.Draw(im).rectangle((4,4,35,55),fill='orange');im.save(stream,'PNG');raw=stream.getvalue()
            plan=dict(bounds=dict(x=20,y=10,width=32,height=52),observed=[[20,10],[51,10],[51,61],[20,61]],exclusions=[],holes=[],completionRequired=True,notes='修复已经观察到的接缝与背景残边。',sourceSHA256=hashlib.sha256(source.read_bytes()).hexdigest())
            node=dict(id='repair',name='角色',type='image',x=20,y=10,width=32,height=52,completionPlan=plan,
                      _repairSource='data:image/png;base64,'+base64.b64encode(raw).decode())
            def generate(prompt,images,target,**kwargs):
                self.assertEqual(len(images),2)
                self.assertEqual(images[0].read_bytes(),raw)
                target.write_bytes(raw)
                return dict(actualImageGeneration=True,transparent=True)
            with patch('workflow_assets.CLIENT.generate',side_effect=generate),patch('asset_geometry.align_to_source',return_value=None),patch('asset_completion.calibrate') as calibrate:
                result=complete_asset(source,node,root,root,lambda:False,force_repair=True)
            calibrate.assert_not_called()
            self.assertEqual(base64.b64decode(result['src'].split(',')[1]),raw)
            self.assertTrue(result['review'])
            self.assertEqual(result['targetedRepair']['inputSHA256'],hashlib.sha256(raw).hexdigest())

    def test_calibration_retry_reuses_verified_complete_pixels_without_regenerating(self):
        import hashlib
        from workflow_assets import complete_asset
        raw=io.BytesIO();Image.new('RGBA',(30,50),(100,120,140,255)).save(raw,'PNG');data=raw.getvalue()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'original.png';Image.new('RGB',(60,60),(100,120,140)).save(source)
            receipt=dict(actualImageGeneration=True,transparent=True,provider='codex',sourceOriginalSHA256=hashlib.sha256(source.read_bytes()).hexdigest(),generatedAssetSHA256=hashlib.sha256(data).hexdigest())
            node=dict(id='body',name='角色',type='image',x=10,y=10,width=30,height=50,
                      completionBase=dict(src='data:image/png;base64,'+base64.b64encode(data).decode(),generationRecord=receipt))
            def regenerated(prompt,images,target,**kwargs):
                target.write_bytes(data)
                return {**receipt,'file':str(target)}
            with patch('workflow_assets.CLIENT.generate',side_effect=regenerated) as generate:
                result=complete_asset(source,node,root,root,lambda:False)
            generate.assert_not_called()
            self.assertEqual(base64.b64decode(result['src'].split(',')[1]),data)
            self.assertEqual(result['completionBase']['generationRecord'],receipt)
            node['completionBase']['generationRecord']={**receipt,'sourceOriginalSHA256':'bad'}
            with patch('workflow_assets.CLIENT.generate') as generate,self.assertRaisesRegex(ValueError,'底稿'):
                complete_asset(source,node,root,root,lambda:False)
            generate.assert_not_called()

    def test_textured_art_text_has_one_owner_and_is_not_duplicated_as_a_logo(self):
        from plan_contract import complete_art_text_assets,link_art_text
        from planner import parse_plan
        import json
        box=dict(left=10,top=10,right=100,bottom=40)
        plan=dict(assets=[dict(id='art',name='完整艺术字',kind='decoration',box=box,z_index=2)],
                  texts=[dict(id='t',text='工坊',box=box,z_index=2)],art_text_ids=['t'],warnings=[])
        fixed=complete_art_text_assets(plan,(120,80))
        self.assertEqual([a['id'] for a in fixed['assets']],['art'])
        assets=parse_plan(json.dumps(fixed),120,80,(120,80))['assets']
        link_art_text(assets,[dict(id='t',text='工坊',bbox=[10,10,100,40])],['t'])
        self.assertEqual(assets[0]['sourceTextParts'],['t'])
        from engine import segment
        rgb=np.full((80,120,3),(20,40,55),np.uint8)
        rgb[14:36,14:96]=(240,230,210)
        parts=segment(rgb,assets,lambda *a:None,lambda:False)
        self.assertIn('flatColor',parts[0])
        self.assertFalse(parts[0].get('pendingGeneration'))

    def test_first_review_timeout_keeps_generated_asset_without_regenerating(self):
        from incremental_assets import extract_checked
        from engine import png
        source=Image.new('RGB',(40,30),'purple');full=Image.new('RGBA',(40,70));ImageDraw.Draw(full).rectangle((5,5,34,64),fill='orange')
        node=dict(id='complete',name='完整人物',type='image',x=0,y=0,width=40,height=30)
        generated={**node,'height':70,'src':png(full),'assetReviewStatus':'PASS','assetReviewChecks':[{'name':'stale','status':'PASS'}],'generationRecord':{'actualImageGeneration':True}}
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'source.png';source.save(path)
            with patch('workflow_assets.complete_asset',return_value=generated) as generate,patch('acceptance.review_asset',side_effect=RuntimeError('图片分析超时')):
                result=extract_checked(path,node,root,root,lambda:False,path,None)
        generate.assert_called_once()
        self.assertEqual(result['src'],png(full));self.assertEqual(result['height'],70)
        self.assertEqual(result['assetReviewStatus'],'NEEDS_REVIEW');self.assertEqual(result['assetReviewChecks'],[])
        self.assertTrue(result['generationRecord']['actualImageGeneration']);self.assertIn('图片分析超时',result['reviewIssue'])

    def test_retry_keeps_reviewed_candidate_when_new_pixels_regress_or_review_fails(self):
        import copy
        from incremental_assets import extract_checked
        from acceptance import ASSET_CRITERIA
        raw=io.BytesIO();Image.new('RGBA',(20,20),'red').save(raw,'PNG')
        node=dict(id='keep',name='角色',type='image',x=0,y=0,width=20,height=20,src='data:image/png;base64,'+base64.b64encode(raw.getvalue()).decode())
        first={**node,'marker':'first'};second={**node,'marker':'second'}
        quality=dict(status='FAIL',issues=['颜色偏差'],checks=[dict(name=n,status='FAIL' if n=='颜色与光照' else 'PASS',notes='实际观察') for n in ASSET_CRITERIA])
        worse=copy.deepcopy(quality);worse['checks'][0]['status']='FAIL'
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.png';Image.new('RGB',(20,20),'red').save(source)
            for next_review in (worse,ValueError('复核无效')):
                with patch('workflow_assets.complete_asset',side_effect=[copy.deepcopy(first),copy.deepcopy(second)]),patch('acceptance.review_asset',side_effect=[copy.deepcopy(quality),next_review]):
                    result=extract_checked(source,node,root,root,lambda:False,source,None)
                self.assertEqual(result['marker'],'first');self.assertEqual(result['assetReviewChecks'],quality['checks'])
                self.assertEqual(len(result['assetReviewAttempts']),2)

    def test_selected_regeneration_does_not_replace_a_better_existing_layer(self):
        import copy
        from acceptance import ASSET_CRITERIA
        from selected_refine import _process
        raw=io.BytesIO();Image.new('RGB',(20,20),'red').save(raw,'PNG');src='data:image/png;base64,'+base64.b64encode(raw.getvalue()).decode()
        node=dict(id='old',name='角色',type='image',x=0,y=0,width=20,height=20,src=src,marker='original')
        scene=dict(format='shijie-scene',version=2,width=20,height=20,source=src,nodes=[node],groups=[],edges=[])
        quality=dict(status='FAIL',issues=['颜色偏差'],placement=None,checks=[dict(name=n,status='FAIL' if n=='颜色与光照' else 'PASS',notes='实际观察') for n in ASSET_CRITERIA])
        bad=copy.deepcopy(node);bad.update(marker='worse',assetReviewStatus='NEEDS_REVIEW',assetReviewChecks=copy.deepcopy(quality['checks']));bad['assetReviewChecks'][0]['status']='FAIL'
        with tempfile.TemporaryDirectory() as home,patch('acceptance.review_asset',return_value=quality),patch('incremental_assets.extract_checked',return_value=bad):
            result=_process(src,'检查',lambda *a:None,lambda:False,src,home,scene,['old'])
        self.assertEqual(result['nodes'][0]['marker'],'original')
        self.assertEqual(result['nodes'][0]['assetReviewChecks'],quality['checks'])
        self.assertEqual(result['recognition']['selectedRefine']['changedIds'],[])

    def test_failed_regeneration_cannot_inherit_old_pass_or_generation_proof(self):
        from incremental_assets import extract_checked
        node=dict(id='kept',name='角色',type='image',x=0,y=0,width=20,height=20,
                  assetReviewStatus='PASS',generationRecord={'actualImageGeneration':True})
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.png';Image.new('RGB',(20,20),'red').save(source)
            with patch('workflow_assets.complete_asset',side_effect=ValueError('颜色校准证据不足')):
                result=extract_checked(source,node,root,root,lambda:False,source,None)
        self.assertEqual(result['assetReviewStatus'],'NEEDS_REVIEW')
        self.assertIn('颜色校准证据不足',result['reviewIssue'])
        self.assertFalse(result.get('generationRecord',{}).get('actualImageGeneration'))
        self.assertEqual(node['assetReviewStatus'],'PASS')

    def test_saved_audit_description_does_not_block_repair_but_external_images_do(self):
        from shijie.pipeline.validation import validate_resume
        raw=io.BytesIO();Image.new('RGB',(4,3)).save(raw,'PNG')
        src='data:image/png;base64,'+base64.b64encode(raw.getvalue()).decode()
        scene=dict(format='shijie-scene',version=2,width=4,height=3,source=src,nodes=[],
                   recognition={'qualityCalibration':{'source':'original image'}})
        self.assertEqual(validate_resume(scene)['recognition'],scene['recognition'])
        with self.assertRaises(ValueError):validate_resume({**scene,'source':'https://example.test/image.png'})
        with self.assertRaises(ValueError):validate_resume({**scene,'nodes':[dict(id='x',type='image',x=0,y=0,width=4,height=3,src='file:///etc/passwd')]})

    def test_new_extraction_expands_reference_and_reviews_the_actual_full_asset(self):
        from incremental_assets import extract_checked
        from acceptance import ASSET_CRITERIA
        source = Image.new('RGB', (120, 100), '#804090')
        ImageDraw.Draw(source).rectangle((40, 20, 79, 99), fill='#ded0a0')
        node = dict(id='new-person', name='角色', type='image', assetKind='person',
                    x=40, y=20, width=40, height=80, pendingGeneration=True)
        plan = dict(bounds=dict(x=40, y=20, width=40, height=140),
                    observed=[[40,20],[79,20],[79,99],[40,99]], exclusions=[],holes=[],
                    completionRequired=True, notes='人物腿脚被画布下边界截断，需要完整腿脚。')
        calls = []
        def analyze(prompt, images, schema, *args, **kwargs):
            if 'bounds' in schema['properties']:return plan
            calls.append('review')
            return dict(status='PASS', issues=[], placement=None,
                        checks=[dict(name=n, status='PASS', notes='实际深浅底完整且比例一致') for n in ASSET_CRITERIA])
        def generate(prompt, images, target, **kwargs):
            with Image.open(images[0]) as ref:
                self.assertGreater(ref.height, 140)
                self.assertEqual(ref.mode, 'RGBA')
            full = Image.new('RGBA', (60,160))
            ImageDraw.Draw(full).rectangle((10,10,49,149), fill='#ded0a0ff')
            full.save(target)
            return dict(file=str(target), actualImageGeneration=True, transparent=True)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); path=root/'original.png';source.save(path)
            with patch('codex_client.CLIENT.analyze', side_effect=analyze), patch('codex_client.CLIENT.generate', side_effect=generate):
                result=extract_checked(path,node,root,root,lambda:False,path,None)
        self.assertEqual(calls,['review'])
        self.assertEqual(result['assetReviewStatus'],'PASS')
        self.assertFalse(result.get('pendingGeneration'))
        self.assertGreater(result['y']+result['height'],140)
        self.assertTrue(result['completionPlan']['completionRequired'])
        self.assertEqual(node['height'],80)

    def test_cut_alpha_is_repaired_even_if_model_says_pass(self):
        from incremental_assets import extract_checked
        from acceptance import ASSET_CRITERIA
        source=Image.new('RGB',(100,100),'#804090')
        ImageDraw.Draw(source).rectangle((25,10,74,99),fill='#caba80')
        node=dict(id='cut',name='角色',type='image',assetKind='person',x=25,y=10,width=50,height=90)
        plan=dict(bounds=dict(x=25,y=10,width=50,height=140),observed=[[25,10],[74,10],[74,99],[25,99]],exclusions=[],holes=[],completionRequired=True,notes='腿脚被画布裁切，补齐完整实体。')
        generations=[]
        def generate(prompt, images, target, **kwargs):
            generations.append(prompt)
            im=Image.new('RGBA',(70,160));ImageDraw.Draw(im).rectangle((10,10,59,159 if len(generations)==1 else 149),fill='#caba80ff');im.save(target)
            return dict(file=str(target),actualImageGeneration=True,transparent=True)
        def analyze(prompt, images, schema, *args, **kwargs):
            if 'bounds' in schema['properties']:return plan
            return dict(status='PASS',issues=[],placement=None,checks=[dict(name=n,status='PASS',notes='已查看实际图层') for n in ASSET_CRITERIA])
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'source.png';source.save(path)
            with patch('codex_client.CLIENT.analyze',side_effect=analyze),patch('codex_client.CLIENT.generate',side_effect=generate):
                result=extract_checked(path,node,root,root,lambda:False,path,None)
        self.assertEqual(len(generations),2)
        self.assertEqual(result['assetReviewStatus'],'PASS')
        self.assertEqual(len(result['assetReviewAttempts']),2)
        self.assertEqual(result['assetReviewAttempts'][0]['status'],'FAIL')
        self.assertNotIn('_repairNotes',node)

    def test_invalid_completion_plan_cannot_expand_allocations_or_copy_foreign_pixels(self):
        from asset_completion import validate_plan
        plan=dict(bounds=dict(x=10,y=10,width=40,height=120),observed=[[10,10],[49,10],[49,99],[10,99]],exclusions=[],holes=[],completionRequired=True,notes='原图下方截断，补绘完整腿脚。')
        self.assertEqual(validate_plan(plan,(100,100))['bounds']['height'],120)
        for changed in [dict(bounds=dict(x=0,y=0,width=6000,height=6000)),
                        dict(observed=[[10,10],[100,10],[49,99]]), dict(completionRequired='yes')]:
            with self.assertRaises(ValueError):validate_plan({**plan,**changed},(100,100))


import copy,hashlib
from engine import png
import image_replace
class RemovalTests(SimpleTestCase):
 def fixture(self):
  im=Image.new('RGBA',(80,100));im.paste((100,150,80,255),(5,5,75,95));src=png(im)
  marks={'version':1,'width':80,'height':100,'sourceHash':hashlib.sha256(src.encode()).hexdigest(),'preserve':'右胳膊完整，补齐遮挡','items':[{'color':'#ffdf24','label':'左胳膊','purpose':'remove','strokes':[[[5,5],[35,10],[35,90],[5,5]]]},{'color':'#39d8ff','label':'右胳膊','purpose':'keep','strokes':[[[45,5],[75,10],[75,90],[45,5]]]}]}
  scene={'format':'shijie-scene','version':2,'width':80,'height':100,'title':'测试手臂','provenance':'user-image','source':src,'comparisonSource':src,'originalSource':src,'nodes':[{'id':'raw','name':'原图','type':'image','src':src,'x':0,'y':0,'width':80,'height':100,'locked':True,'provenance':'imported-source'}],'groups':[],'edges':[],'_sourceAnnotations':marks}
  request={'targetId':'raw','task':'remove','annotations':marks,'prompt':'删除左胳膊，保留右胳膊完整'}
  return scene,request
 def test_validated_semantic_removal_sends_clean_and_separate_aligned_guide(self):
  scene,request=self.fixture();before=copy.deepcopy(scene)
  def generate(prompt,images,target,**kw):
   self.assertEqual(len(images),2);self.assertFalse(kw['allow_identity_change']);self.assertTrue(kw['transparent']);self.assertIn('remove',prompt);self.assertIn('右胳膊完整',prompt);self.assertIn('不是硬裁剪蒙版',prompt)
   with Image.open(images[0]) as clean,Image.open(images[1]) as guide:self.assertEqual(clean.size,guide.size);self.assertNotEqual(clean.tobytes(),guide.tobytes())
   im=Image.new('RGBA',(100,100));im.paste((100,150,80,255),(55,5,85,95));im.save(target);return {'actualImageGeneration':True}
  with tempfile.TemporaryDirectory() as folder,patch('image_provider.CLIENT.generate',side_effect=generate):result=image_replace._process(scene['source'],'测试',lambda *_:None,lambda:False,scene['source'],Path(folder),scene,request)
  self.assertEqual(scene,before);self.assertNotEqual(result['nodes'][0]['src'],scene['source']);self.assertEqual(result['nodes'][0]['width'],80)
 def test_rejects_missing_delete_wrong_source_and_hard_region(self):
  scene,request=self.fixture()
  for mutate in ('missing','keep','hash','region'):
   value=copy.deepcopy(request)
   if mutate=='missing':value.pop('annotations')
   if mutate=='keep':value['annotations']['items'][0]['purpose']='keep'
   if mutate=='hash':value['annotations']['sourceHash']='0'*64
   if mutate=='region':value['region']={'x':0,'y':0,'width':20,'height':20}
   with self.subTest(mutate=mutate),self.assertRaises(ValueError):image_replace.validate_replacement(scene,value)
 def test_rejects_fake_transparency_without_mutating_source(self):
  scene,request=self.fixture();before=copy.deepcopy(scene)
  def generate(prompt,images,target,**kw):Image.new('RGB',(100,100),'white').save(target);return {'actualImageGeneration':True}
  with tempfile.TemporaryDirectory() as folder,patch('image_provider.CLIENT.generate',side_effect=generate),self.assertRaisesRegex(ValueError,'透明通道'):image_replace._process(scene['source'],'测试',lambda *_:None,lambda:False,scene['source'],Path(folder),scene,request)
  self.assertEqual(scene,before)

 def test_transparent_padding_cannot_hide_an_opaque_final_crop(self):
  scene,request=self.fixture()
  def generate(prompt,images,target,**kw):
   im=Image.new('RGBA',(100,100));im.paste((80,120,160,255),(10,0,90,100));im.save(target);return {'actualImageGeneration':True}
  with tempfile.TemporaryDirectory() as folder,patch('image_provider.CLIENT.generate',side_effect=generate),self.assertRaisesRegex(ValueError,'实际内容区'):image_replace._process(scene['source'],'测试',lambda *_:None,lambda:False,scene['source'],Path(folder),scene,request)

 def test_expanded_removal_preserves_scale_and_returns_new_geometry(self):
  scene,request=self.fixture();request['annotations']['allowExpand']=True
  def generate(prompt,images,target,**kw):
   self.assertIn('禁止缩小主体',prompt);self.assertTrue(kw['transparent'])
   im=Image.new('RGBA',(150,150));im.paste((100,150,80,255),(25,10,125,140));im.save(target);return {'actualImageGeneration':True}
  with tempfile.TemporaryDirectory() as folder,patch('image_provider.CLIENT.generate',side_effect=generate):result=image_replace._process(scene['source'],'测试',lambda *_:None,lambda:False,scene['source'],Path(folder),scene,request)
  n=result['nodes'][0];self.assertEqual((n['x'],n['y'],n['width'],n['height']),(-20,-25,120,150));self.assertEqual(n['imageReplacement']['expansion']['inputWidth'],80)
 def test_layer_annotations_are_bound_to_selected_source_not_whole_scene(self):
  scene,request=self.fixture();scene['nodes'][0].update(x=200,y=300,width=40,height=50,locked=False)
  self.assertEqual(image_replace.validate_replacement(scene,request)['annotations']['sourceHash'],request['annotations']['sourceHash'])

 def test_expanded_content_in_aspect_padding_is_not_silently_cropped(self):
  scene,request=self.fixture();request['annotations']['allowExpand']=True
  def generate(prompt,images,target,**kw):
   im=Image.new('RGBA',(150,150));im.paste((100,150,80,255),(25,10,125,140));im.paste((100,150,80,255),(1,1,5,5));im.save(target);return {'actualImageGeneration':True}
  with tempfile.TemporaryDirectory() as folder,patch('image_provider.CLIENT.generate',side_effect=generate):result=image_replace._process(scene['source'],'测试',lambda *_:None,lambda:False,scene['source'],Path(folder),scene,request)
  self.assertEqual((result['nodes'][0]['x'],result['nodes'][0]['width']),(-35,150))

 def test_background_removal_keeps_opaque_frame_inside_expanded_canvas(self):
  scene,request=self.fixture();im=Image.new('RGBA',(80,100),(12,34,56,0));im.paste((80,120,160,255),(10,10,70,90));src=png(im)
  scene.update(source=src,comparisonSource=src,originalSource=png(Image.new('RGB',(60,80),(80,120,160))));scene['nodes'][0]['src']=src
  request['annotations']['sourceHash']=hashlib.sha256(src.encode()).hexdigest();request['annotations']['allowExpand']=True
  def generate(prompt,images,target,**kw):
   self.assertFalse(kw['transparent']);self.assertNotIn('禁止涂背景',prompt);self.assertIn('天空',prompt)
   im=Image.new('RGB',(100,100),(80,120,160));im.save(target);return {'actualImageGeneration':True}
  with tempfile.TemporaryDirectory() as folder,patch('image_provider.CLIENT.generate',side_effect=generate):result=image_replace._process(src,'测试',lambda *_:None,lambda:False,scene['originalSource'],Path(folder),scene,request)
  self.assertEqual((result['nodes'][0]['x'],result['nodes'][0]['width']),(0,80))
  actual=image_replace._image(result['nodes'][0]['src']);self.assertEqual(actual.getchannel('A').getbbox(),(10,10,70,90));self.assertEqual(actual.getpixel((0,0)),(12,34,56,0))

 def test_full_background_can_touch_all_edges_with_default_expand(self):
  scene,request=self.fixture();src=png(Image.new('RGB',(80,100),(80,120,160)))
  scene.update(source=src,comparisonSource=src,originalSource=src);scene['nodes'][0]['src']=src
  request['annotations']['sourceHash']=hashlib.sha256(src.encode()).hexdigest();request['annotations']['allowExpand']=True
  def generate(prompt,images,target,**kw):
   self.assertFalse(kw['transparent']);Image.new('RGB',(100,100),(80,120,160)).save(target);return {'actualImageGeneration':True}
  with tempfile.TemporaryDirectory() as folder,patch('image_provider.CLIENT.generate',side_effect=generate):result=image_replace._process(src,'测试',lambda *_:None,lambda:False,scene['originalSource'],Path(folder),scene,request)
  self.assertEqual(image_replace._image(result['nodes'][0]['src']).getchannel('A').getextrema(),(255,255))
  self.assertEqual(result['nodes'][0]['width'],80)

 def test_background_alpha_failure_is_not_flattened_to_fake_success(self):
  scene,request=self.fixture();src=png(Image.new('RGB',(80,100),(80,120,160)))
  scene.update(source=src,comparisonSource=src,originalSource=src);scene['nodes'][0]['src']=src
  request['annotations']['sourceHash']=hashlib.sha256(src.encode()).hexdigest()
  def generate(prompt,images,target,**kw):
   im=Image.new('RGBA',(100,100),(80,120,160,255));im.putpixel((50,50),(0,0,0,0));im.save(target);return {'actualImageGeneration':True}
  with tempfile.TemporaryDirectory() as folder,patch('image_provider.CLIENT.generate',side_effect=generate),self.assertRaisesRegex(ValueError,'不透明背景'):image_replace._process(src,'测试',lambda *_:None,lambda:False,src,Path(folder),scene,request)

 def test_expanded_edge_alpha_is_preserved_as_reviewable_candidate(self):
  for edge_alpha in (1,255):
   scene,request=self.fixture();request['annotations']['allowExpand']=True
   def generate(prompt,images,target,**kw):
    im=Image.new('RGBA',(150,150));im.paste((100,150,80,255),(25,10,125,140));im.putpixel((0,0),(20,30,40,edge_alpha));im.save(target);return {'actualImageGeneration':True}
   with self.subTest(alpha=edge_alpha),tempfile.TemporaryDirectory() as folder,patch('image_provider.CLIENT.generate',side_effect=generate):result=image_replace._process(scene['source'],'测试',lambda *_:None,lambda:False,scene['source'],Path(folder),scene,request)
   n=result['nodes'][0];self.assertEqual(image_replace._image(n['src']).getpixel((0,0)),(20,30,40,edge_alpha));self.assertTrue(n['review']);self.assertTrue(n['imageReplacement']['boundaryRisk'])
