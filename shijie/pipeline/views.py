import json
import mimetypes
import logging
import traceback
import hashlib
import shutil
import re
from html import escape
from pathlib import Path
from uuid import UUID
from urllib.parse import urlsplit
from django.conf import settings
from django.db import connection, transaction
from django.http import FileResponse, HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.http import require_GET
from shijie.accounts.models import User
from shijie.accounts.services import roles, is_admin, assignable_roles, can_manage_user, grant
from image_wire import decode_job
from local_project_store import LocalProjectStore, ProjectConflict, pack_record
from .models import Job
from .storage import user_root, job_root, check_space, write_scene, read_scene, write_json
from .validation import validate_job, requires_generation


@require_GET
def live(request):
    return JsonResponse({'service': 'shijie', 'version': '0.1.0'})


@require_GET
def ready(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        settings.DATA_ROOT.mkdir(parents=True, exist_ok=True)
        return JsonResponse({'ready': True})
    except Exception:
        return JsonResponse({'ready': False}, status=503)


def error(message, status=400):
    return JsonResponse({'error': message}, status=status)


def body(request):
    if request.content_type != 'application/json':
        raise ValueError('请使用 JSON 请求')
    value = json.loads(request.body, parse_constant=lambda x: (_ for _ in ()).throw(ValueError('无效数值')))
    return decode_job(value)


def api(request, route):
    try:
        if route == 'me' and request.method == 'GET':
            return JsonResponse({'id': request.user.pk, 'name': request.user.display_name or request.user.email,
                                 'roles': sorted(roles(request.user)), 'admin': is_admin(request.user), 'csrf': get_token(request)})
        if route == 'users':
            if not is_admin(request.user):
                return error('无权管理账号', 403)
            if request.method == 'POST':
                value = body(request)
                if set(value) != {'user', 'role'} or type(value['user']) is not int:
                    raise ValueError('账号授权参数无效')
                target = User.objects.get(pk=value['user'])
                grant(request.user, target, value['role'])
                return JsonResponse({'ok': True})
            if request.method == 'GET':
                return JsonResponse({'roles': assignable_roles(request.user), 'users': [
                    {'id': u.pk, 'email': u.email, 'name': u.display_name, 'roles': sorted(roles(u)),
                     'canManage': can_manage_user(request.user, u)} for u in User.objects.order_by('id')]})
        if route.startswith('engine/'):
            response = engine(request, route[7:])
            if route.startswith(('engine/codex/', 'engine/company/', 'engine/ai/', 'engine/assistant/', 'engine/image-provider')):
                response['Cache-Control'] = 'no-store'
            return response
        return error('接口不存在', 404)
    except ProjectConflict as exc:
        return error(str(exc), 409)
    except FileNotFoundError as exc:
        logging.getLogger(__name__).warning('Missing storage record at %s', [(Path(f.filename).name, f.lineno, f.name) for f in traceback.extract_tb(exc.__traceback__)])
        return error('记录不存在', 404)
    except (User.DoesNotExist, Job.DoesNotExist):
        return error('记录不存在', 404)
    except (ValueError, TypeError, KeyError, RecursionError, UnicodeError) as exc:
        return error(str(exc)[:240] or '参数无效')
    except OSError:
        return error('服务器存储读写失败或空间不足，原工程已保留，请重试或导出副本', 507)


def engine(request, route):
    method = request.method
    owner = request.user
    root = user_root(owner.pk)
    directory = '/users/' + str(owner.pk) + '/projects'
    if route == 'connection' and method == 'GET':
        return JsonResponse({'url': settings.PREFIX + '/api/engine', 'user': owner.pk})
    if route in ('health', 'ping') and method == 'GET':
        return JsonResponse({'service': 'shijie-engine', 'version': '1.0.0', 'ready': True, 'missing': [],
                             'codexAvailable': True, 'imageWireVersion': 1, 'regionRefineVersion': 1,
                             'imageReplaceSelectionVersion': 1, 'imageGenerateVersion': 1,
                             'localProjectStoreVersion': 1, 'sourceAnnotationsVersion': 1, 'assistantVersion': 1,
                             'freeAssistantVersion': 1, 'assistantSplitVersion': 1, 'imageProviderVersion': 1, 'selectedDialogueVersion': 1,
                             'jobModes': ['codex', 'local-layered', 'refine-ui', 'refine-selected', 'repair-order', 'replace-image']})
    if route in ('assistant/models', 'assistant/key', 'image-provider'):
        from . import providers
        if method == 'GET' and route == 'assistant/models':
            return JsonResponse(providers.models(owner, request.GET.get('provider', 'auto')))
        if method == 'GET' and route == 'image-provider':
            return JsonResponse(providers.image_status(owner))
        if method == 'POST' and route != 'assistant/models':
            if not request.is_secure() and urlsplit('//' + request.get_host()).hostname not in ('localhost','127.0.0.1','::1'):
                return error('请通过 HTTPS 打开拾界后再配置密钥')
            if len(request.body)>20*1024:raise ValueError('连接请求超过大小限制')
            with transaction.atomic():
                User.objects.select_for_update().get(pk=owner.pk)
                return JsonResponse(providers.save(owner, body(request), 'taishi' if route=='assistant/key' else 'aimake'))
    if route == 'ai/status' and method == 'GET':
        from . import ai
        return JsonResponse(ai.connections(owner))
    if route == 'local-model/status' and method == 'GET':
        from . import local_model
        return JsonResponse(local_model.status())
    if route.startswith('company/'):
        from . import company
        if route == 'company/connection' and method == 'GET':
            return JsonResponse(company.status(owner))
        if route in ('company/connection', 'company/test') and method == 'POST':
            if not request.is_secure() and urlsplit('//' + request.get_host()).hostname not in ('localhost', '127.0.0.1', '::1'):
                return error('请通过 HTTPS 打开拾界后再配置公司 Agent', 400)
            if len(request.body) > 20 * 1024:
                raise ValueError('连接请求超过大小限制')
            value = body(request)
            with transaction.atomic():
                User.objects.select_for_update().get(pk=owner.pk)
                if route == 'company/test':
                    if value != {}: raise ValueError('测试连接参数无效')
                    return JsonResponse(company.probe(owner))
                return JsonResponse(company.save(owner, value))
    if route.startswith('codex/'):
        from . import ai
        if route == 'codex/status' and method == 'GET':
            return JsonResponse(ai.status(owner))
        if route == 'codex/login' and method == 'GET':
            return JsonResponse({'ok': True, 'pending': ai.pending_login(owner)})
        if route in ('codex/login', 'codex/login/cancel', 'codex/logout', 'codex/access-token', 'codex/api-key') and method == 'POST':
            if route in ('codex/access-token', 'codex/api-key') and not request.is_secure() and urlsplit('//' + request.get_host()).hostname not in ('localhost', '127.0.0.1', '::1'):
                return error('请通过 HTTPS 打开拾界后再提交访问令牌或 API Key', 400)
            if len(request.body) > 20 * 1024:
                raise ValueError('账号请求超过大小限制')
            value = body(request)
            field = {'codex/access-token': 'token', 'codex/api-key': 'api_key'}.get(route)
            if set(value) != ({field} if field else set()):
                raise ValueError('账号请求参数无效')
            with transaction.atomic():
                User.objects.select_for_update().get(pk=owner.pk)
                if route == 'codex/access-token':
                    return JsonResponse(ai.access_token(owner, value['token']))
                if route == 'codex/api-key':
                    return JsonResponse(ai.access_token(owner, value['api_key'], api_key=True))
                operation = {'codex/login': ai.login, 'codex/login/cancel': ai.cancel_login, 'codex/logout': ai.logout}[route]
                return JsonResponse(operation(owner))
        if route == 'codex/model' and method == 'POST':
            value = body(request)
            if set(value) != {'model'} or value['model'] not in [m['id'] for m in ai.status(owner).get('models', [])]:
                raise ValueError('该模型不在当前账号可用列表中')
            owner.codex_model = value['model']
            owner.save(update_fields=['codex_model'])
            return JsonResponse({'ok': True, 'model': value['model']})
    if route == 'saved-projects/settings/location':
        return JsonResponse({'directory': directory}) if method == 'GET' else error('工程保存在个人服务器工作区，不能更改宿主路径', 403)
    if route == 'saved-projects' or re.fullmatch(r'saved-projects/[A-Za-z0-9_-]{1,160}', route):
        store = LocalProjectStore(root / 'projects')
        # Lock one user row across the original file CAS operation, including multiple web processes.
        with transaction.atomic():
            User.objects.select_for_update().get(pk=owner.pk)
            if route == 'saved-projects' and method == 'GET':
                return JsonResponse({'projects': store.list(), 'directory': directory})
            ident = route.removeprefix('saved-projects/')
            if method == 'GET':
                return JsonResponse({'project': store.get(ident, wire=True), 'directory': directory})
            if method in ('PUT', 'DELETE'):
                value = body(request)
                expected_directory = value.pop('_expectedDirectory', None)
                if expected_directory not in (None, directory):
                    raise ProjectConflict('当前账号或工作区已变化，请重新打开页面')
                expected = value.get('_expectedVersion')
                if expected is not None and (not isinstance(expected, str) or len(expected) > 160):
                    raise ValueError('版本无效')
                if method == 'DELETE':
                    store.delete(ident, expected)
                    return JsonResponse({'deleted': True})
                check_space(root, len(request.body))
                return JsonResponse({'project': store.save(ident, value, expected), 'directory': directory})
    if route == 'projects' and method == 'GET':
        return JsonResponse({'items': []})
    if route in ('jobs', 'assistant/jobs', 'assistant/split') and method == 'POST':
        value = body(request)
        if route == 'assistant/jobs':
            from free_assistant import validate_request
            validate_request(value)
            validated = {'mode':'assistant-plan', 'title':'AI 助手分析', 'resume':None}
        elif route == 'assistant/split':
            from assistant_split import validate
            validate(value)
            validated = {'mode':'assistant-split', 'title':value['title'], 'resume':None}
        else:
            validated = validate_job(value)
        from . import ai, company, providers
        from codex_client import LOGIN_REQUIRED_MESSAGE, IMAGE_GENERATION_REQUIRED_MESSAGE
        with transaction.atomic():
            User.objects.select_for_update().get(pk=owner.pk)
            provider = 'local' if validated['mode'] == 'local-layered' else ai.selected_provider(owner)
            needs_images = requires_generation(validated)
            analysis = value.get('provider', 'auto') if route=='assistant/jobs' else provider
            if analysis == 'auto': analysis = provider
            image_provider = providers.image_status(owner)['provider'] if provider!='local' else 'codex'
            needs_text = validated['mode'] not in ('replace-image','assistant-split','local-layered')
            needs_codex = (needs_text and analysis=='codex') or (needs_images and image_provider=='codex' and provider=='codex')
            if provider == 'local':
                from . import local_model
                if not local_model.status()['ready']:
                    return JsonResponse({'error': '本机分层服务尚未就绪，请启动本机模型服务后重试；原图和编辑已保留', 'code': 'LOCAL_MODEL_UNAVAILABLE'}, status=503)
            if (needs_text and analysis=='company') or (needs_images and image_provider=='codex' and provider=='company'):
                if not company.credentials(owner):raise ValueError('请先配置并启用个人公司 Agent')
            if analysis=='taishi':
                state = providers.models(owner, 'taishi')
                if not state['ready'] or value['model'] not in [m['id'] for m in state['models']]:raise ValueError('请选择当前太石账号可用的模型')
            if needs_images and image_provider=='aimake': providers.secret(owner, 'aimake')
            if needs_codex:
                state = ai.status(owner)
                if not state.get('ok'):
                    return JsonResponse({'error': '暂时无法检查 Codex 连接，任务未提交。请打开「AI 连接」检查后重试；原图和编辑已保留。', 'code': 'CODEX_UNAVAILABLE'}, status=503)
                if not state.get('ready'):
                    return JsonResponse({'error': LOGIN_REQUIRED_MESSAGE, 'code': 'CODEX_LOGIN_REQUIRED'}, status=409)
                if needs_images and image_provider=='codex' and provider=='codex' and not state.get('imageGeneration'):
                    return JsonResponse({'error': IMAGE_GENERATION_REQUIRED_MESSAGE, 'code': 'CODEX_IMAGE_GENERATION_UNAVAILABLE'}, status=422)
                if route=='assistant/jobs' and analysis=='codex' and value['model'] and value['model'] not in [m['id'] for m in state.get('models', [])]:
                    raise ValueError('当前 Codex 账号没有提供所选模型')
            snapshot = {'provider': provider, 'analysisProvider':analysis, 'imageProvider':image_provider, 'needsCodex':needs_codex, 'codexModel':owner.codex_model}
            project=value.get('projectId') or (value.get('resume') or {}).get('_projectId') or (value.get('workspace') or {}).get('projectId')
            if project is not None:
                if not isinstance(project,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}',project):raise ValueError('任务工程标识无效')
                snapshot['project']=project
            if Job.objects.filter(owner=owner, status__in=['queued', 'running']).count() >= settings.MAX_QUEUED_PER_USER:
                return error('待处理任务已达到个人上限', 429)
            check_space(root, len(request.body))
            job = Job.objects.create(owner=owner, title=validated['title'], mode=validated['mode'])
            write_scene(job_root(job) / 'input.json', value)
            write_json(job_root(job) / 'connection.json', snapshot)
            if validated['resume']:
                write_scene(job_root(job) / 'partial.json', validated['resume'])
                Job.objects.filter(pk=job.pk).update(partial_revision=1)
        return JsonResponse({'id': str(job.pk)}, status=202)
    if route == 'jobs' and method == 'GET':
        return JsonResponse({'jobs': [job_data(j) for j in Job.objects.filter(owner=owner).order_by('-created_at')[:100]]})
    match = re.fullmatch(r'jobs/([a-f0-9-]{36})/purge', route)
    if match and method == 'POST':
        with transaction.atomic():
            job = Job.objects.select_for_update().get(pk=UUID(match[1]), owner=owner)
            if job.status in ('queued', 'running'):
                return error('请先取消任务，等待处理结束后再删除', 409)
            folder = job_root(job)
            if folder.exists():
                shutil.rmtree(folder)
            job.delete()
        return JsonResponse({'deleted': True})
    match = re.fullmatch(r'jobs/([a-f0-9-]{36})', route)
    if match:
        job = Job.objects.get(pk=UUID(match[1]), owner=owner)
        if method == 'GET':
            return JsonResponse(job_data(job, include_result=True, include_input='afterRevision' not in request.GET))
        if method == 'DELETE':
            Job.objects.filter(pk=job.pk, status__in=['queued', 'running']).update(cancel_requested=True)
            Job.objects.filter(pk=job.pk, status='queued').update(status='cancelled', message='已取消', finished_at=timezone.now())
            return JsonResponse({'ok': True})
    match = re.fullmatch(r'sessions/([a-f0-9-]{36})(?:/(scene|psd|review))?', route)
    if match:
        job = Job.objects.get(pk=UUID(match[1]), owner=owner)
        path = job_root(job)
        if method == 'DELETE':
            # Results belong to the persistent job; closing an editor must not erase recovery data.
            return JsonResponse({'ok': True})
        if method == 'GET' and match[2] == 'scene':
            return JsonResponse(read_scene(path / 'result.json'))
        if method == 'GET' and match[2] == 'review':
            return JsonResponse(json.loads((path / 'review.json').read_text()) if (path / 'review.json').exists() else {})
        if method == 'GET' and match[2] == 'psd':
            return FileResponse((path / 'result.psd').open('rb'), as_attachment=True, filename=job.title + '.psd', content_type='image/vnd.adobe.photoshop')
    if route.startswith('web/') or route == 'open-output':
        return error('此独立服务处理图片和导入工程；网页抓取与打开本机文件夹请使用原桌面版', 410)
    return error('接口不存在或请求方法不支持', 404)


def job_data(job, include_result=False, include_input=True):
    value = {'id': str(job.pk), 'title': job.title, 'mode': job.mode, 'status': job.status,
             'progress': job.progress, 'message': job.message, 'partialRevision': job.partial_revision,
             'created': job.created_at.isoformat()}
    if include_result:
        folder = job_root(job)
        try:
            value['previewText'] = json.loads((folder / 'reply.json').read_text()).get('text','')[:4000]
        except FileNotFoundError:
            pass  # Docker's host mount can briefly hide a replaced streaming snapshot; poll again.
        if (folder / 'result.json').is_file() and job.status == 'completed':
            value['result'] = read_scene(folder / 'result.json')
        elif (folder / 'partial.json').is_file():
            value['partial'] = read_scene(folder / 'partial.json')
        elif (include_input or job.status in ('failed','cancelled')) and (folder / 'input.json').is_file():
            # A failure before planning still leaves the exact input available for a new explicit attempt.
            from engine import load_source
            original = read_scene(folder / 'input.json')
            with load_source(original['image']) as image:
                width, height = image.size
            value['input'] = {'format': 'shijie-scene', 'version': 2, 'title': job.title,
                              'width': width, 'height': height, 'source': original['image'],
                              'originalSource': original.get('original', original['image']), 'provenance': 'user-image',
                              'nodes': [{'id': 'original', 'name': '原图（尚未拆分）', 'type': 'image',
                                         'x': 0, 'y': 0, 'width': width, 'height': height, 'src': original['image'], 'locked': True}],
                              'edges': []}
    return value


def page(request, page):
    if request.method != 'GET':
        return error('仅支持 GET', 405)
    if not page:
        return redirect(settings.PREFIX + '/image-editor.html')
    if page in ('users/', 'tasks/'):
        if page == 'users/' and not is_admin(request.user):
            return error('无权管理账号', 403)
        return render(request, 'service.html', {'prefix': settings.PREFIX, 'section': page[:-1]})
    base = settings.BASE_DIR / 'shijie/static/server' if page.startswith('static/server/') else settings.EDITOR_ROOT
    name = page.removeprefix('static/server/')
    path = (base / name).resolve()
    if not path.is_relative_to(base.resolve()) or not path.is_file() or path.suffix not in ('.js', '.css', '.html', '.png', '.svg', '.ico', '.wasm', '.gz', '.traineddata', '.woff2'):
        return error('文件不存在', 404)
    if path.suffix == '.html':
        html = path.read_text()
        tag = '<script src="' + escape(settings.PREFIX) + '/static/server/bootstrap.js" data-prefix="' + escape(settings.PREFIX) + '" data-user="' + str(request.user.pk) + '" data-csrf="' + get_token(request) + '"></script>'
        tag += '<link rel="stylesheet" href="' + escape(settings.PREFIX) + '/static/server/fonts.css">'
        html = html.replace('<head>', '<head>' + tag, 1)
        return HttpResponse(html)
    raw = path.read_bytes()
    etag = '"' + hashlib.sha256(raw).hexdigest() + '"'
    response = HttpResponse(status=304) if request.headers.get('If-None-Match') == etag else HttpResponse(raw, content_type=mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
    response['ETag'] = etag
    return response
