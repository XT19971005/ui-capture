/* Selected correction is one transaction; progress never replaces the document. */
(()=>{
 const button=document.getElementById('refine-selected');if(!button||window.studio?.adapter.kind!=='image')return;
 const clone=value=>structuredClone(value),stable=value=>Array.isArray(value)?value.map(stable):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(k=>[k,stable(value[k])])):value;
 const equal=(a,b)=>JSON.stringify(stable(a))===JSON.stringify(stable(b));let active=null;
 const note=document.getElementById('selected-refine-note');
 const pendingRepair=record=>Array.isArray(record?.repairedAssetsNotRechecked)?record.repairedAssetsNotRechecked.length>0:!!record?.repairedAssetsNotRechecked;
 const completed=record=>['COMPLETED','PASS'].includes(record?.status)&&!pendingRepair(record);
 function metadata(doc){
  const entries=new Map([...(doc.nodes||[]),...(doc.groups||[])].map(n=>[n.id,n])),parents=new Map();
  for(const group of doc.groups||[])for(const id of group.children||[])parents.set(id,group.id);
  function flags(id){let locked=false,visible=true;const seen=new Set();while(id!=null){if(seen.has(id))throw Error('图层分组存在循环');seen.add(id);const n=entries.get(id);if(!n)throw Error('所选图层不存在');locked=locked||!!n.locked;visible=visible&&n.visible!==false&&!n.hidden&&!n.versionArchived;id=parents.get(id)}return {locked,visible}}
  function leaves(roots){const result=new Set(),seen=new Set();function visit(id){if(seen.has(id))throw Error('图层分组存在循环');const n=entries.get(id);if(!n)throw Error('所选图层不存在');if(!Array.isArray(n.children)){result.add(id);return}seen.add(id);for(const child of n.children)visit(child);seen.delete(id)}for(const id of roots)visit(id);return result}
  return {entries,flags,leaves};
 }
 function selection(){
  const doc=window.studio.adapter.get(),roots=window.studio.roots();
  if(!doc||!roots.length)return {ids:[],reason:'请先选择图层或分组'};
  if(!(doc.comparisonSource||doc.source))return {ids:[],reason:'当前工程没有工作原图，无法对照检查'};
  try{
   const meta=metadata(doc),set=typeof window.studio.adapter.leafIds==='function'?new Set(window.studio.adapter.leafIds(roots)):meta.leaves(roots);
   const chosen=doc.nodes.filter(n=>set.has(n.id)&&!n.versionArchived);
   if(chosen.some(n=>meta.flags(n.id).locked))return {ids:[],reason:'所选包含锁定图层，请先解锁'};
   if(chosen.some(n=>n.pendingGeneration||n.provenance==='pending-image-generation'))return {ids:[],reason:'请先完成所选素材的拆分'};
   return {ids:chosen.map(n=>n.id),roots,reason:chosen.length?'仅检查并修正这 '+chosen.length+' 个所选图层':'所选没有可处理图层'};
  }catch(e){return {ids:[],reason:e.message}}
 }
 function regionSelection(region,ids,doc=window.studio.adapter.get()){
  if(!doc?.nodes?.length||!(doc.comparisonSource||doc.source))throw Error('当前工程没有工作原图，无法检查区域');
  if(!region||typeof region!=='object'||Object.keys(region).sort().join(',')!=='height,width,x,y'||Object.values(region).some(v=>typeof v!=='number'||!Number.isFinite(v))||region.x<0||region.y<0||region.width<=0||region.height<=0||region.x+region.width>doc.width||region.y+region.height>doc.height)throw Error('检查区域必须是画布内的有效矩形');
  if(!Array.isArray(ids)||!ids.length||new Set(ids).size!==ids.length||ids.some(id=>typeof id!=='string'))throw Error('请先确认区域内要检查的图层');
  const nodes=new Map(doc.nodes.map(n=>[n.id,n])),meta=metadata(doc);
  for(const id of ids){const n=nodes.get(id);if(!n)throw Error('区域内所选图层不存在');const state=meta.flags(id);if(n.versionArchived||state.locked||!state.visible)throw Error('区域检查仅允许可见、未锁定的当前图层');if(n.pendingGeneration||['pending-image-generation','source-crop-fallback'].includes(n.provenance)||n.type==='image'&&(n.generationRecord?.actualImageGeneration===false||!n.src))throw Error('请先完成区域内所选素材的拆分');if(n.assetKind==='background')throw Error('区域检查不自动重做整张背景，请选择具体前景图层');if(['x','y','width','height'].some(k=>typeof n[k]!=='number'||!Number.isFinite(n[k]))||n.width<=0||n.height<=0||n.x<region.x||n.y<region.y||n.x+n.width>region.x+region.width||n.y+n.height>region.y+region.height)throw Error('所选图层跨出检查区域，请扩大框选或取消该图层')}
  return {ids:ids.slice(),roots:ids.slice(),region:{...region},reason:'仅检查框选区域内已确认的 '+ids.length+' 个图层'};
 }
 function sync(){const chosen=selection();button.disabled=busy||!!active||!chosen.ids.length||typeof ShijieSmartSplit.refineSelected!=='function'||typeof window.ShijieRefinementVersions?.archiveChanges!=='function';button.title=chosen.reason;button.textContent=active?(active.region?'正在检查区域…':'正在检查所选…'):'检查并修正选中项';const record=window.studio.adapter.get()?.recognition?.selectedRefine;if(note)note.textContent=!active&&record&&equal(record.selectedIds,chosen.ids)&&!completed(record)?(record.region?'框选区域':'所选项')+'仍需对照原图校对。':'';}
 function feedback(kind,message){if(note)note.textContent=kind==='review'?(active?.region?'框选区域':'仅所选项')+'已处理，仍需对照原图校对。':'';splitFeedback('selected-'+kind,message);status(message);}
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
 async function run(chosen=selection()){
  if(busy||active)return false;if(!chosen.ids.length||typeof ShijieSmartSplit.refineSelected!=='function'||typeof window.ShijieRefinementVersions?.archiveChanges!=='function')return false;
  const label=chosen.region?'检查并修正框选区域':'检查并修正选中项',scope=chosen.region?'区域':'所选';
  const transaction={id:++task,before:clone(scene),roots:chosen.roots,ids:chosen.ids,region:chosen.region,past:undo.slice(),future:redo.slice(),returned:null};active=transaction;refineBefore=transaction.before;
  setBusy(true);startSplitClock('selected');sync();
  try{
   // Save the intact starting point before any model request can be submitted.
   await durable();if(active!==transaction||task!==transaction.id)return;
   transaction.before=clone(scene);refineBefore=transaction.before;
   if(chosen.region)regionSelection(chosen.region,chosen.ids,transaction.before);
   const result=transaction.returned=await ShijieSmartSplit.refineSelected(clone(transaction.before),chosen.ids,(value,message)=>{if(active===transaction&&task===transaction.id){$('progress').value=value;status(message)}},chosen.region);
   if(active!==transaction||task!==transaction.id){releaseOther(result,transaction.before);return}
   validateResult(transaction.before,result,chosen.ids);
   if(chosen.region)regionSelection(chosen.region,chosen.ids,result);
   const selectedRecord=result.recognition?.selectedRefine||{status:'NEEDS_REVIEW',selectedIds:chosen.ids,warnings:['本次检查尚未得到确认结论']};
   if(chosen.region){if(selectedRecord.region&&!equal(selectedRecord.region,chosen.region))throw Error('返回结果的检查区域与本次框选不一致');selectedRecord.region={...chosen.region}}
   const versioned=window.ShijieRefinementVersions.archiveChanges(transaction.before,result,chosen.ids);
   const next={...transaction.before,...versioned.scene,_projectId:transaction.before._projectId,recognition:{...transaction.before.recognition,selectedRefine:clone(selectedRecord)}};
   const changedPixels=versioned.changedIds.length>0,pending=selectedRecord.status==='NEEDS_REVIEW'||pendingRepair(selectedRecord);
   if(changedPixels||pending)for(const key of ['status','reviewStatus'])if(['PASS','MANUAL_CONFIRMED'].includes(transaction.before.recognition?.[key]))next.recognition[key]=result.recognition?.[key]==='NEEDS_REVIEW'||pending?'NEEDS_REVIEW':'NOT_REVIEWED';
   if(transaction.before._partial)next._partial=true;else if(!Object.hasOwn(transaction.before,'_partial'))delete next._partial;
   // A retained audit describes the old pixels. Only a distinct new session may replace it.
   const oldSession=transaction.before._sessionId||transaction.before.delivery?.sessionId,newSession=result._sessionId||result.delivery?.sessionId;
   if(!newSession||newSession===oldSession){delete next._sessionId;delete next.delivery}
   S.validate(next);
   scene=clone(transaction.before);checkpoint(label);scene={...next,_studioStep:{label,time:Date.now()}};refresh();
   window.studio.select(transaction.roots,true);await durable();if(active!==transaction||task!==transaction.id)return;
   ShijieSmartSplit.releaseSession(transaction.before);stopSplitClock();
   feedback(completed(selectedRecord)?'success':'review',completed(selectedRecord)?scope+'图层检查并修正完成，其他图层保持。':scope+'图层处理完成，仍有项目需要校对。');return true;
  }catch(e){
   releaseOther(transaction.returned,transaction.before);
   if(active===transaction&&task===transaction.id){
    scene=clone(transaction.before);undo=transaction.past;redo=transaction.future;selected=null;refresh();window.studio.select(transaction.roots,true);
    let saved=true;try{await durable()}catch(_){saved=false}
    stopSplitClock();feedback(e.name==='AbortError'?'cancelled':'failure',(e.name==='AbortError'?scope+'修正已取消。':scope+'修正未完成：'+e.message+'。')+'完整工程已保留。'+(saved?'':'恢复保存失败，请下载工程文件。'));
   }
   return false;
  }finally{if(active===transaction&&task===transaction.id){active=null;refineBefore=null;stopSplitClock();setBusy(false);window.studio.sync(false);sync()}else if(active===transaction&&task!==transaction.id&&!transaction.cancelling){active=null;if(refineBefore===transaction.before)refineBefore=null;sync()}}
 }
 async function cancel(){
  const transaction=active;if(!transaction||task!==transaction.id)return;
  transaction.cancelling=true;const scope=transaction.region?'区域':'所选',id=++task;stopSplitClock();$('cancel').disabled=true;status('正在取消'+scope+'修正并保存工程…');
  try{await ShijieSmartSplit.cancel()}catch(_){}
  if(task!==id||active!==transaction)return;
  releaseOther(transaction.returned,transaction.before);
  scene=clone(transaction.before);undo=transaction.past;redo=transaction.future;selected=null;refresh();window.studio.select(transaction.roots,true);
  let saved=true;try{await durable()}catch(_){saved=false}
  if(task!==id||active!==transaction)return;
  active=null;refineBefore=null;setBusy(false);window.studio.sync(false);sync();
  feedback('cancelled',scope+'修正已取消，完整工程保留。'+(saved?'':'恢复保存失败，请下载工程文件。'));
 }
 button.addEventListener('click',()=>{run().catch(e=>{status('所选修正未完成：'+e.message)})});
 $('cancel').addEventListener('click',event=>{if(!active||task!==active.id)return;event.preventDefault();event.stopImmediatePropagation();cancel().catch(e=>status('取消未完成：'+e.message))},true);
 const previous=updateButtons;updateButtons=function(...args){const result=previous.apply(this,args);sync();return result};
 async function runRegion(region,ids){if(busy||active)throw Error('请等待当前操作完成后再检查区域');const chosen=regionSelection(region,ids);if(typeof ShijieSmartSplit.refineSelected!=='function'||typeof window.ShijieRefinementVersions?.archiveChanges!=='function')throw Error('区域检查暂不可用，请重新连接');return run(chosen)}
 window.ShijieSelectedRefine={sync,isActive:()=>!!active,runRegion};sync();
})();
