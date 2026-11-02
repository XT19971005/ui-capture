import unittest
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from engine import text_nodes

def row(text,box,ident='ordinary-role'):
 x,y,r,b=box
 return {'id':ident,'text':text,'bbox':list(box),'quad':[[x,y],[r,y],[r,b],[x,b]],'confidence':.97}

def fixture(text,vertical=True):
 image=Image.new('RGB',(360,500),'white');draw=ImageDraw.Draw(image)
 box=(318,297,343,467) if vertical else (20,30,330,65)
 font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',12 if vertical else 20)
 if vertical:
  for i,c in enumerate(text):draw.text((321,299+i*170/max(1,len(text))),c,font=font,fill='#222222')
 else:draw.text((22,30),text,font=font,fill='#222222')
 return np.array(image),row(text,box)

class VerticalPunctuationTests(unittest.TestCase):
 def assert_upright(self,nodes,text):
  self.assertEqual(len(nodes),1,'one continuous role column must remain one editable text')
  n=nodes[0]
  self.assertEqual(n['text'],'\n'.join(text),'punctuation and digits must be retained in the upright column')
  self.assertEqual(n['name'],text)
  self.assertNotEqual(n.get('rotation'),90)
  self.assertGreater(n['fontSize'],6,'a narrow upright column must not be fitted as a tiny horizontal sentence')
  self.assertIn('lineHeight',n)
  self.assertEqual(n['sourceTextId'],'ordinary-role')

 def test_actual_role_column_with_comma_and_original_slash_stays_upright(self):
  source=Path('C:/Users/tuyou/Desktop/五条人.jpg')
  if not source.is_file():self.skipTest('real narrow-column source unavailable')
  rgb=np.array(Image.open(source).convert('RGB'))
  for text in ('主唱、主音吉他、手风琴','主唱/主音吉他/手风琴'):
   with self.subTest(text=text):
    nodes,_=text_nodes([row(text,(318,216,343,386))],rgb,set())
    self.assert_upright(nodes,text)
    self.assertEqual(nodes[0]['sourceBox'],{'x0':318,'y0':216,'x1':343,'y1':386})

 def test_real_font_narrow_chinese_column_keeps_ascii_fullwidth_digits_and_spaces(self):
  for text in ('主唱/吉他2','主唱、吉他３','主唱 / 吉他2','主唱（吉他2）'):
   with self.subTest(text=text):
    rgb,r=fixture(text);nodes,_=text_nodes([r],rgb,set());self.assert_upright(nodes,text)

 def test_pure_english_and_number_columns_keep_existing_90_degree_layout(self):
  for text in ('VOCAL / GUITAR','2026/10'):
   with self.subTest(text=text):
    rgb,r=fixture(text);nodes,_=text_nodes([r],rgb,set())
    self.assertEqual(len(nodes),1);self.assertEqual(nodes[0]['text'],text)
    self.assertEqual(nodes[0]['rotation'],90)

 def test_horizontal_and_already_multiline_chinese_are_not_split_per_character(self):
  for text,vertical in [('主唱/吉他2',False),('主唱\n吉他2',True)]:
   with self.subTest(text=text):
    rgb,r=fixture(text,vertical);nodes,_=text_nodes([r],rgb,set())
    self.assertEqual(len(nodes),1);self.assertEqual(nodes[0]['text'],text)
    if '\n' in text:
     # An explicit sentence break needs leading, but must not be replaced by
     # the per-character leading of an inferred upright Chinese column.
     self.assertEqual(nodes[0]['text'].count('\n'),text.count('\n'))
     self.assertGreater(nodes[0]['lineHeight'],nodes[0]['fontSize'])
    else:self.assertNotIn('lineHeight',nodes[0])

 def test_latin_mixed_with_chinese_does_not_become_upright_character_stack(self):
  rgb,r=fixture('主唱VOCAL');nodes,_=text_nodes([r],rgb,set())
  self.assertEqual(len(nodes),1);self.assertEqual(nodes[0]['text'],'主唱VOCAL')
  self.assertNotIn('lineHeight',nodes[0])

 def test_accepted_art_text_is_not_reintroduced_as_editable_vertical_text(self):
  rgb,r=fixture('主唱/吉他2');nodes,_=text_nodes([r],rgb,{r['id']})
  self.assertEqual(nodes,[])

if __name__=='__main__':unittest.main()
