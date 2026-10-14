import runtime from '../../../技能包/game-ui-to-psd/scripts/style_runtime.cjs';
import {pathData} from '../../插件程序/edge/psd-native.js';
export const {normalizeStyle,normalizeGradient,normalizeMask,maskPath,gradientData,nativeEffects,stylePadding,gradientPaint,styleCanvas,displayMaskCanvas,nativeMask,nativeToStyle,styleSvg,applyDom,alphaBounds,fitGradientEffects,validatePath,definitionId}=runtime;
export function transformMask(mask,{sx=1,sy=1,dx=0,dy=0}={}){const m=normalizeMask(mask);if(!m)return null;const out={...m,x:m.x*sx+dx,y:m.y*sy+dy,width:m.width*sx,height:m.height*sy};if(m.type==='path')out.d=pathData(m.d,`matrix(${sx},0,0,${sy},${dx},${dy})`).d;return normalizeMask(out);}
