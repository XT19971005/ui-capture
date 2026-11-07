'use strict';
(()=>{
 const el=id=>document.getElementById(id);let state=null,busy=false;
 function controls(){if(el('pair'))el('pair').disabled=busy;el('refresh').disabled=busy;el('toggle').disabled=busy||!state||(!state.enabled&&!state.ready);el('toggle').textContent=state?.enabled?'关闭共享服务':'启用共享服务';}
 function show(value){state=value;el('state').textContent=(value.enabled?'共享已启用 · ':'共享未启用 · ')+(value.online?(value.ready?'本机 Codex 已连接':'本机在线，Codex 未就绪'):'本机离线');el('models').textContent=value.models?.length?'分析模型 '+value.models.length+' 个；'+(value.imageGeneration?'支持 Codex 内置生图':'当前未提供生图能力'):'';controls();}
 async function refresh(){if(busy)return;busy=true;controls();try{show(await ShijieService.request('desktop-service'));el('notice').textContent='状态已更新';}catch(e){el('notice').textContent=e.message;}finally{busy=false;controls();}}
 async function change(data){if(busy)return;busy=true;controls();try{const value=await ShijieService.request('desktop-service',{method:'POST',body:JSON.stringify(data)});show(value);if(value.token){el('token').value=value.token;el('pairing').hidden=false;el('notice').textContent='配对码已生成，请在本机配置入口使用';}else el('notice').textContent=value.enabled?'共享服务已启用，工作台刷新后可直接使用':'共享服务已关闭';}catch(e){el('notice').textContent=e.message;}finally{busy=false;controls();}}
 el('refresh').onclick=refresh;el('toggle').onclick=()=>change({action:'enable',enabled:!state.enabled});
 if(el('pair'))el('pair').onclick=()=>{if(state?.paired&&!confirm('重新生成配对码会断开旧接单程序，继续？'))return;void change({action:'pair'});};
 if(el('copy'))el('copy').onclick=async()=>{try{await navigator.clipboard.writeText(el('token').value);el('notice').textContent='配对码已复制';}catch{el('token').type='text';el('token').select();el('notice').textContent='请复制选中的配对码';}};
 if(el('reveal'))el('reveal').onclick=()=>{const shown=el('token').type==='password';el('token').type=shown?'text':'password';el('reveal').textContent=shown?'隐藏':'显示';};
 window.addEventListener('pagehide',()=>{if(el('token'))el('token').value='';});void refresh();
})();
