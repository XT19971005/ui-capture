'use strict';
if(window.SHIJIE?.sharedCodex){
 const useSharedEngine=()=>{const engine=document.getElementById('split-engine');if(!engine)return;engine.replaceChildren(new Option('Codex 共享服务','codex'));engine.value='codex';engine.hidden=true;engine.style.display='none';engine.setAttribute('aria-hidden','true')};
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',useSharedEngine,{once:true});else useSharedEngine();
}
window.ShijieSharedCodexSettings=button=>{
 const panel=document.createElement('dialog');panel.className='codex-dialog shared-ai-settings';panel.setAttribute('aria-label','共享模型');
 panel.innerHTML='<form method="dialog"><strong>共享模型</strong><button aria-label="关闭共享模型">×</button></form><section><h3>本机 Codex 共享服务</h3><p>由管理员的电脑统一处理任务，无需登录 Codex 或填写 Key。</p><p data-status role="status"></p><label>分析模型<select data-model></select></label><p data-images></p></section><footer><button type="button" data-refresh>检查服务</button><button type="button" data-apply class="primary">应用模型</button><span data-result role="status"></span></footer>';
 document.body.append(panel);const q=s=>panel.querySelector(s),model=q('[data-model]');let revision=0,busy=false;
 async function refresh(){const rev=++revision;q('[data-status]').textContent='正在检查共享电脑…';q('[data-apply]').disabled=true;try{const state=await ShijieService.request('engine/codex/status');if(rev!==revision)return;model.replaceChildren(...state.models.map(m=>new Option(m.name||m.id,m.id)));let preferred;try{preferred=JSON.parse(localStorage.getItem('shijie.assistant.text-model:'+SHIJIE.user)||'null')?.model}catch{}model.value=state.models.some(m=>m.id===preferred)?preferred:state.model;q('[data-status]').textContent=state.ready?'共享电脑在线 · Codex 已连接':'共享电脑离线或 Codex 未连接，请联系管理员';q('[data-images]').textContent=state.imageGeneration?'图片生成与补全：共享 Codex 内置生图':'共享 Codex 暂未提供生图能力';q('[data-apply]').disabled=!state.ready||!model.value;}catch(e){if(rev===revision)q('[data-status]').textContent='共享服务检查失败：'+e.message;}}
 button.onclick=()=>{if(window.studio?.isBusy()||window.ShijieFreeAssistant?.isBusy?.())return;q('[data-result]').textContent='';window.ShijieInlinePanels.open(panel);void refresh();};
 q('[data-refresh]').onclick=()=>{if(!busy)void refresh();};
 q('[data-apply]').onclick=async()=>{if(busy||!model.value)return;busy=true;q('[data-apply]').disabled=true;q('[data-refresh]').disabled=true;try{await ShijieService.request('engine/codex/model',{method:'POST',body:JSON.stringify({model:model.value})});const pref={provider:'codex',model:model.value};localStorage.setItem('shijie.assistant.text-model:'+SHIJIE.user,JSON.stringify(pref));window.dispatchEvent(new CustomEvent('shijie-ai-settings-changed',{detail:pref}));q('[data-result]').textContent='已应用，之后的任务使用此模型';}catch(e){q('[data-result]').textContent=e.message;}finally{busy=false;q('[data-apply]').disabled=false;q('[data-refresh]').disabled=false;}};
 panel.addEventListener('close',()=>{++revision;});
 const old=document.getElementById('codex-settings');if(old)old.onclick=()=>button.click();
};
