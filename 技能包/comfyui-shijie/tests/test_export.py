import sys, unittest, tempfile, json, subprocess
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from exporter import export_scene, _text_image
from unittest.mock import patch
import exporter


class ExportTests(unittest.TestCase):
    def test_native_text_preserves_glyph_aspect_in_wide_target_box(self):
        row={'text':'2024','box':[10,10,180,45],'color':[255,221,0]}
        rgba,native=_text_image(row,Path('C:/Windows/Fonts/arialbd.ttf'),200,80)
        self.assertAlmostEqual(native['transform'][0],native['transform'][3])
        alpha=rgba[...,3];ys,xs=np.where(alpha>0)
        self.assertLessEqual(int(xs.max()),179)
        self.assertLessEqual(int(ys.max()),44)

    def test_packaged_node_runtime_when_no_system_node(self):
        with patch('exporter.shutil.which',return_value=None),patch('exporter.importlib.util.find_spec',return_value=object()):
            command=exporter.node_command()
            self.assertEqual(command,[sys.executable,'-m','nodejs_wheel'])

    def test_native_text_baseline_matches_raster(self):
        from PIL import ImageFont
        font=Path('C:/Windows/Fonts/arial.ttf');row={'text':'2024','box':[10,10,90,40],'color':[0,0,90]}
        raster,native=_text_image(row,font,100,64)
        bbox=ImageFont.truetype(str(font),30).getbbox('2024',anchor='ls')
        sx,_,_,sy,tx,ty=native['transform']
        self.assertAlmostEqual(tx+bbox[0]*sx,10)
        self.assertAlmostEqual(ty+bbox[1]*sy,10)

    def test_native_tags_and_preview(self):
        bg=np.full((64,96,4),255,np.uint8)
        shape=np.zeros_like(bg);shape[5:40,5:40]=[12,30,90,255];shape[16:26,16:26]=0
        plan={'texts':[{'text':'2024','box':[42,10,94,30],'color':[0,0,90]}]}
        font=Path('C:/Windows/Fonts/arial.ttf')
        with tempfile.TemporaryDirectory() as temp:
            result=export_scene([bg,shape],plan,Path(temp),'原生层测试',font,True,False)
            code="""const fs=require('fs'),ag=require(process.argv[1]);ag.initializeCanvas(()=>{throw Error('Canvas forbidden in headless test')},(w,h)=>({width:w,height:h,data:new Uint8ClampedArray(w*h*4)}));const p=ag.readPsd(fs.readFileSync(process.argv[2]),{useImageData:true,useRawThumbnail:true});console.log(JSON.stringify({n:p.children.length,t:p.children.filter(l=>l.text).length,v:p.children.filter(l=>l.vectorFill&&l.vectorMask).length,thumb:!!p.imageResources.thumbnailRaw,pixel:Array.from(p.imageData.data.slice(0,4))}));"""
            data=json.loads(subprocess.check_output(['node','-e',code,str(ROOT/'vendor/node_modules/ag-psd'),str(result['psd'])],text=True))
            self.assertEqual(data['n'],3);self.assertEqual(data['t'],1);self.assertEqual(data['v'],2)
            self.assertTrue(data['thumb']);self.assertEqual(data['pixel'],[255,255,255,255])
            result2=export_scene([bg],{'texts':[]},Path(temp),'原生层测试',font,False,False)
            self.assertNotEqual(result['psd'],result2['psd'])

    def test_prepared_text_branch_stays_native_without_second_ocr_overlay(self):
        bg=np.full((64,96,4),255,np.uint8)
        rgba,native=_text_image({'text':'2024','box':[10,10,90,40],'color':[0,0,90]},Path('C:/Windows/Fonts/arialbd.ttf'),96,64)
        prepared=[{'kind':'text','name':'年份','rgba':rgba,'text':native}]
        with tempfile.TemporaryDirectory() as temp:
            result=export_scene([bg],{'texts':[]},Path(temp),'三路重组测试',None,False,False,None,prepared)
            self.assertEqual(result['text_layers'],1)
            self.assertEqual(result['layers'],2)
            code="const fs=require('fs'),ag=require(process.argv[1]);ag.initializeCanvas(()=>{},(w,h)=>({width:w,height:h,data:new Uint8ClampedArray(w*h*4)}));const p=ag.readPsd(fs.readFileSync(process.argv[2]),{useImageData:true,useRawThumbnail:true});console.log(JSON.stringify(p.children.map(l=>({n:l.name,t:l.text?.text}))));"
            layers=json.loads(subprocess.check_output(['node','-e',code,str(ROOT/'vendor/node_modules/ag-psd'),result['psd']],text=True,encoding='utf8'))
            self.assertEqual(len(layers),2);self.assertEqual(layers[1]['t'],'2024')

    def test_compact_pixels_and_shape_roundtrip_keep_absolute_placement(self):
        from spatial import compact_asset
        bg=np.full((80,120,4),255,np.uint8)
        rgba=np.zeros_like(bg);rgba[24:37,71:89]=[12,30,90,255]
        a=compact_asset(dict(kind='shape',name='小图标',rgba=rgba,color=[12,30,90],shapes=[{'d':'M71 24H89V37H71Z','operation':'combine'}]))
        with tempfile.TemporaryDirectory() as temp:
            result=export_scene([bg],{'texts':[]},Path(temp),'compact',None,False,False,None,[a])
            code="const fs=require('fs'),ag=require(process.argv[1]);ag.initializeCanvas(()=>{},(w,h)=>({width:w,height:h,data:new Uint8ClampedArray(w*h*4)}));const p=ag.readPsd(fs.readFileSync(process.argv[2]),{useImageData:true});const l=p.children[1];console.log(JSON.stringify({box:[l.left,l.top,l.right,l.bottom],size:[l.imageData.width,l.imageData.height],pixel:Array.from(p.imageData.data.slice((24*120+71)*4,(24*120+71)*4+4)),vector:!!l.vectorMask}));"
            d=json.loads(subprocess.check_output(['node','-e',code,str(ROOT/'vendor/node_modules/ag-psd'),result['psd']],text=True))
            self.assertEqual(d['box'],[71,24,89,37]);self.assertEqual(d['size'],[18,13]);self.assertEqual(d['pixel'],[12,30,90,255]);self.assertTrue(d['vector'])

    def test_missing_font_fails_before_output(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                export_scene([np.ones((16,16,4),np.uint8)],{'texts':[{'text':'x','box':[1,1,10,10]}]},Path(temp),'test',None,False,False)
            self.assertEqual(list(Path(temp).iterdir()),[])

if __name__=='__main__':unittest.main()
