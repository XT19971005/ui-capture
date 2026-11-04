'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../legacy/拾界插件/插件程序/edge/workspace-ui.js'), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));

test('HTTP sessions initialize without native randomUUID and provide UUID v4 to editor tools', () => {
  const code = fs.readFileSync(path.join(__dirname, '../legacy/拾界插件/插件程序/edge/app-session.js'), 'utf8');
  let calls = 0;
  const crypto = {getRandomValues(bytes) { calls++; return bytes.fill(255); }};
  const context = {window: {}, crypto};
  vm.runInNewContext(code, context);
  assert.equal(context.window.ShijieSession.writerId, 'ffffffff-ffff-4fff-bfff-ffffffffffff');
  assert.equal(crypto.randomUUID(), 'ffffffff-ffff-4fff-bfff-ffffffffffff');
  assert.equal(calls, 2);
});

test('secure-context sessions preserve the native UUID implementation', () => {
  const code = fs.readFileSync(path.join(__dirname, '../legacy/拾界插件/插件程序/edge/app-session.js'), 'utf8');
  const native = () => 'native-uuid';
  const context = {window: {}, crypto: {randomUUID: native, getRandomValues() { throw Error('unexpected fallback'); }}};
  vm.runInNewContext(code, context);
  assert.equal(context.crypto.randomUUID, native);
  assert.equal(context.window.ShijieSession.writerId, 'native-uuid');
});

test('both editor pages load project transport before starting project restoration', () => {
  for (const [page, adapter] of [['export.html', 'web-studio.js'], ['image-editor.html', 'image-studio.js']]) {
    const html = fs.readFileSync(path.join(__dirname, '../legacy/拾界插件/插件程序/edge', page), 'utf8');
    assert.ok(html.indexOf('src="smart-split.js"') < html.indexOf('src="' + adapter + '"'), page);
  }
});

function setup({dirty = false, busy = false} = {}) {
  const nodes = new Map(), dialogs = [], navigations = [], events = [];
  class Element {
    constructor() { this.attrs = new Map(); this.listeners = {}; this.disabled = false; }
    setAttribute(k, v) { this.attrs.set(k, v); }
    getAttribute(k) { return this.attrs.get(k) ?? null; }
    hasAttribute(k) { return this.attrs.has(k); }
    removeAttribute(k) { this.attrs.delete(k); }
    addEventListener(k, fn) { this.listeners[k] = fn; }
    append() {} after() {} remove() {} focus() {}
    showModal() { this.open = true; dialogs.push(this); }
    close() { this.open = false; this.listeners.close?.(); }
    set innerHTML(html) { for (const m of html.matchAll(/\bid="([^"]+)"/g)) nodes.set('#' + m[1], new Element()); }
    querySelector(s) { return s.includes('data-mode=image') ? image : s.includes('data-mode=web') ? web : node(s); }
    querySelectorAll() { return [web, image]; }
  }
  const node = s => { if (!nodes.has(s)) nodes.set(s, new Element()); return nodes.get(s); };
  const web = new Element(), image = new Element();
  web.href = 'http://localhost/export.html'; image.href = 'http://localhost/image-editor.html';
  const location = {pathname:'/image-editor.html', search:'', set href(url) { navigations.push(url); }};
  const doc = {};
  const studio = {adapter:{get:() => doc, flush:async() => events.push('flush')},
    isBusy:() => busy, flush:async() => { events.push('checkpoint'); dirty=false; }, saveProject:async() => { events.push('save'); dirty = false; }};
  const context = {location, URLSearchParams, document:{readyState:'loading',addEventListener(){},querySelectorAll:()=>[],querySelector:node, getElementById:id => node('#'+id),
    createElement:tag => { const el = new Element(); if (tag === 'nav') nodes.set('nav', el); return el; }, body:new Element()},
    studio, StudioBase:{library:{isDirty:() => dirty}}};
  context.window = context;
  vm.runInNewContext(source, context);
  const click = (options = {}) => web.listeners.click({button:0, preventDefault(){}, ...options});
  return {node, dialogs, navigations, events, studio, click};
}

test('mode switch persists a checkpoint before leaving without writing during edits',async()=>{
 const h=setup({dirty:true});await h.click();assert.deepEqual(h.events,['flush','checkpoint']);assert.deepEqual(h.navigations,['http://localhost/export.html']);assert.equal(h.dialogs.length,0);
});
test('failed checkpoint keeps the current page and unlocks navigation for retry',async()=>{
 const h=setup({dirty:true});h.studio.flush=async()=>{throw Error('保存冲突')};await h.click();assert.deepEqual(h.navigations,[]);assert.match(h.node('#status').textContent,/保存冲突/);assert.equal(h.node('nav').getAttribute('aria-busy'),null);
});
test('repeated mode clicks do not race checkpoint writes',async()=>{
 const h=setup({dirty:true});let release;h.studio.flush=()=>new Promise(r=>release=r);const pending=h.click();await tick();await h.click();assert.deepEqual(h.navigations,[]);release();await pending;assert.match(h.node('#status').textContent,/未保存修改/);
});
test('busy work blocks navigation and modified clicks retain normal link behavior', async () => {
  const h = setup({busy:true}); await h.click();
  assert.match(h.node('#status').textContent, /当前操作尚未完成/);
  assert.deepEqual(h.navigations, []);
  const normal = setup({dirty:true}); await normal.click({metaKey:true});
  assert.deepEqual(normal.events, []);
  assert.equal(normal.dialogs.length, 0);
});
