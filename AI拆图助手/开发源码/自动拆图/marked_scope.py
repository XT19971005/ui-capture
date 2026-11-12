"""Explicit manual-mark requests never expand into an unrequested whole-image plan."""
import re


def bounded(body):
    messages = body.get('messages') or []
    return bool(body.get('annotations') and messages and messages[-1].get('role') == 'user'
                and '只处理本次标注的' in messages[-1].get('content', ''))


RULES = ('本次是用户手动圈选的有限对象，不是自动标注或整图拆分。只返回本次保留标注，'
         '严禁添加未圈的背景、奖杯、建筑、文字或其它对象。圈线只是完整主体的定位证据，'
         '圈内重叠的其它物体不是目标；默认补全遮挡和画外缺失，不裁断翅膀、尾羽或其它细部。'
         '一个标注为完整图片主体时只列一个image层，内在羽毛、材质、纹样不另拆；'
         '同款多处仅在明确reuseKey时逐位置展开。name必须以对应原标注编号开头，例如01 凤凰。'
         'reply只用两三句话说本次对象、类型和必要疑点，不展开整图方案。')


def validate(result, body):
    if not bounded(body) or not result.get('layers'):
        return result
    from source_annotations import summary
    marks = [m for m in summary(body['annotations']) if m['purpose'] != 'remove']
    numbers = {m['number'] for m in marks}
    layers = result['layers']
    for layer in layers:
        number = re.match(r'^\s*0*(\d+)[\s·、._]', layer['name'])
        if not number or int(number.group(1)) not in numbers:
            raise ValueError('方案增加了未标注对象，尚未生成；本次仅处理手动标注对象')
    if len(marks) == 1 and not marks[0].get('reuseKey') and any(l.get('layerType', 'image') == 'image' for l in layers) and len(layers) != 1:
        raise ValueError('单个完整图片主体被扩成多层，尚未生成；本次只需这一层并补全遮挡和画外部分')
    names = '、'.join(l['name'] for l in layers[:3])
    issues = '；'.join(dict.fromkeys(l.get('reviewNote', '') for l in layers if l.get('reviewNote')))[:160]
    result['reply'] = '仅准备本次标注：' + names + ('等' if len(layers) > 3 else '') + '。默认补全遮挡及画外缺失，尚未生成。' + issues
    return result
