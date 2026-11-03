import base64
import io
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from django.test import SimpleTestCase

from source_fidelity import restore_visible, reapply_calibration, contour_mask, matte_against_background


class SourceFidelity(SimpleTestCase):
    def test_source_restoration_does_not_bake_background_into_translucent_pixels(self):
        base=Image.new('RGBA',(60,60),(180,120,50,255));d=ImageDraw.Draw(base)
        for x,alpha in [(10,64),(25,160),(40,240)]:d.rectangle((x,15,x+9,44),fill=(90,150,190,alpha))
        backdrop=Image.new('RGBA',base.size,'#503070');ImageDraw.Draw(backdrop).rectangle((15,0,34,59),fill='#25a040')
        observed=Image.alpha_composite(backdrop,base).convert('RGB')
        raw=io.BytesIO();base.save(raw,'PNG');node=dict(x=0,y=0,width=60,height=60,src='data:image/png;base64,'+base64.b64encode(raw.getvalue()).decode())
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.png';observed.save(source)
            for match_color in (False,True):
                with self.subTest(match_color=match_color):
                    result=restore_visible(source,node,[[0,0],[59,0],[59,59],[0,59]],radius=0,preserve_outline=True,match_color=match_color)
                    im=Image.open(io.BytesIO(base64.b64decode(result['src'].split(',')[1])))
                    for x,alpha in [(12,64),(27,160),(42,240)]:self.assertEqual(im.getpixel((x,30)),(90,150,190,alpha))
                    self.assertEqual(im.getpixel((5,30)),(180,120,50,255))
                    self.assertEqual(im.getchannel('A').tobytes(),base.getchannel('A').tobytes())

    def test_dense_ink_uses_pending_image_without_blocking_other_layers(self):
        from engine import build_scene,png
        from incremental_assets import pending_generation
        rgb=np.full((256,384,3),255,np.uint8);rgb[16:238:3,16:238:3]=(180,40,20);rgb[40:90,310:350]=(180,40,20)
        plan=dict(assets=[dict(id='dense',name='密集纹理字标',kind='logo',box=dict(left=8,top=8,right=248,bottom=248),z_index=1),
                          dict(id='simple',name='简单标记',kind='logo',box=dict(left=300,top=30,right=360,bottom=100),z_index=2)],
                  texts=[],art_text_ids=[],vectors=[],groups=[],warnings=[])
        scene=build_scene(png(Image.fromarray(rgb)),'test',plan,lambda *args:None,lambda:False)
        by_source={n.get('sourceAssetId'):n for n in scene['nodes']}
        dense,simple=by_source['dense'],by_source['simple']
        self.assertEqual(dense['type'],'image');self.assertTrue(pending_generation(dense));self.assertTrue(dense['review'])
        self.assertNotEqual(dense.get('assetReviewStatus'),'PASS');self.assertEqual(dense['sourceEntityId'],'dense')
        self.assertEqual(simple['type'],'path');self.assertFalse(pending_generation(simple))
        self.assertEqual(len(scene['nodes']),3)

    def test_fractional_alignment_does_not_mix_transparent_black_into_edges(self):
        base=Image.new('RGBA',(20,20));ImageDraw.Draw(base).rectangle((5,5,14,14),fill=(220,140,50,255));raw=io.BytesIO();base.save(raw,'PNG')
        node=dict(id='edge',x=.5,y=.5,width=20,height=20,src='data:image/png;base64,'+base64.b64encode(raw.getvalue()).decode())
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.png';Image.new('RGB',(24,24),(220,140,50)).save(source)
            result=restore_visible(source,node,[[8,8],[12,8],[12,12],[8,12]],radius=0,preserve_outline=True)
        im=Image.open(io.BytesIO(base64.b64decode(result['src'].split(',')[1])))
        self.assertGreater(im.getpixel((5,10))[3],80);self.assertLess(im.getpixel((5,10))[3],180)
        for actual,expected in zip(im.getpixel((5,10))[:3],(220,140,50)):self.assertAlmostEqual(actual,expected,delta=2)

    def test_occlusion_boundary_uncertainty_does_not_discard_observed_pixels(self):
        source=Image.new('RGB',(80,80),'#804090');ImageDraw.Draw(source).rectangle((10,10,69,69),fill='#d0a040')
        def node(hole):
            im=Image.new('RGBA',(80,80),'#d0a040ff');ImageDraw.Draw(im).rectangle(hole,fill=(0,0,0,0));raw=io.BytesIO();im.save(raw,'PNG')
            return dict(id='body',x=0,y=0,width=80,height=80,src='data:image/png;base64,'+base64.b64encode(raw.getvalue()).decode())
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source.png';source.save(path)
            kwargs=dict(exclusions=[[[10,50],[69,50],[69,69],[10,69]]],radius=0,preserve_outline=True)
            result=restore_visible(path,node((10,50,10,69)),[[10,10],[69,10],[69,69],[10,69]],**kwargs)
            self.assertTrue(result['sourceFidelity']['hiddenCompletion'])
            with self.assertRaisesRegex(ValueError,'遮挡区域缺少'):
                restore_visible(path,node((35,55,45,65)),[[10,10],[69,10],[69,69],[10,69]],**kwargs)

    def test_automatic_outline_recovers_soft_alpha_without_background_fringe(self):
        source=Image.new('RGB',(80,60),(130,60,170));draw=ImageDraw.Draw(source)
        draw.rectangle((20,15,59,44),fill=(210,150,110))
        draw.line((20,16,20,43),fill=(170,105,140))
        raw=io.BytesIO();Image.new('RGBA',(80,60),(210,150,110,255)).save(raw,'PNG')
        node=dict(id='soft',x=0,y=0,width=80,height=60,src='data:image/png;base64,'+base64.b64encode(raw.getvalue()).decode())
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source.png';source.save(path)
            result=restore_visible(path,node,[[20,15],[59,15],[59,44],[20,44]],radius=0,
                                   preserve_outline=True,lock_observed_outline=True,matte_edges=True)
        pixel=Image.open(io.BytesIO(base64.b64decode(result['src'].split(',')[1]))).getpixel((20,30))
        self.assertAlmostEqual(pixel[3],128,delta=4)
        for actual,expected in zip(pixel[:3],(210,150,110)):self.assertAlmostEqual(actual,expected,delta=4)

    def test_approximate_occlusion_boundary_does_not_cut_a_transparent_seam(self):
        source=Image.new('RGB',(80,80),'#804090')
        ImageDraw.Draw(source).polygon([(10,10),(70,10),(70,55),(10,40)],fill='#d0a040')
        base=Image.new('RGBA',(80,100),'#d0a040ff');raw=io.BytesIO();base.save(raw,'PNG')
        node=dict(id='body',x=0,y=0,width=80,height=100,src='data:image/png;base64,'+base64.b64encode(raw.getvalue()).decode())
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source.png';source.save(path)
            result=restore_visible(path,node,[[10,10],[70,10],[70,55],[10,40]],radius=0,
                                   exclusions=[[[10,43],[70,58],[70,79],[10,79]]],
                                   preserve_outline=True,lock_observed_outline=True)
        image=Image.open(io.BytesIO(base64.b64decode(result['src'].split(',')[1])))
        self.assertEqual(image.getpixel((20,44))[3],255)

    def test_source_canvas_boundary_is_feathered_into_off_canvas_completion(self):
        original=Image.new('RGB',(60,50),(120,140,160));raw=io.BytesIO()
        Image.new('RGBA',(80,70),(100,120,140,255)).save(raw,'PNG')
        node=dict(id='table',x=0,y=0,width=80,height=70,src='data:image/png;base64,'+base64.b64encode(raw.getvalue()).decode())
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.png';original.save(source)
            result=restore_visible(source,node,[[0,0],[59,0],[59,49],[0,49]],radius=0,preserve_outline=True,feather=6)
        image=Image.open(io.BytesIO(base64.b64decode(result['src'].split(',')[1])))
        self.assertEqual(image.getpixel((30,25))[0],120)
        self.assertLess(image.getpixel((59,25))[0],110)
        self.assertEqual(image.getpixel((65,25))[0],100)

    def test_isolated_antialias_pixels_do_not_become_opaque_ink_layers(self):
        from engine import flat_ink_parts
        rgb=np.full((40,80,3),(10,40,55),np.uint8);mask=np.zeros((40,80),np.uint8)
        rgb[10:30,10:40]=(127,244,247);mask[10:30,10:40]=255
        # A fractional edge fragment is on the background-to-ink colour line,
        # with a small local-background variation, and has no solid interior.
        rgb[10,45]=(29,91,103);mask[10,45]=255
        self.assertEqual(len(flat_ink_parts(rgb,mask)),1)
        rgb[20:22,50:52]=(190,70,50);mask[20:22,50:52]=255
        parts=flat_ink_parts(rgb,mask);self.assertEqual(len(parts),2)
        self.assertTrue(any(m[20,50] and tuple(c)==(190,70,50) for m,c in parts))

    def test_smooth_title_fill_stays_one_gradient_not_banded_colour_pieces(self):
        from engine import segment
        rgb=np.full((80,140,3),(20,40,55),np.uint8)
        for y in range(10,70):rgb[y,10:130]=np.rint(np.array([250,245,230])+(y-10)/59*np.array([-28,-30,-36])).astype(np.uint8)
        rgb[25:55,50:70]=(20,40,55)
        result=segment(rgb,[dict(id='title',name='标题',kind='logo',box=[10,10,130,70])],lambda *a:None,lambda:False)
        self.assertEqual(len(result),1)
        gradient=result[0]['observedGradient']
        self.assertEqual(gradient['kind'],'linear')
        self.assertAlmostEqual(gradient['angle'],-90,delta=1)
        self.assertEqual(result[0]['mask'][40,60],0)
        self.assertEqual(result[0]['mask'][40,30],255)

    def test_holes_remain_transparent_while_occluded_material_is_completed(self):
        source=Image.new('RGB',(80,80),'#d0a040')
        ImageDraw.Draw(source).rectangle((30,30,45,45),fill='#804090')
        base=Image.new('RGBA',(80,80),'#d0a040ff')
        ImageDraw.Draw(base).rectangle((30,30,45,45),fill=(0,0,0,0))
        raw=io.BytesIO();base.save(raw,'PNG')
        node=dict(id='body',x=0,y=0,width=80,height=80,src='data:image/png;base64,'+base64.b64encode(raw.getvalue()).decode())
        with tempfile.TemporaryDirectory() as folder:
            original=Path(folder)/'source.png';source.save(original)
            result=restore_visible(original,node,[[5,5],[74,5],[74,74],[5,74]],radius=0,
                                   holes=[[[30,30],[45,30],[45,45],[30,45]]],
                                   exclusions=[[[60,20],[70,20],[70,60],[60,60]]],
                                   preserve_outline=True,lock_observed_outline=True)
        pixels=Image.open(io.BytesIO(base64.b64decode(result['src'].split(',')[1])))
        self.assertEqual(pixels.getpixel((35,35))[3],0)
        self.assertEqual(pixels.getpixel((65,35))[3],255)

    def test_observed_outline_lock_keeps_source_edges_and_unseen_lower_completion(self):
        source=Image.new('RGB',(100,80),'#804090');draw=ImageDraw.Draw(source)
        draw.polygon([(30,10),(65,10),(75,49),(25,49)],fill='#d0a040')
        base=Image.new('RGBA',(80,110));ImageDraw.Draw(base).rectangle((5,5,74,104),fill='#b0a050ff')
        raw=io.BytesIO();base.save(raw,'PNG')
        node=dict(id='body',x=10,y=0,width=80,height=110,src='data:image/png;base64,'+base64.b64encode(raw.getvalue()).decode())
        with tempfile.TemporaryDirectory() as folder:
            original=Path(folder)/'source.png';source.save(original)
            result=restore_visible(original,node,[[30,10],[65,10],[75,49],[25,49]],radius=0,
                                   preserve_outline=True,lock_observed_outline=True)
        image=Image.open(io.BytesIO(base64.b64decode(result['src'].split(',')[1])))
        self.assertEqual(image.getpixel((26-result['x'],12-result['y']))[3],0)
        self.assertEqual(image.getpixel((40-result['x'],25-result['y'])),(208,160,64,255))
        self.assertEqual(image.getpixel((40-result['x'],95-result['y']))[3],255)
        self.assertTrue(result['sourceFidelity']['lockObservedOutline'])

    def test_surface_restoration_feathers_the_known_to_inferred_join(self):
        source=Image.new('RGB',(160,160),(220,150,80));ImageDraw.Draw(source).rectangle((0,100,159,159),fill='blue')
        donor=Image.new('RGBA',(160,160),(180,120,70,255));raw=io.BytesIO();donor.save(raw,'PNG')
        node=dict(x=0,y=0,width=160,height=160,src='data:image/png;base64,'+base64.b64encode(raw.getvalue()).decode())
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source.png';source.save(path)
            result=restore_visible(path,node,[[0,0],[159,0],[159,159],[0,159]],exclusions=[[[0,100],[159,100],[159,159],[0,159]]],radius=0,preserve_outline=True,feather=4,occlusion_feather=48)
        im=Image.open(io.BytesIO(base64.b64decode(result['src'].split(',')[1])))
        self.assertEqual(im.getpixel((80,40)),(220,150,80,255))
        self.assertLess(abs(im.getpixel((80,99))[0]-im.getpixel((80,100))[0]),3)
        self.assertEqual(im.getpixel((80,120)),(180,120,70,255))
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source.png';source.crop((0,0,160,100)).save(path)
            result=restore_visible(path,node,[[0,0],[159,0],[159,99],[0,99]],radius=0,preserve_outline=True,feather=4,occlusion_feather=48)
        im=Image.open(io.BytesIO(base64.b64decode(result['src'].split(',')[1])))
        self.assertLess(abs(im.getpixel((80,99))[0]-im.getpixel((80,100))[0]),3)

    def test_flat_ink_tracing_keeps_source_subpixel_edges(self):
        from engine import observed_ink_alpha
        large=Image.new('L',(320,240));ImageDraw.Draw(large).polygon([(28,20),(294,20),(246,216),(12,216)],fill=255)
        alpha=np.asarray(large.resize((80,60),Image.Resampling.LANCZOS))
        bg=np.full((60,80,3),(20,45,60),float);fg=np.full_like(bg,(245,235,215))
        source=np.rint(bg*(1-alpha[:,:,None]/255)+fg*(alpha[:,:,None]/255)).astype('uint8')
        binary=(alpha>100).astype('uint8')*255
        recovered=observed_ink_alpha(source,bg,binary)
        self.assertLess(np.abs(recovered.astype(float)-alpha).mean(),1.5)
        self.assertGreater(np.count_nonzero((recovered>0)&(recovered<255)),100)
        self.assertEqual(int(recovered[0,0]),0)

    def test_ink_edge_highlights_do_not_become_transparent_notches(self):
        from engine import observed_ink_alpha
        bg=np.full((30,50,3),(10,50,68),float);source=bg.astype('uint8').copy()
        source[5:25,10:40]=(246,227,192)
        source[5:25,10]=(252,246,217)  # Actual cream title has a brighter rim.
        source[5:25,39]=(225,210,195)  # A shallow bevel is not a missing stroke.
        source[14,9]=(166,246,248)  # Neighboring cyan art must stay separate.
        ink=np.zeros((30,50),np.uint8);ink[5:25,10:40]=255;ink[14,9]=255
        recovered=observed_ink_alpha(source,bg,ink,np.array([246,227,192]))
        self.assertGreaterEqual(int(recovered[15,10]),250)
        self.assertGreater(int(recovered[15,39]),180)
        self.assertEqual(int(recovered[14,9]),0)

    def test_precise_vector_preserves_observed_letter_corners_and_counter(self):
        import json, subprocess
        from django.conf import settings
        from vector_trace import trace
        alpha=Image.new('L',(80,60));draw=ImageDraw.Draw(alpha)
        draw.polygon([(5,5),(70,5),(70,12),(28,12),(55,25),(70,40),(59,50),(28,36),(28,54),(5,54)],fill=255)
        draw.rectangle((12,18,18,26),fill=0)
        script="const{createCanvas,Path2D}=require('@napi-rs/canvas'),fs=require('fs'),c=createCanvas(80,60),x=c.getContext('2d');x.fillStyle='white';x.fill(new Path2D(JSON.parse(fs.readFileSync(0,'utf8'))));process.stdout.write(c.toBuffer('image/png'));"
        rendered=subprocess.run(['node','-e',script],input=json.dumps(trace(alpha,precise=True)).encode(),capture_output=True,check=True,cwd=settings.BASE_DIR,timeout=20)
        actual=np.asarray(Image.open(io.BytesIO(rendered.stdout)).getchannel('A'))
        self.assertEqual(actual[22,15],0)
        self.assertEqual(actual[15,69],0)
        # The previous spline simplification gives 4.21 on this angular glyph.
        self.assertLess(np.abs(actual.astype(float)-np.asarray(alpha)).mean(),3)

    def test_soft_edge_retains_blur_without_carrying_background_colour(self):
        background=np.full((8,12,3),(130,60,170),np.uint8)
        foreground=np.full((8,12,3),(210,150,110),np.uint8)
        observed=background.copy();observed[:,4:8]=(170,105,140);observed[:,8:]=foreground[:,8:]
        result=matte_against_background(observed,background,foreground)
        self.assertEqual(result[2,2,3],0)
        self.assertEqual(result[2,6,3],128)
        self.assertEqual(tuple(result[2,6,:3]),(210,150,110))
        self.assertEqual(result[2,10,3],255)
        alpha=result[:,:,3:4]/255
        reconstructed=result[:,:,:3]*alpha+background*(1-alpha)
        self.assertLessEqual(np.abs(reconstructed-observed).max(),1)
        with self.assertRaises(ValueError):matte_against_background(observed,background[:2],foreground)

    def test_visible_print_is_exact_and_occluded_area_keeps_completion(self):
        original = Image.new('RGB', (100, 80), '#8040b0')
        ImageDraw.Draw(original).rectangle((20, 20, 79, 59), fill='#f5e0d0')
        ImageDraw.Draw(original).rectangle((30, 30, 35, 45), fill='#c02020')
        ImageDraw.Draw(original).rectangle((60, 20, 79, 59), fill='#1030e0')
        generated = Image.new('RGBA', (70, 50), '#aaaaaaff')
        raw = io.BytesIO(); generated.save(raw, 'PNG')
        node = dict(id='card', name='card', type='image', x=15, y=15, width=70, height=50,
                    src='data:image/png;base64,' + base64.b64encode(raw.getvalue()).decode())
        before = dict(node)
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'source.png'; original.save(source)
            result = restore_visible(source, node, [[20, 20], [79, 20], [79, 59], [20, 59]],
                                     exclusions=[[[60, 20], [79, 20], [79, 59], [60, 59]]], radius=0)
        pixels = np.asarray(Image.open(io.BytesIO(base64.b64decode(result['src'].split(',')[1]))))
        x, y = int(result['x']), int(result['y'])
        self.assertEqual(tuple(pixels[35-y, 32-x]), (192, 32, 32, 255))
        self.assertEqual(tuple(pixels[35-y, 70-x]), (170, 170, 170, 255))
        self.assertEqual(pixels[16-y, 16-x, 3], 0)
        self.assertEqual(node, before)
        self.assertEqual(result['assetReviewStatus'], 'NOT_REVIEWED')
        self.assertEqual(result['sourceFidelity']['hiddenCompletion'], True)

    def test_repair_keeps_inspected_detail_and_rejects_a_different_original(self):
        from unittest.mock import patch
        from workflow_assets import complete_asset
        generated = Image.new('RGBA', (60, 40), '#aaaaff')
        raw = io.BytesIO(); generated.save(raw, 'PNG')
        node = dict(id='card', name='card', type='image', x=20, y=20, width=60, height=40,
                    src='data:image/png;base64,' + base64.b64encode(raw.getvalue()).decode())
        original = Image.new('RGB', (100, 80), '#8844bb')
        ImageDraw.Draw(original).rectangle((20, 20, 79, 59), fill='#eeeeee')
        ImageDraw.Draw(original).rectangle((40, 30, 45, 40), fill='#c02020')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root/'source.png'; original.save(source)
            calibrated = restore_visible(source, node, [[20,20],[79,20],[79,59],[20,59]], radius=0)
            assets = root/'assets'; structure = root/'structure'; assets.mkdir(); structure.mkdir()
            def generate(prompt, images, target, **kwargs):
                target.write_bytes(raw.getvalue())
                return dict(file=str(target), actualImageGeneration=True, transparent=True)
            with patch('workflow_assets.CLIENT.generate', side_effect=generate):
                result = complete_asset(source, calibrated, assets, structure, lambda:False, force_repair=True)
            pixels = Image.open(io.BytesIO(base64.b64decode(result['src'].split(',')[1])))
            self.assertEqual(pixels.getpixel((42-result['x'], 35-result['y'])), (192,32,32,255))
            import json, hashlib
            record = json.loads((structure/'补全_card.json').read_text())
            self.assertEqual(record['generatedAssetSHA256'], hashlib.sha256(base64.b64decode(result['src'].split(',')[1])).hexdigest())
            self.assertTrue(Path(record['generatedBaseFile']).is_file())
            Image.new('RGB', (100,80), 'white').save(source)
            with self.assertRaisesRegex(ValueError, '原图已变化'):
                reapply_calibration(source, calibrated, node)

    def test_contour_refines_edges_without_learning_the_background_as_foreground(self):
        rgb = np.zeros((100,150,3), np.uint8); rgb[:] = (70,130,50)
        rgb[30:70,30:120] = (235,220,210)
        rgb[38:55,40:48] = (190,25,25)
        rgb[40:46,126:132] = (235,220,210) # Nearby object with the same material.
        mask = contour_mask(rgb, [[27,27],[123,27],[123,73],[27,73]], 8)
        self.assertEqual(mask[40,44], 255)
        self.assertEqual(mask[72,80], 0)
        self.assertEqual(mask[32,115], 255)
        self.assertEqual(mask[42,128], 0)
        for polygon in ([], [[0,0],[1,1],[float('nan'),2]], [[0,0],[150,0],[1,2]]):
            with self.assertRaises(ValueError): contour_mask(rgb, polygon)

    def test_color_match_and_feather_never_import_an_occluder(self):
        original = Image.new('RGB',(100,80),(110,140,90))
        ImageDraw.Draw(original).rectangle((45,30,60,45),fill=(200,20,40))
        generated = Image.new('RGBA',(100,80),(100,150,100,255))
        raw=io.BytesIO(); generated.save(raw,'PNG')
        node=dict(id='table',x=0,y=0,width=100,height=80,src='data:image/png;base64,'+base64.b64encode(raw.getvalue()).decode())
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.png';original.save(source)
            result=restore_visible(source,node,[[5,5],[94,5],[94,74],[5,74]],exclusions=[[[45,30],[60,30],[60,45],[45,45]]],radius=0,preserve_outline=True,match_color=True,feather=4)
            image=Image.open(io.BytesIO(base64.b64decode(result['src'].split(',')[1])))
            self.assertEqual(image.getpixel((50,35)),(110,140,90,255))
            self.assertEqual(image.getpixel((20,20)),(110,140,90,255))

    def test_source_boundary_clipping_and_soft_edge_protection(self):
        original=Image.new('RGB',(60,50),'#decabc');raw=io.BytesIO()
        Image.new('RGBA',(80,60),'#aaaaff').save(raw,'PNG')
        node=dict(id='table',x=-10,y=-5,width=80,height=60,src='data:image/png;base64,'+base64.b64encode(raw.getvalue()).decode())
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.png';original.save(source)
            result=restore_visible(source,node,[[0,0],[59,0],[59,49],[0,49]],radius=0,preserve_outline=True,clip_to_source=True)
            self.assertEqual([result[k] for k in ('x','y','width','height')],[0,0,60,50])
            self.assertEqual(Image.open(io.BytesIO(base64.b64decode(result['src'].split(',')[1]))).size,(60,50))
            observed=restore_visible(source,node,[[0,0],[59,0],[59,49],[0,49]],radius=0)
            pixels=np.asarray(Image.open(io.BytesIO(base64.b64decode(observed['src'].split(',')[1]))))
            self.assertEqual(pixels[0,0,3],0) # Off-canvas generated content is not observed evidence.
            self.assertEqual(pixels[20,20,3],255)
            result['sourceFidelity']['softEdgeCalibration']={'method':'inspected matte'}
            with self.assertRaisesRegex(ValueError,'软边'):
                reapply_calibration(source,result,node)

