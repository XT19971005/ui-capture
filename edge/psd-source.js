// Source for the bundled psd-exporter.js. Build dependencies are listed in BUILD.txt.
import {writePsd} from 'ag-psd';
import {textLayoutTools} from '../../开发源码/文字排版/text-layout.js';
const Text=textLayoutTools();
import {roundedPath,polygon,shape,nativeText,solidSVG,rgb8} from './psd-native.js';

const MAX_PAGE_PIXELS=12000000,MAX_LAYER_PIXELS=32000000;
export function validateCapture(data){
  if(!data||!['gugu-page-to-figma','shijie-ui-capture'].includes(data.format)||data.version!==1||!data.root)throw Error('请选择拾界或旧版咕咕扩展生成的 JSON 文件。');
  if(!Number.isFinite(data.width)||!Number.isFinite(data.height)||data.width<=0||data.height<=0||data.width>30000||data.height>30000)throw Error('画布尺寸无效。');
  let count=0,bytes=0;
  function visit(n,depth){
    if(!n||depth>100||++count>6000)throw Error('图层过多或层级过深。');
    if(!['group','box','text','image','svg'].includes(n.type))throw Error('未知图层类型。');
    if(n.type!=='group'){
      for(const key of ['x','y','width','height'])if(!Number.isFinite(n[key])||Math.abs(n[key])>100000)throw Error('无效的图层坐标。');
      if(n.width<=0||n.height<=0)throw Error('无效的图层尺寸。');
    }
    if(n.image){if(typeof n.image!=='string'||!/^data:image\/(png|jpeg|webp);base64,/.test(n.image))throw Error('图片必须为内嵌 PNG、JPEG 或 WebP。');bytes+=n.image.length;}
    if(bytes>26000000||n.text?.length>100000||n.svg?.length>2000000)throw Error('图层数据超过安全处理上限。');
    if(n.children){if(!Array.isArray(n.children))throw Error('图层结构无效。');n.children.forEach(c=>visit(c,depth+1));}
  }
  visit(data.root,0);return count;
}
const clamp=(v,min,max)=>Math.max(min,Math.min(max,Number.isFinite(v)?v:min));
const rgba=c=>`rgba(${Math.round(clamp(c?.r,0,1)*255)},${Math.round(clamp(c?.g,0,1)*255)},${Math.round(clamp(c?.b,0,1)*255)},${clamp(c?.a??1,0,1)})`;
function canvas(w,h){const c=document.createElement('canvas');c.width=w;c.height=h;return c;}
function path(ctx,n,inset=0){ctx.beginPath();ctx.roundRect(n.x+inset,n.y+inset,Math.max(.01,n.width-inset*2),Math.max(.01,n.height-inset*2),(n.radii||[0,0,0,0]).map(r=>clamp(r-inset,0,Math.min(n.width,n.height)/2)));}
function loadImage(url){return new Promise((resolve,reject)=>{const image=new Image(),timeout=setTimeout(()=>reject(Error('图片读取超时')),8000);image.onload=()=>{clearTimeout(timeout);resolve(image)};image.onerror=()=>{clearTimeout(timeout);reject(Error('图片读取失败'))};image.src=url;});}
function safeSVG(source){
  const doc=new DOMParser().parseFromString(source,'image/svg+xml');
  if(doc.querySelector('parsererror'))throw Error('SVG 解析失败');
  doc.querySelectorAll('script,foreignObject,style').forEach(n=>n.remove());
  for(const el of doc.querySelectorAll('*'))for(const attr of [...el.attributes]){
    if(/^on/i.test(attr.name)||((attr.localName==='href'||attr.name==='src')&&!attr.value.startsWith('#'))||/url\(\s*['"]?(?!#)/i.test(attr.value))el.removeAttribute(attr.name);
  }
  return 'data:image/svg+xml;charset=utf-8,'+encodeURIComponent(new XMLSerializer().serializeToString(doc));
}
function drawText(ctx,n){
 ctx.font=Text.font(n);ctx.fillStyle=rgba(n.color||{r:0,g:0,b:0,a:1});ctx.textBaseline='alphabetic';if('letterSpacing' in ctx)ctx.letterSpacing=(n.letterSpacing||0)+'px';if('wordSpacing' in ctx)ctx.wordSpacing=(n.wordSpacing||0)+'px';if('fontKerning' in ctx)ctx.fontKerning=n.fontKerning||'auto';ctx.direction=n.direction||'ltr';
 for(const run of Text.lines(n)){const baseline=run.y+Text.baseline(n,run),x=n.direction==='rtl'?run.x+run.width:run.x;ctx.textAlign=n.direction==='rtl'?'right':'left';ctx.fillText(run.text,x,baseline);if(n.textDecoration&&n.textDecoration!=='none'){ctx.strokeStyle=ctx.fillStyle;ctx.lineWidth=Math.max(1,(n.fontSize||14)/15);for(const kind of n.textDecoration.split(' ')){if(!['underline','line-through'].includes(kind))continue;const y=kind==='underline'?baseline+1:baseline-(n.fontSize||14)*.3;ctx.beginPath();ctx.moveTo(run.x,y);ctx.lineTo(run.x+run.width,y);ctx.stroke()}}}
}

function hasVisual(n){return (n.rasterStyle?.['background-image']&&n.rasterStyle['background-image']!=='none')||(n.rasterStyle?.['box-shadow']&&n.rasterStyle['box-shadow']!=='none')||n.type==='text'||n.type==='image'||n.type==='svg'||n.background?.a>0||(n.borders||[]).some(b=>b.width>0&&b.color?.a>0&&b.style!=='none');}

// Browser-native CSS rasterization restores gradients, shadows, rounded borders and image masks.
function xml(value){return String(value).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function shadowPad(n){const shadow=n.rasterStyle?.['box-shadow'];if(!shadow||shadow==='none')return 0;const pixels=[...shadow.matchAll(/(-?[\d.]+)px/g)].map(m=>Math.abs(+m[1]));return Math.min(160,Math.ceil(Math.max(0,...pixels)*2+4));}
async function nativeRaster(n,pad,region){
  const allowed=['background-color','background-image','background-size','background-position','background-repeat','border-top','border-right','border-bottom','border-left','border-top-left-radius','border-top-right-radius','border-bottom-right-radius','border-bottom-left-radius','box-shadow'];
  const styles=allowed.map(k=>{const v=n.rasterStyle?.[k];return v&&!/url\(/i.test(v)?k+':'+v:'';}).filter(Boolean);
  styles.push('box-sizing:border-box','position:absolute','left:'+(n.x-region.left)+'px','top:'+(n.y-region.top)+'px','display:block','margin:0','padding:0','width:'+n.width+'px','height:'+n.height+'px');
  let inside='';
  if(n.type==='image'){
    if(!n.image)throw Error('缺少图片数据');
    let imageStyle='display:block;width:100%;height:100%;object-fit:'+(n.objectFit||'cover')+';object-position:'+(n.objectPosition||'50% 50%')+';';
    if(n.maskImage&&n.maskImage!=='none'&&!/url\(/i.test(n.maskImage))imageStyle+='mask-image:'+n.maskImage+';-webkit-mask-image:'+n.maskImage+';';
    inside='<img xmlns="http://www.w3.org/1999/xhtml" src="'+xml(n.image)+'" style="'+xml(imageStyle)+'" />';
  }
  const width=region.right-region.left,height=region.bottom-region.top;
  const html='<div xmlns="http://www.w3.org/1999/xhtml" style="position:relative;box-sizing:border-box;width:'+width+'px;height:'+height+'px;overflow:hidden"><div style="'+xml(styles.join(';'))+'">'+inside+'</div></div>';
  return loadImage('data:image/svg+xml;charset=utf-8,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="'+width+'" height="'+height+'"><foreignObject x="0" y="0" width="100%" height="100%">'+html+'</foreignObject></svg>'));
}

export async function renderCapture(data,onProgress=()=>{}){
  validateCapture(data);const width=Math.ceil(data.width),height=Math.ceil(data.height);
  if(width*height>MAX_PAGE_PIXELS)throw Error('PSD 预览最多支持 1200 万像素。请抓取较短页面；Figma JSON 仍可导出。');
  let allocated=width*height*(data.background?.a>0?2:1),created=0;const warnings=new Set();
  async function bitmap(n,clips){
    if(!hasVisual(n))return null;
    const pad=shadowPad(n);
    let left=Math.max(0,Math.floor(n.x-pad)),top=Math.max(0,Math.floor(n.y-pad)),right=Math.min(width,Math.ceil(n.x+n.width+pad)),bottom=Math.min(height,Math.ceil(n.y+n.height+pad));
    for(const clip of clips){left=Math.max(left,Math.floor(clip.x));top=Math.max(top,Math.floor(clip.y));right=Math.min(right,Math.ceil(clip.x+clip.width));bottom=Math.min(bottom,Math.ceil(clip.y+clip.height));}
    if(right<=left||bottom<=top)return null;
    allocated+=(right-left)*(bottom-top);if(allocated>MAX_LAYER_PIXELS)throw Error('页面图层像素总量太大，请分段抓取或使用 Figma JSON。');
    const c=canvas(right-left,bottom-top),ctx=c.getContext('2d');ctx.translate(-left,-top);
    for(const clip of clips){path(ctx,clip);ctx.clip();}
    let nativeDrawn=false;
    if(n.rasterStyle&&((n.type==='box'&&((n.rasterStyle['background-image']&&n.rasterStyle['background-image']!=='none')||(n.rasterStyle['box-shadow']&&n.rasterStyle['box-shadow']!=='none')))||(n.type==='image'&&n.image))){try{const image=await nativeRaster(n,pad,{left,top,right,bottom});ctx.drawImage(image,left,top);nativeDrawn=true;}catch(error){warnings.add('部分原生 CSS 绘制失败，已使用基础样式。');}}
    if(nativeDrawn){}
    else if(n.type==='text')drawText(ctx,n);
    else{
      if(n.background?.a>0){path(ctx,n);ctx.fillStyle=rgba(n.background);ctx.fill();}
      if(n.type==='image'||n.type==='svg'){
        ctx.save();path(ctx,n);ctx.clip();
        try{
          if(n.type==='image'&&!n.image)throw Error('缺少图片');
          const image=await loadImage(n.type==='svg'?safeSVG(n.svg):n.image);
          const iw=image.naturalWidth,ih=image.naturalHeight;
          const scale=n.fit==='FIT'?Math.min(n.width/iw,n.height/ih):Math.max(n.width/iw,n.height/ih);
          if(n.fit==='STRETCH')ctx.drawImage(image,n.x,n.y,n.width,n.height);
          else ctx.drawImage(image,n.x+(n.width-iw*scale)/2,n.y+(n.height-ih*scale)/2,iw*scale,ih*scale);
        }catch{warnings.add('部分图片或 SVG 无法读取，已使用灰色占位图层。');ctx.fillStyle='#e4e9f0';ctx.fillRect(n.x,n.y,n.width,n.height);}
        ctx.restore();
      }
      const borders=n.borders||[],first=borders[0];
      if(first?.width>0&&first.color?.a>0&&borders.every(b=>b.width===first.width&&JSON.stringify(b.color)===JSON.stringify(first.color)&&b.style===first.style)){
        ctx.strokeStyle=rgba(first.color);ctx.lineWidth=first.width;path(ctx,n,first.width/2);if(first.style==='dashed')ctx.setLineDash([first.width*3,first.width*2]);ctx.stroke();
      }else{
        const corners=[[n.x,n.y],[n.x+n.width,n.y],[n.x+n.width,n.y+n.height],[n.x,n.y+n.height]];
        borders.forEach((b,i)=>{if(!b.width||!b.color?.a||b.style==='none')return;ctx.save();ctx.beginPath();ctx.moveTo(n.x+n.width/2,n.y+n.height/2);ctx.lineTo(...corners[i]);ctx.lineTo(...corners[(i+1)%4]);ctx.closePath();ctx.clip();ctx.strokeStyle=rgba(b.color);ctx.lineWidth=b.width;path(ctx,n,b.width/2);ctx.stroke();ctx.restore();});
      }
    }
    created++;if(created%30===0){onProgress('正在还原第 '+created+' 个图层…');await new Promise(r=>setTimeout(r,0));}
    const label=n.type==='text'?'文字':n.type==='image'?'图片':n.type==='svg'?'图标':'背景与边框';
    return {name:label+' · '+String(n.name||n.text||n.type).slice(0,80),left,top,canvas:c};
  }

  function cleanStyle(n,extra={}){
    const s={...(n.rasterStyle||{}),'background-color':'transparent','background-image':'none','box-shadow':'none'};
    for(const side of ['top','right','bottom','left'])s['border-'+side]='0px solid transparent';
    (n.radii||[0,0,0,0]).forEach((r,i)=>s[['border-top-left-radius','border-top-right-radius','border-bottom-right-radius','border-bottom-left-radius'][i]]=r+'px');
    return {...s,...extra};
  }
  async function visualParts(n,clips){
    if(n.type==='text'){
      const size=n.fontSize||14,c=canvas(1,1),ctx=c.getContext('2d');ctx.font=Text.font(n);if('letterSpacing' in ctx)ctx.letterSpacing=(n.letterSpacing||0)+'px';if('wordSpacing' in ctx)ctx.wordSpacing=(n.wordSpacing||0)+'px';const runs=Text.lines(n);
      const result=[];
      for(const run of runs){
        if(!run.text?.trim())continue;
        const item={...n,text:run.text,x:run.x,y:run.y,width:Math.max(run.width||n.width,ctx.measureText(run.text).width+2),height:Math.max(run.height||n.height,size*1.3),runs:[run],color:{...(n.color||{}),a:1}};
        const layer=nativeText(await bitmap(item,clips),{...item,color:n.color,fontResolved:n.fontResolved||Text.resolveFamily(n)},run.y+Text.baseline(n,run));
        if(layer){if(clips.length)layer.vectorMask={fillStartsWithAllPixels:false,paths:clips.map((clip,i)=>roundedPath(clip,[0,0,0,0],i?'intersect':'combine'))};result.push(layer);}
      }return result;
    }
    if(n.type==='svg'){
      try{
        const result=[];
        for(const part of solidSVG(n)){
          if(!part.paths.length||part.color.a<=0)continue;
          const color={...part.color,a:1},stroke=part.kind==='stroke',c=rgba(color);
          const source='<svg xmlns="http://www.w3.org/2000/svg" width="'+n.width+'" height="'+n.height+'" viewBox="'+n.x+' '+n.y+' '+n.width+' '+n.height+'"><path d="'+xml(part.d)+'" fill="'+(stroke?'none':c)+'" fill-rule="'+(part.paths[0].fillRule==='even-odd'?'evenodd':'nonzero')+'" stroke="'+(stroke?c:'none')+'" stroke-width="'+(part.strokeWidth||0)+'" stroke-linecap="'+(part.lineCap||'butt')+'" stroke-linejoin="'+(part.lineJoin||'miter')+'"/></svg>';
          const layer=shape(await bitmap({...n,svg:source,background:null,borders:[],rasterStyle:null,fit:'STRETCH'},clips),part.color,part.paths,clips);
          if(layer){if(stroke)layer.vectorStroke={strokeEnabled:true,fillEnabled:false,lineWidth:{units:'Pixels',value:part.strokeWidth},lineAlignment:'center',lineCapType:part.lineCap,lineJoinType:part.lineJoin,content:{type:'color',color:rgb8(color)},opacity:1};result.push(layer);}
        }return result;
      }catch(e){warnings.add('SVG「'+String(n.name||'图标').slice(0,30)+'」保留位图：'+e.message);return [await bitmap(n,clips)].filter(Boolean);}
    }
    if(n.type!=='box')return [await bitmap(n,clips)].filter(Boolean);
    const result=[],none={r:0,g:0,b:0,a:0};
    const add=layer=>{if(layer)result.push(layer)};
    const shadows=(n.rasterStyle?.['box-shadow']||'none').split(/,(?![^(]*\))/);
    const outer=shadows.filter(s=>s!=='none'&&!s.includes('inset')).join(','),inner=shadows.filter(s=>s.includes('inset')).join(',');
    if(outer){const l=await bitmap({...n,background:null,borders:[],rasterStyle:cleanStyle(n,{'box-shadow':outer})},clips);if(l)l.name='阴影 · '+n.name;add(l);}
    if(n.background?.a>0){
      const solid={...n.background,a:1};
      add(shape(await bitmap({...n,background:solid,borders:[],rasterStyle:cleanStyle(n,{'background-color':rgba(solid)})},clips),n.background,[roundedPath(n)],clips));
    }
    const gradient=n.rasterStyle?.['background-image'];
    if(gradient&&gradient!=='none'){
      const l=await bitmap({...n,background:null,borders:[],rasterStyle:cleanStyle(n,{'background-image':gradient})},clips);if(l)l.name='渐变或背景图片 · '+n.name;add(l);
    }
    if(inner){const l=await bitmap({...n,background:null,borders:[],rasterStyle:cleanStyle(n,{'box-shadow':inner})},clips);if(l)l.name='内阴影 · '+n.name;add(l);}
    const borders=Array.from({length:4},(_,i)=>n.borders?.[i]||{width:0,color:none,style:'none'});
    const visible=borders.map(b=>b.width>0&&b.color?.a>0&&b.style!=='none');
    const widths=borders.map(b=>b.style==='none'?0:b.width||0);
    const corners=[[n.x,n.y],[n.x+n.width,n.y],[n.x+n.width,n.y+n.height],[n.x,n.y+n.height]];
    for(let i=0;i<4;i++){
      const b=borders[i];if(!visible[i])continue;
      const bs=borders.map((v,j)=>({...v,color:j===i?{...v.color,a:1}:none}));
      const css=cleanStyle(n);bs.forEach((v,j)=>css['border-'+['top','right','bottom','left'][j]]=v.width+'px '+v.style+' '+rgba(v.color));
      const l=await bitmap({...n,background:null,borders:bs,rasterStyle:css},clips);
      if(b.style!=='solid'){if(l)l.name='特殊描边 · '+n.name;warnings.add('虚线、点线等特殊 CSS 边框目前保留位图。');add(l);continue;}
      const ring=[roundedPath(n)];
      if(n.width>widths[1]+widths[3]&&n.height>widths[0]+widths[2])ring.push(roundedPath(n,widths,'subtract'));
      // Wedges partition the corner joins. Equal widths match standard CSS borders.
      ring.push(polygon([[n.x+n.width/2,n.y+n.height/2],corners[i],corners[(i+1)%4]],'intersect'));
      if(l)l.name='矢量描边 · '+n.name+' · '+['上','右','下','左'][i];
      add(shape(l,b.color,ring,clips));
    }
    return result;
  }


  // ag-psd writes children in paint order: bottom first, top last, at EVERY depth.
  async function visit(n,clips){
    if(n.visible===false)return null;
    const children=n.type==='group'?[]:await visualParts(n,clips);
    const childClips=n.clip?[...clips,n]:clips;
    for(const child of n.children||[]){const layer=await visit(child,childClips);if(layer)children.push(layer);}
    if(!children.length)return null;
    if(children.length===1){const only=children[0];only.opacity=(only.opacity??1)*clamp(n.opacity??1,0,1);return only;}
    return {name:String(n.name||'图层组').slice(0,120),children:children,opacity:clamp(n.opacity??1,0,1),blendMode:'normal',opened:false};
  }
  const tree=await visit(data.root,[]),composite=canvas(width,height),ctx=composite.getContext('2d');
  let pageBackground;
  if(data.background?.a>0){const c=canvas(width,height),cctx=c.getContext('2d');cctx.fillStyle=rgba({...data.background,a:1});cctx.fillRect(0,0,width,height);pageBackground=shape({name:'页面背景',left:0,top:0,canvas:c},data.background,[roundedPath({x:0,y:0,width,height})]);ctx.save();ctx.globalAlpha=data.background.a;ctx.drawImage(c,0,0);ctx.restore();}
  function paint(layer,target){
    if(layer.children){
      if((layer.opacity??1)<1){const scratch=canvas(width,height);layer.children.forEach(child=>paint(child,scratch.getContext('2d')));target.save();target.globalAlpha*=layer.opacity;target.drawImage(scratch,0,0);target.restore();scratch.width=1;scratch.height=1;}
      else layer.children.forEach(child=>paint(child,target));
    }else{target.save();target.globalAlpha*=layer.opacity??1;target.drawImage(layer.canvas,layer.left,layer.top);target.restore();}
  }
  if(tree)paint(tree,ctx);
  const stats={text:0,vector:0,raster:0};function types(l){if(l.children)l.children.forEach(types);else stats[l.text?'text':l.vectorFill?'vector':'raster']++;}if(pageBackground)types(pageBackground);if(tree)types(tree);
  return {stats,psd:{width,height,canvas:composite,children:[...(pageBackground?[pageBackground]:[]),...(tree?[tree]:[])]},canvas:composite,count:created+(pageBackground?1:0),warnings:[...warnings]};
}
export function encodePSD(rendered){return writePsd(rendered.psd,{noBackground:true,trimImageData:true});}

// Editing keeps the original DOM geometry. Raster caches are allocated only for export.
export function exportPlan(data,requested='auto'){
  validateCapture(data);let layerPixels=0,opacityDepth=0;
  const page={x:0,y:0,width:data.width,height:data.height};
  function area(n,clips){const pad=shadowPad(n);let l=Math.max(0,n.x-pad),t=Math.max(0,n.y-pad),r=Math.min(data.width,n.x+n.width+pad),b=Math.min(data.height,n.y+n.height+pad);for(const c of clips){l=Math.max(l,c.x);t=Math.max(t,c.y);r=Math.min(r,c.x+c.width);b=Math.min(b,c.y+c.height)}return Math.max(0,r-l)*Math.max(0,b-t)}
  function visit(n,clips,depth){if(n.visible===false)return;const d=depth+((n.opacity??1)<1&&n.children?.length?1:0);opacityDepth=Math.max(opacityDepth,d);let parts=0;if(n.type==='text')parts=Math.max(1,n.runs?.length||String(n.text||'').split('\n').length);else if(n.type==='image')parts=1;else if(n.type==='svg'){try{parts=Math.max(1,solidSVG(n).length)}catch{parts=1}}else if(n.type==='box'){parts=(n.background?.a>0?1:0)+(n.rasterStyle?.['background-image']&&n.rasterStyle['background-image']!=='none'?1:0)+(n.rasterStyle?.['box-shadow']&&n.rasterStyle['box-shadow']!=='none'?2:0)+(n.borders||[]).filter(b=>b.width>0&&b.color?.a>0&&b.style!=='none').length;}if(parts)layerPixels+=area(n,clips)*parts;(n.children||[]).forEach(c=>visit(c,n.clip?[...clips,n]:clips,d))}
  visit(data.root,[],0);const pagePixels=data.width*data.height,estimated=layerPixels+pagePixels*(3+opacityDepth);const safe=Math.min(1,Math.sqrt(10000000/pagePixels),Math.sqrt(24000000/Math.max(1,estimated))),scale=requested==='auto'?Math.min(1,safe*.98):Number(requested);
  if(!Number.isFinite(scale)||scale<=0||scale>1)throw Error('导出比例无效');if(requested!=='auto'&&scale>safe*1.04)throw Error('这个比例的图层缓存过大，请选择“自动适配”。原始图层尺寸会保留在工程与 Figma 数据中。');
  return {scale:scale>.97&&safe===1?1:scale,width:Math.max(1,Math.ceil(data.width*(scale>.97&&safe===1?1:scale))),height:Math.max(1,Math.ceil(data.height*(scale>.97&&safe===1?1:scale))),estimatedPixels:estimated};
}
export function scaledCapture(data,scale){
  const px=v=>typeof v==='string'?v.replace(/(-?(?:\d*\.)?\d+)px\b/g,(_,n)=>(+n*scale)+'px'):v;
  function node(n){const v={...n};for(const k of ['x','y','width','height','fontSize','lineHeight','letterSpacing','wordSpacing'])if(Number.isFinite(v[k]))v[k]*=scale;if(n.radii)v.radii=n.radii.map(r=>r*scale);if(n.borders)v.borders=n.borders.map(b=>({...b,width:b.width*scale}));if(n.rasterStyle)v.rasterStyle=Object.fromEntries(Object.entries(n.rasterStyle).map(([k,v])=>[k,px(v)]));if(n.runs)v.runs=n.runs.map(r=>({...r,x:r.x*scale,y:r.y*scale,width:r.width*scale,height:r.height*scale}));if(n.children)v.children=n.children.map(node);return v;}
  return {...data,width:Math.max(1,Math.ceil(data.width*scale)),height:Math.max(1,Math.ceil(data.height*scale)),root:node(data.root)};
}
export async function renderForExport(data,onProgress=()=>{},requested='auto'){
  const plan=exportPlan(data,requested);onProgress('准备 '+plan.width+' × '+plan.height+' px 导出',0.02);
  const working=plan.scale===1?data:scaledCapture(data,plan.scale);let count=0;const total=validateCapture(working);const rendered=await renderCapture(working,(text)=>{count+=30;onProgress(text,Math.min(.9,.06+count/Math.max(1,total)*.8))});rendered.exportScale=plan.scale;rendered.originalSize={width:data.width,height:data.height};onProgress('图层已准备完成',.94);return rendered;
}
export function releaseRender(rendered){if(!rendered)return;function free(n){if(n.canvas){n.canvas.width=1;n.canvas.height=1}(n.children||[]).forEach(free)}free(rendered.psd);}
