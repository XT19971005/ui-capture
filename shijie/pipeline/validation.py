import copy, math
from image_wire import measure

def validate_resume(value):
    if value is None:return None
    measure(value)
    if not isinstance(value,dict) or value.get('format')!='shijie-scene' or value.get('version')!=2:raise ValueError('续拆工程格式无效')
    def number(n,low,high):return isinstance(n,(int,float)) and not isinstance(n,bool) and math.isfinite(n) and low<=n<=high
    def valid_id(ident):return isinstance(ident,str) and bool(ident) and len(ident)<=160
    if not all(number(value.get(k),1,6000) for k in ('width','height')):raise ValueError('续拆画板尺寸无效')
    def node_ids(nodes):
        if not isinstance(nodes,list) or len(nodes)>700:raise ValueError('续拆图层数量无效')
        ids=set()
        for n in nodes:
            if not isinstance(n,dict) or n.get('type') not in ('text','image','path','rect','ellipse'):raise ValueError('续拆图层类型无效')
            ident=n.get('id')
            if not valid_id(ident) or ident in ids:raise ValueError('续拆图层标识无效')
            ids.add(ident)
            if not all(number(n.get(k),-12000,12000) for k in ('x','y')) or not all(number(n.get(k),.001,12000) for k in ('width','height')):raise ValueError('续拆图层尺寸无效')
        return ids
    ids=node_ids(value.get('nodes'))
    for k in ('edges','groups'):
        if k in value and (not isinstance(value[k],list) or len(value[k])>1400):raise ValueError('续拆工程结构无效')
    def groups_valid(groups):
        if not isinstance(groups,list) or len(groups)>1400:raise ValueError('续拆分组数量无效')
        seen=set();owners={}
        for group in groups:
            if not isinstance(group,dict) or not valid_id(group.get('id')) or group['id'] in seen or not isinstance(group.get('children'),list) or not group['children'] or len(group['children'])>2100:raise ValueError('续拆分组结构无效')
            seen.add(group['id'])
            for ident in group['children']:
                if not valid_id(ident) or ident in owners or ident==group['id']:raise ValueError('续拆分组成员无效')
                owners[ident]=group['id']
        for ident in owners:
            path=set();current=ident
            while current in owners:
                if current in path:raise ValueError('续拆分组循环引用')
                path.add(current);current=owners[current]
    groups_valid(value.get('groups',[]))
    recognition=value.get('recognition',{})
    if not isinstance(recognition,dict):raise ValueError('续拆恢复记录无效')
    if 'resumePendingNodes' in recognition and len(ids|node_ids(recognition['resumePendingNodes']))>700:raise ValueError('续拆待完成图层数量无效')
    if 'resumeGroups' in recognition:groups_valid(recognition['resumeGroups'])
    for key in ('resumeNodeOrder','pendingGenerationIds'):
        if key in recognition:
            entries=recognition[key]
            if not isinstance(entries,list) or len(entries)>1400 or any(not valid_id(ident) for ident in entries) or len(set(entries))!=len(entries):raise ValueError('续拆恢复图层标识无效')
    if 'resumePlan' in recognition and not isinstance(recognition['resumePlan'],dict):raise ValueError('续拆恢复规划无效')
    def inspect(v,depth=0):
        if depth>40:raise ValueError('续拆工程层级过多')
        if isinstance(v,float) and not math.isfinite(v):raise ValueError('续拆工程数值无效')
        if isinstance(v,dict):
            for k,item in v.items():
                # Nested audit records may describe their source in words;
                # only the scene's source and actual image fields are rendered.
                if (k in ('src','originalSource','comparisonSource') or (k=='source' and depth==0)) and item is not None and (not isinstance(item,str) or not item.startswith('data:image/') or len(item)>36000000):raise ValueError('续拆图片必须内嵌在工程中')
                inspect(item,depth+1)
        elif isinstance(v,list):
            for item in v:inspect(item,depth+1)
    inspect(value)
    result=copy.deepcopy(value)
    for k in ('delivery','_sessionId','_projectId'):result.pop(k,None)
    return result


def validate_job(data):
    if not isinstance(data,dict) or set(data)-{'image','title','mode','original','resume','selectedIds','region','replacement'}:raise ValueError('任务参数无效')
    source=data.get('image');original=data.get('original',source);title=str(data.get('title') or '智能拆图')[:160];mode=data.get('mode','codex')
    if mode not in ('codex','local-layered','refine-ui','refine-selected','repair-order','replace-image'):raise ValueError('处理方式无效')
    if not isinstance(source,str) or len(source)>36000000 or not source.startswith('data:image/'):raise ValueError('请选择有效图片')
    if not isinstance(original,str) or len(original)>36000000 or not original.startswith('data:image/'):raise ValueError('原图无效')
    try:resume=validate_resume(data.get('resume'))
    except (ValueError,TypeError,RecursionError) as exc:raise ValueError(str(exc))
    if mode=='local-layered' and resume is not None:raise ValueError('本机分层暂不续拆已有图层，请保存当前工程后重新导入原图；当前编辑已保留')
    selected_ids=data.get('selectedIds');region=data.get('region')
    if mode=='refine-selected':
        from selected_refine import validate_selection
        try:validate_selection(resume,selected_ids,region)
        except (ValueError,TypeError) as exc:raise ValueError(str(exc))
    elif selected_ids is not None or region is not None:raise ValueError('当前处理方式不接受选中图层或检查区域')
    replacement=data.get('replacement')
    if mode=='replace-image':
        from image_replace import validate_replacement
        try:validate_replacement(resume,replacement)
        except (ValueError,TypeError,RecursionError) as exc:raise ValueError(str(exc))
    elif 'replacement' in data:raise ValueError('当前处理方式不接受图片替换参数')
    if mode=='repair-order':
        from layer_order import hierarchy
        try:hierarchy(resume)
        except (ValueError,TypeError,RecursionError) as exc:raise ValueError(str(exc))
    if mode=='refine-ui':
        from refine_ui import can_refine
        if not can_refine(resume):raise ValueError('当前工程没有可精修的完整、未锁定文字或矢量图层；请先完成拆图')
    from engine import load_source
    try:
        load_source(source).close()
        load_source(original).close()
    except (OSError, ValueError) as exc:
        raise ValueError('图片内容无效或尺寸超过限制') from exc
    return {"source": source, "title": title, "mode": mode, "original": original, "resume": resume, "selected_ids": selected_ids, "region": region, "replacement": replacement}


def requires_generation(value):
    # Selected-layer refinement can regenerate an image after review, so check before dispatch.
    return value['mode'] in ('codex', 'replace-image', 'refine-selected')
