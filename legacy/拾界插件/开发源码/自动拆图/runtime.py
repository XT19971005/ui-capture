"""Portable source paths; private task directories supplied by the service."""
import os, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
STATE = Path(os.environ.get('SHIJIE_TASK_ROOT') or tempfile.gettempdir())
TEMP = STATE / 'tmp'
TEMP.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(TEMP)
for name in ('TEMP', 'TMP', 'TMPDIR'):
    os.environ[name] = str(TEMP)
sys.dont_write_bytecode = True
