import copy
import unittest

from annotation_plan import native_node, NATIVE


class NativeFontContractTests(unittest.TestCase):
 def layer(self, family):
  return {'name':'03 系统时间','layerType':'text','box':{'x':0,'y':0,'width':70,'height':24},
          'native':{'text':'19:42','fontFamily':family,'fontSize':18,'fontWeight':400,'fill':'#ffffff'}}

 def test_placeholder_font_is_rejected_before_receiving_scene(self):
  for family in ('','待确认','未知字体','Unregistered Font'):
   with self.subTest(family=family), self.assertRaisesRegex(ValueError,'字体'):
    native_node(self.layer(family),'caption')

 def test_supported_font_keeps_review_and_input_unchanged(self):
  for family in ('Arial','Microsoft YaHei','Noto Sans CJK SC','Noto Serif CJK SC','Liberation Sans','Liberation Serif'):
   layer=self.layer(family);before=copy.deepcopy(layer)
   node=native_node(layer,'caption')
   self.assertEqual(node['fontFamily'],family)
   self.assertTrue(node['fontMatchApproximate'])
   self.assertTrue(node['review'])
   self.assertEqual(layer,before)

 def test_non_text_native_schema_keeps_empty_irrelevant_font_field(self):
  self.assertIn('',NATIVE['properties']['fontFamily']['enum'])
  self.assertEqual(native_node({'name':'平面底板','layerType':'rect','box':{'x':0,'y':0,'width':10,'height':10},'native':{'fill':'#ffffff','fontFamily':''}},'panel')['type'],'rect')
