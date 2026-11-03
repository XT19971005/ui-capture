/* Shared workspace navigation. Working data is released when leaving this page. */
(()=>{
 const imageMode=!!document.getElementById('image-file'),header=document.querySelector('.app-header');if(!header)return;
 // Dialog content uses one inspector panel; no modal stack or backdrop.
 let inlineCurrent=null;
 const inlineApi=window.ShijieInlinePanels={open(dialog){
  document.body.classList.remove('inspector-collapsed');window.dispatchEvent(new Event('shijie-inspector-open'));const aside=document.querySelector('.properties,.inspector');if(!aside)throw Error('设置面板不可用');
  if(inlineCurrent&&inlineCurrent!==dialog)inlineCurrent.close();
  let host=aside.querySelector('.inline-panel-host');if(!host){host=document.createElement('section');host.className='inline-panel-host';aside.append(host)}
  dialog.querySelector('header small')?.remove();dialog.classList.add('inline-inspector-dialog');host.append(dialog);aside.classList.add('has-inline-panel');inlineCurrent=dialog;
  for(const button of dialog.querySelectorAll('form[method=dialog] button,[data-close]')){button.textContent='返回';button.title='返回设计面板'}
  if(!dialog.open)dialog.show();
  dialog.addEventListener('close',()=>{if(inlineCurrent===dialog){inlineCurrent=null;aside.classList.remove('has-inline-panel')}},{once:true});
  dialog.scrollIntoView({block:'nearest'});return dialog;
 },close(){inlineCurrent?.close()}};
 for(const id of ['tab-edit','tab-export','tab-design'])document.getElementById(id)?.addEventListener('click',()=>inlineApi.close());
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&inlineCurrent){e.preventDefault();e.stopImmediatePropagation();inlineApi.close()}},true);
 const nav=document.createElement('nav');nav.className='workspace-switch';nav.setAttribute('aria-label','工作模式');
 nav.innerHTML='<a href="image-editor.html" data-mode="image"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="3"/><path d="m3 16 5-5 4 4 3-3 6 6"/><circle cx="15" cy="8" r="1"/></svg>图片拆分</a><a href="export.html" data-mode="web"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="3"/><path d="M3 9h18m-13-3h1m3 0h1"/></svg>网页编辑</a>';
 header.querySelector('.brand').href='image-editor.html';header.querySelector('.brand').after(nav);nav.querySelector('[data-mode='+(imageMode?'image':'web')+']').setAttribute('aria-current','page');
 for(const link of nav.querySelectorAll('a'))link.addEventListener('click',async e=>{if(e.ctrlKey||e.metaKey||e.shiftKey||e.button)return;e.preventDefault();if(link.hasAttribute('aria-current'))return;const studio=window.studio;if(studio?.isBusy()){document.querySelector('#status').textContent='当前操作尚未完成，请完成或取消后切换。';return}nav.setAttribute('aria-busy','true');try{await studio?.adapter.flush?.();await studio?.flush();location.href=link.href}catch(err){document.querySelector('#status').textContent='切换未完成：'+err.message;nav.removeAttribute('aria-busy')}});
 if(imageMode){
  const controls=document.createElement('div');controls.className='history-tools';for(const id of ['undo','reset-initial','redo'])controls.append(document.getElementById(id));const history=document.querySelector('[data-action=history]');if(history)controls.append(history);document.querySelector('.document-bar').append(controls);document.querySelector('.bar-hint')?.remove();
 }
 const args=new URLSearchParams(location.search);if(args.has('library')){args.delete('library');history.replaceState(null,'',location.pathname+(args.size?'?'+args:''));window.addEventListener('load',()=>window.studio?.run('projects'),{once:true})}
})();

/* Shared toolbar glyphs use consistent SVG strokes instead of font symbols. */
(()=>{
 const paths={select:'<path d="m5 3 14 10-7 1-3 7z"/>',hand:'<path d="M8 12V7a1.5 1.5 0 0 1 3 0v4-7a1.5 1.5 0 0 1 3 0v7-5a1.5 1.5 0 0 1 3 0v6-3a1.5 1.5 0 0 1 3 0v6c0 4-2.5 7-6 7h-1c-2 0-3.3-1-4.5-2.5L4 14a1.5 1.5 0 0 1 2.2-2L8 14"/>',undo:'<path d="m8 5-5 5 5 5M3 10h10a6 6 0 0 1 6 6v3"/>',redo:'<path d="m16 5 5 5-5 5m5-5H11a6 6 0 0 0-6 6v3"/>',reset:'<path d="M3 10a9 9 0 1 1 2 8M3 4v6h6"/>',history:'<path d="M3 11a9 9 0 1 1 2.5 7.5M3 5v6h6"/><path d="M12 7v5l3 2"/>'};
 const extraPaths={image:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="m3 17 5-5 4 4 3-3 6 6M12 2v6m-3-3h6"/>',text:'<path d="M5 5h14M12 5v14m-4 0h8M5 5v3m14-3v3"/>',rectangle:'<rect x="4" y="5" width="16" height="14" rx="2"/>',export:'<path d="M12 15V3m-4 4 4-4 4 4M4 14v6h16v-6"/>',sparkle:'<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5zM20 2v4m-2-2h4"/>'};Object.assign(paths,extraPaths);
 function decorateButton(button,key,label){button.classList.add('workspace-icon-button');button.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">'+paths[key]+'</svg><span>'+label+'</span>';}
 for(const [selector,key,label] of [['[data-tool="select"],#select-tool','select','选择'],['[data-tool="hand"],#hand-tool','hand','平移'],['#undo','undo','撤销'],['#redo','redo','重做'],['#reset-initial','reset','回到初始'],['[data-action="history"]','history','历史']]){
  for(const button of document.querySelectorAll(selector))decorateButton(button,key,label);
 }
 function remaining(){for(const [id,key,label] of [['upload','image','导入图片'],['add-text','text','文字'],['add-box','rectangle','矩形'],['tab-export','export','导出'],['assistant-toggle','sparkle','AI助手']]){const button=document.getElementById(id);if(button)decorateButton(button,key,label);}const heading=document.querySelector('#free-assistant h3');if(heading&&!heading.querySelector('svg'))heading.insertAdjacentHTML('afterbegin','<span class="assistant-heading-icon" aria-hidden="true"><svg viewBox="0 0 24 24">'+paths.sparkle+'</svg></span>');}
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',remaining,{once:true});else remaining();
})();
