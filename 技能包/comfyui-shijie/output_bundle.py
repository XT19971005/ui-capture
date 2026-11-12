"""A single download with the actual exported files and byte hashes."""
import hashlib,json,zipfile,os,uuid
from pathlib import Path

def bundle_outputs(project,psd):
 project=Path(project).resolve();psd=Path(psd).resolve()
 if psd.parent!=project or not psd.is_file():raise ValueError('PSD不在当前导出目录')
 files=sorted(project.glob('*.png'))+[psd]
 report=project/'检查记录.json'
 if report.is_file():files.append(report)
 for p in files:
  if p.is_symlink() or p.resolve().parent!=project:raise ValueError('导出文件越过项目目录')
 manifest=project/'交付文件清单.json'
 manifest.write_text(json.dumps(dict(visual_status='NOT_REVIEWED',files=[dict(name=p.name,bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files]),ensure_ascii=False,indent=2),'utf-8')
 dest=project/'完整素材与PSD.zip';temp=project/(uuid.uuid4().hex+'.tmp')
 try:
  with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as z:
   for p in [*files,manifest]:z.write(p,p.name)
  os.replace(temp,dest)
 finally:
  if temp.exists():temp.unlink()
 return dest,manifest
