// Use the existing game-ui-to-psd exporter, source checks and independent PSD audit.
const fs=require('fs'),path=require('path'),crypto=require('crypto'),cp=require('child_process');
const root=path.resolve(__dirname,'../..'),nm=path.resolve(root,'../技能包/依赖/Node/node_modules'),cv=require(path.join(nm,'@napi-rs/canvas')),ag=require(path.join(nm,'ag-psd'));
globalThis.document={createElement:()=>cv.createCanvas(1,1)};globalThis.Path2D=cv.Path2D;globalThis.ShijieNodeCanvas=cv;ag.initializeCanvas(cv.createCanvas);
for(const [file,name] of [['arial.ttf','Arial'],['arialn.ttf','Arial Narrow'],['arialnb.ttf','Arial Narrow'],['impact.ttf','Impact'],['HATTEN.TTF','Haettenschweiler'],['msyh.ttc','Microsoft YaHei'],['msyhbd.ttc','Microsoft YaHei'],['simhei.ttf','SimHei']])cv.GlobalFonts.registerFromPath('C:/Windows/Fonts/'+file,name);
const S=require('./scene-native.cjs'),skill=path.resolve(root,'../技能包/game-ui-to-psd/scripts');
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
function spawnResult(label,result){
 if(result.error)throw Error(label+'无法启动: '+result.error.message);
 if(result.status!==0)throw Error(label+'失败 ('+(result.status===null?'无退出码':result.status)+'): '+String(result.stderr||result.stdout||'').slice(-1800));
 return result;
}
module.exports={spawnResult};
if(require.main===module)(async()=>{
 const [file,target,preview]=process.argv.slice(2),scene=S.validate(JSON.parse(fs.readFileSync(file,'utf8'))),project=path.resolve(path.dirname(file),'../..'),processRoot=path.join(project,'1_过程');
 const native=ag.readPsd(Buffer.from(await S.psd(scene))),materials=path.join(processRoot,'01_素材'),structure=path.join(processRoot,'02_结构');fs.mkdirSync(materials,{recursive:true});
 const nodes=S.allNodes(scene),layerById=new Map();function indexLayers(items){for(const l of items){if(layerById.has(l.id))throw Error('原生图层 ID 重复');layerById.set(l.id,l);if(l.children)indexLayers(l.children)}}indexLayers(native.children);
 if(nodes.some(n=>typeof n.name!=='string'||!n.name.trim())||new Set(nodes.map(n=>n.name)).size!==nodes.length)throw Error('每个实际图层必须具有唯一且非空的名称，再逐层登记和复核');
 const registry=[],specById=new Map();let auxiliaryIndex=scene.nodes.length;
 const runtimeStyle=require(path.join(skill,'style_runtime.cjs'));
 for(const [i,n] of nodes.entries()){
  const l=layerById.get(i+1);if(!l||l.children)throw Error('原生图层 ID 映射缺失: '+n.id);const name=n.name||n.text||n.id,filename=String(i).padStart(3,'0')+'_'+name.replace(/[<>:"/\\|?*\x00-\x1f]/g,'_')+'.png',f=path.join(materials,filename),edit={};for(const k of ['text','vectorFill','vectorMask','vectorStroke','effects'])if(l[k]!=null)edit[k]=l[k];
  let spec;if(n.type==='image'){
   const bytes=Buffer.from(n.src.split(',')[1],'base64');fs.writeFileSync(f,bytes);const hash=sha(bytes),relative='01_素材/'+filename;
   registry.push({id:n.id,name,file:relative,sha256:hash,source:n.provenance,completeReview:'PENDING',inferred:n.inferred||false});
   const im=await cv.loadImage(bytes);
   spec={kind:'bitmap',name,file:relative,x:n.x,y:n.y,width:n.width,height:n.height,native:{...(edit.effects?{effects:edit.effects}:{})},completeAssetSHA256:hash,completeAssetSource:{file:relative,sha256:hash,transform:[n.width/im.width,0,0,n.height/im.height,n.x,n.y]},...(n.assetKind==='background'||(i===0&&n.x<=0&&n.y<=0&&n.width>=scene.width&&n.height>=scene.height)?{role:'background'}:n.assetKind==='person'?{role:'character',...(n.sourceEntityId?{completeAssetIdentity:n.sourceEntityId}:{})}:n.assetKind==='logo'?{role:'artwork'}:{})};
  }else{fs.writeFileSync(f,l.canvas.toBuffer('image/png'));spec={kind:n.type==='text'?'text':'shape',name,cache:'01_素材/'+filename,x:l.left||0,y:l.top||0,native:edit};}
  Object.assign(spec,{nodeId:n.id,nativeLayerId:l.id,sourceNativeLayerId:l.id,sourceSceneIndex:scene.nodes.findIndex(sn=>sn.id===n.id)>=0?scene.nodes.findIndex(sn=>sn.id===n.id):auxiliaryIndex++,auxiliary:!scene.nodes.some(sn=>sn.id===n.id),opacity:n.opacity??1,blendMode:l.blendMode||'normal'});
  // Mask wrappers preserve pristine complete bitmap and vector glyph caches.
  if(n.displayMask){const wrapperEffects={...(spec.native?.effects||{})},opacity=spec.opacity,blendMode=spec.blendMode;if(n.type==='text'&&n.gradient){const intrinsic=runtimeStyle.nativeEffects({gradientOverlay:{...runtimeStyle.normalizeGradient(n.gradient),enabled:true,opacity:1}});runtimeStyle.fitGradientEffects({canvas:l.canvas,left:l.left,top:l.top,effects:intrinsic},n);spec.native={...(spec.native||{}),effects:intrinsic};if(!n.layerStyle?.gradientOverlay)delete wrapperEffects.gradientOverlay;}else if(spec.native?.effects){delete spec.native.effects;}spec.opacity=1;spec.blendMode='normal';const hasEffects=Object.keys(wrapperEffects).some(k=>!['disabled','scale'].includes(k));spec={kind:'group',name:name+' · 显示蒙版',nodeId:n.id+'__mask',nativeLayerId:20000+l.id,children:[spec],displayMask:{d:runtimeStyle.maskPath(n.displayMask),disabled:!runtimeStyle.normalizeMask(n.displayMask).enabled,reason:'可关闭的显示范围：先遮罩完整底稿，再应用自身样式'},opacity,blendMode,...(hasEffects?{native:{effects:wrapperEffects}}:{})};}

  specById.set(n.id,spec);
 }
 const specs=S.grouped(scene,nodes,nodes.map(n=>specById.get(n.id)),(g,children)=>{const l=layerById.get(10000+scene.groups.indexOf(g));if(!l?.children)throw Error('原生分组 ID 映射缺失: '+g.id);return {kind:'group',name:g.name||'分组',nodeId:g.id,nativeLayerId:l.id,children,opacity:g.opacity??1,hidden:g.visible===false,blendMode:l.blendMode||'normal',native:l.effects?{effects:l.effects}:{},...(g.displayMask?{displayMask:{d:runtimeStyle.maskPath(g.displayMask),disabled:!runtimeStyle.normalizeMask(g.displayMask).enabled,reason:'可关闭的父组显示范围'}}:{})}});
 const original=path.basename(scene.delivery.original),job={format:'game-ui-psd-v1',width:scene.width,height:scene.height,source:'../2_输出/'+original,outputName:path.basename(target),enforceCompleteSources:true,layers:specs};
 fs.writeFileSync(path.join(structure,'项目.json'),JSON.stringify(job,null,2));fs.writeFileSync(path.join(structure,'素材登记.json'),JSON.stringify(registry,null,2));
 const qaRoot=path.resolve(processRoot,'03_检查'),realProject=fs.realpathSync(project);fs.mkdirSync(qaRoot,{recursive:true});
 if(!fs.realpathSync(qaRoot).startsWith(realProject+path.sep))throw Error('Review cleanup must stay inside this project');
 for(const dir of ['独立图层','原生渐变图层','完整底稿参考','父组显示检查']){const targetDir=path.resolve(qaRoot,dir);if(!targetDir.startsWith(qaRoot+path.sep))throw Error('Unsafe review path');if(fs.existsSync(targetDir)){if(!fs.realpathSync(targetDir).startsWith(fs.realpathSync(qaRoot)+path.sep))throw Error('Review directory resolves outside project');fs.rmSync(targetDir,{recursive:true,force:true});}}
 for(const name of fs.readdirSync(qaRoot))if(/^独立图层图册_.*\.png$/.test(name))fs.unlinkSync(path.join(qaRoot,name));
 spawnResult('拆图流水线',cp.spawnSync(process.execPath,[path.join(skill,'pipeline.cjs'),'run','--project',processRoot,'--force'],{cwd:root,encoding:'utf8',windowsHide:true,maxBuffer:5000000}));
 const runtime=require(path.join(skill,'runtime.cjs')).runtime({python:process.env.SHIJIE_PYTHON||'python',psdTools:path.resolve(root,'../技能包/依赖/Python')});
 spawnResult('实际图层渲染',cp.spawnSync(runtime.python,['-B',path.join(__dirname,'render_actual_layers.py'),target,qaRoot,runtime.psdTools],{cwd:root,encoding:'utf8',windowsHide:true,maxBuffer:5000000,env:{...process.env,PYTHONUTF8:'1'}}));
 spawnResult('图层复核初始化',cp.spawnSync(process.execPath,[path.join(skill,'review.cjs'),'init','--project',processRoot],{cwd:root,encoding:'utf8',windowsHide:true}));
 const qa=path.join(processRoot,'03_检查'),composite=path.join(qa,'合成预览.png');if(path.resolve(composite)!==path.resolve(preview))fs.copyFileSync(composite,preview);
 const audit=JSON.parse(fs.readFileSync(path.join(qa,'检查结果.json'),'utf8'));
 console.log(JSON.stringify({status:audit.structuralChecks==='PASS'&&audit.assetChecks==='PASS'?'PASS':'FAIL',workflow:'game-ui-to-psd',audit:'03_检查/检查结果.json',visualReview:'REQUIRED'}));
})().catch(e=>{console.error(e.stack);process.exitCode=1});
