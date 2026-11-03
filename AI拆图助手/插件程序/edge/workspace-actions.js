/* One primary workflow row; secondary tools stay in named menus. */
(()=>{
 'use strict';
 if(window.studio?.adapter.kind!=='image')return;
 const byId=id=>document.getElementById(id),actions=document.querySelector('.document-actions'),bar=document.querySelector('.studio-bar');
 if(!actions||!bar)return;
 actions.append(byId('recognize'),byId('replace-image'));
 byId('replace-image').textContent='圈选编辑';
 const toolsMenu=document.querySelector('.image-tools-menu'),toolItems=toolsMenu?.querySelector('div');
 const checkButtons=[byId('review-region'),byId('refine-ui'),byId('repair-order'),byId('review-info')].filter(Boolean);
 bar.append(...checkButtons);if(toolsMenu){toolsMenu.before(bar);toolsMenu.remove()}bar.hidden=true;
 if(toolsMenu){document.addEventListener('pointerdown',e=>{if(!toolsMenu.contains(e.target))toolsMenu.open=false});toolsMenu.addEventListener('keydown',e=>{if(e.key==='Escape'){toolsMenu.open=false;toolsMenu.querySelector('summary').focus()}})}
 document.querySelector('.doc-tag')?.remove();
 // The assistant owns correction conversation, candidate preview and Apply.
 const controls=document.querySelector('.selected-refine-controls');controls?.remove();
 byId('review-region').textContent='区域检查图层';
 const note=document.createElement('p');note.className='workspace-inspector-help';note.textContent='选中文字层可编辑文字；使用原画标注圈选后，可提取素材、参考生图或局部替换。';byId('no-selection')?.append(note);
 document.addEventListener('pointerdown',e=>{for(const menu of document.querySelectorAll('.workspace-action-menu[open]'))if(!menu.contains(e.target))menu.open=false});
 const previous=updateButtons;updateButtons=function(...args){const result=previous.apply(this,args);const doc=studio.adapter.get(),isRaw=doc?.nodes?.filter(n=>!n.versionArchived).length===1&&window.ShijieImageReplacement?.target(doc,[]);byId('review-region').hidden=!!isRaw;if(toolsMenu)toolsMenu.classList.toggle('is-unavailable',!doc);return result};
 updateButtons();
})();

