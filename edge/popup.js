const openPage=path=>chrome.tabs.create({url:chrome.runtime.getURL(path)});
document.getElementById('workbench').onclick=()=>openPage('export.html');
document.getElementById('capture').onclick=async()=>{const button=document.getElementById('capture'),status=document.getElementById('status'),progress=document.getElementById('progress');button.disabled=true;progress.hidden=false;progress.removeAttribute('value');status.textContent='正在打开抓取工作台…';try{const [tab]=await chrome.tabs.query({active:true,currentWindow:true});if(!tab||!/^(https?:|file:)/.test(tab.url||''))throw Error('请在普通网页或本地 HTML 上使用。');const params=new URLSearchParams({captureTab:tab.id,images:document.getElementById('images').checked?'1':'0',scope:document.getElementById('scope').value});const custom=params.get('scope')==='region';await chrome.tabs.create({url:chrome.runtime.getURL('export.html?'+params),active:!custom});if(custom){window.close();return;}progress.value=1;status.textContent='工作台已打开，那里会显示完整处理进度。'}catch(e){status.textContent='未能开始：'+e.message;progress.hidden=true}finally{button.disabled=false}};

const scopeSelect=document.getElementById('scope');
function updateCaptureScope(){const scope=scopeSelect.value;document.querySelector('#capture span').textContent=scope==='region'?'在网页上框选范围':scope==='viewport'?'抓取当前屏幕':'抓取整页';document.getElementById('status').textContent=scope==='region'?'在原网页框选，仅抓取范围内的图层。':scope==='viewport'?'只抓取当前可见的网页内容。':'抓取已加载内容，不含尚未加载的部分。'}
scopeSelect.value='viewport';scopeSelect.onchange=updateCaptureScope;updateCaptureScope();

for(const b of document.querySelectorAll('[data-scope]'))b.onclick=()=>{scopeSelect.value=b.dataset.scope;for(const x of document.querySelectorAll('[data-scope]'))x.setAttribute('aria-pressed',String(x===b));updateCaptureScope()};

document.getElementById('popup-library').onclick=()=>openPage('export.html?library=1');
