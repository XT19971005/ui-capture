/* Per-user AI connection. Secrets never enter project data or browser storage. */
(() => {
  'use strict';
  const button = document.getElementById('codex-settings');
  if (!button) return;
  button.textContent = 'AI 连接';
  button.title = '配置 Codex、公司 Agent，或检查本机分层模型';
  const panel = document.createElement('dialog');
  panel.className = 'codex-dialog';
  panel.setAttribute('aria-labelledby', 'codex-title');
  panel.innerHTML = `
    <div class="codex-heading"><div><span class="codex-eyebrow">AI拆图助手 · AI 设置</span><h2 id="codex-title">AI 连接</h2></div><button id="codex-close" aria-label="关闭 AI 设置">×</button></div>
    <p class="codex-intro">自动模式优先 Codex，其次公司 Agent。本机分层可单独选择，无需云端登录。</p>
    <div class="ai-routing" role="status" aria-live="polite"><strong id="ai-active">正在读取连接</strong><p id="ai-capabilities">连接仅属于当前AI拆图助手账号，不会写入工程。</p></div>
    <div class="codex-methods ai-providers" role="group" aria-label="选择 AI 服务配置">
      <button id="ai-provider-company" aria-pressed="true"><strong>公司 Agent</strong><span>公司 API Key · 无需 ChatGPT 登录</span></button>
      <button id="ai-provider-codex" aria-pressed="false"><strong>Codex / OpenAI</strong><span>API Key 或账号登录 · 优先使用</span></button>
      <button id="ai-provider-local" aria-pressed="false"><strong>本机模型</strong><span>透明分层 · 试用</span></button>
    </div>
    <section id="ai-local-panel" aria-label="本机分层模型" hidden>
      <h3>Qwen-Image-Layered</h3>
      <p>图片由运行AI拆图助手服务的 Mac 处理，无需公司 Agent Key 或 Codex 登录。首次加载需要一些时间，一次只处理一张图片。</p>
      <p>试用设置：640 分辨率档位、3 个图层（含背景）、20 步。文字仍为图片，边缘、细节和遮挡补全需要校对。原图会保留在工程中。</p>
      <div class="codex-status" role="status" aria-live="polite"><strong id="local-status-title">尚未检查</strong><p id="local-status">请先在运行AI拆图助手的 Mac 上启动本机模型服务。</p></div>
      <div class="codex-inline-actions"><button id="local-check">检查本机服务</button><button id="local-use" class="primary" disabled>选择本机分层</button></div>
      <p>选择后回到页面，点击“开始拆分”。生图、精修等其他功能仍使用已配置的云端服务。</p>
      <details><summary>服务未启动时如何处理？</summary><p>在 Mac 的 shijie 项目目录运行 <code>./shijiectl model-start</code>；首次使用先运行 <code>./shijiectl model-download</code> 下载模型。</p></details>
    </section>
    <section id="ai-company-panel" aria-label="公司 Agent 配置">
      <label for="company-model">模型 ID</label><input id="company-model" autocomplete="off" spellcheck="false" maxlength="120" placeholder="填写公司平台可用模型，例如 grok-4.6">
      <label for="company-key">公司 Agent API Key</label><input id="company-key" type="password" autocomplete="off" spellcheck="false" maxlength="4096" placeholder="粘贴公司 API Key" aria-describedby="company-help">
      <p id="company-help">使用与 TYComfyUI 相同的公司接口。Key 加密保存；更新配置时留空即可保留已存 Key。</p>
      <label class="ai-enable"><input id="company-enabled" type="checkbox" checked>启用公司 Agent 连接</label>
      <div class="codex-inline-actions"><button id="company-save" class="primary">保存连接</button><button id="company-test" disabled>测试图片分析</button></div>
      <p>测试会发送一张测试色块，按公司接口计费。不会发送当前工程；此测试只验证分析，生图结果会在实际任务中检查。</p>
      <details class="ai-endpoint"><summary>接口地址</summary><p>https://zxty.tuyoo.com/aichat/v1/agent/chat</p></details>
      <div class="codex-status" role="status" aria-live="polite"><strong id="company-status-title">尚未配置</strong><p id="company-status">填写模型和 Key 后保存，再测试图片分析。</p></div>
    </section>
    <section id="ai-codex-panel" aria-label="Codex 配置" hidden>
    <div class="codex-methods ai-providers" role="group" aria-label="选择连接方式">
      <button id="codex-method-api" aria-pressed="true"><strong>OpenAI API Key</strong><span>平台密钥 · 按 API 用量计费</span></button>
      <button id="codex-method-token" aria-pressed="false"><strong>团队访问令牌</strong><span>ChatGPT 工作区签发</span></button>
      <button id="codex-method-device" aria-pressed="false"><strong>设备码登录</strong><span>使用 ChatGPT / Codex 套餐额度</span></button>
    </div>
    <section id="codex-api-panel" aria-label="OpenAI API Key">
      <label for="codex-api-key">OpenAI 平台 API Key</label><input id="codex-api-key" type="password" autocomplete="off" spellcheck="false" maxlength="8192" placeholder="粘贴 OpenAI 平台的 API Key" aria-describedby="codex-api-help">
      <p id="codex-api-help">API Key 独立计费，不使用 ChatGPT / Codex 套餐额度。已有套餐请选择“设备码登录”。连接时仅验证模型列表访问权限；实际模型权限、API 额度和透明素材结果在任务中检查。</p>
      <p>Key 仅保存在当前AI拆图助手账号的服务器私有凭据目录，不写入工程、日志或浏览器存储。连接成功后会优先使用 Codex；公司 Agent 配置仍保留。</p>
      <div class="codex-inline-actions"><button id="codex-api-connect" class="primary">验证 API Key 并连接</button><a href="https://platform.openai.com/api-keys" target="_blank" rel="noopener noreferrer">打开 OpenAI API Keys ↗</a></div>
    </section>
    <section id="codex-token-panel" aria-label="团队访问令牌" hidden>
      <ol class="codex-steps">
        <li><div><strong>在团队工作区创建令牌</strong><p>选择你所属的工作区，创建具有 Codex 权限的访问令牌。</p><a href="https://chatgpt.com/admin/access-tokens" target="_blank" rel="noopener noreferrer">打开 ChatGPT 访问令牌管理 ↗</a></div></li>
        <li><div><label for="codex-token">ChatGPT 工作区的 Codex 访问令牌</label><input id="codex-token" type="password" autocomplete="off" spellcheck="false" maxlength="8192" placeholder="粘贴 ChatGPT 工作区签发的访问令牌" aria-describedby="codex-token-help"><p id="codex-token-help">此入口仅接收 ChatGPT 工作区签发的 Codex 访问令牌。平台密钥请切换到“OpenAI API Key”；公司 Key 请填写在“公司 Agent”。令牌按AI拆图助手账号独立保存，提交后输入框清空，不写入工程。</p><button id="codex-token-connect" class="primary">验证并连接</button></div></li>
      </ol>
      <details class="codex-help"><summary>团队账号没有“访问令牌”入口？</summary><p>请工作区管理员开放“允许使用 Codex 访问令牌”和“允许本地使用 Codex”。如果这两项不可用，可切换到设备码登录，但设备码权限也由工作区管理员控制。</p><a href="https://learn.chatgpt.com/docs/enterprise/access-tokens" target="_blank" rel="noopener noreferrer">查看官方权限说明 ↗</a></details>
    </section>
    <section id="codex-device-panel" aria-label="设备码登录" hidden>
      <ol class="codex-steps">
        <li><div><strong>获取本次登录的设备码</strong><p>团队账号需先由工作区管理员开启设备码登录权限。</p><div class="codex-code-row"><input id="codex-device-code" readonly value="" placeholder="尚未获取" aria-label="设备码"><button id="codex-copy" disabled>复制设备码</button></div><p id="codex-expiry">设备码会一直显示在这里，检查连接不会清除它。</p><div class="codex-inline-actions"><button id="codex-login" class="primary">获取设备码</button><button id="codex-cancel-login" hidden>取消本次登录</button></div></div></li>
        <li><div><strong>在官方页面输入设备码</strong><p>登录 ChatGPT 后，选择你的团队工作区并完成授权。</p><a id="codex-login-link" class="codex-link-button" hidden target="_blank" rel="noopener noreferrer">打开登录页 ↗</a><span id="codex-link-hint">先获取设备码，登录链接会显示在这里。</span></div></li>
        <li><div><strong>回来确认连接</strong><p>等待授权时会自动检查。也可以点击下方“检查连接”。</p></div></li>
      </ol>
    </section>
    <div class="codex-status" role="status" aria-live="polite"><strong id="codex-status-title">尚未连接</strong><p id="codex-connection">选择上方一种方式开始。</p></div>
    <div id="codex-connected" hidden><label for="codex-model">分析模型</label><select id="codex-model" disabled></select></div>
    <div class="codex-footer"><button id="codex-check">检查连接</button><button id="codex-logout" hidden>断开此账号</button><span>连接仅属于当前AI拆图助手账号</span></div></section>`;
  document.body.append(panel);
  const $ = id => panel.querySelector('#' + id);
  let pending = null, timer = null, polling = false, busy = false, checking = false;
  let selectedPanel = null, companyDirty = false, companyState = {}, codexState = {}, activeProvider = 'codex';
  const request = (route, value) => ShijieService.request('engine/codex/' + route,
    value === undefined ? {} : {method: 'POST', body: JSON.stringify(value)});
  function note(title, message) { $('codex-status-title').textContent = title; $('codex-connection').textContent = message; }
  const companyRequest = (route, value) => ShijieService.request('engine/company/' + route, {method:'POST', body:JSON.stringify(value)});
  function provider(name) {
    selectedPanel = name;
    $('ai-company-panel').hidden = name !== 'company'; $('ai-codex-panel').hidden = name !== 'codex';
    $('ai-local-panel').hidden = name !== 'local';
    $('ai-provider-company').setAttribute('aria-pressed', String(name === 'company'));
    $('ai-provider-codex').setAttribute('aria-pressed', String(name === 'codex'));
    $('ai-provider-local').setAttribute('aria-pressed', String(name === 'local'));
  }
  async function checkLocal() {
    $('local-check').disabled = true; $('local-use').disabled = true;
    $('local-status-title').textContent = '正在检查';
    try {
      const state = await ShijieService.request('engine/local-model/status');
      $('local-status-title').textContent = state.ready ? state.busy ? '本机正在处理任务' : '本机模型已就绪' : '本机模型尚未就绪';
      $('local-status').textContent = state.ready ? '可以选择本机分层；新任务会按顺序处理。' : (state.message || '本机服务尚未就绪') + '。请等待模型下载完成，并确认本机模型服务正在运行；当前工程不受影响。';
      $('local-use').disabled = !state.ready || !document.getElementById('split-engine');
    } catch (error) { $('local-status-title').textContent = '检查未完成'; $('local-status').textContent = error.message; }
    finally { $('local-check').disabled = false; }
  }
  function companyNote(title, message) { $('company-status-title').textContent = title; $('company-status').textContent = message; }
  function routing() {
    const selected = activeProvider === 'company' ? companyState.enabled : codexState.configured || codexState.ready;
    button.textContent = selected ? 'AI · ' + (activeProvider === 'company' ? '公司 Agent' : 'Codex') : 'AI 连接';
    $('ai-active').textContent = selected ? '自动模式使用：' + (activeProvider === 'company' ? '公司 Agent' : 'Codex') : '尚未配置云端 AI 服务';
    $('ai-capabilities').textContent = !selected ? '选择下方服务完成配置。两边都配置时优先 Codex。' : activeProvider === 'company'
      ? (companyState.verified ? '图片分析已通过测试。' : '图片分析待测试。') + '分析与生图均使用公司 Agent。透明输出由公司图像工具决定，未通过检查时会保留工程并提示。'
      : codexState.ready && codexState.imageGeneration ? codexState.provider === 'apiKey' ? '通过 OpenAI API Key 使用 Codex，按 API 用量计费；模型权限与生图结果在实际任务中检查。' : '分析与生图均使用 Codex，可以开始拆分。' : '已优先选择 Codex，连接或生图权限尚未就绪；不会自动改用公司 Agent。';
  }
  function displayCompany(state) {
    companyState = state;
    if (!companyDirty) { $('company-model').value = state.model || ''; $('company-enabled').checked = state.configured ? state.enabled : true; }
    $('company-key').placeholder = state.configured ? '已保存 Key，留空保留' : '粘贴公司 API Key';
    $('company-test').disabled = !state.configured || companyDirty;
    companyNote(state.verified ? '图片分析测试通过' : state.configured ? '已保存 · 待测试' : '尚未配置',
      state.configured ? (state.enabled ? '连接已启用。' : '连接已停用，已保存的 Key 保留。') + '已接入图片生成，拆分时会检查图片和真实透明通道。' : '填写模型和 Key 后保存，再测试图片分析。');
  }
  function method(name) {
    $('codex-api-panel').hidden = name !== 'api';
    $('codex-token-panel').hidden = name !== 'token'; $('codex-device-panel').hidden = name !== 'device';
    $('codex-method-api').setAttribute('aria-pressed', String(name === 'api'));
    $('codex-method-token').setAttribute('aria-pressed', String(name === 'token'));
    $('codex-method-device').setAttribute('aria-pressed', String(name === 'device'));
  }
  function showCode(value) {
    if (value) {
      const url = new URL(value.url);
      if (url.href !== 'https://auth.openai.com/codex/device' || !/^[A-Z0-9-]{4,32}$/.test(value.userCode) || !Number.isFinite(value.expiresAt)) throw Error('登录服务返回的信息无效，请重新获取');
    }
    if (value?.userCode !== pending?.userCode) $('codex-copy').textContent = '复制设备码';
    pending = value;
    $('codex-device-code').value = value?.userCode || '';
    $('codex-copy').disabled = !value;
    $('codex-login-link').hidden = !value;
    $('codex-link-hint').hidden = Boolean(value);
    $('codex-cancel-login').hidden = !value;
    $('codex-login').textContent = value ? '重新获取设备码' : '获取设备码';
    if (value) $('codex-login-link').href = value.url;
    $('codex-expiry').textContent = value ? '等待你在官方页面完成授权。' : '设备码会一直显示在这里，检查连接不会清除它。';
    clearTimeout(timer);
    if (value && panel.open) timer = setTimeout(poll, 3000);
  }
  async function poll() {
    if (!panel.open || !pending || polling || busy) return;
    if (pending.expiresAt <= Date.now()/1000) { showCode(null); note('本次登录已过期', '点击“获取设备码”开始新的登录；原图和已有连接均保留。'); return; }
    polling = true;
    try {
      const r = await request('login');
      if (r.pending) showCode(r.pending);
      else { showCode(null); await check(); }
    } catch { $('codex-expiry').textContent = '暂时无法自动检查，设备码仍保留；可以手动检查连接。'; }
    finally { polling = false; if (panel.open && pending) { clearTimeout(timer); timer = setTimeout(poll, 3000); } }
  }
  function display(state) {
    if (!state.ok) throw Error(state.error || '暂时无法检查连接，请重试');
    const models = $('codex-model'); models.replaceChildren();
    for (const model of state.models || []) { const option = document.createElement('option'); option.value = model.id; option.textContent = model.name; option.selected = model.id === state.model; models.append(option); }
    models.disabled = !state.ready;
    $('codex-connected').hidden = !state.ready; $('codex-logout').hidden = !state.configured && !state.ready;
    codexState = state; routing();
    if (state.pending) { showCode(state.pending); note('等待完成 ChatGPT 授权', '设备码已准备好。完成授权后才会切换账号，当前连接仍保留。'); }
    else if (state.ready) { showCode(null); note(state.provider === 'apiKey' ? '已连接 · OpenAI API Key' : state.imageGeneration ? '已连接 · 可以拆图' : '已连接 · 暂不能拆图', state.provider === 'apiKey' ? 'API Key 已通过鉴权。'+(state.imageGeneration ? 'Codex 提供图像生成入口；实际模型权限、额度和结果需以任务执行为准。' : '当前 Codex 未提供图像生成入口，暂不能完整拆分。') : state.imageGeneration ? '账号已连接，且提供图像生成能力。关闭此窗口即可开始拆分。' : '当前账号未提供图像生成能力。请确认所选工作区的权限；登录成功不代表已开通图像生成。'); }
    else { if (state.pending) showCode(state.pending); note(pending ? '等待完成授权' : '尚未连接 Codex', pending ? '设备码已准备好，可在“设备码登录”中查看。也可以改用 API Key 或团队访问令牌。' : '可使用 OpenAI API Key、团队访问令牌或设备码登录。'); }
  }
  async function check() {
    if (checking) return;
    checking = true; $('codex-check').disabled = true;
    note('正在检查', '正在检查账号和图像生成能力…');
    try {
      const state = await ShijieService.request('engine/ai/status');
      if (!state.ok) throw Error(state.error || '读取连接失败');
      activeProvider = state.active;
      displayCompany(state.company);
      if (state.codex.ok) display(state.codex);
      else { codexState = state.codex; $('codex-connected').hidden = true; $('codex-logout').hidden = !state.codex.configured; note('Codex 检查未完成', state.codex.error || '请检查连接'); }
      routing();
      if (!selectedPanel) { provider(state.codex.configured || state.codex.pending ? 'codex' : 'company'); method(state.codex.pending ? 'device' : state.codex.provider === 'apiKey' || !state.codex.configured ? 'api' : 'token'); }
    }
    catch (error) { note('检查未完成', error.message); $('ai-active').textContent = '连接状态读取失败'; $('ai-capabilities').textContent = error.message; }
    finally { checking = false; $('codex-check').disabled = false; }
  }
  async function action(work) {
    if (busy) return;
    busy = true;
    for (const id of ['codex-login', 'codex-token-connect', 'codex-api-connect', 'codex-cancel-login', 'codex-logout', 'codex-check', 'company-save', 'company-test']) $(id).disabled = true;
    try { await work(); } catch (error) { if (selectedPanel === 'company') companyNote('操作未完成', error.message); else note('连接未完成', error.message); }
    finally { busy = false; for (const id of ['codex-login', 'codex-token-connect', 'codex-api-connect', 'codex-cancel-login', 'codex-logout', 'codex-check', 'company-save', 'company-test']) $(id).disabled = false; $('company-test').disabled = !companyState.configured || companyDirty; if (pending && panel.open) { clearTimeout(timer); timer = setTimeout(poll, 3000); } }
  }
  button.onclick = async () => { if (!panel.open) panel.showModal(); await check(); };
  $('codex-close').onclick = () => panel.close();
  panel.onclose = () => { clearTimeout(timer); $('codex-token').value = ''; $('codex-api-key').value = ''; $('company-key').value = ''; };
  $('ai-provider-company').onclick = () => provider('company');
  $('ai-provider-codex').onclick = () => provider('codex');
  $('ai-provider-local').onclick = async () => { provider('local'); await checkLocal(); };
  $('local-check').onclick = checkLocal;
  $('local-use').onclick = () => { const select = document.getElementById('split-engine'); if (select && !select.disabled) { select.value = 'local-layered'; panel.close(); } };
  for (const id of ['company-key','company-model','company-enabled']) $(id).oninput = () => { companyDirty = true; $('company-test').disabled = true; companyNote('修改尚未保存', '保存后可测试新的配置。'); };
  $('company-save').onclick = () => action(async () => {
    provider('company');
    if (location.protocol !== 'https:' && !['localhost','127.0.0.1','[::1]'].includes(location.hostname)) throw Error('请通过 HTTPS 打开AI拆图助手后再提交 Key');
    const api_key = $('company-key').value.trim(), model = $('company-model').value.trim(), enabled = $('company-enabled').checked;
    if (!model) throw Error('请填写公司接口可用的模型 ID');
    $('company-key').value = '';
    companyNote('正在保存', '正在加密保存当前账号的连接…');
    const state = await companyRequest('connection', {api_key, model, enabled});
    companyDirty = false; displayCompany(state); await check();
  });
  $('company-test').onclick = () => action(async () => {
    provider('company'); companyNote('正在测试图片分析', '正在发送测试色块，请稍候…');
    try { displayCompany(await companyRequest('test', {})); await check(); }
    catch (error) { companyState.verified = false; routing(); throw error; }
  });
  $('codex-method-api').onclick = () => method('api');
  $('codex-method-token').onclick = () => method('token');
  $('codex-method-device').onclick = () => method('device');
  $('codex-check').onclick = check;
  $('codex-login').onclick = () => action(async () => {
    provider('codex'); method('device'); note('正在获取设备码', '正在准备登录，请稍候…');
    if (pending) { await request('login/cancel', {}); showCode(null); }
    const result = await ShijieSmartSplit.login();
    if (!result.ok) throw Error(result.error || '设备码获取失败，请重试或使用团队访问令牌');
    showCode(result); note('设备码已准备好', '复制上方设备码，打开登录页并完成授权。');
  });
  $('codex-cancel-login').onclick = () => action(async () => { await request('login/cancel', {}); showCode(null); note('已取消本次登录', '可以重新获取设备码，或切换到团队访问令牌。'); });
  $('codex-copy').onclick = async () => {
    try { await navigator.clipboard.writeText($('codex-device-code').value); $('codex-copy').textContent = '已复制'; }
    catch { $('codex-device-code').focus(); $('codex-device-code').select(); note('设备码已选中', '请按 Ctrl+C（Mac 为 ⌘C）复制。'); }
  };
  $('codex-token-connect').onclick = () => action(async () => {
    provider('codex');
    if (location.protocol !== 'https:' && !['localhost', '127.0.0.1', '[::1]'].includes(location.hostname)) throw Error('请通过 HTTPS 打开AI拆图助手后再提交访问令牌');
    const token = $('codex-token').value.trim();
    if (!token) { $('codex-token').focus(); throw Error('请先粘贴 Codex 访问令牌'); }
    $('codex-token').value = '';
    note('正在验证令牌', '正在验证工作区权限和图像生成能力，通常需要几秒钟…');
    display(await request('access-token', {token})); await check();
  });
  $('codex-api-connect').onclick = () => action(async () => {
    provider('codex'); method('api');
    if (location.protocol !== 'https:' && !['localhost','127.0.0.1','[::1]'].includes(location.hostname)) throw Error('请通过 HTTPS 打开AI拆图助手后再提交 API Key');
    const api_key = $('codex-api-key').value.trim();
    if (!api_key) { $('codex-api-key').focus(); throw Error('请先填写 OpenAI 平台 API Key'); }
    $('codex-api-key').value = '';
    note('正在验证 API Key', '正在验证 OpenAI 接口连接，不提交工程或执行生图…');
    display(await request('api-key', {api_key})); await check();
  });
  $('codex-logout').onclick = () => action(async () => { const r = await request('logout', {}); if (!r.ok) throw Error(r.error); showCode(null); await check(); });
  $('codex-model').onchange = async event => { try { await ShijieSmartSplit.setModel(event.target.value); note('模型已更新', '后续拆图会使用所选分析模型。'); } catch (error) { note('模型未更新', error.message); } };
})();
