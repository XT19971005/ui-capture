import sys,unittest,copy
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from shijie_contract import validate_ui_structure,verify_asset_review,validate_instance_reviews,asset_digest,ASSET_CRITERIA

class ShijieContractTests(unittest.TestCase):
 def test_changed_original_rejects_old_asset_and_review(self):
  im=np.ones((20,30,4),np.uint8)*255;original=im.copy();source=asset_digest(original)
  review={'source_index':0,'status':'PASS','visual_reviewed':True,'asset_sha256':asset_digest(im),'source_sha256':source,'issues':[],'checks':[{'name':n,'status':'PASS','notes':'实际核对'} for n in ASSET_CRITERIA]}
  instances=[{'source_index':0}]
  self.assertEqual(len(validate_instance_reviews([im],instances,[review],source,original)),1)
  changed=original.copy();changed[0,0,0]=0
  with self.assertRaises(ValueError):validate_instance_reviews([im],instances,[review],source,changed)
  with self.assertRaises(ValueError):validate_instance_reviews([im],instances,[review],source)
 def test_copy_claim_without_bound_review_cannot_qualify_source(self):
  im=np.ones((20,30,4),np.uint8)*255
  with self.assertRaises(ValueError):validate_instance_reviews([im],[{'source_index':0,'source_review':'PASS'}],[],'a'*64)
 def test_reference_to_unknown_ui_asset_is_rejected(self):
  plan={'assets':[],'texts':[],'vectors':[],'uiComponents':[{'id':'button','category':'button','familyId':'','variant':'blue','observedState':'unknown','parentId':None,'evidence':'原图蓝色按钮','slots':[{'role':'icon','nodeIds':['missing']}]}],'uiReuseGroups':[]}
  with self.assertRaisesRegex(ValueError,'引用|不存在'):validate_ui_structure(plan)
 def test_missing_inventory_is_not_treated_as_empty(self):
  with self.assertRaises(ValueError):validate_ui_structure({})
 def test_review_is_bound_to_actual_pixels_and_complete_observations(self):
  image=np.zeros((20,30,4),np.uint8);image[2:12,3:13]=[40,80,120,255];source='a'*64
  review={'status':'PASS','visual_reviewed':True,'asset_sha256':asset_digest(image),'source_sha256':source,'issues':[],'checks':[{'name':n,'status':'PASS','notes':'已对照原图实际检查此项'} for n in ASSET_CRITERIA]}
  self.assertEqual(verify_asset_review(image,review,source)['status'],'PASS')
  changed=image.copy();changed[2,3,0]=41
  with self.assertRaises(ValueError):verify_asset_review(changed,review,source)
  broken=copy.deepcopy(review);broken['checks'][0]['notes']=''
  with self.assertRaises(ValueError):verify_asset_review(image,broken,source)
  broken=copy.deepcopy(review);broken['checks'][-1]=broken['checks'][0]
  with self.assertRaises(ValueError):verify_asset_review(image,broken,source)
 def test_low_alpha_itself_is_not_a_rejection_reason(self):
  im=np.zeros((20,30,4),np.uint8);im[3:10,4:12]=[10,20,30,12];source='b'*64
  review={'status':'PASS','visual_reviewed':True,'asset_sha256':asset_digest(im),'source_sha256':source,'issues':[],'checks':[{'name':n,'status':'PASS','notes':'原图正常软阴影，已核对'} for n in ASSET_CRITERIA]}
  self.assertEqual(verify_asset_review(im,review,source)['status'],'PASS')

if __name__=='__main__':unittest.main()
