/* Transport for this computer's Codex account and temporary editor sessions. */
'use strict';
window.ShijieSmartSplit=(()=>{
 let connection=null,active=null;
 const cancelledRuns=new Set();
 const MIB=1024*1024,IMAGE_KEYS=new Set(['image','original','src','source','originalSource','comparisonSource']);
 function serializeJob(job,imageTableSupported=false){
  const images=[],imageBytes=[],encodedImageBytes=[],indexes=new Map(),stack=new Set();let uniqueBytes=0,encodedUniqueBytes=0,logicalBytes=0,encodedLogicalBytes=0,metadataBytes=0,items=0;
  const utf8Size=value=>/^[\x00-\x7f]*$/.test(value)?value.length:new TextEncoder().encode(value).byteLength;
  const add=size=>{metadataBytes+=size;if(metadataBytes>16*MIB)throw Error('工程文字与结构超过16MiB限制，原工程已保留。')};
  function pack(value,key=null,depth=0){
   if(++items>200000)throw Error('工程结构条目过多，原工程已保留。');if(depth>40)throw Error('工程结构层级过多，原工程已保留。');
   if(typeof value==='string'&&IMAGE_KEYS.has(key)&&value.startsWith('data:image/')){
    let index=indexes.get(value);
    if(index===undefined){if(value.length>36000000)throw Error('单张内嵌图片超过36MB限制，原工程已保留。');const bytes=utf8Size(value);if(bytes>36000000)throw Error('单张内嵌图片超过36MB限制，原工程已保留。');if(images.length>=4096)throw Error('工程独立图片数量过多，原工程已保留。');uniqueBytes+=bytes;if(uniqueBytes>256*MIB)throw Error('工程独立图片数据超过256MiB限制，原工程已保留。');index=images.length;images.push(value);indexes.set(value,index);imageBytes.push(bytes);const encoded=utf8Size(JSON.stringify(value))-2;encodedImageBytes.push(encoded);encodedUniqueBytes+=encoded;}
    logicalBytes+=imageBytes[index];if(logicalBytes>1024*MIB)throw Error('工程图片引用总量超过1GiB安全限制，原工程已保留。');encodedLogicalBytes+=encodedImageBytes[index];add(2);return {$image:index};
   }
   if(value&&typeof value==='object'){
    if(stack.has(value))throw Error('工程结构存在循环引用，原工程已保留。');if(Object.hasOwn(value,'$image'))throw Error('工程包含保留的图片引用字段，请重新保存工程后重试。');stack.add(value);
    let result;
    if(Array.isArray(value)){if(value.length>200000)throw Error('工程结构条目过多，原工程已保留。');add(2+Math.max(0,value.length-1));result=Array.from(value,item=>pack(item,null,depth+1));}
    else{result=Object.create(null);let count=0;add(2);for(const [name,item] of Object.entries(value)){if(item===undefined||typeof item==='function'||typeof item==='symbol')continue;if(count++)add(1);add(utf8Size(JSON.stringify(name))+1);result[name]=pack(item,name,depth+1);}}
    stack.delete(value);return result;
   }
   if(value===undefined||typeof value==='function'||typeof value==='symbol')value=null;
   if(typeof value==='bigint'||typeof value==='number'&&!Number.isFinite(value))throw Error('工程包含无效数值，原工程已保留。');
   if(typeof value==='string'&&value.length>16*MIB)throw Error('工程文字与结构超过16MiB限制，原工程已保留。');add(utf8Size(JSON.stringify(value)));return value;
  }
  const packed=pack(job);
  const expandedBytes=encodedLogicalBytes+metadataBytes;
  // Old workers have an 80MiB HTTP cap and a separate 72MB resume JSON cap.
  // Stay below both without constructing their giant repeated-image body.
  if(!imageTableSupported&&expandedBytes>(job.resume?70000000:80*MIB))throw Error('本机后端尚未加载大工程传输更新。请等待当前任务结束后重新连接或重启后端完成更新；原工程和全部编辑已保留。');
  if(!imageTableSupported||expandedBytes<=4*MIB){
   function inline(value){if(Array.isArray(value))return value.map(inline);if(value&&typeof value==='object'){if(Object.hasOwn(value,'$image'))return images[value.$image];return Object.fromEntries(Object.entries(value).map(([key,item])=>[key,inline(item)]));}return value}
   return JSON.stringify(inline(packed));
  }
  const wrapper={wireFormat:'shijie-image-table',wireVersion:1,images,job:packed};
  const wireMetadata=utf8Size(JSON.stringify({...wrapper,images:images.map(()=> '')}));if(wireMetadata+encodedUniqueBytes>276*MIB)throw Error('工程传输数据超过容量限制，原工程已保留；不会压缩或替换图片。');
  return JSON.stringify(wrapper);
 }
 const abortError=()=>new DOMException('已取消','AbortError');
 function releaseCancelledOrderResult(run,state){
  if(run.mode!=='repair-order'||state?.status!=='completed')return;
  for(const id of new Set([state.result?._sessionId,state.result?.delivery?.sessionId]))if(typeof id==='string'&&id&&!run.keptSessions.has(id)&&!run.releasedSessions.has(id)){run.releasedSessions.add(id);try{releaseSession({_sessionId:id})}catch(_){}}
 }
 function nativeConnect(){if(location.protocol==='http:'&&['127.0.0.1:19217','localhost:19217'].includes(location.host))return fetch('/connection',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('本机连接失败');return r.json()});return new Promise((resolve,reject)=>{
  if(!globalThis.chrome?.runtime?.sendNativeMessage)return reject(Error('请从 Edge 扩展中打开图片拆分'));
  chrome.runtime.sendNativeMessage('cn.xt.shijie.engine',{action:'connect'},result=>{
   const error=chrome.runtime.lastError;
   if(error||!result?.ok)return reject(Error(result?.error||'本机引擎尚未连接。请在扩展管理页重新加载拾界；仍失败时，运行插件目录中的「连接智能拆图.ps1」'));
   if(result.url!=='http://127.0.0.1:19217'||typeof result.token!=='string')return reject(Error('本机引擎返回无效连接'));
   resolve(result);
  });
 });}
 async function request(path,options={}){
  const response=await fetch(connection.url+path,{...options,headers:{'Content-Type':'application/json','X-Shijie-Token':connection.token},cache:'no-store'});
  let data;try{data=await response.json()}catch(_){const error=Error(response.status===413?'工程传输数据超过容量限制，原工程已保留。请保存工程后重试。':'本机引擎返回了无法读取的响应（HTTP '+response.status+'），原工程已保留。');error.status=response.status;throw error}
  if(!response.ok){const error=Error(typeof data?.error==='string'?data.error:'本机处理请求失败');error.status=response.status;throw error}return data;
 }
 async function connect(){connection=await nativeConnect();const state=await request('/health');if(!state.codexAvailable)throw Error('未找到本机 Codex，请安装 Codex CLI 并登录自己的账号');if(!state.ready)throw Error('拾界运行依赖不完整，请重新解压完整分享包：'+(state.missing||[]).join('、'));return state;}
 async function awaitCancelledCleanup(run,onProgress){
  if(!cancelledRuns.size)return;const started=Date.now();onProgress(.01,'正在等待上一次任务清理…');
  while(cancelledRuns.size){
   if(run.cancelled)throw abortError();
   for(const previous of [...cancelledRuns]){
    if(previous.id){try{const state=await request('/jobs/'+previous.id);releaseCancelledOrderResult(previous,state);if(!['queued','running'].includes(state.status)){await request('/jobs/'+previous.id,{method:'DELETE'}).catch(()=>{});cancelledRuns.delete(previous)}}catch(error){if(error.status===404)cancelledRuns.delete(previous);else throw error}}
    else if(previous.finished)cancelledRuns.delete(previous);
    if(run.cancelled)throw abortError();
   }
   if(!cancelledRuns.size)return;
   if(Date.now()-started>60000)throw Error('上一次任务仍在清理，请稍后重新拆分。');
   await new Promise(resolve=>setTimeout(resolve,200));
  }
 }
 async function run(image,title,onProgress=()=>{},original=image,resumeScene=null,options={}){
  const mode=options?.mode||'codex';if(!['codex','refine-ui','refine-selected','repair-order'].includes(mode))throw Error('处理方式无效');if(active)throw Error('已有图片正在拆分');const run={mode,cancelled:false,id:null,finished:false,partial:null,keptSessions:new Set([resumeScene?._sessionId,resumeScene?.delivery?.sessionId]),releasedSessions:new Set()};active=run;
  try{
   onProgress(.01,'正在连接本机智能引擎…');const engine=await connect();if(run.cancelled)throw abortError();
   if(Array.isArray(engine.jobModes)&&!engine.jobModes.includes(mode))throw Error('本机后端尚不支持当前操作，请更新并重新连接后重试；原工程已保留。');
   if(options.region&&engine.regionRefineVersion!==1)throw Error('本机后端尚未加载区域检查更新，请等待当前任务结束后重新连接或重启后端；完整工程已保留。');
   await awaitCancelledCleanup(run,onProgress);if(run.cancelled)throw abortError();
   onProgress(.02,'正在整理工程图片，保留原图与全部图层…');await new Promise(resolve=>setTimeout(resolve,0));if(run.cancelled)throw abortError();
   const body=serializeJob({image,title,mode,original,...(resumeScene?{resume:resumeScene}:{}),...(mode==='refine-selected'?{selectedIds:options.selectedIds,...(options.region?{region:options.region}:{})}:{})},engine.imageWireVersion===1);await new Promise(resolve=>setTimeout(resolve,0));if(run.cancelled)throw abortError();
   const job=await request('/jobs',{method:'POST',body});run.id=job.id;
   let revision=0;
   while(true){
    if(run.cancelled)throw abortError();
    const state=await request('/jobs/'+run.id+'?afterRevision='+revision);
    if(state.partial){revision=state.partialRevision;if(mode==='codex')run.partial=state.partial}
    if(run.cancelled){releaseCancelledOrderResult(run,state);throw abortError()}
    onProgress(state.progress,state.message,mode==='codex'?state.partial||null:null);
    if(state.status==='completed')return state.result;
    if(['failed','expired'].includes(state.status))throw Error(state.message);
    if(state.status==='cancelled')throw abortError();
    await new Promise(resolve=>setTimeout(resolve,700));
   }
  }catch(error){if(run.partial)error.partial=run.partial;throw error}finally{
   if(run.id&&connection&&!run.cancelled)await request('/jobs/'+run.id,{method:'DELETE'}).catch(()=>{});
   run.finished=true;
   if(active===run)active=null;
  }
 }
 async function cancel(){if(!active)return null;const previous=active;previous.cancelled=true;cancelledRuns.add(previous);active=null;const waitStarted=Date.now();while(!previous.id&&!previous.finished&&Date.now()-waitStarted<60000)await new Promise(r=>setTimeout(r,50));if(!previous.id){cancelledRuns.delete(previous);return previous.partial}if(previous.id&&connection){await request('/jobs/'+previous.id,{method:'DELETE',keepalive:true}).catch(()=>{});const started=Date.now();while(Date.now()-started<60000){try{const state=await request('/jobs/'+previous.id+'?afterRevision=-1');releaseCancelledOrderResult(previous,state);if(state.partial&&previous.mode==='codex')previous.partial=state.partial;if(!['queued','running'].includes(state.status)){await request('/jobs/'+previous.id,{method:'DELETE'}).catch(()=>{});cancelledRuns.delete(previous);break}}catch(e){if(e.status===404){cancelledRuns.delete(previous);break}break}await new Promise(r=>setTimeout(r,200))}}return previous.partial;}
 function canRefine(doc){return !!(doc&&doc.version===2&&!doc._partial&&![doc.recognition?.reviewStatus,doc.recognition?.status].some(v=>['PROCESSING','RUNNING','QUEUED'].includes(v))&&(doc.comparisonSource||doc.source)&&doc.nodes?.some(n=>!n.versionArchived&&!n.locked&&n.assetKind!=='background'&&['text','rect','ellipse','path'].includes(n.type)))}
 async function refine(doc,onProgress=()=>{}){if(!canRefine(doc))throw Error(doc?._partial?'请先继续拆分，完成后再精修。':'当前工程没有可精修的完整文字或矢量图层。');return run(doc.comparisonSource||doc.source,doc.title,onProgress,doc.originalSource||doc.comparisonSource||doc.source,doc,{mode:'refine-ui'})}
 async function refineSelected(doc,selectedIds,onProgress=()=>{},region){if(!doc?.nodes?.length||!(doc.comparisonSource||doc.source)||!Array.isArray(selectedIds)||!selectedIds.length||new Set(selectedIds).size!==selectedIds.length||selectedIds.some(id=>!doc.nodes.some(n=>n.id===id)))throw Error('请选择要检查的图层');if(region!==undefined&&(!region||Object.keys(region).sort().join(',')!=='height,width,x,y'||Object.values(region).some(v=>typeof v!=='number'||!Number.isFinite(v))||region.x<0||region.y<0||region.width<=0||region.height<=0||region.x+region.width>doc.width||region.y+region.height>doc.height))throw Error('检查区域必须完整位于画布内');return run(doc.comparisonSource||doc.source,doc.title,onProgress,doc.originalSource||doc.comparisonSource||doc.source,doc,{mode:'refine-selected',selectedIds,...(region?{region:{...region}}:{})})}
 async function repairOrder(doc,onProgress=()=>{}){if(!doc?.nodes||doc.nodes.length<2||!(doc.comparisonSource||doc.source||doc.originalSource))throw Error('至少需要两个图层和原图');return run(doc.comparisonSource||doc.source||doc.originalSource,doc.title,onProgress,doc.originalSource||doc.comparisonSource||doc.source,doc,{mode:'repair-order'})}
 function renderState(scene){const keys=['id','name','type','x','y','width','height','src','text','fontSize','fontWeight','fontFamily','fontStyle','fitWidth','textSkew','rotation','fill','stroke','strokeWidth','d','radius','opacity','visible','gradient'];const stable=v=>Array.isArray(v)?v.map(stable):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,stable(v[k])])):v;return JSON.stringify(stable({width:scene.width,height:scene.height,background:scene.background??null,nodes:scene.nodes.map(n=>Object.fromEntries(keys.filter(k=>n[k]!==undefined).map(k=>[k,n[k]]))),edges:scene.edges||[],groups:scene.groups||[]}))}
 async function downloadPsd(scene){assertExportable(scene);if([...scene.nodes,...(scene.groups||[])].some(n=>n.versionArchived||n.visible===false||n.hidden===true))return null;if(scene?._partial||(scene?.delivery?.storage==='memory'&&!scene.delivery.psdSHA256))return null;if(scene?.recognition?.reviewStatus==='MANUAL_CONFIRMED')return null;if(!scene?.delivery)return null;const id=scene._sessionId||scene.delivery.sessionId;const route=id?'/sessions/'+encodeURIComponent(id):scene._projectId?.startsWith('codex-')?'/projects/'+encodeURIComponent(scene._projectId):null;if(!route)return null;connection=await nativeConnect();let saved;try{saved=await request(route+(id?'/scene':''))}catch(e){if(e.status===404)return null;throw e}if(renderState(saved)!==renderState(scene))return null;const r=await fetch(connection.url+route+'/psd',{headers:{'X-Shijie-Token':connection.token},cache:'no-store'});if(r.status===404)return null;if(!r.ok){const data=await r.json();throw Error(data.error||'已审计PSD暂不可用')}const blob=await r.blob();if(scene.delivery.psdSHA256){const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',await blob.arrayBuffer())),v=>v.toString(16).padStart(2,'0')).join('');if(hash!==scene.delivery.psdSHA256)throw Error('PSD校验失败，请重新拆分')}return blob}
 function assertExportable(scene,type='psd'){
  if(!scene?.nodes?.length)throw Error('当前没有可导出的图层。');
 }
 function releaseSession(scene){const id=scene?._sessionId||scene?.delivery?.sessionId;if(id&&connection)request('/sessions/'+encodeURIComponent(id),{method:'DELETE',keepalive:true}).catch(()=>{})}
 window.addEventListener('pagehide',()=>{cancel()});
 return {run,refine,refineSelected,repairOrder,canRefine,cancel,connect,downloadPsd,releaseSession,assertExportable,async storeCapture(entry){connection=await nativeConnect();return (await request('/captures',{method:'POST',body:JSON.stringify({image:entry.src,title:entry.title})})).id},async capture(id){connection=await nativeConnect();return request('/captures/'+encodeURIComponent(id))},async clearCapture(id){connection=await nativeConnect();return request('/captures/'+encodeURIComponent(id),{method:'DELETE'})},async projects(){connection=await nativeConnect();return request('/projects')},async project(id){connection=await nativeConnect();return request('/projects/'+encodeURIComponent(id))},async setModel(model){connection=await nativeConnect();return request('/codex/model',{method:'POST',body:JSON.stringify({model})})},async openOutput(project){connection=await nativeConnect();return request('/open-output',{method:'POST',body:JSON.stringify({project})})},async account(){connection=await nativeConnect();return request('/codex/status')},async login(){connection=await nativeConnect();return request('/codex/login',{method:'POST',body:'{}'})}};
})();
