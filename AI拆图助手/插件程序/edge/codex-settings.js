/* All local connection entry points share the same settings and login state. */
(()=>{
 'use strict';
 const button=document.getElementById('codex-settings');if(!button)return;
 button.onclick=()=>{
  const settings=document.getElementById('assistant-model-settings');
  if(settings?.onclick)return settings.onclick();
  button.textContent='AI 设置尚未加载，请刷新页面';
 };
})();
