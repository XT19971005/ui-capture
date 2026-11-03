from django.test import SimpleTestCase
from PIL import ImageFont
from refine_ui import _fit_text


class RefineFonts(SimpleTestCase):
    def test_upright_fraction_does_not_inherit_slash_angle(self):
        import numpy as np
        from PIL import Image,ImageDraw
        from text_style import estimate
        from unittest.mock import patch
        for text in ('12 / 60','1 / 7'):
            font=ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf',32)
            box=font.getbbox(text);source=Image.new('RGB',(box[2]-box[0]+6,box[3]-box[1]+6),'#142039')
            ImageDraw.Draw(source).text((3-box[0],3-box[1]),text,font=font,fill='#f5e5c5')
            # A slash can dominate the line detector without making the glyphs italic.
            slash_lines=np.array([[[x+3,0,x,18]] for x in (12,20,28,36,44)],dtype=np.int32)
            with self.subTest(text=text),patch('text_style.cv2.HoughLinesP',return_value=slash_lines):
                result=estimate(np.array(source),text)
                self.assertIsNotNone(result);self.assertEqual(result['fontStyle'],'normal');self.assertEqual(result['textSkew'],0)

    def test_dark_heading_on_textured_gold_keeps_ink_polarity(self):
        import numpy as np
        from PIL import Image,ImageDraw
        from engine import text_nodes
        font=ImageFont.truetype('/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc',52)
        box=font.getbbox('装备');w,h=box[2]-box[0]+6,box[3]-box[1]+6
        yy,xx=np.indices((h,w));noise=np.random.default_rng(7).normal(0,24,(h,w,1))
        paper=np.array([220,174,92])+(1-yy/h)[:,:,None]*55+noise
        source=Image.fromarray(np.clip(paper,0,255).astype('uint8'))
        ImageDraw.Draw(source).text((3-box[0],3-box[1]),'装备',font=font,fill='#241301')
        row=dict(id='heading',text='装备',bbox=[0,0,w,h],quad=[[0,0],[w-1,0],[w-1,h-1],[0,h-1]],confidence=1)
        nodes,_=text_nodes([row],np.array(source),set());node=nodes[0]
        self.assertEqual(node['fontFamily'],'Noto Serif CJK SC')
        self.assertLess(max(int(node['fill'][i:i+2],16) for i in (1,3,5)),80)
        for _,color in node.get('gradient',{}).get('stops',[]):
            self.assertLess(max(int(color[i:i+2],16) for i in (1,3,5)),80)

    def test_chinese_serif_heading_is_not_replaced_by_sans(self):
        import numpy as np
        from PIL import Image,ImageDraw
        from text_style import estimate
        for weight,face in [(400,'Regular'),(700,'Bold')]:
            font=ImageFont.truetype('/usr/share/fonts/opentype/noto/NotoSerifCJK-'+face+'.ttc',48)
            source=Image.new('RGB',(280,85),'#151f30');ImageDraw.Draw(source).text((12,6),'遗迹背包',font=font,fill='#ead3a2')
            with self.subTest(weight=weight):
                result=estimate(np.array(source),'遗迹背包')
                self.assertIsNotNone(result);self.assertEqual(result['fontFamily'],'Noto Serif CJK SC');self.assertEqual(result['fontWeight'],weight)

    def test_serif_date_matches_installed_serif_instead_of_sans(self):
        import numpy as np
        from PIL import Image,ImageDraw
        from text_style import estimate
        for weight,face in [(400,'Regular'),(700,'Bold')]:
            font=ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSerif-'+face+'.ttf',40)
            source=Image.new('RGB',(320,65),'#fff5e0');ImageDraw.Draw(source).text((8,5),'11.03 — 11.05',font=font,fill='#802d1d')
            with self.subTest(weight=weight):
                result=estimate(np.array(source),'11.03 — 11.05')
                self.assertIsNotNone(result);self.assertEqual(result['fontFamily'],'Liberation Serif');self.assertEqual(result['fontWeight'],weight)
                self.assertFalse(result['fitWidth'])

    def test_deployed_bold_face_survives_refinement_without_regular_font_substitution(self):
        font = ImageFont.truetype('/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc', 100)
        left, top, right, bottom = font.getbbox('组件库', anchor='ls')
        node = dict(id='text', text='组件库', fontFamily='Noto Sans CJK SC', fontWeight=700,
                    fontSize=100, width=right-left, height=bottom-top)
        warnings = []
        _fit_text(node, warnings)
        self.assertEqual(node['fontFamily'], 'Noto Sans CJK SC')
        self.assertEqual(node['fontSize'], 100)
        self.assertEqual(warnings, [])