/* View-only controls never modify the source, and font replacement is one undo. */
(()=>{
 if(window.studio?.adapter.kind!=='image')return;
 const studio=window.studio,byId=id=>document.getElementById(id),viewTools=document.querySelector('.view-tools');
 const fitSelected=document.createElement('button');fitSelected.id='fit-selected';fitSelected.textContent='适应所选';fitSelected.title='按所选素材可见范围缩放，保留半透明光效';byId('fit-width').after(fitSelected);
 const inspectorToggle=document.createElement('button');inspectorToggle.id='inspector-toggle';inspectorToggle.textContent='设计栏';inspectorToggle.setAttribute('aria-controls','inspector-edit');viewTools.append(inspectorToggle);
 inspectorToggle.onclick=()=>{document.body.classList.toggle('inspector-collapsed');sync();window.dispatchEvent(new Event('shijie-assistant-layout'));fit(!['fit','width'].includes(byId('zoom').value))};
 fitSelected.onclick=async()=>{const owner=studio.adapter.get(),ids=studio.adapter.leafIds(studio.roots()),map=studio.adapter.entries(),items=ids.map(id=>map.get(id)).filter(e=>e?.visible),before=items.map(e=>({n:e.node,x:e.node.x,y:e.node.y,width:e.node.width,height:e.node.height,src:e.node.src}));if(!items.length)return;fitSelected.disabled=true;
  try{const boxes=[];for(const entry of items){const n=entry.node;if(n.type!=='image'){boxes.push({...entry.bounds});continue}const im=await ShijieScene.loadImage(n.src),c=document.createElement('canvas');if(im.width*im.height>36000000)throw Error('素材过大，请先使用整画板适应');c.width=im.width;c.height=im.height;const ctx=c.getContext('2d',{willReadFrequently:true});ctx.drawImage(im,0,0);const pixels=ctx.getImageData(0,0,c.width,c.height).data;let l=c.width,t=c.height,r=-1,b=-1;for(let y=0;y<c.height;y++)for(let x=0;x<c.width;x++)if(pixels[(y*c.width+x)*4+3]>0){l=Math.min(l,x);r=Math.max(r,x);t=Math.min(t,y);b=Math.max(b,y)}if(r>=l)boxes.push({x:n.x+l/c.width*n.width,y:n.y+t/c.height*n.height,width:(r-l+1)/c.width*n.width,height:(b-t+1)/c.height*n.height})}
   if(studio.adapter.get()!==owner||ids.join()!==studio.adapter.leafIds(studio.roots()).join()||before.some(v=>owner.nodes.find(n=>n.id===v.n.id)!==v.n||['x','y','width','height','src'].some(k=>v.n[k]!==v[k])))return;
   const box=StudioBase.bounds(boxes);if(!box)throw Error('所选图层没有可见像素');const viewport=byId('viewport'),s=Math.max(.002,Math.min(8,(viewport.clientWidth-64)/box.width,(viewport.clientHeight-64)/box.height)),z=byId('zoom');let option=z.querySelector('[data-custom]');if(!option){option=new Option();option.dataset.custom='true';z.add(option)}option.value=String(s);option.textContent=Math.round(s*100)+'%';z.value=String(s);fit(false);viewport.scrollLeft=imageOrigin.x+(box.x+box.width/2)*scale-viewport.clientWidth/2;viewport.scrollTop=imageOrigin.y+(box.y+box.height/2)*scale-viewport.clientHeight/2;studio.overlay();status('已适应所选可见素材；原图和图层尺寸保持');
  }catch(error){status(error.message)}finally{sync()}
 };
 const fontPanel=document.createElement('details');fontPanel.className='font-mapping';fontPanel.innerHTML='<summary>字体来源与批量替换</summary><p data-font-current></p><label>来源字体<select aria-label="来源字体"></select></label><label>替换字体<select aria-label="批量替换字体"></select></label><button type="button">替换同源字体</button><p data-font-status role="status">替换后重新测量文字；请对照原图复核换行与字形。</p>';
 byId('inspector-edit').append(fontPanel);const source=fontPanel.querySelector('select'),target=fontPanel.querySelectorAll('select')[1],replace=fontPanel.querySelector('button'),fontStatus=fontPanel.querySelector('[data-font-status]');
 for(const family of ['Microsoft YaHei','SimHei','Arial','Impact','Arial Narrow','Haettenschweiler'])target.add(new Option(family,family));let fontSignature='',fontReplacing=false;
 replace.onclick=async()=>{const owner=studio.adapter.get(),family=source.value,next=target.value;if(!owner||studio.isBusy()||fontReplacing||!family)return;const entries=studio.adapter.entries();let nodes=owner.nodes.filter(n=>n.type==='text'&&(n.sourceFontFamily||n.fontFamily||'Microsoft YaHei')===family),editable=nodes.filter(n=>!entries.get(n.id)?.locked);if(!editable.length){fontStatus.textContent='同源文字均已锁定，请先解锁';return}fontReplacing=true;replace.disabled=true;
  try{await document.fonts.ready;if(studio.adapter.get()!==owner||source.value!==family||target.value!==next)throw Error('工程或字体选择已改变，请重新操作');if(studio.isBusy())throw Error('当前有其他操作，请完成后重试');nodes=owner.nodes.filter(n=>n.type==='text'&&(n.sourceFontFamily||n.fontFamily||'Microsoft YaHei')===family);const currentEntries=studio.adapter.entries();editable=nodes.filter(n=>!currentEntries.get(n.id)?.locked);if(!editable.length)throw Error('同源文字已删除或锁定，本次未修改');if(!document.fonts.check('16px "'+next+'"'))throw Error('字体尚未载入，请先检查字体');await studio.adapter.commit(()=>{for(const n of editable){n.sourceFontFamily=n.sourceFontFamily||n.fontFamily||'Microsoft YaHei';n.fontFamily=next;n.resolvedFont=next;const m=ShijieScene.metrics(n);if(!n.textTransform&&!n.rotation){n.width=Math.max(1,Math.ceil(m.width));n.height=Math.max(1,Math.ceil((n.text||'').split(/\r?\n/).length*(n.lineHeight||n.fontSize*1.2)))}n.review=true;n.reviewIssue='字体已替换，请对照原图检查字形、换行与位置'}} ,'批量替换字体');studio.sync();fontStatus.textContent='已替换 '+editable.length+' 层'+(nodes.length>editable.length?'；跳过 '+(nodes.length-editable.length)+' 个锁定层':'')+'，可一次撤销。浏览器可渲染不代表与原字体一致。'}catch(error){fontStatus.textContent=error.message}finally{fontReplacing=false;sync()}
 };
 const manualState=document.createElement('p');manualState.className='manual-review-state';byId('review').after(manualState);
 function sync(){const doc=studio.adapter.get(),ids=studio.adapter.leafIds(studio.roots()),n=doc?.nodes?.find(n=>n.id===studio.adapter.primary());fitSelected.disabled=!doc||!ids.length||studio.isBusy()||byId('view').value==='source';inspectorToggle.setAttribute('aria-expanded',String(!document.body.classList.contains('inspector-collapsed')));manualState.hidden=!n?.manualReviewedAt;manualState.textContent=n?.manualReviewedAt?'此图层已人工确认；不是自动视觉检查结论。':'';const texts=doc?.nodes?.filter(n=>n.type==='text')||[];fontPanel.hidden=!texts.length;const families=[...new Set(texts.map(n=>n.sourceFontFamily||n.fontFamily||'Microsoft YaHei'))],signature=families.join('\n');if(signature!==fontSignature){fontSignature=signature;const previous=source.value;source.replaceChildren(...families.map(f=>new Option(f,f)));if(families.includes(previous))source.value=previous}fontPanel.querySelector('[data-font-current]').textContent=n?.type==='text'?'所选：'+(n.fontFamily||'Microsoft YaHei')+' · 来源：'+(n.sourceFontFamily||n.fontFamily||'Microsoft YaHei'):'按原始字体一次替换多个文字层；锁定层保留。';replace.disabled=fontReplacing||!doc||!families.length||studio.isBusy();}
 const oldSync=studio.sync;studio.sync=function(...args){const result=oldSync.apply(this,args);sync();return result};byId('view').addEventListener('change',sync);sync();
})();
