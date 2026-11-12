"""Read an existing owned export only; no model calls, generation or arbitrary paths."""
import base64,hashlib,json
from pathlib import Path

def export_envelope(output_root,project_name):
 if not isinstance(project_name,str) or not project_name or any(c in project_name for c in '/\\\x00') or project_name in ('.','..'):raise ValueError('只允许当前拾界项目名称')
 root=(Path(output_root)/'拾界').resolve();project=(root/project_name).resolve()
 if project.parent!=root:raise ValueError('项目路径越界')
 p=project/'完整素材与PSD.zip'
 if p.is_symlink() or not p.is_file():raise ValueError('本轮既有导出包不存在，停止；禁止重新生成')
 if p.stat().st_size>64*1024*1024:raise ValueError('导出包超过64MB传输限额')
 data=p.read_bytes()
 return json.dumps(dict(format='qp-existing-export-v1',filename=p.name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),base64=base64.b64encode(data).decode('ascii'),generated_again=False),ensure_ascii=False)
