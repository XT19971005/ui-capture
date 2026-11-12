"""Portable native PSD bridge. Explicit merged pixels and JPEG thumbnail are mandatory."""
import base64
import io
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import numpy as np
from PIL import Image, ImageDraw, ImageFont
try:
    from .core import validate_plan, safe_name, estimate_ink, clear_text, vector_candidate
except ImportError:
    from core import validate_plan, safe_name, estimate_ink, clear_text, vector_candidate


def _text_image(row, font_file, width, height):
    x,y,r,b=map(int,row['box']);size=max(1,min(4096,int(row.get('font_render_size',b-y))))
    # Plain Latin needs no complex shaping. Avoid a broken optional RAQM
    # runtime without changing the shaping engine for Arabic/Indic scripts.
    options={'layout_engine':ImageFont.Layout.BASIC} if row['text'].isascii() else {}
    font=ImageFont.truetype(str(font_file),size,**options)
    lines=row['text'].split('\n');advance=sum(font.getmetrics())
    bounds=[font.getbbox(line or ' ',anchor='ls') for line in lines]
    box=(min(v[0] for v in bounds),min(v[1]+i*advance for i,v in enumerate(bounds)),max(v[2] for v in bounds),max(v[3]+i*advance for i,v in enumerate(bounds)))
    w=max(1,box[2]-box[0]);h=max(1,box[3]-box[1])
    glyph=Image.new('RGBA',(w,h));draw=ImageDraw.Draw(glyph)
    for i,line in enumerate(lines):draw.text((-box[0],-box[1]+i*advance),line,font=font,anchor='ls',fill=tuple(row['color'])+(255,))
    # Fit the natural glyph aspect; target bounds never authorize stretching.
    scale=min((r-x)/w,(b-y)/h)
    glyph=glyph.resize((max(1,round(w*scale)),max(1,round(h*scale))),Image.Resampling.LANCZOS)
    canvas=Image.new('RGBA',(width,height));canvas.alpha_composite(glyph,(x,y))
    family,style=font.getname()
    # PostScript name when available, never use a filename as a fake font identity.
    try:
        from fontTools.ttLib import TTFont
        names=TTFont(str(font_file),fontNumber=0,lazy=True)['name'].names
        postscript=next(n.toUnicode() for n in names if n.nameID==6)
    except (ImportError,StopIteration,KeyError):postscript=family.replace(' ','')+('-'+style.replace(' ','') if style not in ('Regular','Normal') else '')
    return np.array(canvas),{'text':row['text'],'shapeType':'point','antiAlias':'smooth',
        'transform':[scale,0,0,scale,x-box[0]*scale,y-box[1]*scale],
        'style':{'font':{'name':postscript},'fontSize':size,'fillColor':dict(zip(('r','g','b'),row['color']))},
        'paragraphStyle':{'justification':'left'}}


def _encode(rgba):return base64.b64encode(np.ascontiguousarray(rgba,dtype='uint8').tobytes()).decode('ascii')


def node_command():
    system_node=shutil.which('node')
    if system_node:return [system_node]
    if importlib.util.find_spec('nodejs_wheel') is not None:return [sys.executable,'-m','nodejs_wheel']
    raise RuntimeError('Missing server Node runtime: install nodejs-wheel-binaries in ComfyUI Python, or Node.js 18+ on PATH')


try:
    from .spatial import validate_asset
except ImportError:
    from spatial import validate_asset


