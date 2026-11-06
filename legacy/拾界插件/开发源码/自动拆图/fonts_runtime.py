"""Resolve the same font faces for Pillow fitting and Node PSD rendering.

Keep deployed Linux fonts when installed; otherwise use the licensed WOFF2
faces already shipped with the web app. Pillow and Node Canvas both read them
directly, so desktop workers need no OS font installation or conversion cache.
"""
import json
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_BUNDLED = _HERE.parents[3] / 'shijie/static/server/fonts'


def resolve_fonts():
    fonts = []
    for family, weight, installed, bundled in json.loads((_HERE / 'fonts.json').read_text(encoding='utf8')):
        candidates = (Path(installed), _BUNDLED / bundled)
        file = next((file for file in candidates if file.is_file()), None)
        if file is None:
            raise RuntimeError(f'缺少字体 {family} ({weight})：' + ' / '.join(map(str, candidates)))
        fonts.append((family, weight, str(file.resolve())))
    return fonts


FONTS = resolve_fonts()


def font_file(family, weight=400):
    faces = [font for font in FONTS if font[0] == family]
    if not faces:
        raise ValueError('未配置字体：' + family)
    return min(faces, key=lambda face: abs(face[1] - weight))[2]
