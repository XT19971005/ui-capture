"""Create a relocatable Shijie bundle with only the runtime and shared skill deps."""
from __future__ import annotations

import argparse
import os
import re
import zipfile
from pathlib import Path


ROOT_FILES = {
    "启动拾界.ps1", "启动拾界.cmd", "创建拾界快捷方式.ps1", "连接智能拆图.ps1", "打开拾界.html", "目录说明.txt"
}
PLUGIN_DIRS = {
    "开发源码", "插件程序", "依赖/运行环境/python", "依赖/运行环境/node", "依赖/图像重建", "依赖/构建工具/node_modules/playwright", "依赖/构建工具/node_modules/playwright-core"
}
SKILL_DIRS = {"game-ui-to-psd", "imagegen", "依赖/Node", "依赖/Python"}
SKILL_FILES = {"同步到Codex.ps1", "维护约定.md"}
BANNED_PARTS = {
    "__pycache__", ".git", ".venv", "venv", "models", "model", "torch", "torchvision",
    "transformers", "rapidocr", "qwen", "paddle", "onnxruntime", "缓存", "自检记录",
    "测试结果", "归档", "项目", "工程", "交付包", "运行临时", "pip缓存", "npm缓存",
    "npm-cache", "pip-cache", "运行", "测试", "tests", "test", "示例",
}
BANNED_NAMES = {
    "runtime.local.json", "auth.json", "service.json", "native-host.json", "native-host.cmd",
    "python-embed.zip", "grounding.py", "diagnose_palette.py", "diagnose_font.cjs", "构建psd.cjs", "image-recognition.js", "token.json", "credentials.json", "download_models.py", ".env", "启动.log",
}
BANNED_SUFFIXES = {".psd", ".psb", ".safetensors", ".pt", ".pth", ".ckpt", ".onnx", ".gguf", ".traineddata", ".pyc", ".pyo", ".log"}


def is_allowed(relative: Path) -> bool:
    parts = relative.as_posix().split("/")
    if len(parts) < 2 or any(part in ("", ".", "..") for part in parts):
        return False
    lower = [part.lower() for part in parts]
    if any(part.startswith(".") for part in parts):
        return False
    if any(part in BANNED_PARTS for part in lower):
        return False
    name = lower[-1]
    # Keep runtime modules such as requests/auth.py; block credential data and
    # their backup suffix chains, including auth.json.bak and token.json.old.
    sensitive_extensions={'.json','.toml','.yaml','.yml','.ini','.cfg','.env','.pem','.key','.txt','.bak','.backup','.old'}
    runtime_code_extensions={'.py','.pyi','.pyd','.js','.cjs','.mjs','.ts','.map','.so','.dll'}
    if re.match(r'^(auth|credentials?|tokens?)([._-]|$)',name) and (any(suffix in sensitive_extensions for suffix in Path(name).suffixes) or Path(name).suffix not in runtime_code_extensions):
        return False
    if any(name == banned or name.startswith(banned + ".") for banned in BANNED_NAMES) or Path(name).suffix in BANNED_SUFFIXES:
        return False
    if name.startswith("test_") or name.startswith("测试") or name.startswith("验证"):
        return False
    if lower[0] == "拾界插件":
        sub = "/".join(parts[1:])
        if sub.lower().startswith("插件程序/edge/vendor/ocr/"):
            return False
        return sub in ROOT_FILES or any(sub.startswith(folder + "/") for folder in PLUGIN_DIRS)
    if lower[0] == "技能包":
        sub = "/".join(parts[1:])
        return sub in SKILL_FILES or any(sub.startswith(folder + "/") for folder in SKILL_DIRS)
    return False


def build_archive(root: Path, output: Path) -> int:
    root = root.resolve(strict=True)
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    temporary = output.with_suffix('.building.zip')
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
        for top in ("拾界插件", "技能包"):
            base = root / top
            if not base.is_dir():
                raise FileNotFoundError(base)
            for directory, dirs, files in os.walk(base, followlinks=False):
                current = Path(directory)
                dirs[:] = [name for name in dirs if not (current / name).is_symlink() and (current / name).resolve().is_relative_to(root)]
                for name in files:
                    path = current / name
                    resolved = path.resolve()
                    if path.is_symlink() or not resolved.is_relative_to(root) or resolved in (output, temporary):
                        continue
                    relative = path.relative_to(root)
                    if is_allowed(relative):
                        archive.write(path, relative.as_posix())
                        written += 1
    if not written:
        temporary.unlink(missing_ok=True)
        raise ValueError("No shareable files found")
    with zipfile.ZipFile(temporary) as archive:
        if archive.testzip() is not None:
            raise ValueError('分享压缩包校验失败')
    temporary.replace(output)
    return written


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(f"Packed {build_archive(args.root, args.out)} files: {args.out}")
