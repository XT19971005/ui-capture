const openPage=path=>chrome.tabs.create({url:chrome.runtime.getURL(path)});
document.getElementById('workbench').onclick=()=>openPage(popupMode==='image'?'image-editor.html':'export.html');
let imageOrigins=[],permissionScan=null,permissionScanTab=null;
async function inspectImagePermissions(){
 const [tab]=await chrome.tabs.query({active:true,currentWindow:true});permissionScanTab=tab?.id;
 if(!tab||!/^https?:/.test(tab.url||'')){imageOrigins=[];return}
 const values=await chrome.scripting.executeScript({target:{tabId:tab.id},func:()=>{const origins=new Set();const add=value=>{try{const u=new URL(value,location.href);if(/^https?:$/.test(u.protocol)&&u.origin!==location.origin)origins.add(u.origin+'/*')}catch{}};for(const image of document.images)add(image.currentSrc||image.src);for(const el of [...document.querySelectorAll('*')].slice(0,6000)){for(const match of getComputedStyle(el).backgroundImage.matchAll(/url\(["']?([^"')]+)["']?\)/g))add(match[1])}return [...origins].slice(0,32)}});
 const needed=[];for(const origin of values[0]?.result||[])if(!await chrome.permissions.contains({origins:[origin]}))needed.push(origin);imageOrigins=needed;updateCaptureScope();
}
document.getElementById('capture').onclick=async()=>{
 const button=document.getElementById('capture'),status=document.getElementById('status'),progress=document.getElementById('progress'),images=document.getElementById('images').checked;
 // Request from this click before any asynchronous work, preserving the browser's user gesture.
 const permission=images&&imageOrigins.length?chrome.permissions.request({origins:imageOrigins.slice()}):Promise.resolve(true);
 button.disabled=true;progress.hidden=false;progress.removeAttribute('value');status.textContent='正在打开抓取工作台…';
 try{
  if(!await permission)throw Error('未允许读取网页图片。可重试并允许图片域名，或关闭「包含网页图片」。');
  if(images&&permissionScan)await permissionScan;
  const [tab]=await chrome.tabs.query({active:true,currentWindow:true});if(!tab||!/^(https?:|file:)/.test(tab.url||''))throw Error('请在需要抓取的普通网页上点击插件。');
  if(images&&tab.id!==permissionScanTab){await inspectImagePermissions();if(imageOrigins.length)throw Error('已更新图片来源，请再次点击抓取并允许图片读取。')}
  if(images){const missing=[];for(const origin of imageOrigins)if(!await chrome.permissions.contains({origins:[origin]}))missing.push(origin);imageOrigins=missing;if(missing.length)throw Error('图片来源已准备好，请再次点击抓取并允许图片读取。')}
  if(tab.url.startsWith('file:')&&!await chrome.extension.isAllowedFileSchemeAccess())throw Error('请在扩展详情中开启「允许访问文件 URL」，再抓取本地 HTML。');
  const scope=document.getElementById('scope').value,params=new URLSearchParams({captureTab:String(tab.id),images:images?'1':'0',scope});
  await chrome.tabs.create({url:chrome.runtime.getURL('export.html?'+params),active:false});
  if(scope==='region'){window.close();return}progress.value=1;status.textContent='正在抓取，完成后自动打开工作台';
 }catch(e){status.textContent='未能开始：'+e.message;progress.hidden=true}finally{button.disabled=false}
};
const scopeSelect=document.getElementById('scope');
function updateCaptureScope(){const scope=scopeSelect.value;document.querySelector('#capture span').textContent=(imageOrigins.length&&document.getElementById('images').checked?'允许图片读取并':'')+(scope==='region'?'框选抓取':scope==='viewport'?'抓取当前屏幕':'抓取整页');document.getElementById('status').textContent=scope==='page'?'仅抓取已加载内容':''}
scopeSelect.value='viewport';scopeSelect.onchange=updateCaptureScope;updateCaptureScope();

for(const b of document.querySelectorAll('[data-scope]'))b.onclick=()=>{scopeSelect.value=b.dataset.scope;for(const x of document.querySelectorAll('[data-scope]'))x.setAttribute('aria-pressed',String(x===b));updateCaptureScope()};


document.getElementById('image-workbench').onclick=()=>openPage('image-editor.html?import=1');

let popupMode='image';
function choosePopupMode(mode,focus=false){popupMode=mode;for(const button of document.querySelectorAll('[data-popup-mode]')){const selected=button.dataset.popupMode===mode;button.setAttribute('aria-selected',selected);button.tabIndex=selected?0:-1;if(selected&&focus)button.focus()}document.getElementById('popup-web').hidden=mode!=='web';document.getElementById('popup-image').hidden=mode!=='image';if(mode==='web')updateCaptureScope();else document.getElementById('status').textContent=''}
for(const button of document.querySelectorAll('[data-popup-mode]')){button.onclick=()=>choosePopupMode(button.dataset.popupMode);button.onkeydown=e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();choosePopupMode(e.key==='Home'?'image':e.key==='End'?'web':popupMode==='web'?'image':'web',true)}}}
document.getElementById('popup-library').onclick=()=>openPage((popupMode==='image'?'image-editor.html':'export.html')+'?library=1');

choosePopupMode('image');

if(globalThis.chrome?.tabs)chrome.tabs.query({active:true,currentWindow:true}).then(([tab])=>{const label=document.getElementById('current-page-title');label.textContent=tab&&/^(https?:|file:)/.test(tab.url||'')?(tab.title||tab.url):'请先打开需要抓取的普通网页';label.title=tab?.url||''}).catch(()=>{});

if(globalThis.chrome?.tabs)permissionScan=inspectImagePermissions().catch(()=>{});
document.getElementById('images').addEventListener('change',updateCaptureScope);
