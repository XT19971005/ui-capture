/* Geometry-only picking; never copies bitmap payloads or starts a model task. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.ShijieRegionSelection=api})(globalThis,()=>{
 function rectangle(start,end,board){
  if(![start?.x,start?.y,end?.x,end?.y,board?.width,board?.height].every(Number.isFinite)||board.width<=0||board.height<=0)return null;
  const x=Math.max(0,Math.min(board.width,Math.floor(Math.min(start.x,end.x)))),y=Math.max(0,Math.min(board.height,Math.floor(Math.min(start.y,end.y))));
  const right=Math.max(0,Math.min(board.width,Math.ceil(Math.max(start.x,end.x)))),bottom=Math.max(0,Math.min(board.height,Math.ceil(Math.max(start.y,end.y))));
  return right>x&&bottom>y?{x,y,width:right-x,height:bottom-y}:null;
 }
 function candidates(entries,r){
  const ids=[],crossingIds=[];let skipped=0;
  for(const e of entries){const b=e.bounds,n=e.node;if(!e.paint||!e.visible||!b||b.x>=r.x+r.width||b.y>=r.y+r.height||b.x+b.width<=r.x||b.y+b.height<=r.y)continue;
   if(n.assetKind==='background')continue;
   if(e.locked||n.versionArchived||n.pendingGeneration||['pending-image-generation','source-crop-fallback'].includes(n.provenance)||n.type==='image'&&(!n.src||n.generationRecord?.actualImageGeneration===false)){skipped++;continue}
   if(b.x>=r.x&&b.y>=r.y&&b.x+b.width<=r.x+r.width&&b.y+b.height<=r.y+r.height)ids.push(e.id);else crossingIds.push(e.id);
  }
  return {ids,crossingIds,skipped};
 }
 function cycle(stack,current){return stack.length?stack[(stack.indexOf(current)+1)%stack.length]:null}
 return {rectangle,candidates,cycle};
});
