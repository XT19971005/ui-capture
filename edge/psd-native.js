// Native PSD geometry: coordinates are absolute document pixels.
import svgpath from 'svgpath';
const K=.5522847498307936;
const knot=(x,y,ix=x,iy=y,ox=x,oy=y)=>({linked:false,points:[ix,iy,x,y,ox,oy]});
export const rgb8=c=>({r:Math.round((c?.r||0)*255),g:Math.round((c?.g||0)*255),b:Math.round((c?.b||0)*255)});
export function polygon(points,operation='combine'){return {open:false,operation,fillRule:'even-odd',knots:points.map(([x,y])=>knot(x,y))};}
export function roundedPath(n,insets=[0,0,0,0],operation='combine'){
 const [t,r,b,l]=insets,x=n.x+l,y=n.y+t,w=Math.max(0,n.width-l-r),h=Math.max(0,n.height-t-b);
 let rs=(n.radii||[0,0,0,0]).map(v=>Math.max(0,v));
 const f=Math.min(1,n.width/Math.max(1,rs[0]+rs[1]),n.width/Math.max(1,rs[3]+rs[2]),n.height/Math.max(1,rs[0]+rs[3]),n.height/Math.max(1,rs[1]+rs[2]));rs=rs.map(v=>v*f);
 const [a,c,d,e]=rs.map((v,i)=>[Math.max(0,v-(i===0||i===3?l:r)),Math.max(0,v-(i<2?t:b))]);
 return {open:false,operation,fillRule:'even-odd',knots:[
 knot(x+a[0],y,x+a[0]*(1-K),y),knot(x+w-c[0],y,undefined,undefined,x+w-c[0]*(1-K),y),
 knot(x+w,y+c[1],x+w,y+c[1]*(1-K)),knot(x+w,y+h-d[1],undefined,undefined,x+w,y+h-d[1]*(1-K)),
 knot(x+w-d[0],y+h,x+w-d[0]*(1-K),y+h),knot(x+e[0],y+h,undefined,undefined,x+e[0]*(1-K),y+h),
 knot(x,y+h-e[1],x,y+h-e[1]*(1-K)),knot(x,y+a[1],undefined,undefined,x,y+a[1]*(1-K))
 ]};
}
export function shape(layer,color,paths,clips=[]){
 if(!layer)return null;
 layer.name=layer.name.replace('背景与边框','矢量形状').replace('图标','矢量图标');
 layer.vectorFill={type:'color',color:rgb8(color)};
 layer.vectorMask={fillStartsWithAllPixels:false,paths:[...paths,...clips.map(n=>roundedPath(n,[0,0,0,0],'intersect'))]};
 layer.opacity=(layer.opacity??1)*(color?.a??1);return layer;
}
export function nativeText(layer,n,baseline){
 if(!layer)return null;
 const family=String(n.fontResolved||n.fontFamily?.split(',')[0].replace(/["']/g,'').trim()||'Microsoft YaHei'),bold=+n.fontWeight>=600,italic=n.fontStyle==='italic';
 const known={'microsoft yahei':'MicrosoftYaHei','微软雅黑':'MicrosoftYaHei','segoe ui':'SegoeUI','arial':'ArialMT','sans-serif':'ArialMT','system-ui':'SegoeUI','serif':'TimesNewRomanPSMT','times new roman':'TimesNewRomanPSMT','monospace':'Consolas','tahoma':'Tahoma','verdana':'Verdana','simsun':'SimSun','宋体':'SimSun','simhei':'SimHei','黑体':'SimHei'};
 const regular=known[family.toLowerCase()]||family.replace(/\s+/g,'');
 const variants={TimesNewRomanPSMT:['TimesNewRomanPS-BoldMT','TimesNewRomanPS-ItalicMT','TimesNewRomanPS-BoldItalicMT'],'MicrosoftYaHei':['MicrosoftYaHei-Bold'],SegoeUI:['SegoeUI-Bold','SegoeUI-Italic','SegoeUI-BoldItalic'],ArialMT:['Arial-BoldMT','Arial-ItalicMT','Arial-BoldItalicMT'],Tahoma:['Tahoma-Bold'],Verdana:['Verdana-Bold','Verdana-Italic','Verdana-BoldItalic']};
 const variant=(name)=>variants[name]?.[bold&&italic?2:italic?1:0];
 const base=(bold||italic)?variant(regular)||regular:regular;
 const text=String(n.text||'');
 const runs=[];
 // CSS font fallback is explicit in PSD, avoiding Segoe UI missing Chinese glyphs on edit.
 for(const char of text){const font=/[\u2190-\u2bff]/.test(char)?'SegoeUISymbol':char.codePointAt(0)>=0x1f000?'SegoeUIEmoji':/[\u2e80-\u9fff\uff00-\uffef]/.test(char)&&!/yahei|sim|pingfang|noto|sourcehan/i.test(base)?(/TimesNewRoman|serif/i.test(base)?'SimSun':bold?'MicrosoftYaHei-Bold':'MicrosoftYaHei'):base;const tracking=Math.round(Math.max(-1000,Math.min(10000,((n.letterSpacing||0)+(/[ \u00a0]/.test(char)?n.wordSpacing||0:0))*1000/(n.fontSize||14))));const prev=runs.at(-1);if(prev?.style.font.name===font&&prev.style.tracking===tracking)prev.length+=char.length;else runs.push({length:char.length,style:{font:{name:font},tracking,...(font==='SegoeUISymbol'||font==='SegoeUIEmoji'?{fauxBold:false,fauxItalic:false}:{})}});}
 layer.name='可编辑文字 · '+String(n.name||text).slice(0,80);
 layer.text={text,transform:[1,0,0,1,n.x,baseline],shapeType:'point',antiAlias:'smooth',orientation:'horizontal',style:{font:{name:base},fontSize:n.fontSize||14,fauxBold:bold&&!/Bold/i.test(base),fauxItalic:italic&&!/Italic/i.test(base),fillColor:rgb8(n.color),underline:(n.textDecoration||'').includes('underline'),strikethrough:(n.textDecoration||'').includes('line-through'),ligatures:n.fontVariantLigatures!=='none',leading:n.lineHeight||n.fontSize*1.2,autoLeading:false,tracking:Math.round(Math.max(-1000,Math.min(10000,(n.letterSpacing||0)*1000/(n.fontSize||14))))},styleRuns:runs,paragraphStyle:{justification:'left'}};
 layer.opacity=(layer.opacity??1)*(n.color?.a??1);return layer;
}
export function pathData(d,transform=''){
 const p=svgpath(d);if(p.err)throw Error(p.err);
 p.transform(transform).abs().unshort().unarc();
 const paths=[];let current,x=0,y=0;
 function begin(a,b){current={open:true,operation:'combine',fillRule:'non-zero',knots:[knot(a,b)]};paths.push(current);x=a;y=b;}
 p.iterate(s=>{const cmd=s[0];if(cmd==='M'){begin(s[1],s[2]);return;}if(!current)throw Error('SVG 路径缺少起点');
 if(cmd==='Z'){current.open=false;const first=current.knots[0],last=current.knots.at(-1);if(current.knots.length>1&&last.points[2]===first.points[2]&&last.points[3]===first.points[3]){first.points[0]=last.points[0];first.points[1]=last.points[1];current.knots.pop();}x=first.points[2];y=first.points[3];return;}
 let nx,ny,c1x=x,c1y=y,c2x,c2y;
 if(cmd==='L'){nx=s[1];ny=s[2];}else if(cmd==='H'){nx=s[1];ny=y;}else if(cmd==='V'){nx=x;ny=s[1];}
 else if(cmd==='C'){[c1x,c1y,c2x,c2y,nx,ny]=s.slice(1);}
 else if(cmd==='Q'){nx=s[3];ny=s[4];c1x=x+(s[1]-x)*2/3;c1y=y+(s[2]-y)*2/3;c2x=nx+(s[1]-nx)*2/3;c2y=ny+(s[2]-ny)*2/3;}
 else throw Error('不支持的 SVG 路径指令');
 current.knots.at(-1).points.splice(4,2,c1x,c1y);current.knots.push(knot(nx,ny,c2x??nx,c2y??ny));x=nx;y=ny;
 });
 return {paths:paths.filter(p=>p.knots.length>1),d:p.toString()};
}
export function solidSVG(n){
 const doc=new DOMParser().parseFromString(n.svg,'image/svg+xml'),root=doc.documentElement;
 if(doc.querySelector('parsererror,filter,mask,clipPath,use,image,text,foreignObject,pattern,linearGradient,radialGradient'))throw Error('含复杂效果或嵌入内容');
 const vb=(root.getAttribute('viewBox')||'0 0 '+n.width+' '+n.height).split(/[\s,]+/).map(Number);
 if(vb.length!==4||!vb.every(Number.isFinite)||vb[2]<=0||vb[3]<=0)throw Error('无效 viewBox');
 const sx=n.width/vb[2],sy=n.height/vb[3],stretch=root.getAttribute('preserveAspectRatio')==='none',scale=stretch?null:Math.min(sx,sy);
 const ax=scale??sx,ay=scale??sy,base='translate('+(n.x+(n.width-vb[2]*ax)/2)+','+(n.y+(n.height-vb[3]*ay)/2)+') scale('+ax+','+ay+') translate('+(-vb[0])+','+(-vb[1])+')';
 const layers=[];let count=0;
 function parseColor(v){if(v==='none')return null;const c=document.createElement('canvas').getContext('2d');if(!CSS.supports('color',v)||/url|currentColor|var\(/i.test(v))throw Error('非纯色 SVG');c.fillStyle=v;c.fillRect(0,0,1,1);const p=c.getImageData(0,0,1,1).data;return {r:p[0]/255,g:p[1]/255,b:p[2]/255,a:p[3]/255};}
 function walk(el,transform,parent){
  if(++count>1000)throw Error('SVG 图层过多');
  const type=el.localName;if(['defs','title','desc','metadata','style','script'].includes(type))return;
  const style={...parent};for(const key of ['fill','stroke','stroke-width','stroke-linecap','stroke-linejoin','fill-rule','fill-opacity','stroke-opacity']){const v=el.style?.getPropertyValue(key)||el.getAttribute(key);if(v)style[key]=v;}
  const opacity=parent.opacity*+(el.getAttribute('opacity')||el.style?.opacity||1);
  const tr=transform+' '+(el.getAttribute('transform')||'');
  if(type==='g'||type==='svg'){for(const child of el.children)walk(child,tr,{...style,opacity});return;}
  const num=k=>parseFloat(el.getAttribute(k)||0);let d='';
  if(type==='path')d=el.getAttribute('d')||'';
  else if(type==='rect'){const x=num('x'),y=num('y'),w=num('width'),h=num('height'),rx=Math.min(w/2,num('rx')||num('ry')),ry=Math.min(h/2,num('ry')||rx);d=rx?('M'+(x+rx)+' '+y+'H'+(x+w-rx)+'A'+rx+' '+ry+' 0 0 1 '+(x+w)+' '+(y+ry)+'V'+(y+h-ry)+'A'+rx+' '+ry+' 0 0 1 '+(x+w-rx)+' '+(y+h)+'H'+(x+rx)+'A'+rx+' '+ry+' 0 0 1 '+x+' '+(y+h-ry)+'V'+(y+ry)+'A'+rx+' '+ry+' 0 0 1 '+(x+rx)+' '+y+'Z'):('M'+x+' '+y+'h'+w+'v'+h+'h'+(-w)+'Z');}
  else if(type==='circle'||type==='ellipse'){const x=num('cx'),y=num('cy'),rx=type==='circle'?num('r'):num('rx'),ry=type==='circle'?rx:num('ry');d='M'+(x-rx)+' '+y+'a'+rx+' '+ry+' 0 1 0 '+rx*2+' 0a'+rx+' '+ry+' 0 1 0 '+(-rx*2)+' 0Z';}
  else if(type==='line')d='M'+num('x1')+' '+num('y1')+'L'+num('x2')+' '+num('y2');
  else if(type==='polygon'||type==='polyline'){const points=(el.getAttribute('points')||'').trim().split(/[\s,]+/).map(Number);d=points.map((p,i)=>(i%2?' ':i?'L':'M')+p).join('')+(type==='polygon'?'Z':'');}
  else throw Error('未支持的 SVG 元素 '+type);
  if(!d)return;const parsed=pathData(d,tr);parsed.paths.forEach(p=>p.fillRule=style['fill-rule']==='evenodd'?'even-odd':'non-zero');
  const fill=parseColor(style.fill),stroke=parseColor(style.stroke);
  if(fill)layers.push({...parsed,color:{...fill,a:fill.a*opacity*+style['fill-opacity']},kind:'fill'});
  if(stroke&&parseFloat(style['stroke-width'])>0){
   const axes=svgpath('M0 0L1 0L0 1').transform(tr).abs();axes.iterate(()=>{});const a=axes.segments;
   const u=Math.hypot(a[1][1]-a[0][1],a[1][2]-a[0][2]),v=Math.hypot(a[2][1]-a[0][1],a[2][2]-a[0][2]);if(Math.abs(u-v)>.001)throw Error('非等比 SVG 描边');
   layers.push({...parsed,color:{...stroke,a:stroke.a*opacity*+style['stroke-opacity']},kind:'stroke',strokeWidth:parseFloat(style['stroke-width'])*u,lineCap:style['stroke-linecap'],lineJoin:style['stroke-linejoin']});
  }
 }
 walk(root,base,{fill:'black',stroke:'none','stroke-width':1,'stroke-linecap':'butt','stroke-linejoin':'miter','fill-opacity':1,'stroke-opacity':1,opacity:1});
 return layers;
}
