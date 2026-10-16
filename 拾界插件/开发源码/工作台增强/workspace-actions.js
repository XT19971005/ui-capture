/* One primary workflow row; secondary tools stay in named menus. */
(()=>{
 'use strict';
 if(window.studio?.adapter.kind!=='image')return;
 const byId=id=>document.getElementById(id),actions=document.querySelector('.document-actions'),bar=document.querySelector('.studio-bar');
 if(!actions||!bar)return;
 actions.append(byId('recognize'),byId('replace-image'),byId('generate-image'));
 byId('replace-image').textContent='圈选编辑';
 byId('generate-image').title='输入文字或上传参考图，生成一张新图片';
 function menu(label,elements){const details=document.createElement('details');details.className='workspace-action-menu';const summary=document.createElement('summary');summary.textContent=label+' ▾';const content=document.createElement('div');content.className='workspace-action-menu-items';content.append(...elements.filter(Boolean));details.append(summary,content);bar.append(details);content.addEventListener('click',e=>{if(e.target.closest('button')&&!e.target.closest('button').disabled)details.open=false});details.addEventListener('toggle',()=>{if(details.open)for(const other of document.querySelectorAll('.workspace-action-menu'))if(other!==details)other.open=false});return details}
 const layerMenu=menu('图层整理',[bar.querySelector('[data-action="group"]'),bar.querySelector('[data-action="ungroup"]'),bar.querySelector('[data-action="align-menu"]')]);
 const checkMenu=menu('检查修复',[byId('refine-selected'),byId('review-region'),byId('refine-ui'),byId('repair-order'),byId('review-info')]);
 bar.querySelector('.studio-spacer')?.before(layerMenu,checkMenu);
 const controls=document.querySelector('.selected-refine-controls');if(controls)controls.classList.add('secondary-check-notes');
 byId('review-region').textContent='区域检查图层';
 const note=document.createElement('p');note.className='workspace-inspector-help';note.textContent='选中文字层可编辑文字；圈选编辑或生成图片后，在这里填写描述、上传参考图。';byId('no-selection')?.append(note);
 document.addEventListener('pointerdown',e=>{for(const menu of document.querySelectorAll('.workspace-action-menu[open]'))if(!menu.contains(e.target))menu.open=false});
 const previous=updateButtons;updateButtons=function(...args){const result=previous.apply(this,args);const doc=studio.adapter.get(),isRaw=doc?.nodes?.filter(n=>!n.versionArchived).length===1&&window.ShijieImageReplacement?.target(doc,[]);byId('review-region').hidden=!!isRaw;for(const details of [layerMenu,checkMenu])details.classList.toggle('is-unavailable',!doc);return result};
 updateButtons();
})();
