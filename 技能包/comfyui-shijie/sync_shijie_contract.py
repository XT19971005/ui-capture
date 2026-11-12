"""Explicit developer-only migration from the user's existing Shijie sources.
No model/network imports; never run automatically during server installation.
"""
import ast,hashlib,json
from pathlib import Path

def main():
 root=Path(__file__).resolve().parent
 original=root.parent.parent/'拾界插件/开发源码/自动拆图'
 target=root/'shijie_source';target.mkdir(exist_ok=True)
 records=[]
 for name in ('design_properties.py','ui_components.py','acceptance.py'):
  path=original/name;raw=path.read_bytes();text=raw.decode('utf-8-sig')
  if name=='ui_components.py':
   output=text.replace('from design_properties import obj','from .design_properties import obj');filename=name
  elif name=='acceptance.py':
   wanted={'ASSET_CRITERIA','FINAL_CRITERIA','check_errors'};parts=[]
   for node in ast.parse(text).body:
    if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id in wanted for t in node.targets):parts.append(ast.get_source_segment(text,node))
    if isinstance(node,ast.FunctionDef) and node.name in wanted:parts.append(ast.get_source_segment(text,node))
   if len(parts)!=3:raise ValueError('拾界验收源码接口变化，停止迁移并人工核对')
   output='"""Exact named criteria/check function from Shijie; no Codex client import."""\n'+'\n\n'.join(parts)+'\n';filename='acceptance_rules.py'
  else:output=text;filename=name
  (target/filename).write_text(output,encoding='utf8')
  records.append({'source':'拾界插件/开发源码/自动拆图/'+name,'source_sha256':hashlib.sha256(raw).hexdigest(),'target':'shijie_source/'+filename,'target_sha256':hashlib.sha256((target/filename).read_bytes()).hexdigest(),'adaptation':'relative import only' if name=='ui_components.py' else 'criteria and pure check_errors only; exclude model client' if name=='acceptance.py' else 'unchanged source'})
 (target/'__init__.py').write_text('"""Pinned pure-contract migration from the existing Shijie plugin."""\n',encoding='utf8')
 (root/'docs/拾界源码迁移来源.json').write_text(json.dumps({'records':records,'scope':'pure UI structure and named acceptance contracts; not the full plugin or a deployed server implementation'},ensure_ascii=False,indent=2),encoding='utf8')
 print('Migrated 3 existing source modules; external model client excluded.')

if __name__=='__main__':main()
