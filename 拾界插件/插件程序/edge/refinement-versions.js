/* Manual visual corrections retain an adjacent, hidden original version. */
(()=>{
 const clone=value=>structuredClone(value);
 const stable=value=>Array.isArray(value)?value.map(stable):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(key=>[key,stable(value[key])])):value;
 const equal=(a,b)=>JSON.stringify(stable(a))===JSON.stringify(stable(b));
 const visualKeys=Object.freeze(['type','src','text','x','y','width','height','fill','stroke','strokeWidth','d','radius','opacity','visible','blendMode','fontFamily','fontResolved','fontSize','fontWeight','fontStyle','fontVariantLigatures','textSkew','fitWidth','rotation','lineHeight','letterSpacing','wordSpacing','textDecoration','gradient','layerStyle','displayMask']);
 const visual=node=>{
  const value=Object.fromEntries(visualKeys.filter(key=>node[key]!==undefined&&key!=='fontResolved').map(key=>[key,node[key]]));
  value.opacity=node.opacity??1;value.visible=node.visible!==false;
  if(node.type==='text')Object.assign(value,{fontFamily:node.fontFamily||'Microsoft YaHei',fontWeight:node.fontWeight||400,fontStyle:node.fontStyle||'normal',fitWidth:!!node.fitWidth,strokeWidth:node.strokeWidth||0,textSkew:node.textSkew||0,rotation:node.rotation||0,lineHeight:node.lineHeight??node.fontSize*1.2});
  if(node.type==='rect')value.radius=node.radius||0;
  if(!value.strokeWidth)delete value.stroke;
  for(const key of ['gradient','layerStyle','displayMask'])if(value[key]==null||value[key]?.enabled===false)delete value[key];
  return value;
 };
 const visuallyChanged=(before,result)=>!equal(visual(before),visual(result));
 function archiveChanges(before,result,ids){
  if(!Array.isArray(before?.nodes)||!Array.isArray(result?.nodes))throw Error('修正版缺少完整图层，无法保留旧版本');
  const scene=clone(result),oldById=new Map(before.nodes.map(node=>[node.id,node])),chosen=ids==null?null:new Set(ids);
  const forced=new Set((result.recognition?.selectedRefine?.entityChanges||[]).flatMap(op=>op.mode==='vector-group'?op.members:[op.anchorId]));
  const used=new Set([...before.nodes,...result.nodes,...(before.groups||[]),...(result.groups||[])].map(node=>node.id));
  const archives=new Map(),changedIds=[],archivedIds=[];let sequence=0;
  for(const next of scene.nodes){
   const old=oldById.get(next.id);
   if(!old||old.versionArchived||next.versionArchived||(chosen&&!chosen.has(next.id))||!forced.has(next.id)&&!visuallyChanged(old,next))continue;
   const stem='version-'+(globalThis.crypto?.randomUUID?.()||Date.now().toString(36));let id=stem;
   while(used.has(id))id=stem+'-'+(++sequence);used.add(id);
   const ordinal=before.nodes.filter(node=>node.versionArchived&&node.versionOf===old.id).length+1;
   const archive={...clone(old),id,name:String(old.name||old.text||'图层').slice(0,80)+' · 修正前版本 '+ordinal,visible:false,hidden:true,versionOf:old.id,versionArchived:true,versionArchivedAt:new Date().toISOString()};
   archives.set(next.id,archive);changedIds.push(next.id);archivedIds.push(id);
  }
  if(archives.size){
   scene.nodes=scene.nodes.flatMap(node=>archives.has(node.id)?[archives.get(node.id),node]:[node]);
   if(scene.groups)scene.groups=scene.groups.map(group=>({...group,children:group.children.flatMap(id=>archives.has(id)?[archives.get(id).id,id]:[id])}));
  }
  return {scene,changedIds,archivedIds};
 }
 window.ShijieRefinementVersions={archiveChanges,visuallyChanged,visual,visualKeys};
})();
