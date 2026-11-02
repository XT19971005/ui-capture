import tempfile,unittest
from pathlib import Path
from PIL import Image
from runtime import ROOT
from workflow_assets import review_sheets

class ReviewSheetTests(unittest.TestCase):
 def test_current_native_layer_name_cannot_read_stale_same_index_file(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'依赖/运行临时') as folder:
   qa=Path(folder);layers=qa/'独立图层';layers.mkdir()
   Image.new('RGBA',(20,20),(255,0,0,255)).save(layers/'001_A_stale.png')
   Image.new('RGBA',(20,20),(0,0,255,255)).save(layers/'001_Z_current.png')
   files=review_sheets({'nodes':[{'name':'Z_current','type':'text'}]},qa)
   actual=Image.open(files[0]).convert('RGB');self.assertEqual(actual.getpixel((15,40)),(0,0,255))

if __name__=='__main__':unittest.main()
