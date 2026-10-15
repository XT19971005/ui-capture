/* Selected correction is one transaction; progress never replaces the document. */
(()=>{
 const button=document.getElementById('refine-selected');if(!button||window.studio?.adapter.kind!=='image')return;
 const clone=value=>structuredClone(value),stable=value=>Array.isArray(value)?value.map(stable):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(k=>[k,stable(value[k])])):value;
 const equal=(a,b)=>JSON.stringify(stable(a))===JSON.stringify(stable(b));let active=null;
 const note=document.getElementById('selected-refine-note');
 const pendingRepair=record=>Array.isArray(record?.repairedAssetsNotRechecked)?record.repairedAssetsNotRechecked.length>0:!!record?.repairedAssetsNotRechecked;
 const completed=record=>['COMPLETED','PASS'].includes(record?.status)&&!pendingRepair(record);
 const visualKeys=['type','src','text','x','y','width','height','fill','stroke','strokeWidth','d','radius','opacity','visible','blendMode','fontFamily','fontResolved','fontSize','fontWeight','fontStyle','fontVariantLigatures','textSkew','fitWidth','rotation','lineHeight','letterSpacing','wordSpacing','textDecoration','gradient','layerStyle','displayMask'];
 const visual=node=>Object.fromEntries(visualKeys.filter(k=>node[k]!==undefined).map(k=>[k,node[k]]));
 function selection(){
  const doc=window.studio.adapter.get(),roots=window.studio.roots();
  if(!doc||!roots.length)return {ids:[],reason:'请先选择图层或分组'};
  if(!(doc.comparisonSource||doc.source))return {ids:[],reason:'当前工程没有工作原图，无法对照检查'};
  try{
   const subset=window.studio.adapter.selectionData(roots,0),set=new Set(subset.nodes.map(n=>n.id)),entries=window.studio.adapter.entries();
   const chosen=doc.nodes.filter(n=>set.has(n.id));
   if(chosen.some(n=>entries.get(n.id)?.locked))return {ids:[],reason:'所选包含锁定图层，请先解锁'};
   if(chosen.some(n=>n.pendingGeneration||n.provenance==='pending-image-generation'))return {ids:[],reason:'请先完成所选素材的拆分'};
   return {ids:chosen.map(n=>n.id),roots,reason:chosen.length?'仅检查并修正这 '+chosen.length+' 个所选图层':'所选没有可处理图层'};
  }catch(e){return {ids:[],reason:e.message}}
 }
 function sync(){const chosen=selection();button.disabled=busy||!!active||!chosen.ids.length||typeof ShijieSmartSplit.refineSelected!=='function';button.title=chosen.reason;button.textContent=active?'正在检查所选…':'检查并修正选中项';const record=window.studio.adapter.get()?.recognition?.selectedRefine;if(note)note.textContent=!active&&record&&equal(record.selectedIds,chosen.ids)&&!completed(record)?'所选项仍需对照原图校对。':'';}
 function feedback(kind,message){if(note)note.textContent=kind==='review'?'仅所选项已处理，仍需对照原图校对。':'';splitFeedback('selected-'+kind,message);status(kind==='failure'?'所选修正未完成，完整工程已保留，可重试。':message);}
 function releaseOther(result,before){const id=result?._sessionId||result?.delivery?.sessionId,old=before?._sessionId||before?.delivery?.sessionId;if(id&&id!==old)ShijieSmartSplit.releaseSession(result)}
 function validateResult(before,result,ids){
  if(!result||!Array.isArray(result.nodes))throw Error('所选修正没有返回完整工程');S.validate(result);
  if(result.nodes.length!==before.nodes.length||!!result._partial!==!!before._partial)throw Error('返回工程改变了完成状态或图层数量');
  const chosen=new Set(ids);
  for(let i=0;i<before.nodes.length;i++){
   const old=before.nodes[i],next=result.nodes[i];
   if(old.id!==next.id||old.type!==next.type)throw Error('返回工程改变了图层身份、类型或顺序');
   if(!chosen.has(old.id)&&!equal(old,next))throw Error('返回工程改变了未选图层，已拒绝本次结果');
  }
  const allowed=new Set(['nodes','recognition','_projectId','_studioStep','_sessionId','delivery','_partial']);
  for(const key of new Set([...Object.keys(before),...Object.keys(result)]))if(!allowed.has(key)&&!equal(before[key],result[key]))throw Error('返回工程改变了'+key+'，已拒绝本次结果');
 }
 async function durable(){await window.studio.flush()}
 async function run(){
  if(busy||active)return;const chosen=selection();if(!chosen.ids.length||typeof ShijieSmartSplit.refineSelected!=='function')return;
  const transaction={id:++task,before:clone(scene),roots:chosen.roots,ids:chosen.ids,past:undo.slice(),future:redo.slice(),returned:null};active=transaction;refineBefore=transaction.before;
  setBusy(true);startSplitClock('selected');sync();
  try{
   // Save the intact starting point before any model request can be submitted.
   await durable();if(active!==transaction||task!==transaction.id)return;
   transaction.before=clone(scene);refineBefore=transaction.before;
   const result=transaction.returned=await ShijieSmartSplit.refineSelected(clone(transaction.before),chosen.ids,(value,message)=>{if(active===transaction&&task===transaction.id){$('progress').value=value;status(message)}});
   if(active!==transaction||task!==transaction.id){releaseOther(result,transaction.before);return}
   validateResult(transaction.before,result,chosen.ids);
   const selectedRecord=result.recognition?.selectedRefine||{status:'NEEDS_REVIEW',selectedIds:chosen.ids,warnings:['本次检查尚未得到确认结论']};
   const next={...transaction.before,...result,_projectId:transaction.before._projectId,recognition:{...transaction.before.recognition,selectedRefine:clone(selectedRecord)}};
   const changedPixels=transaction.before.nodes.some((n,i)=>!equal(visual(n),visual(result.nodes[i]))),pending=selectedRecord.status==='NEEDS_REVIEW'||pendingRepair(selectedRecord);
   if(changedPixels||pending)for(const key of ['status','reviewStatus'])if(['PASS','MANUAL_CONFIRMED'].includes(transaction.before.recognition?.[key]))next.recognition[key]=result.recognition?.[key]==='NEEDS_REVIEW'||pending?'NEEDS_REVIEW':'NOT_REVIEWED';
   if(transaction.before._partial)next._partial=true;else if(!Object.hasOwn(transaction.before,'_partial'))delete next._partial;
   // A retained audit describes the old pixels. Only a distinct new session may replace it.
   const oldSession=transaction.before._sessionId||transaction.before.delivery?.sessionId,newSession=result._sessionId||result.delivery?.sessionId;
   if(!newSession||newSession===oldSession){delete next._sessionId;delete next.delivery}
   scene=clone(transaction.before);checkpoint('检查并修正选中项');scene={...next,_studioStep:{label:'检查并修正选中项',time:Date.now()}};refresh();
   window.studio.select(transaction.roots,true);await durable();if(active!==transaction||task!==transaction.id)return;
   ShijieSmartSplit.releaseSession(transaction.before);stopSplitClock();
   feedback(completed(selectedRecord)?'success':'review',completed(selectedRecord)?'所选图层检查并修正完成，其他图层保持。':'所选图层处理完成，仍有项目需要校对。');
  }catch(e){
   releaseOther(transaction.returned,transaction.before);
   if(active===transaction&&task===transaction.id){
    scene=clone(transaction.before);undo=transaction.past;redo=transaction.future;selected=null;refresh();window.studio.select(transaction.roots,true);
    let saved=true;try{await durable()}catch(_){saved=false}
    stopSplitClock();feedback(e.name==='AbortError'?'cancelled':'failure',(e.name==='AbortError'?'所选修正已取消。':'所选修正未完成：'+e.message+'。')+'完整工程已保留。'+(saved?'':'恢复保存失败，请下载工程文件。'));
   }
  }finally{if(active===transaction&&task===transaction.id){active=null;refineBefore=null;stopSplitClock();setBusy(false);window.studio.sync(false);sync()}else if(active===transaction&&task!==transaction.id&&!transaction.cancelling){active=null;if(refineBefore===transaction.before)refineBefore=null;sync()}}
 }
 async function cancel(){
  const transaction=active;if(!transaction||task!==transaction.id)return;
  transaction.cancelling=true;const id=++task;stopSplitClock();$('cancel').disabled=true;status('正在取消所选修正并保存工程…');
  try{await ShijieSmartSplit.cancel()}catch(_){}
  if(task!==id||active!==transaction)return;
  releaseOther(transaction.returned,transaction.before);
  scene=clone(transaction.before);undo=transaction.past;redo=transaction.future;selected=null;refresh();window.studio.select(transaction.roots,true);
  let saved=true;try{await durable()}catch(_){saved=false}
  if(task!==id||active!==transaction)return;
  active=null;refineBefore=null;setBusy(false);window.studio.sync(false);sync();
  feedback('cancelled','所选修正已取消，完整工程保留。'+(saved?'':'恢复保存失败，请下载工程文件。'));
 }
 button.addEventListener('click',()=>{run().catch(e=>{status('所选修正未完成：'+e.message)})});
 $('cancel').addEventListener('click',event=>{if(!active||task!==active.id)return;event.preventDefault();event.stopImmediatePropagation();cancel().catch(e=>status('取消未完成：'+e.message))},true);
 const previous=updateButtons;updateButtons=function(...args){const result=previous.apply(this,args);sync();return result};
 window.ShijieSelectedRefine={sync,isActive:()=>!!active};sync();
})();
