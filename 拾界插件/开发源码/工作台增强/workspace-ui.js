/* Shared workspace navigation. Working data is released when leaving this page. */
(()=>{
 const imageMode=location.pathname.endsWith('/image-editor.html'),header=document.querySelector('.app-header');if(!header)return;
 const nav=document.createElement('nav');nav.className='workspace-switch';nav.setAttribute('aria-label','工作模式');
 nav.innerHTML='<a href="export.html" data-mode="web"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="3"/><path d="M3 9h18m-13-3h1m3 0h1"/></svg>网页编辑</a><a href="image-editor.html" data-mode="image"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="3"/><path d="m3 16 5-5 4 4 3-3 6 6"/><circle cx="15" cy="8" r="1"/></svg>图片拆分</a>';
 header.querySelector('.brand').after(nav);nav.querySelector('[data-mode='+(imageMode?'image':'web')+']').setAttribute('aria-current','page');
 for(const link of nav.querySelectorAll('a'))link.addEventListener('click',async e=>{if(e.ctrlKey||e.metaKey||e.shiftKey||e.button)return;e.preventDefault();if(link.hasAttribute('aria-current'))return;const studio=window.studio;if(studio?.isBusy()){document.querySelector('#status').textContent='当前操作尚未完成，请完成或取消后切换。';return}nav.setAttribute('aria-busy','true');try{await studio?.adapter.flush?.();await studio?.flush();location.href=link.href}catch(err){document.querySelector('#status').textContent='保存未完成，请先保存工程再切换。';nav.removeAttribute('aria-busy')}});
 if(imageMode){
  const controls=document.createElement('div');controls.className='history-tools';for(const id of ['undo','reset-initial','redo'])controls.append(document.getElementById(id));const history=document.querySelector('[data-action=history]');if(history)controls.append(history);document.querySelector('.document-bar').append(controls);document.querySelector('.bar-hint')?.remove();
 }
 const args=new URLSearchParams(location.search);if(args.has('library')){args.delete('library');history.replaceState(null,'',location.pathname+(args.size?'?'+args:''));window.addEventListener('load',()=>window.studio?.run('projects'),{once:true})}
})();
