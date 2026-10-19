"""Initial automatic organizational groups may split; node paint is immutable."""
import copy,unittest
from unittest.mock import Mock
from plan_contract import assemble,PlanAssemblyError
from layer_order import hierarchy

def fixture(nested=False):
 nodes=[{'id':ident,'sourceVectorId':ident,'name':ident,'type':'rect','x':0,'y':0,'width':10,'height':10,'fill':'#112233','z_index':i} for i,ident in enumerate('abc')]
 inner={'id':'organization','name':'原语义组','children':['a','c'],'layerStyle':None,'displayMask':None}
 groups=[inner]
 if nested:groups.append({'id':'outer','name':'外组织组','children':['organization','b'],'layerStyle':None,'displayMask':None})
 plan={'assets':[],'texts':[],'vectors':[{'id':n['id']} for n in nodes],'groups':groups,'warnings':[]}
 return plan,{'format':'shijie-scene','version':2,'width':20,'height':20,'nodes':nodes,'groups':[],'recognition':{}}

class InitialGroupNormalizationTests(unittest.TestCase):
 def test_only_organization_splits_and_keeps_exact_node_paint_and_original_evidence(self):
  plan,bare=fixture();before=copy.deepcopy(plan);build=Mock(return_value=copy.deepcopy(bare));repair=Mock(side_effect=AssertionError('pure split needs no analysis'))
  fixed,scene=assemble(plan,build,repair,lambda:False,lambda *_:None,canvas_size=(20,20),normalize_groups=True)
  self.assertEqual(build.call_args.args[0]['groups'],[]);repair.assert_not_called();self.assertEqual(scene['nodes'],bare['nodes']);self.assertEqual(plan,before)
  self.assertEqual(len(scene['groups']),2);self.assertEqual(scene['groups'][0]['id'],'organization');self.assertEqual(scene['groups'][0]['children'],['a']);self.assertEqual(scene['groups'][1]['children'],['c']);hierarchy(scene)
  evidence=scene['recognition']['autoGroupNormalization'];self.assertEqual(evidence['originalGroups'],before['groups']);self.assertEqual(evidence['status'],'SPLIT_WITHOUT_PAINT_CHANGE');self.assertEqual(len(fixed['groups']),2)
 def test_nested_organization_parent_refs_follow_split_children_and_ids_are_stable(self):
  plan,bare=fixture(True);build=lambda p:copy.deepcopy(bare);repair=Mock()
  fixed,scene=assemble(plan,build,repair,lambda:False,lambda *_:None,canvas_size=(20,20),normalize_groups=True);hierarchy(scene)
  original=next(g for g in scene['groups'] if g['id']=='outer');self.assertEqual(original['children'][1],'b');self.assertEqual(original['children'][0],'organization');self.assertEqual(len(original['children']),3)
  _,again=assemble(plan,build,repair,lambda:False,lambda *_:None,canvas_size=(20,20),normalize_groups=True);self.assertEqual(scene['groups'],again['groups']);self.assertEqual(scene['nodes'],bare['nodes'])
 def test_mask_style_opacity_hidden_groups_never_split_or_lose_settings(self):
  for key,value in [('displayMask',{'enabled':True,'type':'rect','x':0,'y':0,'width':20,'height':20}),('layerStyle',{'enabled':True}),('opacity',.5),('hidden',True)]:
   plan,bare=fixture();plan['groups'][0][key]=value;before=copy.deepcopy(plan);repair=Mock()
   with self.subTest(key=key),self.assertRaises(PlanAssemblyError):assemble(plan,lambda p:copy.deepcopy(bare),repair,lambda:False,lambda *_:None,canvas_size=(20,20),normalize_groups=True)
   repair.assert_not_called();self.assertEqual(plan,before)
 def test_contiguous_masked_ancestor_stays_single_and_preserves_its_mask(self):
  plan,bare=fixture(True);mask={'enabled':True,'type':'rect','x':0,'y':0,'width':20,'height':20};plan['groups'][1]['displayMask']=mask
  _,scene=assemble(plan,lambda p:copy.deepcopy(bare),Mock(),lambda:False,lambda *_:None,canvas_size=(20,20),normalize_groups=True)
  parent=next(g for g in scene['groups'] if g['id']=='outer');self.assertEqual(parent['displayMask'],mask);self.assertEqual(len([g for g in scene['groups'] if g['id']=='outer']),1);hierarchy(scene)
 def test_one_source_alias_spanning_fragments_cannot_create_ambiguous_resume_groups(self):
  plan,bare=fixture();bare['nodes'][2]['sourceVectorId']='a';plan['groups'][0]['children']=['a'];repair=Mock()
  with self.assertRaises(PlanAssemblyError):assemble(plan,lambda p:copy.deepcopy(bare),repair,lambda:False,lambda *_:None,canvas_size=(20,20),normalize_groups=True)
  repair.assert_not_called()
 def test_cycle_unknown_reference_and_shared_parent_are_rejected_with_inventory_intact(self):
  for failure in ('cycle','unknown','shared'):
   plan,bare=fixture(True)
   if failure=='cycle':plan['groups'][0]['children']=['outer']
   elif failure=='unknown':plan['groups'][0]['children']=['absent']
   else:plan['groups'].append({'id':'third','name':'重复父','children':['a']})
   before=copy.deepcopy(plan);repair=Mock(return_value=copy.deepcopy(plan))
   with self.subTest(failure=failure),self.assertRaises(PlanAssemblyError):assemble(plan,lambda p:copy.deepcopy(bare),repair,lambda:False,lambda *_:None,canvas_size=(20,20),normalize_groups=True)
   self.assertEqual(plan,before)
 def test_ordinary_existing_resume_path_never_calls_group_normalization(self):
  plan,bare=fixture();build=Mock(side_effect=ValueError('分组「原语义组」跨越交错图层'));repair=Mock(return_value=plan)
  with self.assertRaises(PlanAssemblyError):assemble(plan,build,repair,lambda:False,lambda *_:None,canvas_size=(20,20))
  self.assertEqual(build.call_args.args[0]['groups'],plan['groups']);self.assertEqual(repair.call_count,2)

if __name__=='__main__':unittest.main()
