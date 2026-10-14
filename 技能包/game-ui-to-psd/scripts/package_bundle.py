"""Package the complete sibling bundle without local interpreter settings."""
import argparse, hashlib, json, zipfile
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--bundle', required=True)
parser.add_argument('--out', required=True)
args = parser.parse_args()
bundle = Path(args.bundle).resolve()
destination = Path(args.out).resolve()
if destination.is_relative_to(bundle):
    raise ValueError('分享压缩包必须保存在技能包目录之外。')
excluded_dirs = {'__pycache__', '.git', '.pytest_cache', '.npm-cache', '.logs'}
excluded_files = {'runtime.local.json', '.env'}
files = [p for p in bundle.rglob('*') if p.is_file()
         and not (set(p.relative_to(bundle).parts) & excluded_dirs)
         and p.name not in excluded_files and not p.name.endswith(('.pyc', '.pyo'))]
destination.parent.mkdir(parents=True, exist_ok=True)
temporary = destination.with_suffix('.building.zip')
with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for file in files:
        archive.write(file, '技能包/' + file.relative_to(bundle).as_posix())
temporary.replace(destination)
report = {'status': 'PASS', 'file': str(destination), 'files': len(files),
          'bytes': destination.stat().st_size,
          'sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
          'localSettingsIncluded': False}
destination.with_suffix('.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf8')
print(json.dumps(report, ensure_ascii=False))

