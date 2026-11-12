"""Validate independent objects without turning rejected parameters into assets."""
import copy
import re


def isolate(result, body):
    from free_assistant import validate_plan
    if not isinstance(result, dict) or result.get('action') not in ('discuss', 'split') or result.get('choices'):
        return validate_plan(result, body)
    layers = result.get('layers')
    if not isinstance(layers, list) or len(layers) > 128:
        return validate_plan(result, body)
    if not layers:
        return validate_plan(result, body)
    envelope = copy.deepcopy(result)
    envelope.update(action='discuss', nextStep='discuss', layers=[])
    validate_plan(envelope, body)  # Source, target, scope and envelope remain strict.
    accepted, mapping, issues = [], {}, []
    for index, raw in enumerate(layers):
        layer = copy.deepcopy(raw)
        try:
            if not isinstance(layer, dict): raise ValueError('对象参数格式无效')
            ref = layer.get('reuseOf')
            if ref is not None:
                if type(ref) is not int or ref not in mapping: raise ValueError('同款底稿未通过检查，实例暂缓')
                layer['reuseOf'] = mapping[ref]
            trial = copy.deepcopy(result); trial['layers'] = accepted + [layer]
            validate_plan(trial, body)
        except (ValueError, KeyError, TypeError) as error:
            reason=str(error) if isinstance(error,ValueError) else '对象参数缺失或类型无效'
            issues.append({'index':index, 'name':str(raw.get('name','未命名对象') if isinstance(raw,dict) else '无效对象')[:100], 'reason':reason[:240]})
            continue
        mapping[index] = len(accepted); accepted.append(layer)
    # Several colour parts may belong to one numbered object. Never publish a
    # surviving fragment as the complete object after its required part failed.
    def number(layer):
        match=re.match(r'^\s*0*(\d+)[\s·、._]',str(layer.get('name',''))) if isinstance(layer,dict) else None
        return int(match.group(1)) if match else None
    rejected={i['index'] for i in issues};kept=list(mapping)
    while True:
        bad_numbers={number(layers[i]) for i in rejected}-{None};blocked=[]
        for i in kept:
            if number(layers[i]) in bad_numbers or layers[i].get('reuseOf') in rejected:
                issues.append({'index':i,'name':str(layers[i]['name'])[:100],'reason':'同一编号的必要组件或同款底稿未通过，暂不发布残缺对象'})
                blocked.append(i)
        if not blocked:break
        rejected.update(blocked);kept=[i for i in kept if i not in rejected]
    mapping={original:index for index,original in enumerate(kept)};accepted=[]
    for original in kept:
        layer=copy.deepcopy(layers[original])
        if layer.get('reuseOf') is not None:layer['reuseOf']=mapping[layer['reuseOf']]
        accepted.append(layer)
    output = copy.deepcopy(result); output['layers'] = accepted
    if not accepted: output.update(action='discuss', nextStep='discuss')
    output = validate_plan(output, body)
    if issues:
        output['planIssues'] = issues
        output['reply'] = ('已准备'+str(len(accepted))+'项合格参数；'+str(len(issues))+'项待修复，未生成、未标为合格。'+output['reply'])[:4000]
    return output
