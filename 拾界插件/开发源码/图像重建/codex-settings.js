/* Local account status only. No credentials are read by the page or saved in projects. */
(()=>{
 'use strict';
 const button=document.getElementById('codex-settings');if(!button)return;
 const panel=document.createElement('dialog');panel.className='codex-dialog';
 panel.innerHTML='<form method="dialog"><div class="codex-heading"><strong>连接自己的 Codex</strong><button aria-label="关闭">×</button></div></form><p>使用这台电脑登录的 Codex。分享给别人后，使用他们自己的账号和额度。</p><p id="codex-connection" role="status">点击检查连接。</p><label>分析模型<select id="codex-model" disabled></select></label><div class="codex-actions"><button id="codex-check">检查连接</button><button id="codex-login" class="primary">登录 Codex</button><a id="codex-login-link" hidden target="_blank" rel="noopener noreferrer">打开登录页 ↗</a></div><p class="tip">分享包已附带拾界运行环境，无需另装 Python 或 Node。请在自己的电脑安装并登录 Codex CLI，首次运行拾界目录中的“连接智能拆图.ps1”，然后检查连接。</p>';
 document.body.append(panel);const label=panel.querySelector('#codex-connection');
 async function check(){label.textContent='正在连接本机 Codex…';try{const s=await ShijieSmartSplit.account();if(!s.ok)throw Error(s.error);const models=panel.querySelector('#codex-model');models.replaceChildren();for(const m of s.models||[]){const o=document.createElement('option');o.value=m.id;o.textContent=m.name;o.selected=m.id===s.model;models.append(o)}models.disabled=!s.ready;label.textContent=s.ready?'已连接 · 当前电脑自己的 Codex':'尚未登录，请登录自己的 Codex。';button.textContent=s.ready?'Codex · 已连接':'连接 Codex';}catch(e){label.textContent=e.message;}}
 panel.querySelector('#codex-model').onchange=async e=>{try{await ShijieSmartSplit.setModel(e.target.value);label.textContent='已连接 · 分析模型已更新'}catch(err){label.textContent=err.message}};
 button.onclick=()=>{panel.showModal();check()};panel.querySelector('#codex-check').onclick=check;
 panel.querySelector('#codex-login').onclick=async()=>{label.textContent='正在准备登录…';try{const r=await ShijieSmartSplit.login();const u=new URL(r.url);if(u.protocol!=='https:'&&!(['localhost','127.0.0.1'].includes(u.hostname)&&u.protocol==='http:'))throw Error('登录地址无效');const a=panel.querySelector('#codex-login-link');a.href=u.href;a.hidden=false;label.textContent='点击“打开登录页”，完成登录后回来检查连接。';}catch(e){label.textContent=e.message}};
 // Remove only the retired integration's credential store; never touch Codex auth.
 try{indexedDB.deleteDatabase('shijie-yichuang-settings');localStorage.removeItem('shijie.yichuang.credentials.v1');globalThis.chrome?.storage?.local?.remove('shijie.yichuang.credentials.v1')}catch{}
})();
