import sys,types,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import ocr

class OCRTests(unittest.TestCase):
 def test_low_confidence_number_retains_box_for_review_not_reconstruction(self):
  result=[([[10,10],[60,10],[60,30],[10,30]],'启动们次',.802)]
  fake=types.SimpleNamespace(RapidOCR=lambda **kw:None)
  with patch.dict(sys.modules,{'rapidocr_onnxruntime':fake}),patch.object(ocr,'_engine',lambda im:(result,None)):
   plan=ocr.analyze(np.zeros((40,80,3),np.uint8))
  self.assertEqual(plan['texts'],[])
  candidate=plan['review_candidates'][0]
  self.assertEqual(candidate['text'],'启动们次');self.assertEqual(candidate['box'],[10,10,60,30])
  self.assertEqual(candidate['rebuild_allowed'],False)

if __name__=='__main__':unittest.main()
