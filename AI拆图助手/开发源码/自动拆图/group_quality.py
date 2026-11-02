"""Observe automatic grouping quality without inventing groups or changing paint."""

GROUP_PLANNING_RULES='参考可编辑游戏PSD的组织方式，按原图可观察的语义区域规划有意义的groups，例如标题区、奖励面板、操作区、角色与独立装饰；明确的父子区域可嵌套，children可引用组id。多个区域、多类独立物体的界面应有语义分组，不能机械地每层套一组或把所有内容塞进一个无意义总组。单独素材或确实没有区域组织证据时允许空groups，并在warnings说明。组内图片仍为独立完整透明素材，普通文字仍为独立可编辑文字；完整角色与一体持物不因分组而拆碎。分组只引用本次明确对象，不依据名字猜测，不把uiComponents强制转换为绘制组，不改变z_index和真实遮挡；交错区域按连续层序合理拆组。'
MISSING_GROUP_ISSUE='分组待检查：本次自动拆分包含多个独立图层，但尚无语义文件夹。请按实际区域整理分组；仍可手动导出 PSD，当前导出将保留平层。'


def validate_planned_groups(plan,scene):
 """Fresh assembly must retain every planned folder and its resolved children."""
 planned=plan.get('groups',[])
 if not planned:return
 groups={g['id']:g for g in scene.get('groups',[])}
 planned_ids={g['id'] for g in planned};aliases={}
 for node in scene.get('nodes',[]):
  for key in [node['id'],node.get('sourceAssetId'),node.get('sourceVectorId'),node.get('sourceTextId'),*node.get('sourceEntityParts',[]),*node.get('sourceTextParts',[])]:
   if key:aliases.setdefault(key,set()).add(node['id'])
 for group in planned:
  label=str(group.get('name') or group['id'])
  def fail(reason):raise ValueError('分组结构不完整：「'+label+'」'+reason+'；原规划与图层已保留')
  actual=groups.get(group['id'])
  if actual is None:fail('未保留为文件夹')
  expected=set()
  for ref in group['children']:
   members={ref} if ref in planned_ids else aliases.get(ref)
   if not members:fail('缺少源成员 '+str(ref))
   expected.update(members)
  children=actual.get('children',[])
  if len(children)!=len(set(children)) or set(children)!=expected:fail('成员或嵌套关系与规划不一致')


def mark_group_review(scene):
 """Only automatic extraction receives this advisory; export remains available."""
 recognition=scene.get('recognition',{})
 if recognition.get('automatic') is not True:return scene
 # A resumed task may contain the user's new groups. Remove only our own old
 # advisory; do not erase another review's issues or declare a visual PASS.
 if recognition.get('groupReviewIssue')==MISSING_GROUP_ISSUE:
  recognition.pop('groupReviewIssue')
  if recognition.get('reviewIssue')==MISSING_GROUP_ISSUE:recognition.pop('reviewIssue')
  recognition['warnings']=[w for w in recognition.get('warnings',[]) if w!=MISSING_GROUP_ISSUE]
  recognition['reviewSummary']=recognition.get('reviewSummary','').replace(MISSING_GROUP_ISSUE,'').strip()
 nodes=[n for n in scene.get('nodes',[]) if not n.get('versionArchived') and n.get('assetKind')!='background' and n.get('provenance')!='source-reference']
 if scene.get('groups'):
  recognition['groupReviewStatus']='NOT_REVIEWED'
 elif len(nodes)<=1:
  recognition['groupReviewStatus']='NOT_REQUIRED'
 else:
  issue=MISSING_GROUP_ISSUE
  recognition.update(groupReviewStatus='NEEDS_REVIEW',groupReviewIssue=issue,reviewStatus='NEEDS_REVIEW')
  recognition.setdefault('reviewIssue',issue)
  warnings=recognition.setdefault('warnings',[])
  if issue not in warnings:warnings.append(issue)
  if issue not in recognition.get('reviewSummary',''):recognition['reviewSummary']=(recognition.get('reviewSummary','')+' '+issue).strip()
 return scene