def export_scene(layers,plan,output_root,project_name,font_file,convert_vectors=True,replace_text=False,names=None,prepared_assets=None):
    if not layers:raise ValueError('No layers')
    height,width=layers[0].shape[:2]
    if width*height>12000000:raise ValueError('Maximum canvas is 12 million pixels')
    if width*height*(len(layers)+len(plan.get('texts',[])))+sum(a['rgba'].shape[0]*a['rgba'].shape[1] for a in (prepared_assets or []))>64000000:raise ValueError('Maximum total layer area is 64 million pixels')
    if any(a.shape!=(height,width,4) for a in layers):raise ValueError('All layers must be full-canvas RGBA')
    validate_plan(plan,width,height)
    for asset in prepared_assets or []:
        validate_asset(asset,width,height)
    if plan.get('texts') and (font_file is None or not Path(font_file).is_file()):raise ValueError('Editable text requires an available font file')
    command=node_command()
    safe=safe_name(project_name);output_root=Path(output_root).resolve();output_root.mkdir(parents=True,exist_ok=True)
    # Atomic allocation: concurrent runs and same-name versions never overwrite each other.
    project=None
    for index in range(1,10001):
        candidate=output_root/(safe if index==1 else f'{safe}_{index}')
        try:candidate.mkdir();project=candidate;break
        except FileExistsError:continue
    if project is None:raise RuntimeError('Too many project versions')
    try:
        rows=[dict(t) for t in plan.get('texts',[])];scene=[];warnings=list(plan.get('warnings',[]))
        composite=Image.new('RGBA',(width,height))
        source=composite.copy()
        for rgba in layers:source=Image.alpha_composite(source,Image.fromarray(rgba))
        for row in rows:
            if 'color' not in row:row['color']=estimate_ink(np.array(source),row['box'])
        for i,rgba in enumerate(layers):
            rgba=rgba.copy()
            for row in rows:
                if replace_text:rgba=clear_text(rgba,row)
            name=safe_name(names[i] if names and i<len(names) else f'图层_{i+1:02d}')
            shape=vector_candidate(rgba) if convert_vectors else None
            # Empty layers remain PNGs but cannot become native shapes.
            entry={'name':name,'rgba':_encode(rgba),'kind':'bitmap'}
            if shape:
                entry.update(kind='shape',shapes=shape['shapes'],color=shape['color'])
                warnings.append(f'{name}: 矢量曲线拟合需检查边缘、孔洞及细笔画')
            scene.append(entry);Image.fromarray(rgba).save(project/(f'{i+1:02d}_{name}.png'))
            composite=Image.alpha_composite(composite,Image.fromarray(rgba))
        for row in rows:
            rgba,text=_text_image(row,font_file,width,height)
            name=safe_name('文字_'+row['text'][:24])
            scene.append({'kind':'text','name':name,'rgba':_encode(rgba),'text':text})
            composite=Image.alpha_composite(composite,Image.fromarray(rgba))
        for asset in prepared_assets or []:
            entry=dict(asset);rgba=entry['rgba'];entry['name']=safe_name(entry['name']);entry['rgba']=_encode(rgba)
            entry.update(width=rgba.shape[1],height=rgba.shape[0])
            scene.append(entry);Image.fromarray(rgba).save(project/(f'{len(scene):02d}_{entry["name"]}.png'))
            composite.alpha_composite(Image.fromarray(rgba),(entry.get('left',0),entry.get('top',0)))
        if rows:
            warnings.append('字体为所选字体，未自动证明与原字体一致；OCR内容、颜色与排版需要确认')
            if not replace_text:warnings.append('文字去重关闭：原位图文字仍保留，原生文字会叠加；确认文字框后开启去重')
        thumb=composite.convert('RGB');thumb.thumbnail((160,160));jpeg=io.BytesIO();thumb.save(jpeg,format='JPEG',quality=90)
        payload={'width':width,'height':height,'layers':scene,'merged':_encode(np.array(composite)),
            'thumbnail':{'width':thumb.width,'height':thumb.height,'data':base64.b64encode(jpeg.getvalue()).decode()}}
        with tempfile.TemporaryDirectory(prefix='shijie-') as temp:
            manifest=Path(temp)/'scene.json';manifest.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
            out=project/(safe+'.psd')
            proc=subprocess.run(command+[str(Path(__file__).with_name('write_psd.cjs')),str(manifest),str(out)],capture_output=True,text=True,encoding='utf-8',timeout=180)
            if proc.returncode:raise RuntimeError('PSD export failed: '+proc.stderr[-3000:])
        report={'psd':str(out),'width':width,'height':height,'layers':len(scene),'text_layers':sum(e['kind']=='text' for e in scene),
            'placements':[{'name':e['name'],'left':e.get('left',0),'top':e.get('top',0),'width':e.get('width',width),'height':e.get('height',height)} for e in scene],
            'expert_plan':plan,'branch_asset_count':len(prepared_assets or []),'vector_layers':sum(e['kind']=='shape' for e in scene),'warnings':warnings,'visual_review':'REQUIRED'}
        (project/'检查记录.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        return report
    except BaseException:
        # This folder was allocated exclusively by this invocation.
        if project.parent==output_root:shutil.rmtree(project)
        raise
