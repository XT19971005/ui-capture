/* Transport for this computer's Codex account and temporary editor sessions. */
'use strict';
window.ShijieSmartSplit=(()=>{
 let connection=null,active=null;
 const cancelledRuns=new Set();
 const abortError=()=>new DOMException('已取消','AbortError');
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
  const data=await response.json();if(!response.ok){const error=Error(data.error||'本机处理请求失败');error.status=response.status;throw error}return data;
 }
 async function connect(){connection=await nativeConnect();const state=await request('/health');if(!state.codexAvailable)throw Error('未找到本机 Codex，请安装 Codex CLI 并登录自己的账号');if(!state.ready)throw Error('拾界运行依赖不完整，请重新解压完整分享包：'+(state.missing||[]).join('、'));return state;}
 async function awaitCancelledCleanup(run,onProgress){
  if(!cancelledRuns.size)return;const started=Date.now();onProgress(.01,'正在等待上一次任务清理…');
  while(cancelledRuns.size){
   if(run.cancelled)throw abortError();
   for(const previous of [...cancelledRuns]){
    if(previous.id){try{const state=await request('/jobs/'+previous.id);if(!['queued','running'].includes(state.status)){await request('/jobs/'+previous.id,{method:'DELETE'}).catch(()=>{});cancelledRuns.delete(previous)}}catch(error){if(error.status===404)cancelledRuns.delete(previous);else throw error}}
    else if(previous.finished)cancelledRuns.delete(previous);
    if(run.cancelled)throw abortError();
   }
   if(!cancelledRuns.size)return;
   if(Date.now()-started>60000)throw Error('上一次任务仍在清理，请稍后重新拆分。');
   await new Promise(resolve=>setTimeout(resolve,200));
  }
 }
 async function run(image,title,onProgress=()=>{},original=image,resumeScene=null){
  if(active)throw Error('已有图片正在拆分');const run={cancelled:false,id:null,finished:false,partial:null};active=run;
  try{
   onProgress(.01,'正在连接本机智能引擎…');await connect();if(run.cancelled)throw abortError();
   await awaitCancelledCleanup(run,onProgress);if(run.cancelled)throw abortError();
   const job=await request('/jobs',{method:'POST',body:JSON.stringify({image,title,mode:'codex',original,...(resumeScene?{resume:resumeScene}:{})})});run.id=job.id;
   let revision=0;
   while(true){
    if(run.cancelled)throw abortError();
    const state=await request('/jobs/'+run.id+'?afterRevision='+revision);
    if(state.partial){revision=state.partialRevision;run.partial=state.partial}
    if(run.cancelled)throw abortError();
    onProgress(state.progress,state.message,state.partial||null);
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
 async function cancel(){if(!active)return null;const previous=active;previous.cancelled=true;cancelledRuns.add(previous);active=null;const waitStarted=Date.now();while(!previous.id&&!previous.finished&&Date.now()-waitStarted<60000)await new Promise(r=>setTimeout(r,50));if(!previous.id){cancelledRuns.delete(previous);return previous.partial}if(previous.id&&connection){await request('/jobs/'+previous.id,{method:'DELETE',keepalive:true}).catch(()=>{});const started=Date.now();while(Date.now()-started<60000){try{const state=await request('/jobs/'+previous.id+'?afterRevision=-1');if(state.partial)previous.partial=state.partial;if(!['queued','running'].includes(state.status)){await request('/jobs/'+previous.id,{method:'DELETE'}).catch(()=>{});cancelledRuns.delete(previous);break}}catch(e){if(e.status===404){cancelledRuns.delete(previous);break}break}await new Promise(r=>setTimeout(r,200))}}return previous.partial;}
 function renderState(scene){const keys=['id','name','type','x','y','width','height','src','text','fontSize','fontWeight','fontFamily','fontStyle','fitWidth','textSkew','rotation','fill','stroke','strokeWidth','d','radius','opacity','visible','gradient'];const stable=v=>Array.isArray(v)?v.map(stable):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,stable(v[k])])):v;return JSON.stringify(stable({width:scene.width,height:scene.height,background:scene.background??null,nodes:scene.nodes.map(n=>Object.fromEntries(keys.filter(k=>n[k]!==undefined).map(k=>[k,n[k]]))),edges:scene.edges||[],groups:scene.groups||[]}))}
 async function downloadPsd(scene){assertExportable(scene);if(scene?.recognition?.reviewStatus==='MANUAL_CONFIRMED')return null;if(!scene?.delivery)return null;const id=scene._sessionId||scene.delivery.sessionId;const route=id?'/sessions/'+encodeURIComponent(id):scene._projectId?.startsWith('codex-')?'/projects/'+encodeURIComponent(scene._projectId):null;if(!route)return null;connection=await nativeConnect();let saved;try{saved=await request(route+(id?'/scene':''))}catch(e){if(e.status===404)return null;throw e}if(renderState(saved)!==renderState(scene))return null;const r=await fetch(connection.url+route+'/psd',{headers:{'X-Shijie-Token':connection.token},cache:'no-store'});if(r.status===404)return null;if(!r.ok){const data=await r.json();throw Error(data.error||'已审计PSD暂不可用')}const blob=await r.blob();if(scene.delivery.psdSHA256){const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',await blob.arrayBuffer())),v=>v.toString(16).padStart(2,'0')).join('');if(hash!==scene.delivery.psdSHA256)throw Error('PSD校验失败，请重新拆分')}return blob}
 function assertExportable(scene,type='psd'){
  if(scene?._partial)throw Error('拆分尚未完成，请继续拆分后再导出。');
 }
 function releaseSession(scene){const id=scene?._sessionId||scene?.delivery?.sessionId;if(id&&connection)request('/sessions/'+encodeURIComponent(id),{method:'DELETE',keepalive:true}).catch(()=>{})}
 window.addEventListener('pagehide',()=>{cancel()});
 return {run,cancel,connect,downloadPsd,releaseSession,assertExportable,async storeCapture(entry){connection=await nativeConnect();return (await request('/captures',{method:'POST',body:JSON.stringify({image:entry.src,title:entry.title})})).id},async capture(id){connection=await nativeConnect();return request('/captures/'+encodeURIComponent(id))},async clearCapture(id){connection=await nativeConnect();return request('/captures/'+encodeURIComponent(id),{method:'DELETE'})},async projects(){connection=await nativeConnect();return request('/projects')},async project(id){connection=await nativeConnect();return request('/projects/'+encodeURIComponent(id))},async setModel(model){connection=await nativeConnect();return request('/codex/model',{method:'POST',body:JSON.stringify({model})})},async openOutput(project){connection=await nativeConnect();return request('/open-output',{method:'POST',body:JSON.stringify({project})})},async account(){connection=await nativeConnect();return request('/codex/status')},async login(){connection=await nativeConnect();return request('/codex/login',{method:'POST',body:'{}'})}};
})();
