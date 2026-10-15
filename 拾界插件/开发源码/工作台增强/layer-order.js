/* Explicit full-scene order repair: one durable, undoable transaction. */
(()=>{
 const button=document.getElementById('repair-order');if(!button||window.studio?.adapter.kind!=='image')return;
 const clone=v=>structuredClone(v),stable=v=>Array.isArray(v)?v.map(stable):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,stable(v[k])])):v,equal=(a,b)=>JSON.stringify(stable(a))===JSON.stringify(stable(b));
 const note=document.getElementById('order-repair-note');let active=null;
 const omitted=(value,keys)=>Object.fromEntries(Object.entries(value||{}).filter(([k])=>!keys.includes(k)));
 function eligible(doc=scene){return !!(doc?.nodes?.length>=2&&(doc.comparisonSource||doc.source||doc.originalSource))}
 function sync(){button.disabled=busy||!!active||!eligible()||typeof ShijieSmartSplit.repairOrder!=='function';button.textContent=active?'正在修复层级…':'修复层级';button.title=!scene?'请先打开工程':!eligible()?'至少需要两个图层和原图':'对照原图遮挡关系，仅调整图层前后顺序；锁定项保持原位';const r=scene?.recognition?.orderRepair;if(note&&!active)note.textContent=r?[...(r.notes||[]),...(r.uncertain?.length?['有遮挡关系待校对，已保留未确定部分的顺序。']:[])].join(' ').slice(0,500):''}
 function validate(before,result){
  if(!result||!Array.isArray(result.nodes))throw Error('没有返回完整工程');S.validate(result);
  if(result.nodes.length!==before.nodes.length||new Set(result.nodes.map(n=>n.id)).size!==before.nodes.length)throw Error('返回结果改变了图层数量或身份');
  const byId=new Map(result.nodes.map(n=>[n.id,n])),oldGroups=before.groups||[],nextGroups=result.groups||[];
  for(const old of before.nodes)if(!equal(old,byId.get(old.id)))throw Error('返回结果改变了图层内容，已拒绝本次结果');
  if(oldGroups.length!==nextGroups.length)throw Error('返回结果改变了分组');
  for(let i=0;i<oldGroups.length;i++){
   const old=oldGroups[i],next=nextGroups[i];if(!equal(omitted(old,['children']),omitted(next,['children']))||!Array.isArray(next.children)||next.children.length!==old.children.length||!equal([...next.children].sort(),[...old.children].sort()))throw Error('返回结果改变了分组内容或归属');

  }
  const nextMap=new Map(nextGroups.map(g=>[g.id,g])),owner=new Map();for(const g of nextGroups)for(const id of g.children)owner.set(id,g.id);const flatten=id=>nextMap.has(id)?nextMap.get(id).children.flatMap(flatten):[id],roots=[];for(const n of result.nodes){let id=n.id;while(owner.has(id))id=owner.get(id);if(!roots.includes(id))roots.push(id)}if(!equal(roots.flatMap(flatten),result.nodes.map(n=>n.id)))throw Error('返回结果拆散了分组或成员顺序不一致');
  const entries=new Map([...before.nodes,...oldGroups].map(n=>[n.id,n])),locked=new Set(),pending=[...entries.values()].filter(n=>n.locked).map(n=>n.id);while(pending.length){const id=pending.pop();if(locked.has(id))continue;locked.add(id);pending.push(...(entries.get(id)?.children||[]))}const oldIds=before.nodes.map(n=>n.id),nextIds=result.nodes.map(n=>n.id),oldPosition=new Map(oldIds.map((id,i)=>[id,i])),nextPosition=new Map(nextIds.map((id,i)=>[id,i]));for(const id of oldIds)if(locked.has(id))for(const other of oldIds)if((oldPosition.get(id)<oldPosition.get(other))!==(nextPosition.get(id)<nextPosition.get(other)))throw Error('返回结果移动了锁定图层或分组');
  for(const key of new Set([...Object.keys(before),...Object.keys(result)]))if(!['nodes','groups','recognition','_sessionId','delivery'].includes(key)&&!(key==='_projectId'&&!Object.hasOwn(result,key))&&!equal(before[key],result[key]))throw Error('返回结果改变了工程 '+key);
  const expectedRecognition=clone(before.recognition||{});for(const key of ['status','reviewStatus'])if(['PASS','MANUAL_CONFIRMED'].includes(expectedRecognition[key])&&['NOT_REVIEWED','NEEDS_REVIEW'].includes(result.recognition?.[key]))expectedRecognition[key]=result.recognition[key];if(!equal(omitted(expectedRecognition,['orderRepair']),omitted(result.recognition,['orderRepair'])))throw Error('返回结果改变了其他校对结论');
  const record=result.recognition?.orderRepair;if(!['COMPLETED','NEEDS_REVIEW'].includes(record?.status)||!Array.isArray(record.notes)||!Array.isArray(record.changedIds)||!Array.isArray(record.changedGroupIds)||!Array.isArray(record.relations)||!Array.isArray(record.uncertain)||typeof record.applied!=='boolean')throw Error('层级检查结论无效');
 }
 function feedback(kind,message){splitFeedback('order-'+kind,message);$('split-feedback-text').textContent=message.split(/。|\r?\n/)[0].slice(0,150);status(message);sync()}
 async function durable(){await window.studio.flush()}
 function releaseReturned(tx){const kept=new Set([tx.before?._sessionId,tx.before?.delivery?.sessionId]);for(const id of new Set([tx.returned?._sessionId,tx.returned?.delivery?.sessionId]))if(typeof id==='string'&&id&&!kept.has(id))try{ShijieSmartSplit.releaseSession({_sessionId:id})}catch(_){}}
 async function restore(tx){scene=clone(tx.before);undo=tx.past;redo=tx.future;selected=null;refresh();window.studio.select(tx.roots,true);try{await durable();return true}catch(_){return false}}
 async function run(){
  if(busy||active||!eligible())return;
  const tx={id:++task,before:clone(scene),past:undo.slice(),future:redo.slice(),roots:window.studio.roots(),cancelling:false,returned:null};active=tx;refineBefore=tx.before;setBusy(true);startSplitClock();splitFeedback('order-running','正在对照原图检查图层遮挡关系…');sync();
  try{
   await durable();if(active!==tx||task!==tx.id)return;tx.before=clone(scene);refineBefore=tx.before;
   const result=tx.returned=await ShijieSmartSplit.repairOrder(clone(tx.before),(value,message)=>{if(active===tx&&task===tx.id){$('progress').value=value;status(message)}});
   if(active!==tx||task!==tx.id)return;validate(tx.before,result);
   const next=clone(tx.before),record=clone(result.recognition.orderRepair);next.nodes=clone(result.nodes);if(Object.hasOwn(result,'groups'))next.groups=clone(result.groups);next.recognition={...next.recognition,orderRepair:record};
   const changed=!equal(tx.before.nodes,next.nodes)||!equal(tx.before.groups,next.groups);for(const key of ['status','reviewStatus'])if(['PASS','MANUAL_CONFIRMED'].includes(next.recognition[key])&&(changed||record.status==='NEEDS_REVIEW'))next.recognition[key]=record.status==='NEEDS_REVIEW'?'NEEDS_REVIEW':'NOT_REVIEWED';
   delete next._sessionId;delete next.delivery;scene=clone(tx.before);checkpoint('修复层级');scene={...next,_studioStep:{label:'修复层级',time:Date.now()}};refresh();window.studio.select(tx.roots,true);await durable();if(active!==tx||task!==tx.id)return;
   ShijieSmartSplit.releaseSession(tx.before);stopSplitClock();feedback(record.status==='NEEDS_REVIEW'?'review':'success',record.status==='NEEDS_REVIEW'?'层级检查完成，有遮挡关系需要校对；未确定部分保持原顺序。':changed?'层级已修复，图层内容保持，可撤销。':'层级检查完成，当前顺序无需调整。');
  }catch(e){if(active===tx&&task===tx.id){const saved=await restore(tx);stopSplitClock();feedback(e.name==='AbortError'?'cancelled':'failure',(e.name==='AbortError'?'层级修复已取消。':'层级修复未完成：'+e.message+'。')+'完整工程已保留。'+(saved?'':'恢复保存失败，请下载工程文件。'))}}
  finally{releaseReturned(tx);if(active===tx&&task===tx.id){active=null;refineBefore=null;stopSplitClock();setBusy(false);window.studio.sync(false);sync()}}
 }
 async function cancel(){const tx=active;if(!tx||task!==tx.id)return;tx.cancelling=true;const id=++task;stopSplitClock();$('cancel').disabled=true;status('正在取消层级修复并保存工程…');try{await ShijieSmartSplit.cancel()}catch(_){}if(active!==tx||task!==id)return;const saved=await restore(tx);if(active!==tx||task!==id)return;active=null;refineBefore=null;setBusy(false);window.studio.sync(false);feedback('cancelled','层级修复已取消，完整工程保留。'+(saved?'':'恢复保存失败，请下载工程文件。'))}
 button.addEventListener('click',()=>run().catch(e=>status('层级修复未完成：'+e.message)));
 $('cancel').addEventListener('click',event=>{if(!active||task!==active.id)return;event.preventDefault();event.stopImmediatePropagation();cancel().catch(e=>status('取消未完成：'+e.message))},true);
 const previous=updateButtons;updateButtons=function(...args){const result=previous.apply(this,args);sync();return result};window.ShijieLayerOrder={sync,isActive:()=>!!active};sync();
})();
