'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../legacy/拾界插件/插件程序/edge/workspace-ui.js'), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));

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
    isBusy:() => busy, flush:async() => {}, saveProject:async() => { events.push('save'); dirty = false; }};
  const context = {location, URLSearchParams, document:{querySelector:node, getElementById:id => node('#'+id),
    createElement:tag => { const el = new Element(); if (tag === 'nav') nodes.set('nav', el); return el; }, body:new Element()},
    studio, StudioBase:{library:{isDirty:() => dirty}}};
  context.window = context;
  vm.runInNewContext(source, context);
  const click = (options = {}) => web.listeners.click({button:0, preventDefault(){}, ...options});
  return {node, dialogs, navigations, events, studio, click};
}

test('unsaved mode switch presents a choice; cancel preserves work and allows retry', async () => {
  const h = setup({dirty:true});
  const pending = h.click(); await tick();
  assert.equal(h.dialogs.length, 1, 'show an in-page choice before attempting to leave');
  assert.deepEqual(h.navigations, []);
  assert.deepEqual(h.events, ['flush']);
  h.node('#workspace-switch-stay').onclick(); await pending;
  assert.equal(h.node('nav').getAttribute('aria-busy'), null);
  const retry = h.click(); await tick();
  assert.equal(h.dialogs.length, 2);
  h.dialogs.at(-1).close(); await retry;
  assert.deepEqual(h.navigations, []);
});

test('saved navigation unlocks even when the browser cancels the leave request', async () => {
  const h = setup(); await h.click();
  assert.deepEqual(h.navigations, ['http://localhost/export.html']);
  assert.equal(h.node('nav').getAttribute('aria-busy'), null);
});

test('save and switch waits for successful persistence before leaving', async () => {
  const h = setup({dirty:true}), pending = h.click(); await tick();
  assert.equal(h.dialogs.length, 1);
  await h.node('#workspace-switch-save').onclick(); await pending;
  assert.deepEqual(h.events, ['flush', 'save']);
  assert.deepEqual(h.navigations, ['http://localhost/export.html']);
});

test('save failure stays on the project with an error and retry', async () => {
  const h = setup({dirty:true});
  h.studio.saveProject = async() => { throw Error('保存冲突'); };
  const pending = h.click(); await tick();
  assert.equal(h.dialogs.length, 1);
  await h.node('#workspace-switch-save').onclick();
  assert.deepEqual(h.navigations, []);
  assert.match(h.node('#workspace-switch-note').textContent, /保存冲突/);
  assert.equal(h.node('#workspace-switch-save').disabled, false);
  assert.equal(h.dialogs[0].open, true);
  h.node('#workspace-switch-stay').onclick(); await pending;
  assert.equal(h.node('nav').getAttribute('aria-busy'), null);
});

test('repeated clicks create only one prompt and never race saves', async () => {
  const h = setup({dirty:true}), pending = h.click();
  await h.click(); await tick();
  assert.equal(h.dialogs.length, 1);
  h.dialogs[0].close(); await pending;
});

test('busy work blocks navigation and modified clicks retain normal link behavior', async () => {
  const h = setup({busy:true}); await h.click();
  assert.match(h.node('#status').textContent, /当前操作尚未完成/);
  assert.deepEqual(h.navigations, []);
  const normal = setup({dirty:true}); await normal.click({metaKey:true});
  assert.deepEqual(normal.events, []);
  assert.equal(normal.dialogs.length, 0);
});
