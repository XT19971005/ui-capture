/* Durable previews: stored with their base project, never applied during load. */
(()=>{
 'use strict';
 const clone=v=>structuredClone(v),blankDrafts=new Map();let applyingRecord=false;
 function content(doc){return JSON.stringify(doc,(key,value)=>['_assistantChat','_assistantCandidates','_sessionId','delivery','_studioStep'].includes(key)?undefined:value)}
 async function signature(doc){const bytes=new TextEncoder().encode(content(doc)),hash=await (window.ShijieSession||crypto.subtle).digest('SHA-256',bytes);return Array.from(new Uint8Array(hash),v=>v.toString(16).padStart(2,'0')).join('')}
 function records(doc){return Array.isArray(doc?._assistantCandidates)?doc._assistantCandidates.filter(r=>r?.version===1&&typeof r.id==='string'&&['scene','image'].includes(r.kind)):[]}
 const omitted=new Set(['_assistantChat','_assistantCandidates','_sessionId','delivery','_studioStep','_splitBaseline','_splitDraftCore']);
 function snapshot(doc){if(!doc)return doc;return JSON.parse(JSON.stringify(doc,(key,value)=>omitted.has(key)?undefined:value))}
 const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
 // Apply only candidate changes; current-only edits survive, overlapping edits conflict.
 function mergeValue(base,generated,current,path='工程'){
  if(same(base,generated))return clone(current);
  if(same(base,current)||same(generated,current))return clone(generated);
  if([base,generated,current].every(v=>Array.isArray(v)&&v.every(n=>n&&typeof n==='object'&&typeof n.id==='string'))){
   const maps=[base,generated,current].map(items=>new Map(items.map(n=>[n.id,n])));
   if([base,generated,current].some((items,i)=>maps[i].size!==items.length))throw Error(path+'存在重复标识，候选已保留');
   const ids=[...current.map(n=>n.id),...generated.filter(n=>!maps[2].has(n.id)).map(n=>n.id)],out=[];
   for(const id of ids){const value=mergeValue(maps[0].get(id),maps[1].get(id),maps[2].get(id),path+'/'+id);if(value!==undefined)out.push(value)}return out;
  }
  if([base,generated,current].every(v=>v&&typeof v==='object'&&!Array.isArray(v))){
   const out={};for(const key of new Set([...Object.keys(base),...Object.keys(generated),...Object.keys(current)])){const value=mergeValue(base[key],generated[key],current[key],path+'/'+key);if(value!==undefined)Object.defineProperty(out,key,{value,enumerable:true,writable:true,configurable:true})}return out;
  }
  throw Error(path+'与生成时内容冲突，候选已保留，未覆盖当前编辑');
 }
 async function prepare(record,current){
  if(record.projectId&&current?._projectId!==record.projectId)throw Error('已切换工程，候选未应用');
  if(!record.base&&await signature(current)!==record.baseHash)throw Error('工程内容已改变，此候选仍保留；请先撤销到生成时的状态再应用');
  if(record.kind==='image')return ShijieImageGeneration.createDocument(current.nodes.length?current:null,record.candidate,crypto.randomUUID());
  if(!record.base)return clone(record.candidate);
  const next=mergeValue(record.base,snapshot(record.candidate),snapshot(current));
  // Private baselines and live session metadata belong to the open project.
  for(const key of omitted)if(Object.hasOwn(current,key))next[key]=clone(current[key]);
  return next;
 }
 async function retain({kind,candidate,before,base,completeSplit=false}){
  const studio=window.studio,owner=studio.adapter.get();
  if(owner!==before)throw Error('工程已改变，候选未写入其他工程');
  if(owner&&!owner._projectId)owner._projectId=StudioBase.id();
  if(base&&base._projectId!==owner?._projectId)throw Error('候选发起工程不一致，未写入当前工程');
  const ownerHash=await signature(owner),baseHash=await signature(base||owner),record={version:1,id:crypto.randomUUID(),kind,completeSplit,createdAt:new Date().toISOString(),baseHash,candidate:base?snapshot(candidate):clone(candidate),...(base?{base:snapshot(base)}:{})};delete record.candidate._assistantCandidates;delete record.candidate._assistantChat;
  if(owner!==studio.adapter.get()||await signature(owner)!==ownerHash)throw Error('工程内容已改变，候选尚未保存');
  if(!owner){
   const blank=document.createElement('canvas');blank.width=blank.height=1;
   const doc={format:'shijie-scene',version:2,_projectId:crypto.randomUUID(),title:(candidate.name||'新图片')+' · 待确认候选',width:candidate.width,height:candidate.height,source:blank.toDataURL('image/png'),nodes:[],groups:[],edges:[],_assistantChat:{version:1,messages:window.ShijieFreeAssistant?.conversation?.()||[],outcomes:[],earlier:[]},_assistantCandidates:[record]};
   record.projectId=doc._projectId;record.baseHash=await signature(doc);blankDrafts.set(record.id,doc);try{await StudioBase.library.put(doc,'image',{checkpoint:true})}catch(e){e.record=record;throw e}return record;
  }
  record.projectId=owner._projectId;owner._assistantCandidates=[...records(owner),record];
  try{await studio.saveCheckpoint('生成候选完成')}catch(e){e.record=record;throw e}render();return record;
 }
 async function remove(id){const studio=window.studio,doc=studio.adapter.get();if(!doc)return;doc._assistantCandidates=records(doc).filter(r=>r.id!==id);await studio.saveCheckpoint('放弃候选');render()}
 function render(){
  if(typeof document==='undefined')return;const host=document.getElementById('free-assistant');if(!host)return;
  let shelf=host.querySelector('[data-saved-candidates]');if(!shelf){shelf=document.createElement('section');shelf.dataset.savedCandidates='';shelf.className='saved-candidates';host.querySelector('textarea').before(shelf)}
  const doc=window.studio.adapter.get(),items=records(doc);shelf.hidden=!items.length;
  const key=items.map(r=>r.id).join(',');if(shelf.dataset.key===key)return;shelf.dataset.key=key;shelf.replaceChildren();
  for(const record of items){const row=document.createElement('div'),label=document.createElement('span');label.textContent=(record.candidate.name||record.candidate.title||'生成结果')+' · 待确认';const view=document.createElement('button');view.type='button';view.textContent='查看候选';view.onclick=()=>preview(record).catch(e=>window.studio.adapter.status(e.message));const discard=document.createElement('button');discard.type='button';discard.textContent='放弃';discard.onclick=()=>remove(record.id).catch(e=>window.studio.adapter.status('保存失败：'+e.message));row.append(label,view,discard);shelf.append(row)}
 }
 async function preview(record){
  const studio=window.studio,owner=studio.adapter.get();if(studio.isBusy())throw Error('请等待当前任务结束');
  if(record.projectId&&owner?._projectId!==record.projectId)throw Error('已切换工程，候选未应用');
  let prepared;try{prepared=await prepare(record,owner)}catch(e){if(!record.base)throw e;prepared=clone(record.candidate);studio.adapter.status(e.message+'；仍可查看生成候选，应用时会重新核对')}
  const original='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(ShijieScene.svg(owner));
  const candidate=prepared;
  ShijieScene.validate(candidate);const after=record.kind==='image'?record.candidate.src:'data:image/svg+xml;charset=utf-8,'+encodeURIComponent(ShijieScene.svg(candidate));
  let applying=false,applied=false;
  ShijieCanvasComparison.show({before:original,after,isCurrent:()=>studio.adapter.get()===owner,apply:async()=>{
   if(applying||applied||applyingRecord||studio.isBusy())throw Error(applied?'候选已应用':'候选正在应用中');applying=applyingRecord=true;setBusy(true);studio.sync(false);try{
   const live=studio.adapter.get(),liveHash=await signature(live),candidate=await prepare(record,live);
   if(studio.adapter.get()!==live||await signature(live)!==liveHash)throw Error('工程正在改变，候选仍已保留，请重试应用');
   candidate._projectId=live._projectId;candidate._assistantChat=clone(live._assistantChat);candidate._assistantCandidates=records(live).filter(r=>r.id!==record.id);
   ShijieScene.validate(candidate);
   const rollback=clone(live);try{await studio.adapter.restore(candidate);await studio.adapter.finish(rollback,'应用已保存候选')}catch(error){try{await studio.adapter.restore(rollback)}catch(rollbackError){throw Error(error.message+'；恢复当前工程失败：'+rollbackError.message+'；候选仍保留在保存工程中')}throw error}applied=true;if(record.completeSplit)studio.setInitial(studio.adapter.get(),{completedSplit:true});
   try{await studio.saveCheckpoint('确认应用候选');studio.adapter.status('候选已应用并保存，可撤销')}catch(e){studio.adapter.status('候选已应用但保存失败：'+e.message+'；请重试保存')}
   ShijieCanvasComparison.close();render();
   }finally{applying=applyingRecord=false;setBusy(false);studio.sync(false)}
  },discard:()=>ShijieCanvasComparison.close()});
 }
 async function retry(id){const blank=blankDrafts.get(id);if(blank){await StudioBase.library.put(blank,'image',{checkpoint:true});return records(blank).find(r=>r.id===id)}await window.studio.saveCheckpoint('重试保存候选');return records(window.studio.adapter.get()).find(r=>r.id===id)}
 window.ShijieCandidateStore={retain,records,signature,render,preview,remove,retry,savedBase:id=>clone(blankDrafts.get(id))};
 if(typeof document==='undefined')return;
 document.addEventListener('DOMContentLoaded',()=>{const old=updateButtons;updateButtons=function(...args){const result=old.apply(this,args);render();return result};render()},{once:true});
})();
