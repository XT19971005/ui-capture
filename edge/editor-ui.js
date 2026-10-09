/* Shared background controls and history shortcuts for both editors. */
window.ShijieEditorUI=(()=>{
 const valid=v=>/^#[0-9a-f]{6}$/i.test(v);
 function bindHistory({undo,redo,busy}){
  const dirty=new WeakSet();
  document.addEventListener('input',e=>{if(e.target.matches('input,textarea'))dirty.add(e.target)},true);
  document.addEventListener('change',e=>dirty.delete(e.target),true);
  document.addEventListener('focusout',e=>dirty.delete(e.target),true);
  document.addEventListener('keydown',e=>{
   if(document.querySelector('dialog[open]'))return;
   if(e.key==='Enter'&&!e.isComposing&&e.target.matches('input:not([type=checkbox]):not([type=color]):not([type=file])')&&dirty.has(e.target)&&!busy()){e.preventDefault();e.target.dispatchEvent(new Event('change',{bubbles:true}));return;}
   if(!(e.ctrlKey||e.metaKey)||e.altKey||e.isComposing)return;
   const key=e.key.toLowerCase();if(key!=='z'&&key!=='y')return;
   const target=e.target,typing=target.closest('[contenteditable=true],#inline-text')||((target.matches('textarea,input:not([type=checkbox]):not([type=color]):not([type=range])'))&&dirty.has(target));
   if(typing)return; e.preventDefault();e.stopImmediatePropagation();if(busy())return;
   (key==='y'||e.shiftKey?redo:undo)();
  },true);
 }
 function background(host,{get,set,busy,workspace}){
  host.innerHTML=`<section class="background-controls"><div class="background-heading">工作区背景</div><div class="background-color-row"><input type="color" id="workspace-color" aria-label="工作区底色"><input id="workspace-hex" aria-label="工作区底色色值" maxlength="7" spellcheck="false"></div><details><summary>画板底色 · 随设计导出</summary><div class="background-color-row"><input type="color" id="canvas-color" aria-label="画板背景颜色"><input id="canvas-hex" aria-label="画板背景色值" maxlength="7" spellcheck="false" placeholder="#FFFFFF"></div><label class="background-transparent"><input id="canvas-transparent" type="checkbox">透明画板</label></details></section>`;
  const $=id=>host.querySelector('#'+id);let last='#ffffff';
  function sync(){const state=get();if(state?.color)last=state.color;$('canvas-color').value=last;$('canvas-hex').value=state?.color||last;$('canvas-transparent').checked=!state?.color;for(const id of ['canvas-color','canvas-hex','canvas-transparent'])$(id).disabled=!state||busy();}
  function apply(value){if(!valid(value)){sync();return;}last=value.toLowerCase();set(last);}
  $('canvas-color').onchange=e=>apply(e.target.value);$('canvas-hex').onchange=e=>{let value=e.target.value.trim();if(!value.startsWith('#'))value='#'+value;if(/^#[0-9a-f]{3}$/i.test(value))value='#'+[...value.slice(1)].map(c=>c+c).join('');apply(value)};
  $('canvas-transparent').onchange=e=>set(e.target.checked?null:last);
  function work(value){if(!valid(value))return;workspace.style.backgroundColor=value;$('workspace-color').value=value;$('workspace-hex').value=value;try{localStorage.setItem('shijie-workspace-color',value)}catch{}}
  let stored;try{stored=localStorage.getItem('shijie-workspace-color')}catch{}work(valid(stored||'')?stored:'#34363c');
  $('workspace-color').onchange=e=>work(e.target.value);$('workspace-hex').onchange=e=>{let value=e.target.value.trim();if(!value.startsWith('#'))value='#'+value;if(valid(value))work(value);else $('workspace-hex').value=$('workspace-color').value};
  sync();return {sync};
 }
 return {bindHistory,background};
})();
