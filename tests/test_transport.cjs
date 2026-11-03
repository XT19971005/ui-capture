'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

test('missing personal Codex opens connection settings and preserves the submitted image', async () => {
  const calls = [], source = 'data:image/png;base64,YWJj';
  let opened = 0;
  const context = {TextEncoder, DOMException, setTimeout, clearTimeout,
    SHIJIE: {prefix: '', user: 1}, ShijieService: {headers: () => ({})},
    document: {getElementById: id => id === 'codex-settings' ? {click: () => opened++} : null}};
  context.window = context;
  context.fetch = async (url, options = {}) => {
    calls.push({url, options});
    if (url.endsWith('/health')) return {ok: true, status: 200, json: async () => ({ready: true, codexAvailable: true, imageWireVersion: 1})};
    assert.equal(url, '/api/engine/jobs');
    assert.equal(options.method, 'POST');
    return {ok: false, status: 409, json: async () => ({code: 'CODEX_LOGIN_REQUIRED', error: '请先连接个人 Codex'})};
  };
  vm.runInNewContext(readFileSync(path.join(__dirname, '../legacy/拾界插件/插件程序/edge/smart-split.js'), 'utf8'), context);
  await assert.rejects(context.ShijieSmartSplit.run(source, '原图'), error => error.code === 'CODEX_LOGIN_REQUIRED' && error.message === '请先连接个人 Codex');
  assert.equal(opened, 1);
  assert.equal(calls.length, 2);
  assert.equal(JSON.parse(calls[1].options.body).image, source);
  assert.equal(JSON.parse(calls[1].options.body).original, source);
});
