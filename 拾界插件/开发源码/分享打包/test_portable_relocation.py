"""Exercise a freshly built portable bundle at a relocated Chinese path."""

import os
import importlib.util
import shutil
import subprocess
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BUILDER = Path(__file__).with_name("build_shijie_share.py")
spec = importlib.util.spec_from_file_location("share", BUILDER)
share = importlib.util.module_from_spec(spec)
spec.loader.exec_module(share)


class RelocationTest(unittest.TestCase):
    def test_isolated_path_uses_only_relocated_runtime(self):
        output = (ROOT / "测试结果").resolve(strict=True)
        temporary = Path(tempfile.mkdtemp(prefix="shijie-relocated-", dir=output)).resolve(strict=True)
        try:
            archive_path = temporary / "share.zip"
            share.build_archive(ROOT, archive_path)
            target = temporary / "接收者 目录"
            with zipfile.ZipFile(archive_path) as archive:
                archive.extractall(target)

            env = os.environ.copy()
            system_root = Path(env.get("SystemRoot", r"C:\Windows"))
            env["SystemRoot"] = str(system_root)
            env["PATH"] = str(system_root / "System32") + os.pathsep + str(system_root)
            env.pop("SHIJIE_PYTHON", None)
            env.pop("SHIJIE_CODEX_BIN", None)
            process = subprocess.run(
                [str(system_root / "System32/WindowsPowerShell/v1.0/powershell.exe"), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(target / "拾界插件/启动拾界.ps1"), "-CheckOnly"],
                env=env, cwd=target, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", timeout=90,
            )
            self.assertEqual(process.returncode, 0, process.stdout)
            self.assertIn("Python portable OK", process.stdout)
            self.assertIn("检查通过", process.stdout)
        finally:
            safe_root = output.resolve(strict=True)
            safe_target = temporary.resolve(strict=True)
            if not safe_target.is_relative_to(safe_root) or safe_target == safe_root or not safe_target.name.startswith("shijie-relocated-"):
                raise RuntimeError(f"Refusing to remove unexpected test directory: {safe_target}")
            for attempt in range(20):
                try:
                    shutil.rmtree(safe_target)
                    break
                except PermissionError:
                    if attempt == 19:
                        raise
                    time.sleep(0.5)


if __name__ == "__main__":
    unittest.main()
