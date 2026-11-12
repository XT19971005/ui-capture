"""Bounded call-site diagnostics without image, prompt, locals or credentials."""
import functools
import traceback
from pathlib import Path

def path_failure_context(function):
    @functools.wraps(function)
    def wrapped(*args,**kwargs):
        try:
            return function(*args,**kwargs)
        except TypeError as error:
            frames=traceback.extract_tb(error.__traceback__)[-10:]
            sites=' > '.join(f'{Path(f.filename).name}:{f.lineno}:{f.name}' for f in frames)
            raise RuntimeError(f'专家类型错误 [{sites}] {error}') from error
    return wrapped
