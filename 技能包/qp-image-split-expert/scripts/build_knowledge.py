"""Rebuild server knowledge from canonical skill texts, with no silent summarization."""
import hashlib,json,re,sys
from pathlib import Path
skill=Path(__file__).resolve().parents[1];skills=skill.parent;workspace=skills.parent
sys.path.insert(0,str(skills/'comfyui-shijie'))
from knowledge_store import make_bundle,load_knowledge

def build():
 paths=[skills/'game-ui-to-psd/SKILL.md',skill/'SKILL.md']
 paths+=sorted(p for p in (skills/'game-ui-to-psd/references').iterdir() if p.suffix in ('.md','.json'))
 paths+=sorted(p for p in (skill/'references').iterdir() if p.suffix in ('.md','.json'))
 rows=[];versions={}
 for p in paths:
  raw=p.read_bytes();content=raw.decode('utf-8-sig')
  if re.search(r'\bsk-[A-Za-z0-9_-]{24,}|\bAKIA[A-Z0-9]{16}\b',content):raise ValueError('知识源疑似含凭据，停止打包：'+p.name)
  relative=p.relative_to(workspace).as_posix()
  rows.append({'path':relative,'raw_sha256':hashlib.sha256(raw).hexdigest(),'content':content})
  if p.name=='SKILL.md':versions[p.parent.name]=re.search(r'version:\s*["\']?([^"\'\s]+)',content).group(1)
 bundle=make_bundle('1.1.0',rows,versions)
 for directory in [skill/'knowledge',skills/'comfyui-shijie/expert_knowledge']:
  directory.mkdir(parents=True,exist_ok=True)
  target=directory/'knowledge.json';target.write_text(json.dumps(bundle,ensure_ascii=False,indent=2),encoding='utf-8');load_knowledge(target)
 inventory={k:v for k,v in bundle.items() if k!='sources'};inventory['sources']=[{k:v for k,v in r.items() if k!='content'} for r in rows]
 (skill/'knowledge/来源清单.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'receipt':bundle['receipt'],'sources':len(rows),'text_bytes':sum(len(r['content'].encode('utf-8')) for r in rows)},ensure_ascii=False))
 return bundle
if __name__=='__main__':build()
