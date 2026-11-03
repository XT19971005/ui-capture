/* Narrow page bridge; it cannot navigate to arbitrary URLs or read tab data. */
(()=>{'use strict';if(!['http://127.0.0.1:19217','http://localhost:19217'].includes(location.origin))return;
 window.addEventListener('message',event=>{
  const data=event.data;if(event.source!==window||event.origin!==location.origin||data?.source!=='shijie-manager-page'||typeof data.id!=='string'||data.id.length>100||!['ping','open'].includes(data.action))return;
  chrome.runtime.sendMessage({type:data.action==='open'?'shijie-manager-open':'shijie-manager-ping'}).then(result=>window.postMessage({source:'shijie-manager-extension',id:data.id,result},location.origin)).catch(()=>window.postMessage({source:'shijie-manager-extension',id:data.id,result:{ok:false,error:'插件连接已过期，请刷新工作台'}},location.origin));
 });
})();
