"""Isolated legacy algorithm runner; progress and recovery bytes survive process exit."""
import importlib
import json
import os
import sys
import traceback
import tempfile
import time
from contextlib import nullcontext
from host_lock import exclusive
from pathlib import Path
from codex_client import CLIENT, CodexLoginRequired, CodexImageGenerationRequired, CodexImageGenerationFailed, CodexQuotaExceeded
from company_agent import CompanyError
from session_outputs import SESSIONS
from shijie.pipeline.storage import read_scene, write_scene, write_json
from shijie.pipeline.validation import validate_job, requires_generation
from shijie.pipeline.local_model import LocalModelError


def main():
    os.umask(0o077)
    root = Path(os.environ['SHIJIE_TASK_ROOT'])
    ident, model = sys.argv[1:3]
    revision = 1 if (root / 'partial.json').exists() else 0
    completed_progress = 0
    CLIENT.selected_model = model or None
    stage = 'account_lock'
    started = time.monotonic()

    def finish(value):
        write_json(root / 'finished.json', {**value, 'elapsedSeconds': time.monotonic()-started})

    def cancelled():
        return (root / 'cancel').exists()

    def progress(amount, message):
        nonlocal completed_progress
        completed_progress = max(completed_progress, min(1, float(amount)))
        write_json(root / 'progress.json', {'progress': completed_progress, 'message': str(message)[:500], 'revision': revision})

    def preview(scene):
        nonlocal revision
        if not cancelled():
            write_scene(root / 'partial.json', scene)
            revision += 1
            progress(0, '中间图层已保留')

    try:
        connection = json.loads(sys.stdin.read(16 * 1024)) or {}
        local_root = connection.get('local_model_root')
        envelope = 'analysisProvider' in connection
        CLIENT.company = connection.get('company') if envelope and connection['analysisProvider']=='company' else None if envelope or local_root else connection or None
        import assistant_models, image_provider, tygpt_transport
        tygpt_transport.CONNECTION = {'key': connection.get('tygpt')}
        assistant_models.CONNECTION = {'key': connection.get('taishi')}
        image_provider.CONNECTION = connection.get('image', {'provider':'codex','model':'gpt-image-2'})
        needs_codex = connection.get('needsCodex', not CLIENT.company and not local_root)
        with (nullcontext() if not needs_codex else exclusive(Path(os.environ['CODEX_HOME']) / 'account.lock')):
            stage = 'validate_input'
            raw = read_scene(root / 'input.json')
            mode = connection.get('mode', raw.get('mode','codex'))
            if mode=='assistant-plan':
                from free_assistant import validate_request
                value = {'mode':mode, 'body':validate_request(raw)}
                value['body']['provider'] = connection.get('analysisProvider', raw['provider'])
            elif mode=='assistant-split':
                from assistant_split import validate
                validate(raw)
                value = {'mode':mode, 'body':raw}
            else:
                value = validate_job(raw)
            if cancelled():
                raise InterruptedError()
            stage = 'check_account'
            if needs_codex:
                CLIENT.ensure_ready(require_images=requires_generation(value) and image_provider.settings()['provider']=='codex')
            stage = 'process'
            modes = {'codex': 'codex_pipeline', 'refine-ui': 'refine_ui', 'refine-selected': 'selected_refine',
                     'repair-order': 'layer_order', 'replace-image': 'image_replace'}
            process = importlib.import_module(modes[value['mode']]).process if value['mode'] not in ('local-layered','assistant-plan','assistant-split') else None
            options = {}
            if value['mode']=='codex' and value.get('annotations'):
                options['annotations']=value['annotations']
            if value['mode'] == 'refine-selected':
                if value.get('dialogue'): options['dialogue']=value['dialogue']
                options['selected_ids'] = value['selected_ids']
                if value['region'] is not None:
                    options['region'] = value['region']
            if value['mode'] == 'replace-image':
                options['replacement'] = value['replacement']
            if value['mode'] in ('assistant-plan','assistant-split'):
                def assistant_run(folder):
                    if value['mode']=='assistant-plan':
                        from free_assistant import plan
                        return plan(value['body'], folder, cancelled, lambda m:progress(0,m),
                                    lambda text:write_json(root/'reply.json',{'text':text[:4000]}))
                    from assistant_split import generate
                    return generate(value['body'], folder, cancelled, progress, on_scene=preview)
                with tempfile.TemporaryDirectory(prefix='assistant-', dir=root) as folder:
                    scene = assistant_run(Path(folder))
                if value['mode']=='assistant-split':
                    from layer_review import unique_layer_names
                    unique_layer_names(scene)
            elif value['mode'] == 'local-layered':
                from shijie.pipeline.local_model import process as local_process
                if not local_root:
                    raise LocalModelError('本机模型连接未配置')
                scene = local_process(value, local_root, progress, cancelled)
            else:
                scene = process(value['source'], value['title'], progress, cancelled, original_source=value['original'],
                                on_scene=preview, resume_scene=value['resume'], **options)
            if cancelled():
                raise InterruptedError()
            stage = 'persist_result'
            session = SESSIONS.get(scene.get('_sessionId'))
            if session and session['psd'] is not None:
                (root / 'result.psd').write_bytes(session['psd'])
            if session and session['audit']:
                write_json(root / 'review.json', session['audit'])
            if scene.get('format')=='shijie-scene': scene['_sessionId'] = ident
            if scene.get('delivery'):
                scene['delivery']['sessionId'] = ident
            write_scene(root / 'result.json', scene)
            incomplete = scene.get('_partial') or scene.get('recognition', {}).get('pendingGenerationIds')
            finish({'status': 'completed', 'message': '部分素材未完成，已保留现有图层，可继续拆分' if incomplete else '处理完成；可在任务记录中找回结果'})
    except InterruptedError:
        finish({'status': 'cancelled', 'message': '已取消，中间图层已保留'})
    except Exception as exc:
        # Store code locations, never provider text, image payloads or credentials.
        try:
            write_json(root / 'failure.json', {'exception': type(exc).__name__, 'stage': stage,
                       'frames': [{'file': Path(f.filename).name, 'line': f.lineno, 'function': f.name}
                                  for f in traceback.extract_tb(exc.__traceback__)]})
        except OSError:
            pass
        # Only known user-actionable errors cross the boundary; paths/provider messages stay private.
        if isinstance(exc, BlockingIOError):
            message = '个人 Codex 正在登录，请完成登录后重试'
        elif isinstance(exc, (CodexLoginRequired, CodexImageGenerationRequired, CodexImageGenerationFailed, CodexQuotaExceeded, CompanyError, LocalModelError)):
            message = str(exc)
        else:
            message = '任务处理发生异常，原图和已有图层已保留；请联系管理员检查任务记录'
        finish({'status': 'failed', 'message': message})
    finally:
        CLIENT.close()


if __name__ == '__main__':
    main()
