// Render complete text from font data onto transparent pixels; never sample screenshot RGB.
const fs=require('fs'),path=require('path'),crypto=require('crypto'),{libraries}=require('./runtime.cjs');
const sha=value=>crypto.createHash('sha256').update(value).digest('hex');
function renderText(text,options={}){
 const {cv}=libraries(options.runtime||{}),fontName=text.style?.font?.name;
 const fonts={ArialMT:'arial.ttf','Arial-BoldMT':'arialbd.ttf',Impact:'impact.ttf',SimHei:'simhei.ttf',MicrosoftYaHei:'msyh.ttc','MicrosoftYaHei-Bold':'msyhbd.ttc'};
 const fontFile=options.fontFile||path.join(process.env.WINDIR||'C:/Windows','Fonts',fonts[fontName]||'');
 if(!fonts[fontName]&&!options.fontFile)throw Error('请为该原生字体配置实际文件：'+fontName);
 const family='CleanCache_'+fontName;
 if(!cv.GlobalFonts.registerFromPath(fontFile,family))throw Error('无法加载文字缓存字体：'+fontFile);
 const probe=cv.createCanvas(1,1).getContext('2d'),size=text.style.fontSize;
 probe.font=`${size}px "${family}"`;probe.textBaseline='alphabetic';
 const color=text.style.fillColor,css=`rgb(${color.r},${color.g},${color.b})`,operations=[];
 function bounds(value,matrix){
  const m=probe.measureText(value),x0=-m.actualBoundingBoxLeft,x1=m.actualBoundingBoxRight,y0=-m.actualBoundingBoxAscent,y1=m.actualBoundingBoxDescent;
  const corners=[[x0,y0],[x1,y0],[x1,y1],[x0,y1]].map(([x,y])=>[matrix[0]*x+matrix[2]*y+matrix[4],matrix[1]*x+matrix[3]*y+matrix[5]]);
  operations.push({value,matrix,corners});
 }
 if(text.warp&&text.warp.style!=='none'){
  if(!options.arcLayout)throw Error('弧形文字需要已核对的定位；不能静默改成直线或复制脏缓存。');
  if(options.arcLayout.glyphs.map(g=>g.char).join('')!==text.text.replace(/\s/g,''))throw Error('弧形字符与可编辑文字内容不同');
  for(const glyph of options.arcLayout.glyphs){
   const m=probe.measureText(glyph.char),x0=-m.actualBoundingBoxLeft,x1=m.actualBoundingBoxRight,y0=-m.actualBoundingBoxAscent,y1=m.actualBoundingBoxDescent;
   const sx=(glyph.inkWidth||x1-x0)/(x1-x0),sy=(glyph.inkHeight||y1-y0)/(y1-y0),cs=Math.cos(glyph.angle),sn=Math.sin(glyph.angle);
   const a=cs*sx,b=sn*sx,c=-sn*sy,d=cs*sy,cx=(x0+x1)/2,cy=(y0+y1)/2;
   bounds(glyph.char,[a,b,c,d,glyph.center[0]-a*cx-c*cy,glyph.center[1]-b*cx-d*cy]);
  }
 }else bounds(text.text,text.transform);
 const points=operations.flatMap(o=>o.corners),left=Math.floor(Math.min(...points.map(p=>p[0])))-3,top=Math.floor(Math.min(...points.map(p=>p[1])))-3;
 const right=Math.ceil(Math.max(...points.map(p=>p[0])))+3,bottom=Math.ceil(Math.max(...points.map(p=>p[1])))+3;
 const canvas=cv.createCanvas(right-left,bottom-top),ctx=canvas.getContext('2d');ctx.font=probe.font;ctx.textBaseline='alphabetic';ctx.fillStyle=css;
 for(const o of operations){const t=o.matrix;ctx.setTransform(t[0],t[1],t[2],t[3],t[4]-left,t[5]-top);ctx.fillText(o.value,0,0);}
 const png=canvas.toBuffer('image/png');
 return {canvas,png,x:left,y:top,width:canvas.width,height:canvas.height,proof:{method:'font-only-transparent-render',nativeTextSHA256:sha(JSON.stringify(text)),cacheSHA256:sha(png),fillColor:color,fontFile,glyphCount:text.text.replace(/\s/g,'').length,arcLayout:options.arcLayout||null}};
}
function repairProject(project,arcLayouts={}){
 const root=path.resolve(project),dirs=require('./project_dirs.cjs')(root),file=path.join(root,(dirs.plan+'/项目.json')),job=JSON.parse(fs.readFileSync(file,'utf8')),dir=path.join(root,(dirs.plan+'/干净文字缓存'));fs.mkdirSync(dir,{recursive:true});let index=0;const rows=[];
 function visit(items){for(const s of items){if(s.kind==='group'){visit(s.children||[]);continue;}if(s.kind!=='text'||!s.cache)continue;
  if(!s.native?.text)throw Error('文字缓存没有原生描述：'+s.name);
  const result=renderText(s.native.text,{arcLayout:arcLayouts[s.name],runtime:job.runtime});const target=path.join(dir,String(++index).padStart(3,'0')+'.png');fs.writeFileSync(target,result.png);
  s.cache=path.relative(root,target).replace(/\\/g,'/');s.x=result.x;s.y=result.y;s.cleanTextSource=result.proof;
  rows.push({name:s.name,text:s.native.text.text,cache:s.cache,width:result.width,height:result.height,method:result.proof.method});
 }}visit(job.layers);fs.writeFileSync(file,JSON.stringify(job,null,2));fs.writeFileSync(path.join(root,(dirs.plan+'/干净文字登记.json')),JSON.stringify(rows,null,2));return rows;
}
module.exports={renderText,repairProject};
if(require.main===module){const i=process.argv.indexOf('--project'),a=process.argv.indexOf('--arc-layouts');if(i<0)throw Error('render_text_cache.cjs --project DIR [--arc-layouts JSON]');const layouts=a>=0?JSON.parse(fs.readFileSync(process.argv[a+1],'utf8')):{};console.log(JSON.stringify({cleanTextLayers:repairProject(process.argv[i+1],layouts).length}));}
