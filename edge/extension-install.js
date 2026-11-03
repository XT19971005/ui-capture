/* Installation preparation, with browser-owned final confirmation. */
(()=>{'use strict';
 const form=document.getElementById('url-capture-form');if(!form)return;
 const browserGuides={
  edge:{name:'Edge',address:'edge://extensions/',load:'加载解压缩的扩展'},
  chrome:{name:'Chrome',address:'chrome://extensions/',load:'加载已解压的扩展程序'},
  brave:{name:'Brave',address:'brave://extensions/',load:'加载已解压的扩展程序（Load unpacked）'},
  opera:{name:'Opera / GX',address:'opera:extensions',load:'加载解压缩的扩展（Load unpacked）'},
  vivaldi:{name:'Vivaldi',address:'vivaldi://extensions/',load:'加载已解压的扩展程序（Load unpacked）'},
  chromium:{name:'Chromium',address:'chrome://extensions/',load:'加载已解压的扩展程序（Load unpacked）'},
  qq:{name:'QQ 浏览器',address:'qqbrowser://extensions/manage',load:'加载已解压的扩展程序'},
  browser360:{name:'360 浏览器',address:'chrome://extensions/',load:'加载解压缩的扩展'}
 };
 function detectedBrowser(){const ua=navigator.userAgent;return /Edg\//.test(ua)?'edge':/QQBrowser\//.test(ua)?'qq':/360SE|360EE/.test(ua)?'browser360':/OPR\//.test(ua)?'opera':/Vivaldi\//.test(ua)?'vivaldi':/Chromium\//.test(ua)?'chromium':'chrome'}

 if(globalThis.chrome?.runtime?.id){const manage=document.createElement('button');manage.type='button';manage.id='install-browser-extension';manage.textContent='插件管理';manage.onclick=()=>chrome.tabs.create({url:(/Edg\//.test(navigator.userAgent)?'edge':'chrome')+'://extensions/?id='+chrome.runtime.id});form.after(manage);return;}
 const button=document.createElement('button');button.type='button';button.id='install-browser-extension';button.textContent='安装浏览器插件';button.title='查看常见浏览器的插件安装步骤';form.after(button);
 const panel=document.createElement('dialog');panel.className='codex-dialog extension-install-panel';panel.setAttribute('aria-label','安装浏览器插件');panel.innerHTML='<form method="dialog"><strong>安装浏览器插件</strong><button aria-label="关闭安装引导">×</button></form><p class="install-intro">首次安装按下面三步操作。</p><label class="install-browser-label">安装浏览器<select data-browser-select aria-label="选择安装浏览器"></select></label><p class="install-browser-note" data-browser-note></p><div class="install-steps"><section><span>1</span><div><strong data-step-one>复制并打开管理页</strong><p data-step-one-note>复制下方地址，粘贴到浏览器地址栏，按回车打开。</p><input data-manager-address readonly aria-label="扩展管理页地址"><button type="button" data-manager>复制管理页地址</button></div></section><section><span>2</span><div><strong>开启开发者模式</strong><p data-step-two-note>在管理页开启「开发者模式」，再点「加载解压缩的扩展」。</p></div></section><section><span>3</span><div><strong>加载插件文件夹</strong><p data-step-three-note>复制插件路径，在文件夹选择窗口粘贴并确认。</p><div class="install-directory" data-directory-area><button type="button" data-copy>复制插件路径</button><textarea data-directory readonly rows="3" aria-label="插件目录" hidden></textarea></div><button type="button" data-prepare>打开插件文件夹</button></div></section></div><p data-feedback role="status" hidden></p><div class="install-alternative"><button type="button" data-download>下载插件包</button></div><p class="install-footnote">安装完成后，刷新助手网页，再到目标网页点击插件抓取。Firefox、Safari 不能直接使用这份 Chromium 插件包。</p>';
 document.body.append(panel);const q=s=>panel.querySelector(s),local=['localhost','127.0.0.1'].includes(location.hostname);let directory='',browser=detectedBrowser();
 const browserSelect=q('[data-browser-select]');browserSelect.replaceChildren(...Object.entries(browserGuides).map(([value,guide])=>new Option(guide.name,value))); 
 function feedback(text,error=false){const el=q('[data-feedback]');el.hidden=!text;el.textContent=text;el.classList.toggle('install-error',error)}
 function browserUI(){browserSelect.value=browser;const guide=browserGuides[browser];q('[data-manager-address]').value=guide.address;q('[data-browser-note]').textContent=['edge','chrome'].includes(browser)?'请选择实际安装插件的浏览器。':'这是 '+guide.name+' 的安装指引；本机尚未验证该浏览器的完整插件兼容性。';q('[data-step-two-note]').textContent='开启「开发者模式」，再点「'+guide.load+'」。';q('[data-prepare]').textContent=local?'打开插件文件夹':'下载插件包';q('[data-directory-area]').hidden=!local;q('[data-download]').hidden=!local;q('[data-step-three-note]').textContent=local?'复制插件路径，在文件夹选择窗口粘贴并确认。':'下载并解压插件包，再选择「AI拆图助手插件」文件夹。';}
 browserSelect.onchange=()=>{browser=browserSelect.value;feedback('');browserUI()};browserUI();if(navigator.brave?.isBrave)navigator.brave.isBrave().then(value=>{if(value&&browser==='chrome'){browser='brave';browserUI()}}).catch(()=>{});
 async function request(path,body){const connection=await fetch('/connection',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('无法连接安装服务');return r.json()});const response=await fetch(path,{method:body?'POST':'GET',headers:{'X-Shijie-Token':connection.token,...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});if(!response.ok){const error=await response.json().catch(()=>({}));throw Error(error.error||'安装准备失败')}return response}
 async function copy(value){if(!value)return false;try{await navigator.clipboard.writeText(value);return true}catch{return false}}
 async function download(){const response=await request('/extension/download'),blob=await response.blob(),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='AI拆图助手_浏览器插件.zip';a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);feedback('下载已发起，解压后在浏览器中加载。')}
 async function readDirectory(){const info=await request('/extension/install-info').then(r=>r.json());directory=info.directory;q('[data-directory]').value=directory;q('[data-directory-area]').title=directory;}
 button.onclick=async()=>{window.ShijieInlinePanels.open(panel);feedback('');q('[data-directory-area]').hidden=!local;browserUI();if(local)try{await readDirectory();browserUI()}catch(e){feedback(e.message,true)}};
 q('[data-prepare]').onclick=async e=>{const target=e.currentTarget;target.disabled=true;try{if(!local){await download();return}await request('/extension/setup',{browser});feedback('插件文件夹已打开。点击「复制插件路径」，在浏览器的文件夹选择窗口粘贴并确认。')}catch(error){feedback(error.message,true)}finally{target.disabled=false}};
 q('[data-copy]').onclick=async()=>{try{if(!directory)await readDirectory();const copied=await copy(directory);q('[data-directory]').hidden=copied;feedback(copied?'插件路径已复制。':'请选中下方路径手动复制。',!copied)}catch(error){feedback(error.message,true)}};
 q('[data-manager]').onclick=async()=>{const guide=browserGuides[browser];feedback(await copy(guide.address)?guide.name+' 管理页地址已复制，粘贴到该浏览器地址栏打开。':'请在 '+guide.name+' 地址栏输入 '+guide.address)};
 q('[data-download]').onclick=()=>download().catch(e=>feedback(e.message,true));
})();
