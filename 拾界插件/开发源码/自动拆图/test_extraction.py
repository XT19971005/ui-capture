"""Regression for colour/material preservation using real extraction functions."""
import unittest
import numpy as np
import cv2
from engine import segment, text_nodes,logo_background

class ExtractionTests(unittest.TestCase):
 def test_disconnected_yellow_ink_is_not_flattened_to_white(self):
  rgb=np.full((100,200,3),[215,140,130],np.uint8)
  rgb[20:75,20:80]=255;rgb[40:60,100:120]=[245,220,40]
  result=segment(rgb,[{'id':'title','name':'Title','kind':'logo','box':[15,15,140,80]}],lambda *_:None,lambda:False)
  self.assertEqual(len(result),2)
  yellow=[r for r in result if r['flatColor'][2]<100]
  self.assertEqual(len(yellow),1)
  self.assertEqual(int(yellow[0]['mask'][50,110]),255)
  self.assertEqual(int(yellow[0]['mask'][30,30]),0)
 def test_red_flower_does_not_fill_white_center_with_red(self):
  rgb=np.full((100,100,3),[250,160,115],np.uint8)
  cv2.circle(rgb,(50,50),32,(250,20,40),-1);cv2.circle(rgb,(50,50),10,(255,255,255),-1)
  result=segment(rgb,[{'id':'flower','name':'Flower','kind':'logo','box':[16,16,84,84]}],lambda *_:None,lambda:False)
  red=[r for r in result if r['flatColor'][1]<80]
  self.assertEqual(len(red),1);self.assertEqual(int(red[0]['mask'][50,50]),0)
  self.assertTrue(any(r['mask'][50,50] for r in result))
 def test_gradient_detected_even_when_ocr_box_touches_glyph_edges(self):
  rgb=np.full((40,220,3),255,np.uint8)
  for x in range(10,210):
   if x%18<12:rgb[5:35,x]=[230-x*.4,110,80+x*.3]
  row={'id':'t','text':'TEST GRADIENT','confidence':.99,'bbox':[10,5,210,35],'quad':[[10,5],[210,5],[210,35],[10,35]]}
  nodes,_=text_nodes([row],rgb,set())
  self.assertIn('gradient',nodes[0]);self.assertEqual(nodes[0]['strokeWidth'],0)
 def test_neighbor_panel_does_not_pollute_title_background_fit(self):
  rgb=np.empty((140,220,3),np.uint8)
  for x in range(220):rgb[:,x]=[240-x*.2,145,115+x*.2]
  rgb[40:95,30:65]=255;rgb[110:140,10:210]=255
  result=segment(rgb,[{'id':'title','name':'Title','kind':'logo','box':[25,30,200,105]}],lambda *_:None,lambda:False)
  self.assertEqual(len(result),1)
  self.assertEqual(int(result[0]['mask'][60,100]),0)
  self.assertEqual(int(result[0]['mask'][60,40]),255)
 def test_lower_contrast_secondary_ink_keeps_full_interior(self):
  rgb=np.full((100,200,3),[245,160,120],np.uint8)
  rgb[20:75,20:80]=255;rgb[20:75,80:90]=[255,200,180];rgb[40:60,100:120]=[245,140,65]
  result=segment(rgb,[{'id':'title','name':'Title','kind':'logo','box':[15,15,140,80]}],lambda *_:None,lambda:False)
  orange=[r for r in result if r['flatColor'][2]<100]
  self.assertEqual(len(orange),1);self.assertEqual(int(orange[0]['mask'][50,110]),255)
 def test_white_panel_inside_loose_art_box_is_excluded_from_material_fit(self):
  rgb=np.empty((140,220,3),np.uint8)
  for x in range(220):rgb[:,x]=[240-x*.2,145,115+x*.2]
  rgb[40:95,30:65]=255;rgb[110:140,10:210]=255
  background=logo_background(rgb,(25,30,200,118))
  self.assertLess(np.linalg.norm(background[60,100]-[220,145,135]),12)
  rows=segment(rgb,[{'id':'title','name':'Title','kind':'logo','box':[25,30,200,118]}],lambda *_:None,lambda:False,exclude_boxes=[[10,110,210,140]])
  self.assertEqual(len(rows),1);self.assertEqual(int(rows[0]['mask'][115,100]),0)
 def test_geometry_registered_as_vector_is_not_also_extracted_as_bitmap(self):
  from engine import assets_without_native_duplicates
  assets=[{'id':'panel','kind':'panel','box':[10,20,110,60]},{'id':'person','kind':'person','box':[120,20,180,60]}]
  vectors=[{'type':'rect','x':10,'y':20,'width':100,'height':40}]
  self.assertEqual([a['id'] for a in assets_without_native_duplicates(assets,vectors)],['person'])
 def test_ocr_padding_does_not_turn_logo_into_retyped_ordinary_text(self):
  from engine import art_rows_for_assets
  rgb=np.full((100,220,3),[240,155,115],np.uint8);rgb[40:70,45:175]=255
  row={'id':'brand','text':'BRAND','bbox':[20,15,200,90],'quad':[[20,15],[200,15],[200,90],[20,90]]}
  assets=[{'id':'logo','kind':'logo','box':[40,35,180,75]}]
  self.assertEqual(art_rows_for_assets([row],rgb,assets),{'brand'})
 def test_art_box_keeps_existing_descender_outside_model_tight_box(self):
  from engine import expanded_logo_assets
  rgb=np.full((100,220,3),[240,155,115],np.uint8);rgb[30:60,35:145]=255;rgb[60:80,70:80]=255
  row={'id':'title','text':'Title','bbox':[20,20,160,85],'quad':[[20,20],[160,20],[160,85],[20,85]]}
  assets=[{'id':'logo','kind':'logo','box':[20,20,160,65]}]
  result=expanded_logo_assets([row],rgb,assets);self.assertGreaterEqual(result[0]['box'][3],80)

if __name__=='__main__':unittest.main()
