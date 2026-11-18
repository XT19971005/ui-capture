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
         '逐个原编号说明本次每个圈选实际是什么，包含的部件、排除的独立对象、遮挡及画外补全和具体疑点，不能用前三项加等省略。'
         '用户最新明确的部件归属优先于旧方案；例如用户指定腿含脚蹬，不能仍按旧马具归属排除脚蹬。'
         '执行所需包含、排除、补全、材质和姿态要求必须写进对应层instruction，不能仅写在reply或reviewNote。'
         '只解释本次圈选清单，不展开未圈选的全图对象；已有图片不代表满足最新要求或已经视觉验收。')


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
    covered = {int(re.match(r'^\s*0*(\d+)[\s·、._]', l['name']).group(1)) for l in layers}
    missing = [m for m in marks if m['number'] not in covered]
    if missing:
        result.setdefault('planIssues', []).extend({'index': -1, 'name': f"{m['number']:02d} {m['name']}", 'reason': '本次圈选尚未返回分层方案，未生成'} for m in missing)
    kinds = {'image': '图片', 'text': '可编辑文字', 'rect': '原生矢量', 'ellipse': '原生矢量', 'path': '原生矢量'}
    lines = [f"{l['name']}（{kinds.get(l.get('layerType', 'image'), '待确认类型')}）：{l.get('instruction', '范围尚未说明')}" + (f"；具体说明：{l['reviewNote']}" if l.get('reviewNote') else '') for l in layers]
    lines.extend(f"{m['number']:02d} {m['name']}：尚未提供方案，未生成。" for m in missing)
    header = f'仅准备本次标注，共{len(marks)}个对象。默认补全遮挡及画外缺失，尚未生成。'
    full = header + '\n' + '\n'.join(lines)
    # The complete, unabridged instructions remain in layers for the expandable
    # object report. Keep the existing 4000-character chat transport contract.
    result['reply'] = full if len(full) <= 4000 else header + '\n逐项范围及具体说明见“本次圈选对象清单”（完整保留，不省略对象）。' + (f'其中{len(missing)}个对象尚未提供方案，未生成。' if missing else '')
    return result
