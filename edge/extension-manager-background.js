/* Only opens the browser's own extension manager for this local workbench. */
const workbenchOrigins=new Set(['http://127.0.0.1:19217','http://localhost:19217']);
chrome.runtime.onMessage.addListener((message,sender,respond)=>{
 let origin;try{origin=new URL(sender.tab?.url||'').origin}catch{return false}
 if(!workbenchOrigins.has(origin)||sender.id!==chrome.runtime.id||!['shijie-manager-ping','shijie-manager-open'].includes(message?.type))return false;
 const url=/Edg\//.test(navigator.userAgent)?'edge://extensions/':'chrome://extensions/';
 if(message.type==='shijie-manager-ping'){respond({ok:true,url});return false}
 chrome.tabs.create({url,active:true}).then(tab=>respond({ok:true,url,tabId:tab.id})).catch(()=>respond({ok:false,error:'浏览器未能打开扩展管理页'}));return true;
});
