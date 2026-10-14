"""Portable lightweight paths; temporary task data stays inside this application."""
import os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
DEPS=ROOT/'依赖/自动拆图';STATE=DEPS/'运行';STATE.mkdir(parents=True,exist_ok=True)
TEMP=ROOT/'依赖/运行临时';TEMP.mkdir(parents=True,exist_ok=True)
for name in ('TEMP','TMP','TMPDIR'):os.environ[name]=str(TEMP)
os.environ['PYTHONDONTWRITEBYTECODE']='1';sys.dont_write_bytecode=True
node=ROOT/'依赖/运行环境/node'
if (node/'node.exe').is_file():os.environ['PATH']=str(node)+os.pathsep+os.environ.get('PATH','')
python=ROOT/'依赖/运行环境/python'
if (python/'python.exe').is_file():
 os.environ['PATH']=str(python)+os.pathsep+os.environ.get('PATH','')
 os.environ['SHIJIE_PYTHON']=str(python/'python.exe')
for path in (ROOT.parent/'技能包/依赖/Python',ROOT/'依赖/运行环境/python/site-packages'):
 if path.is_dir():sys.path.insert(0,str(path))
