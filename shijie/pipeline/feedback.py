"""User-submitted feedback. No files are written until an explicit submission."""
import base64,io,json,re,uuid
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path
from PIL import Image

def redact(value,limit=2000):
    text=str(value or '')[:limit]
    text=re.sub(r'(?i)\b(?:Bearer\s+)[\w.\-]+','Bearer [已隐藏]',text)
    text=re.sub(r'\bsk-[A-Za-z0-9_-]{8,}','[密钥已隐藏]',text)
    text=re.sub(r'(?i)(api[_-]?key|token|password|authorization|cookie)\s*[:=]\s*[^\s,;]+',r'\1=[已隐藏]',text)
    text=re.sub(r'https?://[^\s<>"\']+',lambda m:m[0].split('?')[0].split('#')[0],text)
    text=re.sub(r'[A-Za-z]:[\\/][^\n\r<>"\']+','[本机路径已隐藏]',text)
    return text

def diagnostics(value):
    if not isinstance(value,dict):raise ValueError('问题信息格式无效')
    output={k:redact(value.get(k,''),300) for k in ('version','mode','browser')}
    output['viewport']={k:max(0,min(20000,int(value.get('viewport',{}).get(k,0)))) for k in ('width','height')}
    for key,fields,limit in [('errors',('time','source','message','path','status'),10),('actions',('time','action'),20)]:
        rows=value.get(key,[])
        if not isinstance(rows,list):raise ValueError('问题记录格式无效')
        output[key]=[{k:redact(row.get(k,''),500) for k in fields} for row in rows[-limit:] if isinstance(row,dict)]
    return output

def screenshot_bytes(value):
    if value is None:return None
    if not isinstance(value,str) or len(value)>5600000 or not re.match(r'^data:image/(png|jpeg|webp);base64,',value):raise ValueError('截图格式或大小无效，请使用 4 MB 以内的 PNG、JPG 或 WebP')
    try:
        raw=base64.b64decode(value.split(',',1)[1],validate=True)
        if len(raw)>4*1024*1024:raise ValueError()
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in ('PNG','JPEG','WEBP') or image.width*image.height>12000000:raise ValueError()
            image.load();out=io.BytesIO();image.convert('RGB').save(out,format='PNG',optimize=True)
        if out.tell()>4*1024*1024:raise ValueError()
        return out.getvalue()
    except Exception:raise ValueError('截图无法读取或超过限制，请换一张图片')

def submit(owner, value):
    from django.db import transaction
    from shijie.accounts.models import User
    from .storage import user_root, check_space, write_json
    if not isinstance(value, dict):
        raise ValueError('反馈格式无效')
    try:
        key = str(uuid.UUID(value.get('submissionKey', '')))
    except (ValueError, TypeError, AttributeError):
        raise ValueError('反馈编号无效')
    category = value.get('category')
    description = value.get('description')
    if category not in ('功能异常','图片问题','界面问题','建议反馈'):
        raise ValueError('请选择反馈类型')
    if not isinstance(description, str) or not 2 <= len(description.strip()) <= 2000:
        raise ValueError('请填写2至2000字的问题描述')
    diag = diagnostics(value.get('diagnostics', {}))
    shot = screenshot_bytes(value.get('screenshot'))
    with transaction.atomic():
        User.objects.select_for_update().get(pk=owner.pk)
        root = user_root(owner.pk)
        target = root / 'feedback' / (key + '.json')
        if target.exists():
            previous = json.loads(target.read_text('utf8'))
            return {'id': previous['id'], 'status': previous['status'], 'received': True}, 200
        record = {'id': 'FB-' + datetime.now(timezone.utc).strftime('%Y%m%d') + '-' + uuid.uuid4().hex[:10].upper(),
                  'status': '待处理', 'created': datetime.now(timezone.utc).isoformat(),
                  'category': category, 'description': redact(description.strip()), 'diagnostics': diag,
                  'screenshot': base64.b64encode(shot).decode('ascii') if shot else None}
        check_space(root, len(json.dumps(record, ensure_ascii=False).encode('utf8')))
        write_json(target, record)
        return {'id': record['id'], 'status': record['status'], 'received': True}, 201
