"""Validate Codex placement coordinates without local inference."""
import json,math
from design_properties import design_fields

def complete_entities(assets):
    """Merge only explicitly identified parts into one complete entity.

    Names, overlap and hierarchy alone are not reliable person identities.
    """
    entities={a.get('entityId') for a in assets if a.get('entityId')}
    groups={entity:[a for a in assets if a.get('entityId')==entity] for entity in entities}
    result=[];done=set()
    for a in assets:
        entity=a.get('entityId')
        if entity not in groups:result.append(a);continue
        if entity in done:continue
        done.add(entity);parts=groups[entity]
        roots=[p for p in parts if p['kind']=='person'] or [p for p in parts if p['kind'] not in ('panel','button')] or parts
        root=max(roots,key=lambda p:(p['box'][2]-p['box'][0])*(p['box'][3]-p['box'][1]))
        box=[min(p['box'][0] for p in parts),min(p['box'][1] for p in parts),max(p['box'][2] for p in parts),max(p['box'][3] for p in parts)]
        merged={**root,'box':box,'entityParts':list(dict.fromkeys(k for p in parts for k in p.get('entityParts',[p['id']]))) }
        orders=[p['z_index'] for p in parts if 'z_index' in p]
        if orders:merged['z_index']=max(orders)
        text_parts=list(dict.fromkeys(k for p in parts for k in p.get('sourceTextParts',[])))
        if text_parts:merged['sourceTextParts']=text_parts
        result.append(merged)
    aliases={part:a['id'] for a in result for part in a.get('entityParts',[a['id']])}
    for a in result:
        parent=aliases.get(a.get('parent'),a.get('parent'))
        a['parent']=parent if parent!=a['id'] else None
    return result

def layer_order(row):
    if 'z_index' not in row:return {}
    value=row['z_index']
    if not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value):
        raise ValueError('图层 '+str(row.get('id') or row.get('name') or '')+' 的 z_index 必须是有限数值')
    return {'z_index':value}
def asset_box(row,width,height,input_size,index=0):
 """Validate explicit inventory entries; never discard them by size or area."""
 label=str(row.get('name') or '第'+str(index+1)+'项')+'('+str(row.get('id') or '')+')'
 def fail(reason):raise ValueError('素材「'+label+'」的 box '+reason)
 box=row.get('box')
 if isinstance(box,dict):box=[box.get(k) for k in ('left','top','right','bottom')]
 if not isinstance(box,list) or len(box)!=4:fail('须为左上右下四个坐标')
 if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in box):fail('须为有限数值')
 if not(0<=box[0]<box[2]<=input_size[0] and 0<=box[1]<box[3]<=input_size[1]):fail('超出原图或顺序无效')
 x0,y0,x1,y1=[int(round(v*k/size)) for v,k,size in zip(box,[width,height,width,height],[*input_size,*input_size])]
 if x1-x0<8 or y1-y0<8 or x1>width or y1>height:fail('取整后宽高须至少8像素且位于画布内')
 return [x0,y0,x1,y1]


def parse_plan(value, width, height, input_size=(1000,1000)):
    raw = value.strip()
    start, end = raw.find('{'), raw.rfind('}')
    if start < 0 or end < start: raise ValueError("视觉模型没有返回有效图层规划")
    obj = json.loads(raw[start:end+1])
    assets = []
    used = set()
    if len(obj.get('assets',[]))>120:raise ValueError('独立素材超过本次120项容量，请分批处理，不能截断或合并掩盖遗漏')
    for index,a in enumerate(obj.get('assets', [])):
        if not isinstance(a,dict):raise ValueError('素材规划第'+str(index+1)+'项不是对象')
        ident=a.get('id')
        if not isinstance(ident,str) or not ident or len(ident)>60 or ident in used:raise ValueError('素材ID缺失、重复或超过60字符，原清单不能静默过滤')
        x0,y0,x1,y1=asset_box(a,width,height,input_size,index)
        used.add(ident)
        assets.append({'id':ident,'name':str(a.get('name') or '素材')[:80],
                       'kind':('logo' if a.get('kind')=='text' else a.get('kind','decoration')),'box':[x0,y0,x1,y1],
                       'parent':str(a.get('parent') or '')[:60] or None,'entityId':str(a.get('entity_id') or a.get('entityId') or '')[:80],**({'derivedFromArtTextId':a['derivedFromArtTextId']} if a.get('derivedFromArtTextId') else {}),**design_fields(a),**layer_order(a)})
    if not assets and not obj.get("vectors") and not obj.get("text_corrections") and not obj.get("texts"): raise ValueError("视觉模型未找到可信素材，原图已保留")
    for a in assets:
        if a['parent'] not in used or a['parent']==a['id']: a['parent']=None
    return {'assets':complete_entities(assets),'art_text_ids':[str(x) for x in obj.get('art_text_ids',[])][:100],
            'text_corrections':[{ 'id':str(x.get('id','')),'text':str(x.get('text',''))[:300]} for x in obj.get('text_corrections',[]) if isinstance(x,dict)][:100]}
