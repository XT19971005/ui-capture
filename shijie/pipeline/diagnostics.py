"""Only code locations cross the desktop boundary; never exception messages."""
import re

STAGES = frozenset(('account_lock', 'validate_input', 'check_account', 'process', 'persist_result'))


def sanitize_failure(value):
    if not isinstance(value, dict):
        return None
    kind, stage = value.get('exception'), value.get('stage')
    if not isinstance(kind, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,79}', kind) or not isinstance(stage, str) or stage not in STAGES:
        return None
    frames = []
    for frame in (value.get('frames') if isinstance(value.get('frames'), list) else [])[-24:]:
        if not isinstance(frame, dict):
            continue
        file, line, function = frame.get('file'), frame.get('line'), frame.get('function')
        if (isinstance(file, str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,100}\.py', file)
                and type(line) is int and 0 < line <= 10000000 and isinstance(function, str)
                and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,99}|<(?:module|lambda|listcomp|dictcomp|genexpr)>', function)):
            frames.append({'file': file, 'line': line, 'function': function})
    return {'exception': kind, 'stage': stage, 'frames': frames}


def failure_message(value):
    if value['exception'] == 'SelectedStageAnalysisTimeout':
        return '所选类别参数分析超时，尚未生成；原图标注保留，仅需重试当前类型，不重算其他类型'
    if value['exception'] == 'CodexQuotaExceeded':
        return '共享 Codex 额度不足，已有结果保留；本次不会自动重试'
    if value['exception'] == 'CodexLoginRequired':
        return '共享电脑的 Codex 登录已失效，请管理员重新登录；本次不会自动重试'
    if value['stage'] == 'validate_input':
        return '本次输入或标注未通过检查，尚未开始处理；请核对当前图片和标注'
    if value['stage'] == 'process' and any(f['file'] == 'design_properties.py' and f['function'] == 'color' for f in value['frames']):
        return '当前批次的颜色参数未通过检查，尚未生成；原标注保留，无需重画，可重新准备当前类别参数'
    if value['stage'] == 'process' and any(f['file'] == 'annotation_plan.py' and f['function'] == 'native_node' for f in value['frames']):
        return 'AI返回的矢量或文字方案参数不完整，尚未生成；原图和标注已保留，请返回原画标注重新准备方案'
    if value['stage'] == 'process' and any(f['file'] == 'free_assistant.py' and f['function'] == 'validate_plan' for f in value['frames']):
        return '助手返回的方案未通过检查，尚未开始生图；请核对标注和拆分范围后重新讨论'
    return '共享电脑处理未完成，错误位置已保留供管理员检查；已有结果保留，不会自动重试'
