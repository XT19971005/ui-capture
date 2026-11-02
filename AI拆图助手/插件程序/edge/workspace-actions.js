/* One primary workflow row; secondary tools stay in named menus. */
(()=>{
 'use strict';
 if(window.studio?.adapter.kind!=='image')return;
 const byId=id=>document.getElementById(id),actions=document.querySelector('.document-actions'),bar=document.querySelector('.studio-bar');
 if(!actions||!bar)return;
 actions.append(byId('recognize'),byId('replace-image'),byId('generate-image'));
 byId('replace-image').textContent='圈选编辑';
 byId('generate-image').title='输入文字或上传参考图，生成一张新图片';
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
