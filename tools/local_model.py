# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "torch==2.12.0", "torchvision==0.27.0", "transformers==5.8.1",
#   "diffusers @ git+https://github.com/huggingface/diffusers.git@79de3064ddf87ac7425731d201f84a88d0770607",
#   "accelerate==1.13.0", "Pillow==12.2.0", "safetensors==0.8.0rc0",
# ]
# ///
"""Native Qwen runner: uv run tools/local_model.py serve --model-dir /model/snapshot.

The private queue is mounted into Docker; no HTTP listener or cloud credentials.
Each inference runs in a child so cancellation and memory release are reliable.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
MODEL_REVISION = '8f0ca708dfff6ba1dd5f2d85d78f8c108a040bcf'


def write(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False))
    temporary.replace(path)


def validate_request(value):
    if not isinstance(value, dict) or set(value) != {'layers', 'steps', 'resolution', 'seed'}:
        raise ValueError('invalid model request')
    if any(type(v) is not int for v in value.values()):
        raise ValueError('model options must be integers')
    if not 2 <= value['layers'] <= 6 or not 1 <= value['steps'] <= 50 or value['resolution'] != 640 or not 0 <= value['seed'] < 2**32:
        raise ValueError('model request outside supported limits')
    return value


def model_ready(path):
    # Only completed safetensors snapshots are accepted; .incomplete downloads never count.
    try:
        files = ['model_index.json', 'vae/diffusion_pytorch_model.safetensors', 'tokenizer/tokenizer_config.json']
        for part in ('transformer/diffusion_pytorch_model.safetensors.index.json', 'text_encoder/model.safetensors.index.json'):
            index = json.loads((path / part).read_text())
            files += [str(Path(part).parent / name) for name in set(index['weight_map'].values())]
        return all((path / name).is_file() for name in files)
    except (OSError, ValueError, KeyError, TypeError):
        return False


def infer(folder, model_dir):
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    import torch
    from PIL import Image
    from diffusers import QwenImageLayeredPipeline

    options = validate_request(json.loads((folder / 'request.json').read_text()))
    source = folder / 'input.png'
    if source.is_symlink() or source.stat().st_size > 25 * 1024**2:
        raise ValueError('invalid input file')
    with Image.open(source) as raw:
        if raw.width * raw.height > 6_000_000 or max(raw.size) > 6000:
            raise ValueError('input dimensions exceed limits')
        image = raw.convert('RGBA')
    if not torch.backends.mps.is_available():
        raise RuntimeError('Apple MPS is unavailable')
    started = time.monotonic()
    write(folder / 'progress.json', {'progress': .03, 'message': '正在加载本机 Qwen 分层模型…'})
    pipe = QwenImageLayeredPipeline.from_pretrained(str(model_dir), torch_dtype=torch.bfloat16, local_files_only=True).to('mps')
    pipe.vae.enable_slicing()
    loaded = time.monotonic() - started
    write(folder / 'progress.json', {'progress': .08, 'message': '模型已加载，正在分析原图并准备分层…'})
    peak = 0

    def step(pipe, index, timestep, values):
        nonlocal peak
        if (folder / 'cancel').exists():
            raise InterruptedError('cancelled')
        if not torch.isfinite(values['latents']).all().item():
            raise ValueError('non-finite model latents')
        peak = max(peak, torch.mps.driver_allocated_memory())
        write(folder / 'progress.json', {'progress': .15 + .75 * (index + 1) / options['steps'],
                                        'mpsAllocatedBytes': peak,
                                        'message': f"本机分层：{index + 1}/{options['steps']} 步，生成 {options['layers']} 个图层…"})
        return values

    with torch.inference_mode():
        images = pipe(image=image, layers=options['layers'], resolution=options['resolution'],
                      num_inference_steps=options['steps'], generator=torch.Generator('cpu').manual_seed(options['seed']),
                      true_cfg_scale=4.0, negative_prompt='', cfg_normalize=True, use_en_prompt=True,
                      callback_on_step_end=step).images[0]
    files = []
    for index, layer in enumerate(images):
        if layer.mode != 'RGBA':
            raise ValueError('model did not return RGBA')
        name = f'layer_{index}.png'
        temporary = folder / f'layer_{index}.tmp'
        layer.save(temporary, format='PNG')
        temporary.replace(folder / name)
        files.append(name)
    write(folder / 'result.json', {'layers': files, 'seconds': time.monotonic() - started, 'modelLoadSeconds': loaded,
                                  'peakMpsBytes': peak, 'options': options, 'model': 'Qwen-Image-Layered'})


def serve(root, model_dir):
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    jobs = root / 'jobs'
    jobs.mkdir(exist_ok=True, mode=0o700)
    child = None
    with (root / 'worker.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for marker in jobs.glob('*/running'):
            (marker.parent / 'failed').touch()  # Never silently replay interrupted inference.
            marker.unlink()
        def shutdown(*args):
            raise KeyboardInterrupt()
        signal.signal(signal.SIGTERM, shutdown)
        try:
            while True:
                ready = model_ready(model_dir)
                write(root / 'status.json', {'heartbeat': time.time(), 'ready': ready, 'busy': False})
                # ponytail: one GPU task at a time; use a scheduler only when multiple GPUs are deployed.
                for request in sorted(jobs.glob('*/request.json')) if ready else []:
                    folder = request.parent
                    if folder.is_symlink() or request.is_symlink() or not re.fullmatch(r'[a-f0-9-]{36}', folder.name):
                        continue
                    if any((folder / name).exists() for name in ('result.json', 'failed', 'cancel')):
                        continue
                    try:
                        if request.stat().st_size > 1024:
                            raise ValueError('oversized request')
                        validate_request(json.loads(request.read_text()))
                        (folder / 'running').touch()
                        with (folder / 'inference.log').open('wb') as log:
                            child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), 'infer',
                                                      '--root', str(folder), '--model-dir', str(model_dir)],
                                                     stdout=log, stderr=subprocess.STDOUT)
                            start = time.monotonic()
                            while child.poll() is None:
                                write(root / 'status.json', {'heartbeat': time.time(), 'ready': True, 'busy': True})
                                if (folder / 'cancel').exists() or time.monotonic() - start > 7000:
                                    child.terminate()
                                    try:
                                        child.wait(timeout=8)
                                    except subprocess.TimeoutExpired:
                                        child.kill()
                                        child.wait()
                                    break
                                time.sleep(1)
                            if child.returncode or not (folder / 'result.json').exists():
                                log.write(f'\nNative exit code: {child.returncode}; cancelled: {(folder / "cancel").exists()}\n'.encode())
                                (folder / 'failed').touch()
                    except (OSError, ValueError, TypeError):
                        (folder / 'failed').touch()
                    finally:
                        (folder / 'running').unlink(missing_ok=True)
                        child = None
                    break
                time.sleep(1)
        finally:
            if child is not None and child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
            write(root / 'status.json', {'heartbeat': time.time(), 'ready': False, 'busy': False})


if __name__ == '__main__':
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['serve', 'infer', 'download'])
    parser.add_argument('--root', type=Path, default=ROOT / '.local/local-model')
    parser.add_argument('--model-dir', type=Path)
    args = parser.parse_args()
    if args.action == 'download':
        from huggingface_hub import snapshot_download
        model = snapshot_download('Qwen/Qwen-Image-Layered', revision=MODEL_REVISION,
                                  allow_patterns=['*.json', '*.safetensors', '*.txt', '*.jinja'])
        args.root.mkdir(parents=True, exist_ok=True)
        (args.root / 'model-path.txt').write_text(model)
        print('Model downloaded:', model)
    else:
        model = (args.model_dir or Path((ROOT / '.local/local-model/model-path.txt').read_text().strip())).resolve()
        if args.action == 'infer':
            infer(args.root.resolve(), model)
        else:
            serve(args.root.resolve(), model)
