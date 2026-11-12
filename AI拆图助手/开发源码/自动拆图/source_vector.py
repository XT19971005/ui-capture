"""Reconstruct native paths from observed ink, never a model's guessed silhouette."""
import copy
import base64
import json
import math
import re
import subprocess

import cv2
import numpy as np
from PIL import Image

from runtime import ROOT


class SourceVectorError(ValueError):
    pass


def _failure(name, reason):
    return SourceVectorError('矢量“'+name+'”未通过原图贴合检查：'+reason+'；已保留完成结果，请调整该对象范围或分类，不会改用生图')


def observed_ink(image, layer, companions=(), check_connectivity=True):
    name = layer['name']
    box = layer['box']
    margin = max(3, min(12, math.ceil(min(box['width'], box['height'])*.2)))
    left = max(0, math.floor(box['x'])-margin)
    top = max(0, math.floor(box['y'])-margin)
    right = min(image.width, math.ceil(box['x']+box['width'])+margin)
    bottom = min(image.height, math.ceil(box['y']+box['height'])+margin)
    if right-left < 3 or bottom-top < 3 or (right-left)*(bottom-top) > 4000000:
        raise _failure(name, '参考范围不可可靠识别')
    patch = np.asarray(image.crop((left, top, right, bottom)).convert('RGB')).astype(float)
    from engine import logo_background
    background = logo_background(patch)
    fill = layer['native']['fill']
    foreground = np.array([int(fill[i:i+2], 16) for i in (1, 3, 5)], dtype=float)
    ys, xs = np.indices(patch.shape[:2])
    inside = ((xs+left >= box['x']) & (xs+left < box['x']+box['width']) &
              (ys+top >= box['y']) & (ys+top < box['y']+box['height']))

    def alpha_for(color):
        direction = color-background
        length = np.sum(direction**2, axis=2)
        alpha = np.sum((patch-background)*direction, axis=2)/np.maximum(length, 1)
        residual = np.linalg.norm(patch-(background+alpha[..., None]*direction), axis=2)
        contrast = np.linalg.norm(patch-background, axis=2)
        eligible = (length > 24**2) & (residual < (14 if color.max()<90 else 26)) & (contrast > 14)
        if color.max()<90:
            # A dark bat is not the brighter blue/green rail crossing its box.
            eligible &= patch.max(axis=2) < max(55, float(color.max())+22)

        return np.where(eligible, np.clip(alpha, 0, 1), 0)

    # Small second inks may be much darker than the model's suggested fill.
    # Hue identifies the observed ink; its actual source colour supplies the fill.
    hsv = cv2.cvtColor(patch.astype('uint8'), cv2.COLOR_RGB2HSV).astype(float)
    wanted = cv2.cvtColor(np.uint8([[foreground]]), cv2.COLOR_RGB2HSV)[0, 0].astype(float)
    material = np.median(hsv[~inside], axis=0) if np.any(~inside) else np.median(hsv.reshape(-1, 3), axis=0)
    hue_delta = lambda values, h: np.minimum(np.abs(values-h), 180-np.abs(values-h))
    chromatic = wanted[2] > 75 and wanted[1] > 85 and hue_delta(material[0], wanted[0]) > 20
    if chromatic:
        selected = (hue_delta(hsv[:, :, 0], wanted[0]) < 13) & (hsv[:, :, 1] > 80) & (hsv[:, :, 2] > 35)
        selected &= cv2.dilate(inside.astype('uint8'), np.ones((3, 3), np.uint8)) > 0
        if np.any(selected):
            pixels = patch[selected]
            brightness = pixels.max(axis=1)
            foreground = np.median(pixels[brightness >= np.quantile(brightness, .65)], axis=0)
            exclusion = cv2.dilate(selected.astype('uint8'), np.ones((3, 3), np.uint8))
            background = cv2.inpaint(patch.astype('uint8'), exclusion, 3, cv2.INPAINT_TELEA).astype(float)
        if min(box['width'], box['height']) <= 8:
            inside = cv2.dilate(inside.astype('uint8'), np.ones((5, 5), np.uint8)) > 0

    alpha = alpha_for(foreground)
    if chromatic:
        alpha = np.where(cv2.dilate(selected.astype('uint8'),np.ones((3,3),np.uint8))>0,alpha,0)

    def components(values):
        count, labels, stats, _ = cv2.connectedComponentsWithStats((values >= .5).astype('uint8'), 8)
        keep = np.zeros(values.shape, bool)
        accepted = 0
        touches_boundary = False
        boundary_core = accepted_core = 0
        for index in range(1, count):
            region = labels == index
            core = region & inside & (values >= .65)
            if not np.any(core):
                continue
            # A neighboring dark object crossing the crop is not this flat mark.
            if np.any(region[0]) or np.any(region[-1]) or np.any(region[:, 0]) or np.any(region[:, -1]):
                touches_boundary = True
                boundary_core = max(boundary_core, int(np.count_nonzero(core)))
                continue  # A separate neighbouring rail must not veto a bounded mark.

            if np.count_nonzero(region & inside)/stats[index, cv2.CC_STAT_AREA] < .55:
                continue
            keep |= region
            accepted += 1
            accepted_core += int(np.count_nonzero(core))
        if touches_boundary and (not accepted or boundary_core > accepted_core):
            raise _failure(name, '目标轮廓与参考边缘相连，未找到独立完整色块')
        if not accepted or accepted > 32:
            raise _failure(name, '没有找到可信的独立纯色色块')
        return keep

    keep = components(alpha)
    cores = keep & (alpha >= .8)
    if not np.any(cores):
        raise _failure(name, '缺少可确认的主体颜色')
    pixels = patch[cores]
    if foreground.max() < 90 and len(pixels) >= 4:
        luminance = pixels @ np.array([.2126, .7152, .0722])
        pixels = pixels[luminance <= np.quantile(luminance, .4)]
    observed_color = np.median(pixels, axis=0)
    if np.quantile(np.linalg.norm(pixels-observed_color, axis=1), .9) > 42:
        raise _failure(name, '局部具有复杂材质，不能可靠还原为纯色矢量')
    alpha = alpha_for(observed_color)
    if chromatic:
        alpha = np.where(cv2.dilate(selected.astype('uint8'),np.ones((3,3),np.uint8))>0,alpha,0)
    # The body silhouette continues beneath separately editable eyes/markings.
    for part in companions:
        extra, (ex, ey), _ = observed_ink(image, part, check_connectivity=False)
        x0, y0 = max(left, ex), max(top, ey)
        x1, y1 = min(right, ex+extra.shape[1]), min(bottom, ey+extra.shape[0])
        if x1 > x0 and y1 > y0:
            alpha[y0-top:y1-top, x0-left:x1-left] = np.maximum(
                alpha[y0-top:y1-top, x0-left:x1-left], extra[y0-ey:y1-ey, x0-ex:x1-ex])
            # Colour transitions around an overlaid eye are still opaque body,
            # not transparent material. Use source contrast only in this small
            # observed component neighborhood, never a rectangular blind fill.
            q=part['box']
            ax0=max(left,math.floor(min(ex,q['x']))-2);ay0=max(top,math.floor(min(ey,q['y']))-2)
            ax1=min(right,math.ceil(max(ex+extra.shape[1],q['x']+q['width']))+2)
            ay1=min(bottom,math.ceil(max(ey+extra.shape[0],q['y']+q['height']))+2)
            magnitude=np.linalg.norm(patch-background,axis=2)/np.maximum(1,np.linalg.norm(observed_color-background,axis=2))
            alpha[ay0-top:ay1-top,ax0-left:ax1-left]=np.maximum(alpha[ay0-top:ay1-top,ax0-left:ax1-left],np.clip(magnitude[ay0-top:ay1-top,ax0-left:ax1-left],0,1))

    keep = components(alpha)
    # Compare topology with source-supported foreground; do not fill gaps
    # blindly or merge independent eye/mark components.
    contrast = np.linalg.norm(patch-background, axis=2)
    border = np.concatenate([contrast[0], contrast[-1], contrast[:, 0], contrast[:, -1]])
    source_support = contrast > max(18, float(np.quantile(border, .75))*2.5)
    _, reference_labels = cv2.connectedComponents(source_support.astype('uint8'), connectivity=8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(keep.astype('uint8'), connectivity=8)
    for reference in (np.unique(reference_labels[keep]) if check_connectivity else []):
        if not reference:
            continue
        pieces = [i for i in range(1, count) if stats[i, cv2.CC_STAT_AREA] >= 1 and
                  np.any((labels == i) & (reference_labels == reference) & (alpha >= .7))]
        if len(pieces) > 1:
            raise _failure(name, '原图连续轮廓仍被提取成断片，未发布残缺主体')
    # Keep fractional edge coverage around the selected connected components.
    support = cv2.dilate(keep.astype('uint8'), np.ones((3, 3), np.uint8)) > 0
    alpha = np.where(support, alpha, 0)
    yy, xx = np.where(keep)
    x0, y0 = max(0, int(xx.min())-1), max(0, int(yy.min())-1)
    x1, y1 = min(alpha.shape[1], int(xx.max())+2), min(alpha.shape[0], int(yy.max())+2)
    return alpha[y0:y1, x0:x1], (left+x0, top+y0), '#'+''.join(f'{int(round(c)):02x}' for c in observed_color)


def _render(d, width, height):
    script = """const fs=require('fs');let cv;try{cv=require('./依赖/构建工具/node_modules/@napi-rs/canvas')}catch{cv=require('@napi-rs/canvas')};
const n=JSON.parse(fs.readFileSync(0,'utf8')),c=cv.createCanvas(n.width,n.height),x=c.getContext('2d');
x.fillStyle='white';x.fill(new cv.Path2D(n.d),'evenodd');
process.stdout.write(Buffer.from(x.getImageData(0,0,n.width,n.height).data).toString('base64'));"""
    result = subprocess.run(['node', '-e', script], cwd=ROOT,
                            input=json.dumps({'d': d, 'width': width, 'height': height}),
                            capture_output=True, text=True, check=True, timeout=20)
    return np.frombuffer(base64.b64decode(result.stdout), np.uint8).reshape(height, width, 4)[:, :, 3]


def topology_matches(expected, actual, scale):
    """Global overlap cannot prove that a neck, counter or separate eyes survived."""
    ec, el, es, _ = cv2.connectedComponentsWithStats(expected.astype('uint8'), connectivity=8)
    ac, al, ast, _ = cv2.connectedComponentsWithStats(actual.astype('uint8'), connectivity=8)
    minimum = max(1, scale*scale*.2)
    for labels, stats, count, other in [(el, es, ec, al), (al, ast, ac, el)]:
        for i in range(1, count):
            if stats[i, cv2.CC_STAT_AREA] < minimum:
                continue
            ids, areas = np.unique(other[labels == i], return_counts=True)
            significant = [label for label, area in zip(ids, areas) if label and area >= minimum]
            if len(significant) != 1:
                return False
    backgrounds=[]
    for empty in (~expected, ~actual):
        hc, hl, hs, _ = cv2.connectedComponentsWithStats(empty.astype('uint8'), connectivity=4)
        closed=set()
        for i in range(1,hc):
            x,y,w,h,area=hs[i]
            if area>=minimum and x>0 and y>0 and x+w<expected.shape[1] and y+h<expected.shape[0]:closed.add(i)
        backgrounds.append((hl,hs,closed))
    for (labels,stats,closed),(other,_,other_closed) in [backgrounds,backgrounds[::-1]]:
        for i in closed:
            region=labels==i
            if np.count_nonzero((other>0)&region)/stats[i,cv2.CC_STAT_AREA]<.8:return False
            ids,areas=np.unique(other[region],return_counts=True)
            matches=[label for label,area in zip(ids,areas) if label and area>=minimum]
            if len(matches)!=1 or matches[0] not in other_closed:return False
    return True


def reconstruct(image, layer, node, companions=(), check_connectivity=True):
    """Return a source-aligned editable path, or fail before publishing an approximation."""
    alpha, (x, y), fill = observed_ink(image, layer, companions, check_connectivity)
    scale = max(1, min(8, int(math.sqrt(4000000/max(1, alpha.size)))))
    enlarged = cv2.resize(alpha, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    ink = (enlarged >= .5).astype('uint8')*255
    coarse_count = cv2.connectedComponents((alpha >= .5).astype('uint8'), connectivity=8)[0]-1
    fine_count = cv2.connectedComponents((ink > 0).astype('uint8'), connectivity=8)[0]-1
    if check_connectivity and fine_count > coarse_count:
        # Cubic interpolation can open a subpixel neck present in the source.
        # Limit repair to half a source pixel and locally supported coverage.
        support = cv2.resize(alpha, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR) >= .4
        radius = max(1, scale//2)
        closed = cv2.morphologyEx((ink > 0).astype('uint8'), cv2.MORPH_CLOSE, np.ones((radius*2+1, radius*2+1), np.uint8)) > 0
        ink = np.where((ink > 0) | (closed & support), 255, 0).astype('uint8')
        if cv2.connectedComponents((ink > 0).astype('uint8'), connectivity=8)[0]-1 != coarse_count:
            raise _failure(layer['name'], '亚像素拟合破坏原图连接处，暂不发布断裂矢量')
    from vector_trace import trace
    d = trace(ink)
    if not d or len(d) > 120000:
        raise _failure(layer['name'], '平滑轮廓为空或过于复杂')
    rendered = _render(d, ink.shape[1], ink.shape[0]) >= 128
    expected = ink > 0
    union = np.count_nonzero(expected | rendered)
    iou = np.count_nonzero(expected & rendered)/max(1, union)
    lost = np.count_nonzero(expected & ~rendered)/max(1, np.count_nonzero(expected))
    # A high global overlap must not conceal a missing disconnected eye/dot.
    count, labels, stats, _ = cv2.connectedComponentsWithStats(expected.astype('uint8'), 8)
    coverage = [np.count_nonzero(rendered & (labels == i))/stats[i, cv2.CC_STAT_AREA] for i in range(1, count)]
    expected_edge = expected & ~(cv2.erode(expected.astype('uint8'), np.ones((3, 3), np.uint8)) > 0)
    actual_edge = rendered & ~(cv2.erode(rendered.astype('uint8'), np.ones((3, 3), np.uint8)) > 0)
    to_expected = cv2.distanceTransform((~expected_edge).astype('uint8'), cv2.DIST_L2, 5)
    to_actual = cv2.distanceTransform((~actual_edge).astype('uint8'), cv2.DIST_L2, 5)
    drift = np.concatenate([to_expected[actual_edge], to_actual[expected_edge]])/scale
    contour95 = float(np.quantile(drift, .95)) if len(drift) else float('inf')
    if not topology_matches(expected, rendered, scale):
        raise _failure(layer['name'], '平滑后出现断片、合并独立色块或填掉孔洞，未发布错误矢量')
    if iou < .86 or lost > .10 or contour95 > .6 or any(value < .9 for value in coverage):
        raise _failure(layer['name'], '平滑后轮廓偏离原图或丢失细节')
    # VTracer emits absolute M/L/C/Q/H/V/Z coordinates, so uniform scaling is exact.
    tokens = re.findall(r'[A-Za-z]|[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?', d)
    d = ' '.join(t if t.isalpha() else str(round(float(t)/scale, 4)) for t in tokens)
    result = copy.deepcopy(node)
    result.update(type='path', x=x, y=y, width=alpha.shape[1], height=alpha.shape[0], d=d,
                  fill=fill, fillRule='evenodd', provenance='source-observed-native',
                  sourceFidelity={'version': 2, 'connectivityChecked': True, 'connectivityMode': 'object' if check_connectivity else 'independent-colour-parts',
                                  'method': 'observed-ink-bezier', 'silhouetteIoU': round(iou, 5),
                                  'lostInkRatio': round(lost, 5), 'contour95Px': round(contour95, 4), 'sourceBox': copy.deepcopy(layer['box'])},
                  assetReviewStatus='NEEDS_REVIEW', review=True,
                  reviewIssue='已按原图色块拟合并检查轮廓贴合；仍需核对原图中模糊或遮挡细节。')
    return result
