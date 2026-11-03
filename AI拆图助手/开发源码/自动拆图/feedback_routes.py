"""User-submitted feedback. No files are written until an explicit submission."""
import base64,io,json,os,re,sqlite3,uuid
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path
from flask import request,jsonify
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

def register_feedback_routes(app,default_directory):
    def database():
        folder=Path(os.environ.get('SHIJIE_FEEDBACK_DIRECTORY') or default_directory)
        folder.mkdir(parents=True,exist_ok=True)
        conn=sqlite3.connect(str(folder/'feedback.sqlite3'),timeout=10)
        conn.execute('CREATE TABLE IF NOT EXISTS feedback (id TEXT PRIMARY KEY, submission_key TEXT UNIQUE NOT NULL, created TEXT NOT NULL, category TEXT NOT NULL, description TEXT NOT NULL, diagnostics TEXT NOT NULL, screenshot BLOB, status TEXT NOT NULL)')
        return conn
    @app.post('/feedback')
    def submit_feedback():
        if request.content_length and request.content_length>8*1024*1024:return jsonify(error='反馈内容超过 8 MB，请缩小截图'),413
        body=request.get_json(silent=True)
        if not isinstance(body,dict):return jsonify(error='反馈内容格式无效'),400
        try:
            key=str(uuid.UUID(body.get('submissionKey','')))
            category=body.get('category','')
            if category not in ('功能异常','图片问题','界面问题','建议反馈'):raise ValueError('请选择反馈类型')
            description=body.get('description','')
            if not isinstance(description,str) or not 2<=len(description.strip())<=2000:raise ValueError('请填写 2 至 2000 字的问题描述')
            description=redact(description.strip())
            diag=diagnostics(body.get('diagnostics',{}));shot=screenshot_bytes(body.get('screenshot'))
        except (ValueError,TypeError,AttributeError) as error:return jsonify(error=str(error) or '反馈内容无效'),400
        report='FB-'+datetime.now(timezone.utc).strftime('%Y%m%d')+'-'+uuid.uuid4().hex[:10].upper()
        try:
            with closing(database()) as db:
                with db:
                    db.execute('INSERT OR IGNORE INTO feedback VALUES (?,?,?,?,?,?,?,?)',(report,key,datetime.now(timezone.utc).isoformat(),category,description,json.dumps(diag,ensure_ascii=False),shot,'待处理'))
                    row=db.execute('SELECT id,status FROM feedback WHERE submission_key=?',(key,)).fetchone()
            return jsonify(id=row[0],status=row[1],received=True),201 if row[0]==report else 200
        except (OSError,sqlite3.Error):return jsonify(error='反馈暂时无法保存，请稍后重试；当前填写内容已保留'),503
