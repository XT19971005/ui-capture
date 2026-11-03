"""Bridge the existing job runner to the native Mac model through a private volume."""
import json
import os
import time
import uuid
from pathlib import Path

from django.conf import settings
from PIL import Image
from engine import load_source, png
from .storage import write_json


class LocalModelError(ValueError):
    pass


def status(root=None):
    try:
        value = json.loads((Path(root or settings.LOCAL_MODEL_ROOT) / 'status.json').read_text())
        alive = 0 <= time.time() - value['heartbeat'] < 20
        ready = value.get('ready') is True and alive
        return {'ready': ready, 'busy': ready and value.get('busy') is True,
                'model': 'Qwen-Image-Layered', 'message': '本机模型已就绪' if ready else '本机服务运行中，模型文件尚未齐全' if alive else '本机模型未启动或心跳已过期'}
    except (OSError, ValueError, KeyError, TypeError):
        return {'ready': False, 'busy': False, 'model': 'Qwen-Image-Layered', 'message': '本机模型尚未启动'}


def scene_from_result(folder, value, result):
    files = result.get('layers')
    if not isinstance(files, list) or not 2 <= len(files) <= 8 or not all(isinstance(f, str) for f in files) or len(set(files)) != len(files):
        raise LocalModelError('本机模型返回的图层数量无效，原工程已保留')
    with load_source(value['source']) as source:
        width, height = source.size
    nodes, dimensions, transparent = [], None, False
    for index, filename in enumerate(files):
        if filename != f'layer_{index}.png':
            raise LocalModelError('本机模型返回的文件名无效')
        path = folder / filename
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 25 * 1024**2:
            raise LocalModelError('本机模型图片文件无效')
        with Image.open(path) as image:
            if image.format != 'PNG' or image.mode != 'RGBA' or image.width * image.height > 2_000_000:
                raise LocalModelError('本机模型未返回有效的透明 PNG')
            if dimensions is None:
                dimensions = image.size
            if image.size != dimensions or abs(image.width / image.height / (width / height) - 1) > .04:
                raise LocalModelError('本机模型图层尺寸不一致')
            alpha = image.getchannel('A')
            low, high = alpha.getextrema()
            if high == 0:
                continue
            transparent |= low < 250 and high > 5
            nodes.append({'id': f'local-layer-{index}', 'name': '背景（本机）' if index == 0 else f'素材 {index}（本机）',
                          'type': 'image', 'x': 0, 'y': 0, 'width': width, 'height': height,
                          'src': png(image), 'assetKind': 'background' if index == 0 else 'image',
                          'provenance': 'local-model-generated', 'opacity': 1})
    if len(nodes) < 2 or not transparent:
        raise LocalModelError('本机输出缺少有效透明分层，原图和已有工程已保留')
    return {'format': 'shijie-scene', 'version': 2, 'title': value['title'], 'width': width, 'height': height,
            'source': value['source'], 'originalSource': value['original'], 'provenance': 'user-image',
            'nodes': nodes, 'edges': [], 'groups': [],
            'recognition': {'automatic': True, 'extractionStatus': 'COMPLETED', 'reviewStatus': 'NOT_REVIEWED',
                            'provider': 'local', 'model': 'Qwen-Image-Layered', 'rasterOnly': True,
                            'generatedSize': {'width': dimensions[0], 'height': dimensions[1]},
                            'warnings': [f'本机模型生成尺寸为 {dimensions[0]} × {dimensions[1]}，已按画板大小显示；请对照原图检查细节。',
                                       '文字仍为图片，尚未重建为可编辑文本。遮挡补全为模型推测，需要人工校对。'],
                            'reviewSummary': '本机透明分层试用：文字仍为图片，细节与遮挡补全需校对；保留原始图片。'}}


def process(value, root, progress, cancelled):
    root = Path(root)
    if not status(root)['ready']:
        raise LocalModelError('本机模型服务未就绪，请启动后重试')
    folder = root / 'jobs' / str(uuid.uuid4())
    folder.mkdir(parents=True, mode=0o700)
    if os.environ.get('SHIJIE_TASK_ROOT'):
        write_json(Path(os.environ['SHIJIE_TASK_ROOT']) / 'local-request.json', {'id': folder.name})
    completed = False
    try:
        with load_source(value['source']) as image:
            image.convert('RGBA').save(folder / 'input.png')
        write_json(folder / 'request.json', {'layers': 3, 'steps': 20, 'resolution': 640, 'seed': 42})
        healthy_at = time.monotonic()
        while True:
            if cancelled():
                raise InterruptedError()
            result = folder / 'result.json'
            if result.is_file():
                scene = scene_from_result(folder, value, json.loads(result.read_text()))
                completed = True
                return scene
            if (folder / 'failed').exists():
                raise LocalModelError('本机模型执行未完成，请检查本机模型日志；原工程已保留')
            if status(root)['ready']:
                healthy_at = time.monotonic()
            elif time.monotonic() - healthy_at > 20:
                raise LocalModelError('本机模型服务已断开，原工程已保留；启动后可重试')
            try:
                state = json.loads((folder / 'progress.json').read_text())
                progress(float(state['progress']), str(state['message'])[:300])
            except FileNotFoundError:
                progress(.01, '等待本机模型；首次加载需要一些时间…')
            time.sleep(1)
    finally:
        if not completed:
            (folder / 'cancel').touch()
