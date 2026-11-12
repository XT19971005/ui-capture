"""Exact named criteria/check function from Shijie; no Codex client import."""
ASSET_CRITERIA=('身份与完整实体','比例与定位','颜色与光照','透明边缘与孔洞','材质文字与标识','独立物品归属')

FINAL_CRITERIA=('拆分粒度','文字合并边界','画布与比例','位置与层级','颜色与光照','人物身份与完整实体','文字内容与字形','文字原生编辑','矢量完整与孔洞','透明边缘','背景去件与补全','渐变与图层样式','蒙版与完整底稿','来源与独立回读','PSD编辑与重组','完成状态与清理')

def check_errors(checks,expected):
 names=[c.get('name') for c in checks];errors=[]
 if len(names)!=len(expected) or set(names)!=set(expected) or len(set(names))!=len(names):errors.append('验收项目缺失、重复或未知')
 for c in checks:
  if c.get('status')!='PASS' or not isinstance(c.get('notes'),str) or not c['notes'].strip():errors.append(str(c.get('name'))+'未通过或缺少实际观察')
 return errors
