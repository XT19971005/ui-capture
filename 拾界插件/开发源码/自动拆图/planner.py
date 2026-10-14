"""Validate Codex placement coordinates without local inference."""
import json
from design_properties import design_fields

def complete_entities(assets):
    """Merge explicitly identified parts before generating one whole person.

    Names, overlap and hierarchy alone are not reliable person identities.
    """
    entities={a.get('entityId') for a in assets if a['kind']=='person' and a.get('entityId')}
    groups={entity:[a for a in assets if a.get('entityId')==entity] for entity in entities}
    result=[];done=set()
    for a in assets:
        entity=a.get('entityId')
        if entity not in groups:result.append(a);continue
        if entity in done:continue
        done.add(entity);parts=groups[entity]
        root=max((p for p in parts if p['kind']=='person'),key=lambda p:(p['box'][2]-p['box'][0])*(p['box'][3]-p['box'][1]))
        box=[min(p['box'][0] for p in parts),min(p['box'][1] for p in parts),max(p['box'][2] for p in parts),max(p['box'][3] for p in parts)]
        result.append({**root,'box':box,'entityParts':[p['id'] for p in parts]})
    return result
def parse_plan(value, width, height, input_size=(1000,1000)):
    raw = value.strip()
    start, end = raw.find('{'), raw.rfind('}')
    if start < 0 or end < start: raise ValueError("视觉模型没有返回有效图层规划")
    obj = json.loads(raw[start:end+1])
    assets = []
    used = set()
    if len(obj.get('assets',[]))>120:raise ValueError('独立素材超过本次120项容量，请分批处理，不能截断或合并掩盖遗漏')
    for a in obj.get('assets', []):
        b = a.get('box')
        if isinstance(b,dict):b=[b.get(k) for k in ('left','top','right','bottom')]
        ident = str(a.get('id',''))[:60]
        if not ident or ident in used or not isinstance(b,list) or len(b)!=4: continue
        if any(not isinstance(v,(float,int)) or not 0 <= v <= max(input_size) for v in b): continue
        x0,y0,x1,y1=[int(round(v*k/1000)) for v,k in zip(b,[width/input_size[0]*1000,height/input_size[1]*1000,width/input_size[0]*1000,height/input_size[1]*1000])]
        if (x1-x0)*(y1-y0)>width*height*.93: continue
        if x1-x0<8 or y1-y0<8 or x1>width or y1>height:raise ValueError('模型素材框不符合左上右下格式，请重新分析')
        used.add(ident)
        assets.append({'id':ident,'name':str(a.get('name') or '素材')[:80],
                       'kind':('logo' if a.get('kind')=='text' else a.get('kind','decoration')),'box':[x0,y0,x1,y1],
                       'parent':str(a.get('parent') or '')[:60] or None,'entityId':str(a.get('entity_id') or a.get('entityId') or '')[:80],**design_fields(a)})
    if not assets and not obj.get("vectors") and not obj.get("text_corrections") and not obj.get("texts"): raise ValueError("视觉模型未找到可信素材，原图已保留")
    for a in assets:
        if a['parent'] not in used or a['parent']==a['id']: a['parent']=None
    return {'assets':complete_entities(assets),'art_text_ids':[str(x) for x in obj.get('art_text_ids',[])][:100],
            'text_corrections':[{ 'id':str(x.get('id','')),'text':str(x.get('text',''))[:300]} for x in obj.get('text_corrections',[]) if isinstance(x,dict)][:100]}
