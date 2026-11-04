/* Durable previews: stored with their base project, never applied during load. */
(()=>{
 'use strict';
 const clone=v=>structuredClone(v),blankDrafts=new Map();let applying=false;
 function content(doc){return JSON.stringify(doc,(key,value)=>['_assistantChat','_assistantCandidates','_sessionId','delivery','_studioStep'].includes(key)?undefined:value)}
 async function signature(doc){const bytes=new TextEncoder().encode(content(doc)),hash=await (window.ShijieSession||crypto.subtle).digest('SHA-256',bytes);return Array.from(new Uint8Array(hash),v=>v.toString(16).padStart(2,'0')).join('')}
 function records(doc){return Array.isArray(doc?._assistantCandidates)?doc._assistantCandidates.filter(r=>r?.version===1&&typeof r.id==='string'&&['scene','image'].includes(r.kind)):[]}
 async function retain({kind,candidate,before,completeSplit=false}){
  const studio=window.studio,owner=studio.adapter.get();
  if(owner!==before)throw Error('工程已改变，候选未写入其他工程');
  if(owner&&!owner._projectId)owner._projectId=StudioBase.id();
  const baseHash=await signature(owner),record={version:1,id:crypto.randomUUID(),kind,completeSplit,createdAt:new Date().toISOString(),baseHash,candidate:clone(candidate)};delete record.candidate._assistantCandidates;delete record.candidate._assistantChat;
  if(owner!==studio.adapter.get()||await signature(owner)!==baseHash)throw Error('工程内容已改变，候选尚未保存');
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
  if(await signature(owner)!==record.baseHash)throw Error('工程内容已改变，此候选仍保留；请先撤销到生成时的状态再应用');
  const original='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(ShijieScene.svg(owner));
  const candidate=record.kind==='image'?ShijieImageGeneration.createDocument(owner.nodes.length?owner:null,record.candidate,crypto.randomUUID()):clone(record.candidate);
  ShijieScene.validate(candidate);const after=record.kind==='image'?record.candidate.src:'data:image/svg+xml;charset=utf-8,'+encodeURIComponent(ShijieScene.svg(candidate));
  ShijieCanvasComparison.show({before:original,after,isCurrent:()=>studio.adapter.get()===owner,apply:async()=>{
   if(applying||studio.isBusy())throw Error('当前操作尚未结束');applying=true;setBusy(true);studio.sync(false);try{
   const currentHash=await signature(owner);if(studio.adapter.get()!==owner||currentHash!==record.baseHash)throw Error('工程已改变，候选未应用');
   candidate._projectId=owner._projectId;candidate._assistantChat=clone(owner._assistantChat);candidate._assistantCandidates=records(owner).filter(r=>r.id!==record.id);
   await studio.adapter.restore(candidate);await studio.adapter.finish(owner,'应用已保存候选');if(record.completeSplit)studio.setInitial(studio.adapter.get(),{completedSplit:true});
   try{await studio.saveCheckpoint('确认应用候选');studio.adapter.status('候选已应用并保存，可撤销')}catch(e){studio.adapter.status('候选已应用但保存失败：'+e.message+'；请重试保存')}
   ShijieCanvasComparison.close();render();
   }finally{applying=false;setBusy(false);studio.sync(false)}
  },discard:()=>ShijieCanvasComparison.close()});
 }
 async function retry(id){const blank=blankDrafts.get(id);if(blank){await StudioBase.library.put(blank,'image',{checkpoint:true});return records(blank).find(r=>r.id===id)}await window.studio.saveCheckpoint('重试保存候选');return records(window.studio.adapter.get()).find(r=>r.id===id)}
 window.ShijieCandidateStore={retain,records,signature,render,preview,remove,retry,savedBase:id=>clone(blankDrafts.get(id))};
 if(typeof document==='undefined')return;
 document.addEventListener('DOMContentLoaded',()=>{const old=updateButtons;updateButtons=function(...args){const result=old.apply(this,args);render();return result};render()},{once:true});
})();
