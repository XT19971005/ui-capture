const fs=require('fs'),path=require('path'),assert=require('assert');
const root=path.resolve(__dirname,'../..'),out=path.join(root,'自检记录/图像重建');
const libs='D:/@谢涛/@TUSY/麻将/2026_8_24AI/2026_10_9UI拆分/拾界插件/依赖/构建工具/node_modules/';
const ag=require(libs+'ag-psd'),{createCanvas,ImageData,GlobalFonts}=require(libs+'@napi-rs/canvas');
GlobalFonts.registerFromPath('C:/Windows/Fonts/msyh.ttc','Microsoft YaHei');
ag.initializeCanvas(createCanvas,(w,h)=>new ImageData(w,h));
const art=fs.readFileSync(path.join(out,'艺术字_矢量路径.svg'),'utf8');
const titlePaths=[...art.matchAll(/<path\s+d="([^"]+)"\s+fill="([^"]+)"\s+transform="translate\(([^)]+)\)"/g)].map(m=>{
const [tx,ty]=m[3].split(/[ ,]+/).map(Number);const tokens=m[1].match(/[MLZ]|-?\d+(?:\.\d+)?/g);const parts=[];let current=[];
for(let i=0;i<tokens.length;){const cmd=tokens[i++];if(cmd==='M'||cmd==='L'){if(cmd==='M'&&current.length){parts.push(current);current=[];}current.push([+tokens[i++]+tx+64,+tokens[i++]+ty+36]);}else if(cmd==='Z'){parts.push(current);current=[];}else throw Error('Unsupported path command');}if(current.length)parts.push(current);return {fill:m[2],parts};});
assert(titlePaths.length>=2);
const scene={format:'shijie-scene',version:1,width:1280,height:760,title:'拾界 · 编辑能力技术验证',provenance:'Synthetic fixture; not an automatic reconstruction result',nodes:[
{id:'page',type:'rect',x:0,y:0,width:1280,height:760,fill:'#141b27'},
{id:'art',type:'path',paths:titlePaths,sourceText:'拾界',semanticTextEditable:true},
{id:'subtitle',type:'text',text:'图片重建 · 文字 / 矢量 / 流程关系',x:360,y:110,fontSize:25,fill:'#e8eef6'},
{id:'caption',type:'text',text:'技术验证样例：文字是真实文本；标题来自位图描摹；方框和箭头是路径。',x:360,y:157,fontSize:16,fill:'#9caabd'},
{id:'n1',type:'rect',x:80,y:285,width:250,height:130,fill:'#25364c'},
{id:'n2',type:'rect',x:515,y:285,width:250,height:130,fill:'#20463f'},
{id:'n3',type:'rect',x:950,y:285,width:250,height:130,fill:'#25364c'},
{id:'t1',type:'text',text:'选择图片',x:126,y:345,fontSize:30,fill:'#f4f7fb'},
{id:'t2',type:'text',text:'编辑与校对',x:555,y:345,fontSize:30,fill:'#f4f7fb'},
{id:'t3',type:'text',text:'导出设计',x:996,y:345,fontSize:30,fill:'#f4f7fb'},
{id:'s1',type:'text',text:'UI / 流程图 / 海报',x:126,y:383,fontSize:15,fill:'#b7c8d9'},
{id:'s2',type:'text',text:'修改文字、移动节点',x:564,y:383,fontSize:15,fill:'#b7dcd4'},
{id:'s3',type:'text',text:'HTML / Figma / PSD / SVG',x:972,y:383,fontSize:15,fill:'#b7c8d9'},
{id:'explain',type:'text',text:'文字保留字符和字体信息；路径保留可缩放轮廓；流程图保留源节点与目标节点。',x:80,y:530,fontSize:20,fill:'#d0dbe7'},
{id:'limit',type:'text',text:'尚未接入自动图片识别；艺术字路径不能直接打字改形，修改内容需要重新生成轮廓。',x:80,y:577,fontSize:17,fill:'#94a5b9'},
{id:'limit2',type:'text',text:'PSD 导出结构已回读验证，Photoshop 客户端编辑验收仍待完成。',x:80,y:615,fontSize:17,fill:'#94a5b9'}
],edges:[{id:'e1',source:'n1',target:'n2'},{id:'e2',source:'n2',target:'n3'}]};
function polygon(parts,fill){return {type:'path',paths:[{parts,fill}]};}
for(const e of scene.edges){const a=scene.nodes.find(n=>n.id===e.source),b=scene.nodes.find(n=>n.id===e.target),x=a.x+a.width+16,y=a.y+a.height/2,x2=b.x-16;scene.nodes.push({id:e.id,...polygon([[[x,y-3],[x2-12,y-3],[x2-12,y-10],[x2,y],[x2-12,y+10],[x2-12,y+3],[x,y+3]]],'#5dd4b9')});}
const rgb=h=>({r:parseInt(h.slice(1,3),16),g:parseInt(h.slice(3,5),16),b:parseInt(h.slice(5,7),16)});
const layers=[],composite=createCanvas(scene.width,scene.height),cc=composite.getContext('2d');
function pathsFor(n){return n.type==='rect'?[{fill:n.fill,parts:[[[n.x,n.y],[n.x+n.width,n.y],[n.x+n.width,n.y+n.height],[n.x,n.y+n.height]]]}]:n.paths;}
for(const n of scene.nodes){if(n.type==='text'){
const c=createCanvas(scene.width,scene.height),ctx=c.getContext('2d');ctx.font=n.fontSize+'px "Microsoft YaHei"';ctx.fillStyle=n.fill;ctx.fillText(n.text,n.x,n.y);cc.drawImage(c,0,0);
layers.push({name:'可编辑文字 · '+n.id,canvas:c,text:{text:n.text,transform:[1,0,0,1,n.x,n.y],antiAlias:'smooth',style:{font:{name:'MicrosoftYaHei'},fontSize:n.fontSize,fillColor:rgb(n.fill)},shapeType:'point'}});
}else for(const p of pathsFor(n)){
const c=createCanvas(scene.width,scene.height),ctx=c.getContext('2d');ctx.fillStyle=p.fill;ctx.beginPath();for(const part of p.parts){part.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.closePath();}ctx.fill('evenodd');cc.drawImage(c,0,0);
layers.push({name:'矢量形状 · '+n.id,canvas:c,vectorFill:{type:'color',color:rgb(p.fill)},vectorMask:{fillStartsWithAllPixels:false,paths:p.parts.map(part=>({open:false,fillRule:'even-odd',operation:'combine',knots:part.map(([x,y])=>({linked:false,points:[x,y,x,y,x,y]}))}))}});
}}
const psd=ag.writePsdBuffer({width:scene.width,height:scene.height,canvas:composite,children:layers},{noBackground:true,trimImageData:true});
fs.writeFileSync(path.join(out,'原生文字与矢量_技术验证.psd'),psd);
fs.writeFileSync(path.join(out,'技术验证_预览.png'),composite.toBuffer('image/png'));
fs.writeFileSync(path.join(out,'技术验证.scene.json'),JSON.stringify(scene,null,2));
const parsed=ag.readPsd(psd,{skipLayerImageData:true,skipCompositeImageData:true,skipThumbnail:true});
const texts=parsed.children.filter(l=>l.text),vectors=parsed.children.filter(l=>l.vectorMask);
assert.equal(texts.length,scene.nodes.filter(n=>n.type==='text').length);assert(vectors.length>=8);assert(texts.some(l=>l.text.text==='编辑与校对'));assert(vectors.every(l=>l.vectorMask.paths.length));
assert(psd.includes(Buffer.from('TySh'))&&psd.includes(Buffer.from('vmsk')));
const metrics={status:'PASS',textLayers:texts.length,vectorLayers:vectors.length,pathContours:vectors.reduce((a,l)=>a+l.vectorMask.paths.length,0),photoshopClientVerified:false,automaticImageReconstruction:false,inputs:'synthetic controlled fixture + raster title'};
fs.writeFileSync(path.join(out,'导出验证结果.json'),JSON.stringify(metrics,null,2));console.log(JSON.stringify(metrics));
module.exports={scene,titlePaths};

