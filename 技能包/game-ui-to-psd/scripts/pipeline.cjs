#!/usr/bin/env node
// Deterministic PSD stages. Recognition and image extraction are supplied by model tools.
const fs=require('fs'),path=require('path'),crypto=require('crypto'),cp=require('child_process');
const styleRuntime=require('./style_runtime.cjs');
const toolRoot=__dirname,{runtime,libraries:loadLibraries}=require('./runtime.cjs'),{checkSource}=require('./complete_assets.cjs'),{paintEffects}=require('./layer_effects.cjs');
const args=process.argv.slice(2),command=args.shift()||'status',opts={};
for(let i=0;i<args.length;i++){if(!args[i].startsWith('--'))throw Error('Expected named option');const key=args[i].slice(2);opts[key]=args[i+1]&&!args[i+1].startsWith('--')?args[++i]:true;}
if(!opts.project){console.error('Usage: node pipeline.cjs init|status|build|verify|run --project DIRECTORY [--source IMAGE] [--force]');process.exit(2)}
const project=path.resolve(opts.project),dirs=require('./project_dirs.cjs')(project);
const planFile=path.join(project,dirs.plan,'项目.json'),stateFile=path.join(project,dirs.qa,'流水线状态.json');
const writeJSON=(f,v)=>fs.writeFileSync(f,JSON.stringify(v,null,2),'utf8');
const hash=f=>crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex');
const resolveFile=f=>path.isAbsolute(f)?f:path.resolve(project,f);
function loadJob(){if(!fs.existsSync(planFile))throw Error('需要先 init 项目，再由识别阶段填写 03_结构/项目.json');return JSON.parse(fs.readFileSync(planFile,'utf8'))}
function libraries(job={}){return loadLibraries(job.runtime||{});}
function leaves(ls){return (ls||[]).flatMap(l=>l.kind==='group'?leaves(l.children):[l])}
function preflight(job){
 const errors=[],ls=leaves(job.layers);if(!Number.isInteger(job.width)||!Number.isInteger(job.height)||job.width<=0||job.height<=0)errors.push('识别阶段未填写有效画布尺寸');
 if(!ls.length)errors.push('识别阶段未填写图层');
 if(job.width*job.height>12000000)errors.push('画布超过此工具的 1200 万像素上限');
 const assets=[];if(job.source){const f=resolveFile(job.source);if(!fs.existsSync(f))errors.push('缺少原始截图: '+f);else assets.push(f)}
 for(const l of ls){if(!['bitmap','text','shape'].includes(l.kind)){errors.push('未知图层类型: '+l.kind);continue}
  if(l.clipping||l.native?.clipping)errors.push('当前导出器未实现剪贴组，请先展开或提供实际素材: '+l.name);
  if(l.blendMode&&!['normal','multiply','screen','overlay'].includes(l.blendMode))errors.push('不支持的混合模式: '+l.name);
  if(l.file||l.cache){const f=resolveFile(l.cache||l.file);if(!fs.existsSync(f))errors.push('缺少素材: '+f);else assets.push(f)}else if(l.kind==='bitmap')errors.push('位图缺少文件: '+l.name);
  if(['character','background','artwork'].includes(l.role)&&l.kind!=='bitmap')errors.push('完整素材必须保留位图底稿: '+l.name);
  if(l.role==='artwork'&&!l.completeAssetSHA256)errors.push('完整艺术字必须固定已确认素材的 SHA256: '+l.name);
  if(l.role==='artwork'&&l.cache)errors.push('完整艺术字直接渲染确认素材，不能用另一张显示缓存替代: '+l.name);
  if(l.completeAssetSHA256){const f=resolveFile(l.file||'');if(!fs.existsSync(f)||hash(f)!==l.completeAssetSHA256.toLowerCase())errors.push('完整素材已被改写，与确认底稿不一致: '+l.name)}
  if(l.completeAssetSource){const ref=l.completeAssetSource,f=resolveFile(ref.file);if(!ref.sha256||!fs.existsSync(f)||hash(f)!==ref.sha256.toLowerCase())errors.push('完整素材来源与确认底稿不一致: '+l.name);else assets.push(f);if(l.kind!=='bitmap'||l.cache)errors.push('完整素材来源检查只支持直接位图: '+l.name)}
  if(l.completeAssetSource&&(l.native?.vectorMask||l.native?.mask||l.clipping||l.native?.clipping))errors.push('当前直接素材蒙版未实现完整回读验证，请使用父组 displayMask 保留完整底稿: '+l.name);
  if(job.enforceCompleteSources&&l.role==='character'&&!l.completeAssetSource)errors.push('完整人物缺少源底稿登记，先运行 register_asset: '+l.name);
  if(l.kind==='text'&&l.cache&&!l.native?.text)errors.push('文字缓存缺少原生 text 描述: '+l.name);
  if(l.cleanTextSource){
   const proof=l.cleanTextSource,cache=resolveFile(l.cache||'');
   if(!fs.existsSync(cache)||hash(cache)!==proof.cacheSHA256)errors.push('干净文字缓存被改写：'+l.name);
   if(crypto.createHash('sha256').update(JSON.stringify(l.native?.text||{})).digest('hex')!==proof.nativeTextSHA256)errors.push('文字内容或描述已修改，必须重新绘制透明缓存：'+l.name);
  }
  if(l.kind==='shape'&&l.cache&&(!l.native?.vectorFill||!l.native?.vectorMask))errors.push('形状缓存缺少原生填充或路径: '+l.name);
 }
 if(ls.filter(l=>l.role==='background').length>1)errors.push('同一完整素材被拆成多个 background 图层');
 // Distinct people are legal. Repeated source or repeated semantic entity is
 // independently illegal: renaming an entity must never hide source reuse.
 const characterSources=new Set(),characterEntities=new Set();
 for(const l of ls.filter(l=>l.role==='character')){
  const source=l.completeAssetSource?.sha256||l.completeAssetSHA256||(l.file&&fs.existsSync(resolveFile(l.file))?hash(resolveFile(l.file)):null),entity=l.completeAssetIdentity;
  if(source){const key=source.toLowerCase();if(characterSources.has(key))errors.push('同一完整素材被拆成多个 character 图层（重复底稿 SHA256）: '+l.name);characterSources.add(key)}
  if(entity){if(typeof entity!=='string')errors.push('人物实体编号必须是字符串: '+l.name);else{if(characterEntities.has(entity))errors.push('同一完整素材被拆成多个 character 图层（重复人物实体）: '+l.name);characterEntities.add(entity)}}
 }
 return {errors,assets,leafCount:ls.length};
}
function fingerprint(job,assets){const h=crypto.createHash('sha256');for(const file of ['pipeline.cjs','runtime.cjs','runtime.json','complete_assets.cjs','audit_psd.py','layer_effects.cjs','gradient_fill.cjs','style_runtime.cjs','psd_gradient_compat.py','project_dirs.cjs'])h.update(hash(path.join(toolRoot,file)));h.update(JSON.stringify(job));for(const f of [...new Set(assets)].sort())h.update(f+'\n'+hash(f));return h.digest('hex');}
function outputPath(job){const name=job.outputName||'可编辑分层.psd';if(path.basename(name)!==name||!name.toLowerCase().endsWith('.psd'))throw Error('outputName 必须是 PSD 文件名');return path.join(project,dirs.output,name);}
async function build(job,check){
 const {ag,cv,svgpath}=libraries(job),{createCanvas,loadImage,GlobalFonts,Path2D}=cv;ag.initializeCanvas(createCanvas);
 for(const f of job.fonts||[])if(!GlobalFonts.registerFromPath(resolveFile(f.file),f.family))throw Error('字体载入失败: '+f.file);
 const W=job.width,H=job.height,color=s=>({r:parseInt(s.slice(1,3),16),g:parseInt(s.slice(3,5),16),b:parseInt(s.slice(5,7),16)});
 const knot=(x,y,ix=x,iy=y,ox=x,oy=y)=>({linked:false,points:[ix,iy,x,y,ox,oy]});
 function paths(d,operation='combine'){
  const p=svgpath(d).abs().unshort().unarc(),ps=[];let cur,x=0,y=0;
  p.iterate(s=>{let cmd=s[0];if(cmd==='M'){cur={open:true,operation,fillRule:'even-odd',knots:[knot(s[1],s[2])]};ps.push(cur);x=s[1];y=s[2];return}
   if(cmd==='Z'){cur.open=false;let a=cur.knots[0],b=cur.knots.at(-1);if(a.points[2]===b.points[2]&&a.points[3]===b.points[3]){a.points[0]=b.points[0];a.points[1]=b.points[1];cur.knots.pop()}x=a.points[2];y=a.points[3];return}
   let nx,ny,ax=x,ay=y,bx,by;if(cmd==='L'){nx=s[1];ny=s[2]}else if(cmd==='H'){nx=s[1];ny=y}else if(cmd==='V'){nx=x;ny=s[1]}else if(cmd==='C'){[ax,ay,bx,by,nx,ny]=s.slice(1)}else if(cmd==='Q'){nx=s[3];ny=s[4];ax=x+(s[1]-x)*2/3;ay=y+(s[2]-y)*2/3;bx=nx+(s[1]-nx)*2/3;by=ny+(s[2]-ny)*2/3}else throw Error(cmd);
   cur.knots.at(-1).points.splice(4,2,ax,ay);cur.knots.push(knot(nx,ny,bx??nx,by??ny));x=nx;y=ny;
  });return ps;
 }
 function trim(c){const d=c.getContext('2d').getImageData(0,0,W,H).data;let left=W,top=H,right=0,bottom=0;for(let y=0;y<H;y++)for(let x=0;x<W;x++)if(d[(y*W+x)*4+3]){left=Math.min(left,x);top=Math.min(top,y);right=Math.max(right,x+1);bottom=Math.max(bottom,y+1)}if(right<=left||bottom<=top)throw Error('空图层');const small=createCanvas(right-left,bottom-top);small.getContext('2d').drawImage(c,left,top,right-left,bottom-top,0,0,right-left,bottom-top);return {left,top,right,bottom,canvas:small};}
 async function leaf(s){
  const native={...(s.native||{})};for(const bad of ['canvas','imageData','children','mask'])if(bad in native)throw Error('unsupported native field: '+bad);
  let layer;if(s.cache){const im=await loadImage(resolveFile(s.cache));const c=createCanvas(im.width,im.height);c.getContext('2d').drawImage(im,0,0);layer={canvas:c,left:s.x||0,top:s.y||0};}
  else if(s.kind==='bitmap'){const im=await loadImage(resolveFile(s.file)),w=Math.ceil(s.width??im.width),h=Math.ceil(s.height??im.height),c=createCanvas(w,h);c.getContext('2d').drawImage(im,0,0,s.width??im.width,s.height??im.height);layer={canvas:c,left:s.x||0,top:s.y||0,right:(s.x||0)+w,bottom:(s.y||0)+h};}
  else {const c=createCanvas(W,H),ctx=c.getContext('2d');
   if(s.kind==='bitmap'){const im=await loadImage(resolveFile(s.file));ctx.drawImage(im,s.x||0,s.y||0,s.width??im.width,s.height??im.height);}
   else if(s.kind==='text'){const t=s.text||{},size=t.size||24,baseline=t.baseline??((s.y||0)+size),family=t.family||'Microsoft YaHei';ctx.font=`${t.bold?'bold ':''}${size}px "${family}"`;ctx.textBaseline='alphabetic';ctx.lineJoin='round';const scale=t.targetWidth?t.targetWidth/ctx.measureText(t.value||'').width:1;ctx.save();ctx.translate(s.x||0,baseline);ctx.scale(scale,1);if(t.stroke){ctx.strokeStyle=t.stroke;ctx.lineWidth=(t.strokeWidth||1)*2;ctx.strokeText(t.value,0,0)}ctx.fillStyle=t.color||'#ffffff';ctx.fillText(t.value,0,0);ctx.restore();native.text={text:t.value,shapeType:'point',antiAlias:'smooth',transform:[scale,0,0,1,s.x||0,baseline],style:{font:{name:t.postscript||'MicrosoftYaHei'},fontSize:size,fillColor:color(t.color||'#ffffff'),fauxBold:!!t.fauxBold,leading:size*1.2,autoLeading:false,...(t.stroke?{strokeFlag:true,fillFlag:true,fillFirst:false,outlineWidth:t.strokeWidth||1,strokeColor:color(t.stroke)}:{})},paragraphStyle:{justification:'left'}};}
   else if(s.kind==='shape'){const sh=s.shapes||[{d:s.d}];for(const p of sh){ctx.fillStyle='#fff';if(p.operation==='intersect'){const tmp=createCanvas(W,H);tmp.getContext('2d').fillStyle='#fff';tmp.getContext('2d').fill(new Path2D(p.d));ctx.globalCompositeOperation='destination-in';ctx.drawImage(tmp,0,0)}else{ctx.globalCompositeOperation=p.operation==='subtract'?'destination-out':'source-over';ctx.fill(new Path2D(p.d),'evenodd')}}ctx.globalCompositeOperation='source-in';if(s.gradient){native.vectorFill=require('./gradient_fill.cjs').paintGradient(ctx,c,s,cv);}else{ctx.fillStyle=s.color||'#ffffff';native.vectorFill={type:'color',color:color(s.color||'#ffffff')}}ctx.fillRect(0,0,W,H);native.vectorMask={fillStartsWithAllPixels:false,paths:sh.flatMap(p=>paths(p.d,p.operation))};}
   layer=trim(c);
  }
  if(s.gradient&&native.vectorFill){const g=s.gradient,bw=layer.right-layer.left,bh=layer.bottom-layer.top;let cx,cy;if((g.style||'linear')==='radial'){[cx,cy]=g.axis;native.vectorFill.scale=2*g.axis[5]/bw;}else{const [x0,y0,x1,y1]=g.axis,dx=x1-x0,dy=y1-y0,len=Math.hypot(dx,dy);cx=(x0+x1)/2;cy=(y0+y1)/2;native.vectorFill.scale=len/(Math.abs(dx/len)*bw+Math.abs(dy/len)*bh);}native.vectorFill.offset={x:(cx-(layer.left+layer.right)/2)/bw,y:(cy-(layer.top+layer.bottom)/2)/bh};}
  const result={...native,...layer,...((s.sourceNativeLayerId??s.nativeLayerId)!==undefined?{id:s.sourceNativeLayerId??s.nativeLayerId}:{}),name:s.name,opacity:s.opacity??1,hidden:!!s.hidden,blendMode:s.blendMode||'normal'};
  if(s.completeAssetSource){
   const actual=createCanvas(W,H);actual.getContext('2d').drawImage(result.canvas,result.left,result.top);
   await checkSource(s,job,cv,resolveFile,actual);
  }
  if(s.kind==='text'&&!result.text)throw Error('文字没有原生描述');if(s.kind==='shape'&&!result.vectorFill)throw Error('矢量没有原生填充');
  if(['character','background'].includes(s.role)){const full=createCanvas(W,H);full.getContext('2d').drawImage(result.canvas,result.left,result.top);const index=leaves(job.layers).indexOf(s)+1,name=s.role==='character'&&leaves(job.layers).filter(l=>l.role==='character').length>1?'完整人物_'+String(index).padStart(3,'0')+'_'+s.name.replace(/[\\/:*?"<>|]/g,'_')+'.png':s.role==='character'?'完整人物.png':'完整背景.png';fs.writeFileSync(path.join(project,dirs.compact?dirs.qa:dirs.output,name),full.toBuffer('image/png'))}return result;
 }
 async function visit(s){if(s.kind==='group'){const children=[];for(const ch of s.children||[])children.push(await visit(ch));const result={name:s.name,children,...(s.nativeLayerId!==undefined?{id:s.nativeLayerId}:{}),hidden:!!s.hidden,opacity:s.opacity??1,opened:false,blendMode:s.blendMode||'normal',...(s.native?.effects?{effects:s.native.effects}:{})};if(s.displayMask){const m=s.displayMask;if(!m.d||!m.reason)throw Error('显示遮罩必须登记路径和用途: '+s.name);const alpha=createCanvas(W,H),ac=alpha.getContext('2d');ac.fillStyle='#fff';ac.fill(new Path2D(m.d),'evenodd');const gray=createCanvas(W,H),gc=gray.getContext('2d');gc.fillStyle='#000';gc.fillRect(0,0,W,H);gc.drawImage(alpha,0,0);result.mask={canvas:gray,left:0,top:0,right:W,bottom:H,disabled:!!m.disabled,defaultColor:0};result._displayMask={canvas:alpha,disabled:!!m.disabled};}return result}try{return await leaf(s)}catch(e){throw Error(s.name+': '+e.message)}}
 const children=[];for(const s of job.layers)children.push(await visit(s));
 function paint(ls,target){for(const l of ls){if(l.hidden)continue;let base,left=l.left||0,top=l.top||0;if(l.children){base=createCanvas(W,H);paint(l.children,base.getContext('2d'));left=top=0;}else base=l.canvas;const effectBounds=styleRuntime.alphaBounds(base);if(l._displayMask&&!l._displayMask.disabled){const masked=createCanvas(base.width,base.height),mc=masked.getContext('2d');mc.drawImage(base,0,0);mc.globalCompositeOperation='destination-in';mc.drawImage(l._displayMask.canvas,-left,-top);base=masked;}const rendered=styleRuntime.styleCanvas(base,styleRuntime.nativeToStyle(l.effects,l.blendMode||'normal'),createCanvas,effectBounds),tmp=createCanvas(W,H),tc=tmp.getContext('2d');tc.drawImage(rendered.canvas,left-rendered.pad,top-rendered.pad);target.save();target.globalAlpha*=l.opacity??1;target.globalCompositeOperation=l.blendMode==='normal'?'source-over':l.blendMode||'source-over';target.drawImage(tmp,0,0);target.restore();}}
 const c=createCanvas(W,H);paint(children,c.getContext('2d'));const psd={width:W,height:H,canvas:c,children};
 const buf=ag.writePsdBuffer(psd,{noBackground:true,trimImageData:true,invalidateTextLayers:false}),file=outputPath(job),tmp=file+'.writing';fs.writeFileSync(tmp,buf);fs.renameSync(tmp,file);
 fs.writeFileSync(path.join(project,dirs.compact?dirs.qa:dirs.output,'合成预览.png'),c.toBuffer('image/png'));
 let state={};if(fs.existsSync(stateFile))state=JSON.parse(fs.readFileSync(stateFile));state={...state,build:{fingerprint:fingerprint(job,check.assets),psdSHA256:hash(file),completedAt:new Date().toISOString()},verify:{status:'REQUIRED'},visualReview:'REQUIRED'};writeJSON(stateFile,state);console.log(JSON.stringify({stage:'PSD_EXPORT',status:'PASS',file,visualReview:'REQUIRED'}));
}
async function verify(job){
 const rt=runtime(job.runtime||{}),{cv}=libraries(job),rows=[];
 const refDir=path.join(project,dirs.qa,'完整底稿参考');fs.mkdirSync(refDir,{recursive:true});
 for(const [index,s] of leaves(job.layers).entries()){if(!s.completeAssetSource)continue;const result=await checkSource(s,job,cv,resolveFile);const file=path.join(refDir,String(index+1).padStart(3,'0')+'.png');fs.writeFileSync(file,result.canvas.toBuffer('image/png'));rows.push({index,name:s.name,sourceSHA256:result.sourceSHA256,assetSHA256:result.assetSHA256,changedPixels:result.changedPixels,reference:path.relative(project,file).replace(/\\/g,'/'),referenceSHA256:hash(file)});}
 writeJSON(path.join(project,dirs.qa,'来源检查.json'),{projectManifestSHA256:hash(planFile),psdSHA256:hash(outputPath(job)),checks:rows});
 const a=[path.join(toolRoot,'audit_psd.py'),outputPath(job),'--project',project,'--psd-tools-path',rt.psdTools];
 const r=cp.spawnSync(rt.python,a,{encoding:'utf8',env:{...process.env,PYTHONUTF8:'1',PYTHONPATH:rt.psdTools+(process.env.PYTHONPATH?path.delimiter+process.env.PYTHONPATH:'')},windowsHide:true});if(r.stdout)process.stdout.write(r.stdout);if(r.stderr)process.stderr.write(r.stderr);if(r.error)throw Error('无法启动 PSD 检查运行时: '+r.error.message);if(r.status!==0)throw Error('PSD 回读检查失败');
 let state=fs.existsSync(stateFile)?JSON.parse(fs.readFileSync(stateFile)):{},report=JSON.parse(fs.readFileSync(path.join(project,dirs.qa,'检查结果.json')));state.verify={psdSHA256:hash(outputPath(job)),completedAt:new Date().toISOString(),structuralChecks:report.structuralChecks,assetChecks:report.assetChecks};state.visualReview='REQUIRED';writeJSON(stateFile,state);
}
async function main(){
 if(command==='init'){for(const d of Object.values(dirs).filter(d=>typeof d==='string'))fs.mkdirSync(path.join(project,d),{recursive:true});if(fs.existsSync(planFile))throw Error('项目已有清单，不覆盖；请使用 status');if(!opts.source)throw Error('init 需要 --source 原始截图');const input=path.join(project,dirs.input,path.basename(opts.source));if(path.resolve(opts.source)!==input)fs.copyFileSync(path.resolve(opts.source),input);const {cv}=libraries(),im=await cv.loadImage(input);writeJSON(planFile,{format:'game-ui-psd-v1',width:im.width,height:im.height,source:path.relative(project,input).replace(/\\/g,'/'),outputName:'可编辑分层.psd',enforceCompleteSources:true,layers:[]});writeJSON(stateFile,{input:{sha256:hash(input)},recognition:'REQUIRED',assets:'REQUIRED',visualReview:'REQUIRED'});console.log(JSON.stringify({project,next:'识别原图，填写项目.json；完整人物/艺术字先 register，再组装与检查。'}));return}
 const job=loadJob(),check=preflight(job);if(command==='status'){let state=fs.existsSync(stateFile)?JSON.parse(fs.readFileSync(stateFile)):{},finger=check.errors.length?null:fingerprint(job,check.assets);console.log(JSON.stringify({project,canvas:[job.width,job.height],leafCount:check.leafCount,blocking:check.errors,buildReusable:!!finger&&state.build?.fingerprint===finger&&fs.existsSync(outputPath(job))&&state.build?.psdSHA256===hash(outputPath(job)),visualReview:state.visualReview||'REQUIRED'},null,2));return}
 if(check.errors.length)throw Error(check.errors.join('\n'));
 if(!['run','build','verify'].includes(command))throw Error('Unknown command: '+command);
 for(const d of Object.values(dirs).filter(d=>typeof d==='string'))fs.mkdirSync(path.join(project,d),{recursive:true});
 if(command!=='verify'){const state=fs.existsSync(stateFile)?JSON.parse(fs.readFileSync(stateFile)):{},reusable=state.build?.fingerprint===fingerprint(job,check.assets)&&fs.existsSync(outputPath(job))&&state.build?.psdSHA256===hash(outputPath(job));if(reusable&&!opts.force)console.log(JSON.stringify({stage:'PSD_EXPORT',status:'REUSED'}));else await build(job,check)}
 if(command!=='build')await verify(job);
 if(command==='run')await require('./render_checks.cjs')(project);
}
main().catch(e=>{console.error(e.message);process.exitCode=1});
