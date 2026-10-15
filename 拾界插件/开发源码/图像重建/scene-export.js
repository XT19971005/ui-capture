import {normalizeStyle,normalizeGradient,normalizeMask,maskPath,gradientData as nativeGradientData,nativeEffects,styleCanvas,displayMaskCanvas,nativeMask,styleSvg,gradientPaint,fitGradientEffects,alphaBounds,definitionId} from './layer-style.js';
export {normalizeStyle,normalizeGradient,normalizeMask} from './layer-style.js';
import {writePsd} from 'ag-psd';
import {nativeText,pathData} from '../../插件程序/edge/psd-native.js';
export const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const color=h=>({r:parseInt(h.slice(1,3),16)/255,g:parseInt(h.slice(3,5),16)/255,b:parseInt(h.slice(5,7),16)/255,a:1});
// Storage is measured once per distinct embedded image, independently of how
// many current/hidden layers display it. Export buffers are checked separately.
export const SCENE_CAPACITY_LIMITS=Object.freeze({uniqueImageBytes:256*1024*1024,metadataBytes:16*1024*1024,logicalBytes:1024*1024*1024,pathChars:3000000,decodedPixels:256000000,imagePixels:64000000,imageEdge:16384,psdWorkingBytes:1024*1024*1024,layerRasterPixels:16000000,decodeCachePixels:16000000});
const imageURI=/^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$/;
function capacityError(code,label,used,limit,unit='MiB',phase='storage'){
 const scale=unit==='MiB'?1024*1024:unit==='MP'?1000000:1,amount=value=>(Math.ceil(value/scale*10)/10).toLocaleString('en-US');
 const error=Error(label+' '+amount(used)+' '+unit+'，超过 '+amount(limit)+' '+unit+'。请先保存工程，再按所选图层或分组分批导出。');
 Object.assign(error,{name:'SceneCapacityError',code,used,limit,phase});throw error;
}
function jsonStringBytes(value){
 let bytes=2;
 for(let i=0;i<value.length;i++){
  const c=value.charCodeAt(i);
  if(c===34||c===92||[8,9,10,12,13].includes(c))bytes+=2;
  else if(c<32)bytes+=6;
  else if(c<128)bytes++;
  else if(c<2048)bytes+=2;
  else if(c>=0xd800&&c<=0xdbff&&value.charCodeAt(i+1)>=0xdc00&&value.charCodeAt(i+1)<=0xdfff){bytes+=4;i++}
  else bytes+=c>=0xd800&&c<=0xdfff?6:3;
 }
 return bytes;
}
function measureScene(s){
 let metadataBytes=0,imageReferences=0,imageReferenceBytes=0;const images=new Map(),visiting=new Set();
 function visit(value,depth=0){
  if(depth>128)throw Error('工程元数据嵌套超过128层');
  if(typeof value==='string'){
   if(value.startsWith('data:image/')&&(images.has(value)||imageURI.test(value))){imageReferences++;imageReferenceBytes+=value.length;metadataBytes+=2;if(!images.has(value))images.set(value,{bytes:value.length,compressedBytes:Math.floor((value.length-value.indexOf(',')-1)*3/4)-(value.endsWith('==')?2:value.endsWith('=')?1:0)});}
   else metadataBytes+=jsonStringBytes(value);return;
  }
  if(value==null||typeof value!=='object'){metadataBytes+=typeof value==='number'&&Number.isFinite(value)?String(value).length:typeof value==='boolean'?String(value).length:4;return}
  if(visiting.has(value))throw Error('工程含循环引用，无法持久保存');visiting.add(value);
  if(Array.isArray(value)){metadataBytes+=2+Math.max(0,value.length-1);for(const item of value)visit(item,depth+1)}
  else {const entries=Object.entries(value).filter(([,v])=>v!==undefined&&typeof v!=='function'&&typeof v!=='symbol');metadataBytes+=2+Math.max(0,entries.length-1);for(const [key,item] of entries){metadataBytes+=jsonStringBytes(key)+1;visit(item,depth+1)}}
  visiting.delete(value);
 }
 visit(s);const uniqueImageBytes=[...images.values()].reduce((sum,image)=>sum+image.bytes,0),compressedImageBytes=[...images.values()].reduce((sum,image)=>sum+image.compressedBytes,0);
 return {images,uniqueImages:images.size,imageReferences,uniqueImageBytes,compressedImageBytes,metadataBytes,logicalBytes:metadataBytes+imageReferenceBytes,displayPixels:(s.nodes||[]).reduce((sum,n)=>sum+n.width*n.height,0),pathChars:(s.nodes||[]).reduce((sum,n)=>sum+(n.type==='path'?n.d.length:0),0)};
}
export function sceneUsage(s){const {images,...usage}=measureScene(s);return usage}
function assertSceneStorageCapacity(s){
 const usage=sceneUsage(s),labels={uniqueImageBytes:['SCENE_IMAGE_BYTES','工程唯一图片数据'],metadataBytes:['SCENE_METADATA_BYTES','工程非图片元数据'],logicalBytes:['SCENE_LOGICAL_BYTES','工程展开引用数据']};
 for(const [key,[code,label]] of Object.entries(labels))if(usage[key]>SCENE_CAPACITY_LIMITS[key])capacityError(code,label,usage[key],SCENE_CAPACITY_LIMITS[key]);
 if(usage.pathChars>SCENE_CAPACITY_LIMITS.pathChars)capacityError('SCENE_PATH_CHARS','工程矢量路径字符',usage.pathChars,SCENE_CAPACITY_LIMITS.pathChars,'字符');return usage;
}
export function imageMetadata(src){
 if(typeof src!=='string'||!imageURI.test(src))throw Error('图片不是有效的内嵌PNG/JPEG/WebP');
 const comma=src.indexOf(','),base=src.slice(comma+1),length=Math.floor(base.length*3/4)-(base.endsWith('==')?2:base.endsWith('=')?1:0);
 function read(offset,count){if(offset<0||offset+count>length)throw Error('图片头部或尺寸数据不完整');const aligned=Math.floor(offset/3)*3,start=aligned/3*4,end=Math.min(base.length,Math.ceil((offset+count)/3)*4),raw=atob(base.slice(start,end)),out=new Uint8Array(count);for(let i=0;i<count;i++)out[i]=raw.charCodeAt(offset-aligned+i);return out}
 const be32=(a,i)=>a[i]*16777216+a[i+1]*65536+a[i+2]*256+a[i+3],le32=(a,i)=>(a[i]+a[i+1]*256+a[i+2]*65536+a[i+3]*16777216)>>>0,le24=(a,i)=>a[i]+a[i+1]*256+a[i+2]*65536;
 const head=read(0,Math.min(length,32));let width,height;
 if(src.startsWith('data:image/png;')&&head[0]===137&&head[1]===80&&head[2]===78&&head[3]===71&&head[12]===73&&head[13]===72&&head[14]===68&&head[15]===82){width=be32(head,16);height=be32(head,20)}
 else if(src.startsWith('data:image/jpeg;')&&head[0]===255&&head[1]===216){
  let offset=2;for(let i=0;i<4096&&offset<length;i++){
   const marker=read(offset,4);if(marker[0]!==255)throw Error('JPEG图片头部标记无效');if(marker[1]===255){offset++;continue}
   if([0xc0,0xc1,0xc2,0xc3,0xc5,0xc6,0xc7,0xc9,0xca,0xcb,0xcd,0xce,0xcf].includes(marker[1])){const frame=read(offset,9);height=frame[5]*256+frame[6];width=frame[7]*256+frame[8];break}
   if(marker[1]===0xd9||marker[1]===0xda)break;const size=marker[2]*256+marker[3];if(size<2)throw Error('JPEG图片头部长度无效');offset+=2+size;
  }
 }else if(src.startsWith('data:image/webp;')&&String.fromCharCode(...head.slice(0,4))==='RIFF'&&String.fromCharCode(...head.slice(8,12))==='WEBP'){
  let offset=12;for(let i=0;i<4096&&offset+8<=length;i++){
   const h=read(offset,8),kind=String.fromCharCode(...h.slice(0,4)),size=le32(h,4);
   if(kind==='VP8X'){const p=read(offset+8,10);width=le24(p,4)+1;height=le24(p,7)+1;break}
   if(kind==='VP8L'){const p=read(offset+8,5);if(p[0]!==47)break;const bits=le32(p,1);width=(bits&16383)+1;height=((bits>>>14)&16383)+1;break}
   if(kind==='VP8 '){const p=read(offset+8,10);if(p[3]!==157||p[4]!==1||p[5]!==42)break;width=(p[6]+p[7]*256)&16383;height=(p[8]+p[9]*256)&16383;break}
   offset+=8+size+(size&1);
  }
 }
 if(!Number.isInteger(width)||!Number.isInteger(height)||width<=0||height<=0)throw Error('图片尺寸头部无效或不受支持');return {width,height,pixels:width*height,compressedBytes:length};
}
function assertImageDecodeCapacity(info,label){
 if(info.pixels>SCENE_CAPACITY_LIMITS.imagePixels)capacityError('IMAGE_DECODE_PIXELS',label+'单张解码像素',info.pixels,SCENE_CAPACITY_LIMITS.imagePixels,'MP','decode');
 if(Math.max(info.width,info.height)>SCENE_CAPACITY_LIMITS.imageEdge)capacityError('IMAGE_DECODE_EDGE',label+'单边解码尺寸',Math.max(info.width,info.height),SCENE_CAPACITY_LIMITS.imageEdge,'像素','decode');
}
function decodeUsage(nodes){
 const images=new Map();for(const n of nodes)if(n.type==='image'&&!images.has(n.src)){let info;try{info=imageMetadata(n.src)}catch(error){throw Error('图层「'+(n.name||n.id)+'」：'+error.message)}assertImageDecodeCapacity(info,'图层「'+(n.name||n.id)+'」');images.set(n.src,info)}
 const decodedPixels=[...images.values()].reduce((sum,image)=>sum+image.pixels,0),maxDecodedPixels=Math.max(0,...[...images.values()].map(image=>image.pixels));
 if(decodedPixels>SCENE_CAPACITY_LIMITS.decodedPixels)capacityError('SCENE_DECODE_PIXELS','导出唯一图片解码像素',decodedPixels,SCENE_CAPACITY_LIMITS.decodedPixels,'MP','decode');return {decodedPixels,maxDecodedPixels,uniqueDecodedImages:images.size};
}
export function assertExportCapacity(s){
 validate(s);const usage=sceneUsage(s),nodes=allNodes(s,true),decoded=decodeUsage(nodes);let layerRasterPixels=0,maskPixels=0,maxDepth=0;
 for(const n of nodes){const box=n.type==='text'?textInkBounds(n):n,pad=Math.ceil(n.strokeWidth||0)+2,w=Math.ceil(box.width)+pad*2,h=Math.ceil(box.height)+pad*2;
  if(w>12000||h>12000)capacityError('PSD_LAYER_RASTER_EDGE','图层「'+(n.name||n.id)+'」实际显示缓存边长',Math.max(w,h),12000,'像素','export');
  if(w*h>SCENE_CAPACITY_LIMITS.layerRasterPixels)capacityError('PSD_LAYER_RASTER_PIXELS','图层「'+(n.name||n.id)+'」实际显示缓存',w*h,SCENE_CAPACITY_LIMITS.layerRasterPixels,'MP','export');layerRasterPixels+=w*h;if(n.displayMask?.enabled!==false&&n.displayMask)maskPixels+=s.width*s.height;
 }
 const owner=new Map();for(const g of s.groups||[]){for(const id of g.children)owner.set(id,g.id);if(g.displayMask&&g.displayMask.enabled!==false)maskPixels+=s.width*s.height}
 for(const n of nodes){let id=n.id,depth=0;while(owner.has(id)){depth++;id=owner.get(id)}maxDepth=Math.max(maxDepth,depth)}
 // Layer caches, channel writing and masks are retained; composites need a
 // small number of full-canvas scratch buffers at each active group depth.
 const decodeWorkingPixels=Math.min(decoded.decodedPixels,Math.max(SCENE_CAPACITY_LIMITS.decodeCachePixels,decoded.maxDecodedPixels));
 const estimatedWorkingBytes=4*(layerRasterPixels*3+maskPixels*2+s.width*s.height*(6+2*maxDepth)+decodeWorkingPixels)+usage.uniqueImageBytes*2;
 if(estimatedWorkingBytes>SCENE_CAPACITY_LIMITS.psdWorkingBytes)capacityError('PSD_WORKING_BYTES','PSD导出预计工作内存',estimatedWorkingBytes,SCENE_CAPACITY_LIMITS.psdWorkingBytes,'MiB','export');
 return {...usage,...decoded,layerRasterPixels,maskPixels,estimatedWorkingBytes};
}
export function validate(s){
 if(!s||s.format!=='shijie-scene'||s.version!==2||!Array.isArray(s.nodes)||s.nodes.length>700)throw Error('请选择拾界图片工程（v2），最多 700 层');
 if(![s.width,s.height].every(v=>Number.isInteger(v)&&v>0&&v<=6000)||s.width*s.height>6000000)throw Error('画布尺寸超限');
 if(s.background!=null&&!/^#[0-9a-f]{6}$/i.test(s.background))throw Error('画布背景色无效');
 const ids=new Set();
 for(const n of s.nodes){if(typeof n.id!=='string'||ids.has(n.id)||!['text','rect','ellipse','path','image'].includes(n.type))throw Error('图层 ID 或类型无效');ids.add(n.id);if(n.opacity!==undefined&&(!Number.isFinite(n.opacity)||n.opacity<0||n.opacity>1))throw Error('图层透明度无效');if(n.fontWeight!==undefined&&(!Number.isFinite(n.fontWeight)||n.fontWeight<100||n.fontWeight>900))throw Error('字重无效');if(n.radius!==undefined&&(!Number.isFinite(n.radius)||n.radius<0||n.radius>6000))throw Error('圆角无效');
 for(const k of ['x','y','width','height'])if(!Number.isFinite(n[k])||Math.abs(n[k])>12000)throw Error('图层坐标无效');
 if(n.width<=0||n.height<=0||n.width*n.height>6000000)throw Error('图层尺寸无效');
 if(n.type!=='image'&&!/^#[\da-f]{6}$/i.test(n.fill))throw Error('图层颜色无效');
 normalizeGradient(n.gradient);normalizeStyle(n.layerStyle);normalizeMask(n.displayMask);
 if(n.strokeWidth!==undefined&&(!Number.isFinite(n.strokeWidth)||n.strokeWidth<0||n.strokeWidth>30))throw Error('文字描边宽度无效');if(n.stroke!==undefined&&!/^#[\da-f]{6}$/i.test(n.stroke))throw Error('文字描边颜色无效');
 if(n.rotation!==undefined&&![0,90].includes(n.rotation))throw Error('文字旋转方向无效');if(n.fontFamily!==undefined&&!['Arial','Microsoft YaHei','SimHei','Impact','Arial Narrow','Haettenschweiler'].includes(n.fontFamily))throw Error('字体无效');
 if(n.fontStyle!==undefined&&!['normal','italic'].includes(n.fontStyle))throw Error('字体样式无效');if(n.fitWidth!==undefined&&typeof n.fitWidth!=='boolean')throw Error('文字字宽拟合参数无效');
 if(n.textSkew!==undefined&&(!Number.isFinite(n.textSkew)||n.textSkew<0||n.textSkew>.6))throw Error('文字倾斜参数无效');
 if(n.lineHeight!==undefined&&(!Number.isFinite(n.lineHeight)||n.lineHeight<=0||n.lineHeight>6000))throw Error('文字行高无效');
 if(n.type==='text'&&(typeof n.text!=='string'||n.text.length>10000||!Number.isFinite(n.fontSize)||n.fontSize<1||n.fontSize>1000))throw Error('文字数据无效');
 if(n.type==='path'){if(typeof n.d!=='string'||!/^[MmLlHhVvCcSsQqTtAaZz\s\d.eE,+\-]+$/.test(n.d))throw Error('矢量路径无效');}
 if(n.type==='image'){if(!/^data:image\/(png|jpeg|webp);base64,[\w+/=]+$/.test(n.src))throw Error('只支持内嵌图片');}}
 if(s.groups!==undefined){if(!Array.isArray(s.groups)||s.groups.length>350)throw Error('分组数量无效');const groupIds=new Set(),owned=new Set();for(const g of s.groups){if(!g||typeof g.id!=='string'||ids.has(g.id)||groupIds.has(g.id)||!Array.isArray(g.children)||!g.children.length)throw Error('分组结构无效');groupIds.add(g.id);normalizeStyle(g.layerStyle);normalizeMask(g.displayMask);if(g.opacity!==undefined&&(!Number.isFinite(g.opacity)||g.opacity<0||g.opacity>1))throw Error('分组透明度无效')}for(const g of s.groups)for(const id of g.children){if((!ids.has(id)&&!groupIds.has(id))||owned.has(id)||id===g.id)throw Error('分组成员无效');owned.add(id)}const map=new Map(s.groups.map(g=>[g.id,g])),visiting=new Set(),done=new Set();function check(g){if(visiting.has(g.id))throw Error('分组循环引用');if(done.has(g.id))return;visiting.add(g.id);for(const id of g.children)if(map.has(id))check(map.get(id));visiting.delete(g.id);done.add(g.id)}s.groups.forEach(check);}
 if(s.source&&!/^data:image\/(png|jpeg|webp);base64,[\w+/=]+$/.test(s.source))throw Error('原图无效');
 if(!Array.isArray(s.edges)||s.edges.length>300)throw Error('连线数据无效');
 for(const e of s.edges)if(!ids.has(e.from)||!ids.has(e.to)||e.from===e.to||!/^#[\da-f]{6}$/i.test(e.fill))throw Error('连线端点无效');
 assertSceneStorageCapacity(s);return s;
}
export function geometry(n){if(n.type==='path')return n.d;if(n.type==='ellipse')return `M0 ${n.height/2}a${n.width/2} ${n.height/2} 0 1 0 ${n.width} 0a${n.width/2} ${n.height/2} 0 1 0 ${-n.width} 0Z`;const r=Math.max(0,Math.min(n.radius||0,n.width/2,n.height/2)),w=n.width,h=n.height;return `M${r} 0H${w-r}Q${w} 0 ${w} ${r}V${h-r}Q${w} ${h} ${w-r} ${h}H${r}Q0 ${h} 0 ${h-r}V${r}Q0 0 ${r} 0Z`;}
const ctx=()=>document.createElement('canvas').getContext('2d');
export function contourOperations(paths){
 const polygon=p=>{const points=[];for(let i=0;i<p.knots.length;i++){const a=p.knots[i].points,b=p.knots[(i+1)%p.knots.length].points;for(let j=0;j<12;j++){const t=j/12,u=1-t;points.push([u*u*u*a[2]+3*u*u*t*a[4]+3*u*t*t*b[0]+t*t*t*b[2],u*u*u*a[3]+3*u*u*t*a[5]+3*u*t*t*b[1]+t*t*t*b[3]])}}return points};
 const contains=(pts,x,y)=>{let inside=false;for(let i=0,j=pts.length-1;i<pts.length;j=i++){const a=pts[i],b=pts[j];if((a[1]>y)!==(b[1]>y)&&x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0])inside=!inside}return inside};
 const rows=paths.map(p=>{const points=polygon(p),area=Math.abs(points.reduce((sum,a,i)=>{const b=points[(i+1)%points.length];return sum+a[0]*b[1]-b[0]*a[1]},0));return {p,points,area}}).sort((a,b)=>b.area-a.area);
 const fullyInside=(inner,outer)=>inner.points.every(p=>contains(outer.points,p[0],p[1]));
 const crossing=(a,b)=>{const orient=(p,q,r)=>(q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0]);for(let i=0;i<a.points.length;i++){const p=a.points[i],q=a.points[(i+1)%a.points.length];for(let j=0;j<b.points.length;j++){const r=b.points[j],s=b.points[(j+1)%b.points.length];if(Math.max(p[0],q[0])<Math.min(r[0],s[0])||Math.max(r[0],s[0])<Math.min(p[0],q[0])||Math.max(p[1],q[1])<Math.min(r[1],s[1])||Math.max(r[1],s[1])<Math.min(p[1],q[1]))continue;if(orient(p,q,r)*orient(p,q,s)<-1e-9&&orient(r,s,p)*orient(r,s,q)<-1e-9)return true}}return false};
 // The Canvas/SVG preview uses even-odd fill. Intersecting subpaths must
 // therefore use native XOR; a single inside anchor cannot identify a hole.
 const partlyInside=(inner,outer)=>{const flags=inner.points.map(p=>contains(outer.points,p[0],p[1]));return flags.some(Boolean)&&!flags.every(Boolean)};
 const intersects=rows.some((r,i)=>rows.slice(0,i).some(o=>crossing(r,o)||partlyInside(r,o)||partlyInside(o,r)));
 for(let i=0;i<rows.length;i++){const r=rows[i],depth=rows.slice(0,i).filter(o=>fullyInside(r,o)).length;r.p.operation=intersects?(i?'exclude':'combine'):(depth%2?'subtract':'combine');r.p.fillRule='non-zero'}return rows.map(r=>r.p);
}
export const textLines=n=>String(n.text??'').replace(/\r\n?/g,'\n').split('\n');
export const textLeading=n=>n.lineHeight??n.fontSize*1.2;
export function metrics(n){const c=ctx();c.font=`${n.textSkew?'normal':n.fontStyle||'normal'} ${n.fontWeight||400} ${n.fontSize}px "${n.fontFamily||'Microsoft YaHei'}",sans-serif`;const lines=textLines(n),rows=lines.map(t=>c.measureText(t||''));if(rows.length===1)return c.measureText(n.text||'文字');const first=rows[0],last=rows.at(-1),leading=textLeading(n);return {width:Math.max(...rows.map(r=>r.width)),actualBoundingBoxLeft:Math.max(0,...rows.map(r=>r.actualBoundingBoxLeft||0)),actualBoundingBoxRight:Math.max(0,...rows.map(r=>r.actualBoundingBoxRight||r.width)),actualBoundingBoxAscent:first.actualBoundingBoxAscent||n.fontSize*.85,actualBoundingBoxDescent:(rows.length-1)*leading+(last.actualBoundingBoxDescent||0),firstLineAscent:first.actualBoundingBoxAscent||n.fontSize*.85,firstLineDescent:first.actualBoundingBoxDescent||0,fontBoundingBoxAscent:first.fontBoundingBoxAscent,fontBoundingBoxDescent:last.fontBoundingBoxDescent,lineHeight:leading,lineCount:rows.length};}
export function textInkBounds(n){const m=metrics(n),matrix=textMatrix(n),l=-(m.actualBoundingBoxLeft||0),r=m.actualBoundingBoxRight||m.width,t=-(m.actualBoundingBoxAscent||n.fontSize*.85),b=m.actualBoundingBoxDescent||0,points=[[l,t],[r,t],[r,b],[l,b]].map(([x,y])=>[matrix[0]*x+matrix[2]*y+matrix[4],matrix[1]*x+matrix[3]*y+matrix[5]]),x=Math.min(n.x,...points.map(p=>p[0])),y=Math.min(n.y,...points.map(p=>p[1]));return {x,y,width:Math.max(n.x+n.width,...points.map(p=>p[0]))-x,height:Math.max(n.y+n.height,...points.map(p=>p[1]))-y};}
export function edgeNode(s,e,i=0){const a=s.nodes.find(n=>n.id===e.from),b=s.nodes.find(n=>n.id===e.to);if(!a||!b||a.visible===false||b.visible===false)return null;const ac=[a.x+a.width/2,a.y+a.height/2],bc=[b.x+b.width/2,b.y+b.height/2],dx=bc[0]-ac[0],dy=bc[1]-ac[1],len=Math.hypot(dx,dy);if(len<1)return null;const ux=dx/len,uy=dy/len,t1=Math.min(Math.abs(a.width/2/(ux||1e-9)),Math.abs(a.height/2/(uy||1e-9))),t2=Math.min(Math.abs(b.width/2/(ux||1e-9)),Math.abs(b.height/2/(uy||1e-9)));const p=[ac[0]+ux*t1,ac[1]+uy*t1],q=[bc[0]-ux*t2,bc[1]-uy*t2],nx=-uy*2,ny=ux*2;return {id:'edge-'+i,name:'连线',type:'path',x:0,y:0,width:s.width,height:s.height,fill:e.fill,d:`M${p[0]+nx} ${p[1]+ny}L${q[0]-ux*12+nx} ${q[1]-uy*12+ny}L${q[0]-ux*12-uy*6} ${q[1]-uy*12+ux*6}L${q[0]} ${q[1]}L${q[0]-ux*12+uy*6} ${q[1]-uy*12-ux*6}L${q[0]-ux*12-nx} ${q[1]-uy*12-ny}L${p[0]-nx} ${p[1]-ny}Z`};}
const layerHidden=n=>n.visible===false||n.visible===undefined&&n.hidden===true;
export const allNodes=(s,includeHidden=false)=>[...(s.background?[{id:'__canvas_background__',name:'画布背景',type:'rect',x:0,y:0,width:s.width,height:s.height,fill:s.background,locked:true}]:[]),...s.nodes,...s.edges.map((e,i)=>edgeNode(s,e,i)).filter(Boolean)].filter(n=>includeHidden||!layerHidden(n));
export function textMatrix(n){const m=metrics(n),a=m.actualBoundingBoxAscent||n.fontSize*.85,d=m.actualBoundingBoxDescent||0;if(n.rotation===90)return [0,n.fitWidth?n.height/Math.max(1,m.width):1,-1,0,n.x+(n.width-a-d)/2+d,n.y];const skew=n.textSkew||0,sx=n.fitWidth?n.width/Math.max(1,(m.actualBoundingBoxLeft||0)+(m.actualBoundingBoxRight||m.width)+skew*(a+d)):1;return [sx,0,-skew*sx,1,n.x+(n.fitWidth?((m.actualBoundingBoxLeft||0)+skew*d)*sx:0),n.y+a];}
export function gradientData(n){return nativeGradientData(n.gradient,n.name||'原图渐变');}
function gradientCache(canvas,n,left,top){const c=canvas.getContext('2d');c.save();c.setTransform(1,0,0,1,0,0);c.globalCompositeOperation='source-in';c.fillStyle=gradientPaint(c,n.gradient,{x:n.x-left,y:n.y-top,width:n.width,height:n.height});c.fillRect(0,0,canvas.width,canvas.height);c.restore();}
export function nodeSvg(n){let content=nodeSvgBase(n);return styleSvg(content,n,{x:n.x,y:n.y,width:n.width,height:n.height});}
function nodeSvgBase(n){if(n.gradient){const g=normalizeGradient(n.gradient),id=definitionId(n,'gradient-'),a=g.angle*Math.PI/180,dx=Math.cos(a),dy=-Math.sin(a),span=(Math.abs(dx)*n.width+Math.abs(dy)*n.height)*g.scale,cx=(n.type==='text'?n.x:0)+n.width/2,cy=(n.type==='text'?n.y:0)+n.height/2;const matrix=n.type==='text'?textMatrix(n):null,det=matrix?matrix[0]*matrix[3]-matrix[1]*matrix[2]:1,inv=matrix?` gradientTransform="matrix(${[matrix[3]/det,-matrix[1]/det,-matrix[2]/det,matrix[0]/det,(matrix[2]*matrix[5]-matrix[3]*matrix[4])/det,(matrix[1]*matrix[4]-matrix[0]*matrix[5])/det].join(' ')})"`:'';const definition=g.kind==='radial'?`<radialGradient id="${esc(id)}" gradientUnits="userSpaceOnUse"${inv} cx="${cx}" cy="${cy}" r="${n.width*g.scale/2}">`:`<linearGradient id="${esc(id)}" gradientUnits="userSpaceOnUse"${inv} x1="${cx-dx*span/2}" y1="${cy-dy*span/2}" x2="${cx+dx*span/2}" y2="${cy+dy*span/2}">`;const stops=g.stops.map(([t,h])=>`<stop offset="${t}" stop-color="${h}"/>`).join(''),end=g.kind==='radial'?'radialGradient':'linearGradient';return `<defs>${definition}${stops}</${end}></defs>`+nodeSvgBase({...n,gradient:null}).replace(`fill="${n.fill}"`,`fill="url(#${esc(id)})"`)}const a=`data-id="${esc(n.id)}" pointer-events="${n.locked?'none':'visiblePainted'}" opacity="${n.opacity??1}"`;if(n.type==='text'){return `<text ${a} transform="matrix(${textMatrix(n).join(' ')})" fill="${n.fill}" stroke="${n.stroke||n.fill}" stroke-width="${(n.strokeWidth||0)*2}" stroke-linejoin="round" paint-order="stroke fill" font-family="${esc(n.fontFamily||'Microsoft YaHei')},sans-serif" font-size="${n.fontSize}" font-style="${n.textSkew?'normal':n.fontStyle||'normal'}" font-weight="${n.fontWeight||400}" xml:space="preserve">${textLines(n).map((line,i)=>`<tspan x="0" y="${i*textLeading(n)}">${esc(line)}</tspan>`).join('')}</text>`;}if(n.type==='image')return `<image ${a} x="${n.x}" y="${n.y}" width="${n.width}" height="${n.height}" href="${esc(n.src)}" preserveAspectRatio="none"/>`;return `<path ${a} transform="translate(${n.x} ${n.y})" d="${geometry(n)}" fill="${n.fill}" fill-rule="evenodd"/>`;}

export function grouped(s,nodes,values,wrap){const byId=new Map(nodes.map((n,i)=>[n.id,values[i]])),groups=new Map((s.groups||[]).map(g=>[g.id,g])),owner=new Map(),seen=new Set(),result=[];for(const g of groups.values())for(const id of g.children)owner.set(id,g.id);function item(id){if(groups.has(id)){const g=groups.get(id);return wrap(g,g.children.map(item).filter(v=>v!=null))}return byId.get(id)}function root(id){while(owner.has(id))id=owner.get(id);return id}for(const n of nodes){const id=root(n.id);if(seen.has(id))continue;seen.add(id);const v=item(id);if(v!=null)result.push(v)}return result;}
export function groupBounds(s,g){const map=new Map(s.nodes.map(n=>[n.id,n])),groups=new Map((s.groups||[]).map(v=>[v.id,v]));const bs=g.children.map(id=>map.get(id)||groupBounds(s,groups.get(id))).filter(Boolean),x=Math.min(...bs.map(n=>n.x)),y=Math.min(...bs.map(n=>n.y));return {x,y,width:Math.max(...bs.map(n=>n.x+n.width))-x,height:Math.max(...bs.map(n=>n.y+n.height))-y};}
export function assertRenderCapacity(s){
 validate(s);const groups=new Map((s.groups||[]).map(g=>[g.id,g])),owner=new Map();for(const g of groups.values())for(const id of g.children)owner.set(id,g.id);
 const nodes=allNodes(s).filter(n=>{let id=n.id;while(owner.has(id)){id=owner.get(id);if(layerHidden(groups.get(id)))return false}return true});
 return decodeUsage(nodes);
}
export function svg(s){assertRenderCapacity(s);const nodes=allNodes(s);return `<svg xmlns="http://www.w3.org/2000/svg" width="${s.width}" height="${s.height}" viewBox="0 0 ${s.width} ${s.height}">${grouped(s,nodes,nodes.map(nodeSvg),(g,parts)=>layerHidden(g)?'':styleSvg('<g data-group="'+esc(g.id)+'" data-name="'+esc(g.name)+'" opacity="'+(g.opacity??1)+'">'+parts.join('')+'</g>',g,groupBounds(s,g))).join('')}</svg>`;}
export function figma(s){validate(s);const visible=allNodes(s),layers=visible.map(n=>{const base={name:n.name||n.text||n.id,x:n.x,y:n.y,width:n.width,height:n.height,opacity:n.opacity??1};if(n.type==='text')return {...base,type:'text',text:n.text,textStroke:n.stroke?color(n.stroke):null,textStrokeWidth:n.strokeWidth||0,fontFamily:n.fontFamily||'Microsoft YaHei',fontStyle:n.fontStyle||'normal',fontSize:n.fontSize,fontWeight:n.fontWeight||400,lineHeight:textLeading(n),height:Math.max(n.height,n.fontSize*1.5),color:color(n.fill)};if(n.type==='image')return {...base,type:'image',image:n.src};if(n.type==='rect')return {...base,type:'box',background:color(n.fill),radii:[1,1,1,1].map(()=>n.radius||0),children:[]};return {...base,type:'svg',svg:'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 '+n.width+' '+n.height+'"><path fill="'+n.fill+'" fill-rule="evenodd" d="'+geometry(n)+'"/></svg>'};});const children=grouped(s,visible,layers,(g,children)=>{const x=Math.min(...children.map(n=>n.x)),y=Math.min(...children.map(n=>n.y));return {type:'box',name:g.name||'分组',x,y,width:Math.max(...children.map(n=>n.x+n.width))-x,height:Math.max(...children.map(n=>n.y+n.height))-y,children,clip:false,background:null}});return {format:'gugu-page-to-figma',version:1,title:s.title,width:s.width,height:s.height,root:{type:'box',name:s.title,x:0,y:0,width:s.width,height:s.height,children},sceneMetadata:{edges:s.edges,groups:s.groups,source:s.provenance},warnings:['文字和形状可编辑；字体为估计值，请对照原图校对。流程关系保存在工程 JSON。']};}
export async function loadImage(src){
 const expected=typeof src==='string'&&imageURI.test(src)?imageMetadata(src):null;if(expected)assertImageDecodeCapacity(expected,'图片');
 let im;if(globalThis.ShijieNodeCanvas)im=await globalThis.ShijieNodeCanvas.loadImage(src);else{im=new Image();im.src=src;await im.decode()}
 const actual={width:im.width,height:im.height,pixels:im.width*im.height};assertImageDecodeCapacity(actual,'图片');
 if(expected&&!((actual.width===expected.width&&actual.height===expected.height)||(actual.width===expected.height&&actual.height===expected.width)))throw Error('实际解码尺寸与图片头部不一致');return im;
}
function releaseDecodedImage(im){if(typeof im.close==='function')im.close();else if(!globalThis.ShijieNodeCanvas&&typeof Image!=='undefined'&&im instanceof Image)im.src=''}
export async function psd(s){assertExportCapacity(s);s=structuredClone(s);const decodedImages=new Map();let cachedPixels=0;
 async function exportImage(src){
  if(decodedImages.has(src)){const image=decodedImages.get(src);decodedImages.delete(src);decodedImages.set(src,image);return image}
  const info=imageMetadata(src);while(decodedImages.size&&cachedPixels+info.pixels>SCENE_CAPACITY_LIMITS.decodeCachePixels){const [key,image]=decodedImages.entries().next().value;cachedPixels-=image.width*image.height;decodedImages.delete(key);releaseDecodedImage(image)}
  const image=await loadImage(src);decodedImages.set(src,image);cachedPixels+=image.width*image.height;return image;
 }
 try{const factory=(w,h)=>{const c=document.createElement('canvas');c.width=w;c.height=h;return c},composite=factory(s.width,s.height),cc=composite.getContext('2d'),layers=[];
 const exportNodes=allNodes(s,true);for(const [index,n] of exportNodes.entries()){const box=n.type==='text'?textInkBounds(n):n,pad=Math.ceil(n.strokeWidth||0)+2,left=Math.floor(box.x)-pad,top=Math.floor(box.y)-pad,w=Math.ceil(box.width)+pad*2,h=Math.ceil(box.height)+pad*2;const canvas=factory(w,h),c=canvas.getContext('2d');c.translate(n.x-left,n.y-top);const layer={id:index+1,name:n.name||n.text||n.id,left,top,canvas,opacity:n.opacity??1,hidden:layerHidden(n),...(n.locked?{protected:{transparency:true,composite:true,position:true}}:{}),blendMode:normalizeStyle(n.layerStyle)?.blendMode||'normal'};
 if(n.type==='image')c.drawImage(await exportImage(n.src),0,0,n.width,n.height);
 else if(n.type==='text'){const matrix=textMatrix(n);c.setTransform(matrix[0],matrix[1],matrix[2],matrix[3],matrix[4]-left,matrix[5]-top);c.font=`${n.textSkew?'normal':n.fontStyle||'normal'} ${n.fontWeight||400} ${n.fontSize}px "${n.fontFamily||'Microsoft YaHei'}"`;c.fillStyle=n.fill;const intrinsicStroke=n.strokeWidth&&n.stroke&&n.layerStyle?.enabled===false;if(intrinsicStroke){c.strokeStyle=n.stroke;c.lineWidth=n.strokeWidth*2;c.lineJoin='round';textLines(n).forEach((line,i)=>c.strokeText(line,0,i*textLeading(n)));}textLines(n).forEach((line,i)=>c.fillText(line,0,i*textLeading(n)));nativeText(layer,{...n,fontStyle:n.textSkew?'normal':n.fontStyle,color:color(n.fill),fontFamily:n.fontFamily||'Microsoft YaHei',lineHeight:textLeading(n)},matrix[5]);layer.text.transform=matrix;if(intrinsicStroke)Object.assign(layer.text.style,{strokeFlag:true,fillFlag:true,fillFirst:false,outlineWidth:n.strokeWidth,strokeColor:{r:parseInt(n.stroke.slice(1,3),16),g:parseInt(n.stroke.slice(3,5),16),b:parseInt(n.stroke.slice(5,7),16)}});if(n.strokeWidth&&n.stroke)layer.effects=nativeEffects({stroke:{color:n.stroke,size:n.strokeWidth,opacity:1,position:'outside'}});}
 else{const d=geometry(n);c.fillStyle=n.fill;c.fill(new Path2D(d),'evenodd');layer.vectorFill={type:'color',color:{r:parseInt(n.fill.slice(1,3),16),g:parseInt(n.fill.slice(3,5),16),b:parseInt(n.fill.slice(5,7),16)}};layer.vectorMask={fillStartsWithAllPixels:false,paths:contourOperations(pathData(d,`translate(${n.x},${n.y})`).paths)};}
 if(n.gradient&&n.type!=='image'){const g=gradientData(n);if(n.type==='text'){const fx=nativeEffects({gradientOverlay:{...normalizeGradient(n.gradient),enabled:true,opacity:1}});layer.effects={...(layer.effects||{}),...fx};}else{gradientCache(canvas,n,left,top);layer.vectorFill=g;}}
 if(n.layerStyle){const fx=nativeEffects(n.layerStyle);layer.effects={...(layer.effects||{}),...fx};}if(n.type==='text'&&n.gradient&&n.layerStyle?.enabled===false){
  // The PSD master covers both intrinsic text gradients and external effects.
  // Keep external parameters as disabled entries, then enable only the source
  // gradient. A second gradientOverlay entry preserves an external override.
  const fx=nativeEffects(n.layerStyle);fx.disabled=false;
  for(const value of Object.values(fx))for(const effect of Array.isArray(value)?value:[value])if(effect&&typeof effect==='object')effect.enabled=false;
  const intrinsic=nativeEffects({gradientOverlay:{...normalizeGradient(n.gradient),enabled:true,opacity:1}}).gradientOverlay;
  fx.gradientOverlay=[...(fx.gradientOverlay||[]),...intrinsic];layer.effects=fx;
 }if(n.type==='text')fitGradientEffects(layer,n);if(n.displayMask)layer.mask=nativeMask(n.displayMask,s.width,s.height,factory,Path2D);layer._target=n;layers.push(layer);}
 const children=grouped(s,exportNodes,layers,(g,children)=>({id:10000+(s.groups||[]).indexOf(g),name:g.name||'分组',children,opened:true,hidden:layerHidden(g),...(g.locked?{protected:{transparency:true,composite:true,position:true}}:{}),opacity:g.opacity??1,blendMode:normalizeStyle(g.layerStyle)?.blendMode||'normal',...(g.layerStyle?{effects:nativeEffects(g.layerStyle)}:{}),...(g.displayMask?{mask:nativeMask(g.displayMask,s.width,s.height,factory,Path2D)}:{}),_target:g}));
 function paint(layer,target){if(layer.hidden)return;let base,left=layer.left||0,top=layer.top||0;if(layer.children){base=factory(s.width,s.height);layer.children.forEach(l=>paint(l,base.getContext('2d')));left=top=0;}else base=layer.canvas;let style=layer._target.layerStyle;if(layer._target.strokeWidth&&layer._target.stroke&&!style?.stroke)style={...(style||{enabled:true}),stroke:{color:layer._target.stroke,size:layer._target.strokeWidth,opacity:1,position:'outside'}};if(layer._target.type==='text'&&layer._target.gradient){style=style?.enabled===false?{enabled:true,gradientOverlay:{...normalizeGradient(layer._target.gradient),enabled:true,opacity:1}}:{...(style||{enabled:true}),gradientOverlay:{...normalizeGradient(layer._target.gradient),enabled:true,opacity:1},...(style?.gradientOverlay?{gradientOverlay:style.gradientOverlay}:{})};}const effectBounds=layer._target.width?{x:layer._target.x-left,y:layer._target.y-top,width:layer._target.width,height:layer._target.height}:alphaBounds(base);if(normalizeMask(layer._target.displayMask)?.enabled){const masked=factory(base.width,base.height),mc=masked.getContext('2d');mc.drawImage(base,0,0);mc.globalCompositeOperation='destination-in';mc.drawImage(displayMaskCanvas(layer._target.displayMask,s.width,s.height,factory,Path2D),-left,-top);base=masked;}const rendered=styleCanvas(base,style,factory,effectBounds),scratch=factory(s.width,s.height),sc=scratch.getContext('2d');sc.drawImage(rendered.canvas,left-rendered.pad,top-rendered.pad);target.save();target.globalAlpha=layer.opacity??1;target.globalCompositeOperation=layer.blendMode==='normal'?'source-over':layer.blendMode;target.drawImage(scratch,0,0);target.restore();}
 children.forEach(l=>paint(l,cc));function clean(l){delete l._target;(l.children||[]).forEach(clean)}children.forEach(clean);return writePsd({width:s.width,height:s.height,canvas:composite,children},{noBackground:true,trimImageData:true});
 }finally{for(const image of decodedImages.values())releaseDecodedImage(image);decodedImages.clear()}
}
export function html(s){validate(s);const data=JSON.stringify(s).replace(/</g,'\\u003c');return `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>${esc(s.title)}</title><style>*{box-sizing:border-box}body{margin:0;background:#151b24;font-family:"Microsoft YaHei",sans-serif;color:#e8eff7}header{padding:14px 22px;display:flex;gap:12px;align-items:center}button{padding:8px 15px;background:#283a49;color:white;border:1px solid #647888;border-radius:6px;cursor:pointer}#wrap{overflow:auto;padding:20px}#board{position:relative;isolation:isolate;background:transparent;transform-origin:top left}.node{position:absolute;cursor:move}.text{white-space:pre;line-height:1;cursor:text}.node:focus{outline:2px solid #5ad7b7}svg{display:block}#connections{position:absolute;inset:0;pointer-events:none}</style><header><b>${esc(s.title)}</b><span>双击文字修改 · 拖动图层 · 流程连线跟随</span><button id="reset">恢复</button><button id="save">保存工程</button></header><div id="wrap"><div id="board"></div></div><script>const original=${data};let s=structuredClone(original);const board=document.getElementById('board');const geom=${geometry.toString()};const edge=${edgeNode.toString()};function drawEdges(){const el=document.getElementById('connections');el.replaceChildren();s.edges.forEach((e,i)=>{const n=edge(s,e,i);if(!n)return;const p=document.createElementNS('http://www.w3.org/2000/svg','path');p.setAttribute('d',n.d);p.setAttribute('fill',n.fill);el.append(p);});}function render(){board.replaceChildren();board.style.width=s.width+'px';board.style.height=s.height+'px';board.style.background=s.background||'transparent';for(const n of s.nodes){if(n.visible===false)continue;let el=document.createElement('div');el.className='node';el.dataset.id=n.id;Object.assign(el.style,{left:n.x+'px',top:n.y+'px',width:n.width+'px',height:n.height+'px',opacity:n.opacity??1});if(n.type==='text'){el.classList.add('text');el.textContent=n.text;Object.assign(el.style,{fontFamily:n.fontFamily||'Microsoft YaHei',fontSize:n.fontSize+'px',fontStyle:n.fontStyle||'normal',fontWeight:n.fontWeight||400,lineHeight:(n.lineHeight||n.fontSize*1.2)+'px',color:n.fill,WebkitTextStroke:(n.strokeWidth||0)*2+'px '+(n.stroke||n.fill),paintOrder:'stroke fill'});el.ondblclick=()=>{if(el.querySelector('textarea'))return;const editor=document.createElement('textarea');editor.value=n.text;editor.setAttribute('aria-label','编辑同一文案');editor.style.cssText='display:block;box-sizing:border-box;width:100%;height:100%;min-height:44px;resize:vertical;font:inherit;line-height:inherit;color:inherit;background:transparent;border:1px solid currentColor;outline:none;padding:0;margin:0';el.replaceChildren(editor);editor.onblur=()=>{n.text=editor.value;el.textContent=n.text};editor.focus();editor.select()};}else if(n.type==='image'){const im=new Image();im.src=n.src;im.style.width='100%';im.style.height='100%';im.draggable=false;el.append(im);}else{const svg=document.createElementNS('http://www.w3.org/2000/svg','svg'),p=document.createElementNS(svg.namespaceURI,'path');svg.setAttribute('width','100%');svg.setAttribute('height','100%');svg.setAttribute('viewBox','0 0 '+n.width+' '+n.height);p.setAttribute('d',geom(n));p.setAttribute('fill',n.fill);p.setAttribute('fill-rule','evenodd');svg.append(p);el.append(svg);}el.onpointerdown=e=>{if(el.isContentEditable||el.querySelector('textarea')||n.locked)return;const x=e.clientX,y=e.clientY,nx=n.x,ny=n.y;el.setPointerCapture(e.pointerId);el.onpointermove=e=>{n.x=nx+e.clientX-x;n.y=ny+e.clientY-y;el.style.left=n.x+'px';el.style.top=n.y+'px';drawEdges()};el.onpointerup=()=>{el.onpointermove=null;};};board.append(el);}const lines=document.createElementNS('http://www.w3.org/2000/svg','svg');lines.id='connections';lines.setAttribute('width',s.width);lines.setAttribute('height',s.height);board.append(lines);drawEdges();}document.getElementById('reset').onclick=()=>{s=structuredClone(original);render()};document.getElementById('save').onclick=()=>{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(s)],{type:'application/json'}));a.download='拾界-网页编辑.scene.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)};render();<\/script></html>`;}

export function resizePath(n,width,height){n.d=pathData(n.d,`scale(${width/n.width},${height/n.height})`).d;n.width=width;n.height=height;}
