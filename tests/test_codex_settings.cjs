'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../legacy/拾界插件/插件程序/edge/codex-settings.js'), 'utf8');
function setup() {
  const nodes = new Map(), calls = [], clipboard = [];
  class Element {
    constructor() { this.value = ''; this.hidden = false; this.disabled = false; this.dataset = {}; this.textContent = ''; }
    set innerHTML(html) { for (const match of html.matchAll(/<[^>]*\bid="([^"]+)"[^>]*>/g)) { const el = new Element(); el.hidden = /\bhidden\b/.test(match[0]); nodes.set(match[1], el); } }
    querySelector(selector) { return nodes.get(selector.slice(1)); }
    setAttribute(key, value) { this[key] = value; }
    append() {} replaceChildren() {} focus() {} select() {}
    showModal() { this.open = true; } close() { this.open = false; this.onclose?.(); }
  }
  nodes.set('codex-settings', new Element());
  const state = {ok: true, ready: false, models: [], pending: null};
  const pending = {ok: true, userCode: 'TEST-1234', url: 'https://auth.openai.com/codex/device', expiresAt: Date.now()/1000 + 600};
  const context = {URL, Date, location: {protocol: 'http:', hostname: '127.0.0.1'}, setTimeout: () => 1, clearTimeout() {}, setInterval: () => 1, clearInterval() {},
    document: {getElementById: id => nodes.get(id), createElement: () => new Element(), body: {append() {}}},
    navigator: {clipboard: {writeText: async text => clipboard.push(text)}},
    ShijieSmartSplit: {account: async () => state, login: async () => pending, setModel: async () => ({ok: true})},
    ShijieService: {request: async (route, options) => { calls.push({route, options}); if (route === 'engine/ai/status') return {ok:true, active:'codex', company:{ok:true,configured:false,enabled:false}, codex:state}; if (route.startsWith('engine/company/')) return {ok:true,configured:true,enabled:true,model:'grok-4.6'}; return {ok: true, ...state}; }}};
  context.window = context;
  vm.runInNewContext(source, context);
  return {nodes, calls, clipboard, state, pending, context};
}
test('device code remains visible after checking, copying and reopening the dialog', async () => {
  const h = setup();
  await h.nodes.get('codex-settings').onclick();
  await h.nodes.get('codex-login').onclick();
  assert.equal(h.nodes.get('codex-device-code')?.value, 'TEST-1234');
  await h.nodes.get('codex-check').onclick();
  assert.equal(h.nodes.get('codex-device-code').value, 'TEST-1234');
  await h.nodes.get('codex-copy').onclick();
  assert.deepEqual(h.clipboard, ['TEST-1234']);
  await h.nodes.get('codex-settings').onclick();
  assert.equal(h.nodes.get('codex-device-code').value, 'TEST-1234');
});
test('switching from an API key keeps the pending ChatGPT code until authorization completes', async () => {
  const h = setup();
  Object.assign(h.state, {ready:true, configured:true, provider:'apiKey', imageGeneration:true, pending:h.pending});
  await h.nodes.get('codex-settings').onclick();
  assert.equal(h.nodes.get('codex-device-panel').hidden, false);
  assert.equal(h.nodes.get('codex-device-code').value, 'TEST-1234');
  await h.nodes.get('codex-check').onclick();
  assert.equal(h.nodes.get('codex-device-code').value, 'TEST-1234');
  assert.match(h.nodes.get('codex-connection').textContent, /授权/);
  Object.assign(h.state, {provider:'chatgpt', pending:null});
  await h.nodes.get('codex-check').onclick();
  assert.equal(h.nodes.get('codex-device-code').value, '');
  assert.match(h.nodes.get('codex-connection').textContent, /账号已连接/);
});
test('team token is sent once then cleared; reconnect failures do not expose it', async () => {
  const h = setup(), input = h.nodes.get('codex-token');
  assert.ok(input, 'team access token entry must exist');
  input.value = 'private-team-token-value';
  await h.nodes.get('codex-token-connect').onclick();
  const sent = h.calls.find(call => call.route === 'engine/codex/access-token');
  assert.equal(JSON.parse(sent.options.body).token, 'private-team-token-value');
  assert.equal(input.value, '');
  assert.ok(!h.nodes.get('codex-connection').textContent.includes('private-team-token-value'));
  h.context.ShijieService.request = async () => { throw Error('令牌验证失败'); };
  input.value = 'another-private-team-token';
  await h.nodes.get('codex-token-connect').onclick();
  assert.equal(input.value, '');
  assert.equal(h.nodes.get('codex-connection').textContent, '令牌验证失败');
});
test('device renewal cancels the previous attempt before requesting another code', async () => {
  const h = setup();
  await h.nodes.get('codex-login').onclick();
  h.pending.userCode = 'NEXT-5678';
  h.context.ShijieSmartSplit.login = async () => {
    assert.equal(h.calls.at(-1).route, 'engine/codex/login/cancel');
    return h.pending;
  };
  await h.nodes.get('codex-login').onclick();
  assert.equal(h.nodes.get('codex-device-code').value, 'NEXT-5678');
});
test('team token can be submitted over remote HTTP and is cleared afterwards', async () => {
  const h = setup();
  h.context.location.hostname = 'remote.example';
  h.nodes.get('codex-token').value = 'private-team-token-value';
  await h.nodes.get('codex-token-connect').onclick();
  const sent = h.calls.filter(call => call.route === 'engine/codex/access-token');
  assert.equal(sent.length, 1);
  assert.equal(JSON.parse(sent[0].options.body).token, 'private-team-token-value');
  assert.equal(h.nodes.get('codex-token').value, '');
});
test('company connection saves privately and probe is an explicit separate action', async () => {
  const h = setup();
  h.context.location.hostname = 'remote.example';
  assert.ok(h.nodes.get('company-key'), 'company API key entry must exist');
  h.nodes.get('company-key').value = 'private-company-test-key';
  h.nodes.get('company-model').value = 'grok-4.6';
  h.nodes.get('company-enabled').checked = true;
  await h.nodes.get('company-save').onclick();
  const sent = h.calls.find(call => call.route === 'engine/company/connection');
  assert.deepEqual(JSON.parse(sent.options.body), {api_key:'private-company-test-key', model:'grok-4.6', enabled:true});
  assert.equal(h.nodes.get('company-key').value, '');
  assert.equal(h.calls.filter(call => call.route === 'engine/company/test').length, 0);
  await h.nodes.get('company-test').onclick();
  assert.equal(h.calls.filter(call => call.route === 'engine/company/test').length, 1);
});
test('company-only selection shows one service for analysis and generation without asking for Codex', async () => {
  const h = setup();
  h.context.ShijieService.request = async () => ({ok:true, active:'company', company:{ok:true, configured:true, enabled:true, model:'grok-4.6', verified:true}, codex:h.state});
  await h.nodes.get('codex-settings').onclick();
  assert.match(h.nodes.get('ai-active').textContent, /公司 Agent/);
  assert.match(h.nodes.get('ai-capabilities').textContent, /分析与生图均使用公司 Agent/);
  assert.equal(h.nodes.get('ai-company-panel').hidden, false);
});
test('both configured visibly prefer Codex and keep the company connection', async () => {
  const h = setup();
  h.state.ready = true; h.state.imageGeneration = true;
  h.context.ShijieService.request = async () => ({ok:true, active:'codex', company:{ok:true, configured:true, enabled:true, model:'grok-4.6'}, codex:{...h.state,configured:true}});
  await h.nodes.get('codex-settings').onclick();
  assert.match(h.nodes.get('ai-active').textContent, /Codex/);
  assert.match(h.nodes.get('ai-capabilities').textContent, /分析与生图均使用 Codex/);
  assert.equal(h.nodes.get('company-model').value, 'grok-4.6');
  assert.equal(h.nodes.get('ai-codex-panel').hidden, false);
});
test('local model check needs no cloud account and selecting it never submits an image', async () => {
  const h = setup();
  const selector = {value:'codex'};
  h.nodes.set('split-engine', selector);
  h.context.ShijieService.request = async route => {
    h.calls.push({route});
    assert.equal(route, 'engine/local-model/status');
    return {ready:true,busy:false};
  };
  assert.ok(h.nodes.get('ai-provider-local'), 'local model entry must exist');
  await h.nodes.get('ai-provider-local').onclick();
  assert.equal(h.nodes.get('ai-local-panel').hidden, false);
  assert.equal(h.nodes.get('local-use').disabled, false);
  h.nodes.get('local-use').onclick();
  assert.equal(selector.value, 'local-layered');
  assert.equal(h.calls.length, 1);
});

test('OpenAI API Key has its own method and submits only to the API key endpoint', async () => {
  const h = setup(), input = h.nodes.get('codex-api-key');
  assert.ok(input, 'API Key must have a separate entry');
  h.nodes.get('codex-method-api').onclick();
  assert.equal(h.nodes.get('codex-api-panel').hidden, false);
  assert.equal(h.nodes.get('codex-token-panel').hidden, true);
  input.value = 'sk-proj-private-api-test-key';
  await h.nodes.get('codex-api-connect').onclick();
  const sent = h.calls.find(call => call.route === 'engine/codex/api-key');
  assert.deepEqual(JSON.parse(sent.options.body), {api_key:'sk-proj-private-api-test-key'});
  assert.equal(input.value, '');
  assert.ok(!h.calls.some(call => call.route === 'engine/codex/access-token'));
});

test('API Key entry supports remote HTTP and clears unsent secrets when closed', async () => {
  const h = setup(), input = h.nodes.get('codex-api-key');
  assert.ok(input);
  input.value = 'sk-proj-private-api-test-key';
  h.context.location.hostname = 'remote.example';
  await h.nodes.get('codex-api-connect').onclick();
  const sent = h.calls.filter(call => call.route === 'engine/codex/api-key');
  assert.equal(sent.length, 1);
  assert.equal(JSON.parse(sent[0].options.body).api_key, 'sk-proj-private-api-test-key');
  assert.equal(input.value, '');
  input.value = 'another-unsent-test-key';
  h.nodes.get('codex-close').onclick();
  assert.equal(input.value, '');
});

test('an expired API key remains identified with its actionable error', async () => {
  const h = setup();
  h.context.ShijieService.request = async () => ({ok:true, active:'codex', company:{configured:true,enabled:true}, codex:{ok:false,configured:true,provider:'apiKey',ready:false,error:'OpenAI API Key 无效或已撤销（HTTP 401）'}});
  await h.nodes.get('codex-settings').onclick();
  assert.match(h.nodes.get('codex-connection').textContent, /401/);
  assert.equal(h.nodes.get('codex-api-panel').hidden, false);
  assert.equal(h.nodes.get('codex-logout').hidden, false);
});
