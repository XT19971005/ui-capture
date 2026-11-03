/* Shared workspace navigation. Working data is released when leaving this page. */
(()=>{
 const imageMode=location.pathname.endsWith('/image-editor.html'),header=document.querySelector('.app-header');if(!header)return;
 const nav=document.createElement('nav');nav.className='workspace-switch';nav.setAttribute('aria-label','工作模式');
 nav.innerHTML='<a href="export.html" data-mode="web"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="3"/><path d="M3 9h18m-13-3h1m3 0h1"/></svg>网页编辑</a><a href="image-editor.html" data-mode="image"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="3"/><path d="m3 16 5-5 4 4 3-3 6 6"/><circle cx="15" cy="8" r="1"/></svg>图片拆分</a>';
 header.querySelector('.brand').after(nav);nav.querySelector('[data-mode='+(imageMode?'image':'web')+']').setAttribute('aria-current','page');
 async function saveBeforeSwitch(studio){
  const doc=studio?.adapter.get();if(!doc||!StudioBase.library.isDirty(doc))return true;
  // ponytail: reuse the existing manual save; no second draft store or unload bypass.
  const dialog=document.createElement('dialog');dialog.className='studio-dialog';
  dialog.setAttribute('aria-labelledby','workspace-switch-title');dialog.setAttribute('aria-describedby','workspace-switch-note');
  dialog.innerHTML='<header><h2 id="workspace-switch-title">保存后切换工作模式？</h2></header><div class="studio-dialog-body"><p id="workspace-switch-note" role="status">当前工程有未保存修改。保存成功后再切换，稍后可从“打开工程”继续编辑。</p><footer><button id="workspace-switch-stay" autofocus>留在此页</button><button id="workspace-switch-save" class="primary">保存并切换</button></footer></div>';
  document.body.append(dialog);
  return new Promise(resolve=>{
   dialog.addEventListener('close',()=>{dialog.remove();resolve(false)});
   dialog.querySelector('#workspace-switch-stay').onclick=()=>dialog.close();
   const save=dialog.querySelector('#workspace-switch-save'),note=dialog.querySelector('#workspace-switch-note');
   save.onclick=async()=>{
    if(save.disabled)return;save.disabled=true;note.textContent='正在保存工程…';
    try{await studio.saveProject();if(studio.adapter.get()!==doc||StudioBase.library.isDirty(doc))throw Error('工程仍有未保存修改，请重试');resolve(true);dialog.close()}
    catch(err){note.textContent='保存未完成：'+err.message+'。当前工程仍在页面中，可重试保存。'}
    finally{save.disabled=false}
   };
   dialog.showModal();
  });
 }
 for(const link of nav.querySelectorAll('a'))link.addEventListener('click',async e=>{
  if(e.ctrlKey||e.metaKey||e.shiftKey||e.altKey||e.button)return;e.preventDefault();
  if(link.hasAttribute('aria-current')||nav.hasAttribute('aria-busy'))return;
  const studio=window.studio;if(studio?.isBusy()){document.querySelector('#status').textContent='当前操作尚未完成，请完成或取消后切换。';return}
  nav.setAttribute('aria-busy','true');
  try{await studio?.adapter.flush?.();await studio?.flush();if(await saveBeforeSwitch(studio))location.href=link.href}
  catch(err){document.querySelector('#status').textContent='切换未完成：'+err.message}
  finally{nav.removeAttribute('aria-busy')}
 });
 if(imageMode){
  const controls=document.createElement('div');controls.className='history-tools';for(const id of ['undo','reset-initial','redo'])controls.append(document.getElementById(id));const history=document.querySelector('[data-action=history]');if(history)controls.append(history);document.querySelector('.document-bar').append(controls);document.querySelector('.bar-hint')?.remove();
 }
 const args=new URLSearchParams(location.search);if(args.has('library')){args.delete('library');history.replaceState(null,'',location.pathname+(args.size?'?'+args:''));window.addEventListener('load',()=>window.studio?.run('projects'),{once:true})}
})();
