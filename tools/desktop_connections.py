"""Read the explicitly installed desktop connections without exporting secrets."""
import importlib.util
from pathlib import Path
import sys
import types

def load_connections(base):
    source=Path(base).parent/'AI拆图助手/开发源码/自动拆图'
    if not source.is_dir():return None
    package='_shijie_desktop_connections'
    if package not in sys.modules:
        module=types.ModuleType(package);module.__path__=[str(source)];sys.modules[package]=module
    def load(name):
        ident=package+'.'+name
        if ident in sys.modules:return sys.modules[ident]
        spec=importlib.util.spec_from_file_location(ident,source/(name+'.py'))
        module=importlib.util.module_from_spec(spec);sys.modules[ident]=module
        spec.loader.exec_module(module);return module
    import PIL.Image, requests, numpy
    runtime=load('runtime')
    old=sys.modules.get('runtime');sys.modules['runtime']=runtime
    try:
        assistant=load('assistant_models');image=load('image_provider')
    finally:
        if old is None:sys.modules.pop('runtime',None)
        else:sys.modules['runtime']=old
    return assistant,image

def credentials(base,analysis,images,mode):
    modules=load_connections(base)
    value={'mode':mode,'company':{},'analysisProvider':analysis,'image':dict(images),
           'needsCodex':analysis=='codex' and mode=='assistant-plan' or images['provider']=='codex' and mode!='assistant-plan'}
    if analysis=='tygpt':
        if not modules:raise ValueError('本机TYGPT设置不可用，未改用Codex')
        value['tygpt']=modules[0].gateway_key()
    if images['provider']=='aimake':
        if not modules:raise ValueError('本机亿创设置不可用，未改用Codex')
        # key() imports the DPAPI helper by its historical module name.
        old=sys.modules.get('assistant_models');sys.modules['assistant_models']=modules[0]
        try:value['image']['key']=modules[1].key()
        finally:
            if old is None:sys.modules.pop('assistant_models',None)
            else:sys.modules['assistant_models']=old
    return value