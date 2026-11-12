import sys,unittest
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from branches import prepare_text, prepare_vectors, combine_branches, _ink_mask, _fit_font

class BranchTests(unittest.TestCase):
 def test_font_match_does_not_use_horizontal_stretch_to_claim_fit(self):
  path=Path('C:/Windows/Fonts/arialbd.ttf');f=ImageFont.truetype(str(path),30);box=f.getbbox('2024',anchor='ls')
  glyph=Image.new('L',(box[2]-box[0],box[3]-box[1]));ImageDraw.Draw(glyph).text((-box[0],-box[1]),'2024',font=f,anchor='ls',fill=255)
  target=np.asarray(glyph.resize((glyph.width*3,glyph.height),Image.Resampling.LANCZOS))>100
  score,_,_=_fit_font('2024',target,[path])
  self.assertLess(score,.65)

 def test_text_removed_before_image_model_and_native_separate(self):
  im=Image.new('RGB',(200,80),(140,240,240));ImageDraw.Draw(im).text((10,10),'2024',font=ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf',34),fill=(0,20,120))
  row={'text':'2024','box':[8,10,110,48],'color':[0,20,120]}
  clean,branch=prepare_text(np.array(im),{'texts':[row]},[Path('C:/Windows/Fonts/arial.ttf'),Path('C:/Windows/Fonts/arialbd.ttf')])
  self.assertEqual(len(branch['assets']),1);self.assertEqual(branch['assets'][0]['kind'],'text')
  self.assertGreater(clean[20:35,15:80,:3].mean(),np.array(im)[20:35,15:80,:3].mean())
  np.testing.assert_array_equal(clean[55:,:,:3],np.array(im)[55:])
  self.assertIn('Bold',branch['assets'][0]['text']['style']['font']['name'])
 def test_art_text_goes_only_to_vector_branch_and_holes_survive(self):
  im=np.full((80,100,3),240,np.uint8);im[10:60,10:60]=[0,20,120];im[25:45,25:45]=240
  plan={'texts':[{'text':'O','box':[8,8,62,62],'color':[0,20,120],'render_as':'vector'}]}
  clean,text=prepare_text(im,plan,[Path('C:/Windows/Fonts/arial.ttf')]);clean,vec=prepare_vectors(im,clean,plan)
  self.assertEqual(text['assets'],[]);self.assertEqual(len(vec['assets']),1);self.assertEqual(vec['assets'][0]['kind'],'shape')
  self.assertTrue(any(s['operation']=='subtract' for s in vec['assets'][0]['shapes']))
 def test_merge_rejects_misaligned_branch_not_silent_scale(self):
  with self.assertRaises(ValueError):combine_branches([np.zeros((20,20,4),np.uint8)],{'width':21,'height':20,'assets':[]},{'width':20,'height':20,'assets':[]})
 def test_soft_shadow_remains_bitmap(self):
  shadow=np.zeros((20,20,4),np.uint8);shadow[4:16,4:16]=[30,10,20,40]
  branch={'width':20,'height':20,'assets':[],'warnings':[]}
  result=combine_branches([shadow],branch,branch)
  self.assertEqual(result[0]['kind'],'bitmap');np.testing.assert_array_equal(result[0]['rgba'],shadow)
 def test_light_text_on_dark_does_not_extract_background(self):
  im=np.zeros((60,80,3),np.uint8);im[15:45,20:50]=255
  mask,box,_=_ink_mask(im,{'text':'I','box':[10,10,60,50],'color':[255,255,255]})
  self.assertEqual(int(mask[12,12]),0);self.assertEqual(int(mask[25,30]),255)
  clean,b=prepare_text(im,{'texts':[{'text':'I','box':[10,10,60,50],'color':[255,255,255]}]},[Path('C:/Windows/Fonts/arial.ttf')])
  self.assertTrue(b['assets']);a=b['assets'][0]['rgba']
  self.assertGreater(a[25,30,3],0);self.assertEqual(int(a[12,12,3]),0)
 def test_vector_gradient_is_preserved_as_bitmap(self):
  im=np.full((80,100,3),240,np.uint8)
  im[10:60,10:60]=np.arange(50,dtype=np.uint8)[None,:,None]+80
  plan={'texts':[],'vectors':[{'name':'渐变图形','box':[8,8,62,62],'color':[90,90,90]}]}
  clean,b=prepare_vectors(im,im.copy(),plan)
  self.assertEqual(b['assets'][0]['kind'],'bitmap')
  self.assertTrue(b['warnings'])
 def test_low_font_match_preserves_ink_not_wrong_native(self):
  im=np.full((60,100,3),240,np.uint8);im[20:40,20:80]=[0,20,120]
  clean,b=prepare_text(im,{'texts':[{'text':'XYZ','box':[18,18,82,42],'color':[0,20,120]}]},[Path('C:/Windows/Fonts/arial.ttf')])
  self.assertEqual(b['assets'][0]['kind'],'bitmap');self.assertTrue(b['warnings'])
 def test_declared_flat_art_ignores_antialias_at_edges_not_real_gradient(self):
  im=np.full((80,100,3),240,np.uint8);im[10:60,10:60]=[0,36,138];im[12,20:50]=[70,130,180]
  plan={'texts':[{'text':'艺术字','box':[8,8,62,62],'color':[0,36,138],'render_as':'vector'}]}
  _,b=prepare_vectors(im,im.copy(),plan)
  self.assertEqual(b['assets'][0]['kind'],'shape')
 def test_approximate_mode_does_not_accept_bad_font(self):
  im=np.full((60,100,3),240,np.uint8);im[20:40,20:80]=[0,20,120]
  _,b=prepare_text(im,{'texts':[{'text':'XYZ','box':[18,18,82,42],'color':[0,20,120]}]},[Path('C:/Windows/Fonts/arial.ttf')],allow_approximate=True)
  self.assertEqual(b['assets'][0]['kind'],'bitmap')
 def test_shallow_directional_gradient_is_not_flattened(self):
  im=np.full((80,100,3),240,np.uint8);im[10:60,10:60]=np.rint(np.linspace(0,20,50)).astype('uint8')[None,:,None]+80
  _,branch=prepare_vectors(im,im.copy(),{'texts':[],'vectors':[{'name':'浅渐变','box':[8,8,62,62],'color':[90,90,90]}]})
  self.assertEqual(branch['assets'][0]['kind'],'bitmap')
 def test_failed_font_bitmap_retains_all_erased_antialias_pixels(self):
  im=np.full((60,100,3),240,np.uint8);im[20:40,20:80]=[0,20,120];im[19,20:80]=[110,120,180]
  clean,branch=prepare_text(im,{'texts':[{'text':'XYZ','box':[18,18,82,42],'color':[0,20,120]}]},[Path('C:/Windows/Fonts/arial.ttf')])
  rgba=branch['assets'][0]['rgba'];changed=np.any(clean!=im,axis=2)
  self.assertTrue(np.all(rgba[changed,3]==255))
  np.testing.assert_array_equal(rgba[changed,:3],im[changed])
if __name__=='__main__':unittest.main()
