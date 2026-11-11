'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function pollingHarness(events,postFailure=false){
 const calls=[],context={TextEncoder,DOMException,setTimeout:fn=>setTimeout(fn,0),clearTimeout,SHIJIE:{prefix:'',user:99,sharedCodex:true},ShijieService:{headers:()=>({})},document:{getElementById:()=>null}};context.window=context;
 context.fetch=async(url,options={})=>{
  calls.push({url,method:options.method||'GET'});let data;
  if(url.endsWith('/health'))data={ready:true,codexAvailable:true,imageWireVersion:1,freeAssistantVersion:1,assistantSplitVersion:1};
  else if(options.method==='POST'){if(postFailure)throw TypeError('Failed to fetch fixture');data={id:'isolated-poll-job'}}
  else if(options.method==='DELETE')data={ok:true};
  else{const event=events.shift();assert.ok(event,'unexpected extra polling');if(event==='network')throw new TypeError('Failed to fetch fixture');if(event==='json')return {ok:true,status:200,headers:{get:name=>name==='content-type'?'application/json':'132000'},json:async()=>{throw new SyntaxError('fixture private response text')}};if(event.businessStatus)return {ok:false,status:event.businessStatus,json:async()=>({error:'fixture business error',code:'FIXTURE_BUSINESS'})};data=event;}
  return {ok:true,status:200,json:async()=>data};
 };
 vm.runInNewContext(readFileSync(path.join(__dirname,'../legacy/拾界插件/开发源码/图像重建/smart-split.js'),'utf8'),context);
 return {api:context.ShijieSmartSplit,calls};
}
const pollInvokers={run:(api,progress)=>api.run('fixture-image','隔离轮询',progress),assistant:(api,progress)=>api.assistant({image:'fixture-image'},progress),assistantSplit:(api,progress)=>api.assistantSplit({image:'fixture-image'},progress)};

test('temporary reads retry only GET; split receipts remain recoverable until saved',async()=>{
 for(const [kind,invoke] of Object.entries(pollInvokers)){
  const h=pollingHarness(['json','network',{status:'completed',result:{nodes:[{id:'result'}]}}]),result=await invoke(h.api);
  assert.equal(result.nodes[0].id,'result');assert.equal(h.calls.filter(c=>c.method==='POST').length,1);assert.equal(h.calls.filter(c=>c.method==='GET'&&c.url.includes('/jobs/')).length,3);assert.equal(h.calls.filter(c=>c.method==='DELETE').length,kind==='assistantSplit'?0:1);if(kind==='assistantSplit')assert.equal(result._assistantJobId,'isolated-poll-job');
 }
});

test('exhausted job reads retain the job and completed partial layers without reposting or cancelling',async()=>{
 for(const invoke of Object.values(pollInvokers)){
  const h=pollingHarness([{status:'running',partial:{nodes:[{id:'kept'}]},partialRevision:1},'json','network','json']);
  await assert.rejects(invoke(h.api),error=>{assert.equal(error.deliveryPending,true);assert.equal(error.jobId,'isolated-poll-job');assert.equal(error.status,200);assert.equal(error.contentType,'application/json');assert.equal(error.contentLength,'132000');assert.match(error.message,/HTTP 200/);assert.match(error.message,/任务记录/);assert.equal(error.partial.nodes[0].id,'kept');assert.ok(!JSON.stringify(error).includes('private response text'));return true});
  assert.equal(h.calls.filter(c=>c.method==='POST').length,1);assert.equal(h.calls.filter(c=>c.method==='GET'&&c.url.includes('/jobs/')).length,4);assert.equal(h.calls.filter(c=>c.method==='DELETE').length,0);
 }
});

test('nontransient API business failures keep their exact status code and message without retry or DELETE',async()=>{
 for(const invoke of Object.values(pollInvokers))for(const status of [401,403,404,409]){
  const h=pollingHarness([{businessStatus:status}]);await assert.rejects(invoke(h.api),error=>error.deliveryPending===undefined&&error.jobId==='isolated-poll-job'&&error.status===status&&error.code==='FIXTURE_BUSINESS'&&error.message==='fixture business error');
  assert.equal(h.calls.filter(c=>c.method==='POST').length,1);assert.equal(h.calls.filter(c=>c.method==='GET'&&c.url.includes('/jobs/')).length,1);assert.equal(h.calls.filter(c=>c.method==='DELETE').length,0);
 }
});

test('explicit cancellation still deletes the running job after polling begins',async()=>{
 for(const invoke of Object.values(pollInvokers)){
  const h=pollingHarness([{status:'running'},{status:'cancelled'}]);let cancellation;
  await assert.rejects(invoke(h.api,(_v,message)=>{if(message===undefined&&!cancellation)cancellation=h.api.cancel()}),error=>error.name==='AbortError');await cancellation;
  assert.equal(h.calls.filter(c=>c.method==='POST').length,1);assert.ok(h.calls.some(c=>c.method==='DELETE'));
 }
});

test('known failed expired and cancelled terminal states retain their original cleanup',async()=>{
 for(const invoke of Object.values(pollInvokers))for(const status of ['failed','expired','cancelled']){
  const h=pollingHarness([{status,message:'fixture terminal state'}]);await assert.rejects(invoke(h.api),error=>status==='cancelled'?error.name==='AbortError':error.message==='fixture terminal state');
  assert.equal(h.calls.filter(c=>c.method==='POST').length,1);assert.equal(h.calls.filter(c=>c.method==='DELETE').length,1);
 }
});

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

test('delivery waiting stops assistant polling without retrying generation and preserves its identity', async () => {
  const calls=[],message='生成结果保存在共享电脑，等待回传；请稍后刷新任务记录，无需重新生成';
  const context={TextEncoder,DOMException,setTimeout,clearTimeout,SHIJIE:{prefix:'',user:1,sharedCodex:true},ShijieService:{headers:()=>({})},document:{getElementById:()=>null}};
  context.window=context;
  context.fetch=async(url,options={})=>{
    calls.push({url,options});
    let data;
    if(url.endsWith('/health'))data={freeAssistantVersion:1,assistantSplitVersion:1};
    else if(url.endsWith('/assistant/split'))data={id:'waiting-job'};
    else if(options.method==='DELETE')data={ok:true,deliveryPending:true};
    else data={status:'failed',deliveryPending:true,message,partial:{nodes:[{id:'kept'}]}};
    return {ok:true,status:200,json:async()=>data};
  };
  vm.runInNewContext(readFileSync(path.join(__dirname,'../legacy/拾界插件/插件程序/edge/smart-split.js'),'utf8'),context);
  await assert.rejects(context.ShijieSmartSplit.assistantSplit({image:'fake'},()=>{}),error=>{
    assert.equal(error.deliveryPending,true);assert.equal(error.jobId,'waiting-job');
    assert.equal(error.message,message);assert.equal(error.partial.nodes[0].id,'kept');return true;
  });
  assert.equal(calls.filter(c=>c.options.method==='POST').length,1);
  assert.equal(calls.filter(c=>!c.options.method&&c.url.includes('/jobs/')).length,1);
});

test('opening delivery waiting retains the snapshot guard and never invites another split', async () => {
  const elements={status:{textContent:''},recognize:{textContent:'',disabled:false}},listeners={};
  const scene={source:'same-image',nodes:[]},message='生成结果保存在共享电脑，等待回传；请稍后刷新任务记录，无需重新生成';
  const context={URLSearchParams,Map,AbortController,setTimeout,clearTimeout,location:{search:'?job=waiting-job'},
    document:{currentScript:{dataset:{prefix:'',user:'1',sharedCodex:'true',csrf:'fake'}},querySelector:()=>null,getElementById:id=>elements[id]},
    localStorage:{getItem:()=>null,setItem:()=>{}},studio:{adapter:{load:async()=>{}},setInitial:()=>{},sync:()=>{}},
    fetch:async()=>({ok:true,json:async()=>({status:'failed',deliveryPending:true,message,input:scene})})};
  context.window=context;context.addEventListener=(name,callback)=>listeners[name]=callback;
  vm.runInNewContext(readFileSync(path.join(__dirname,'../shijie/static/server/bootstrap.js'),'utf8'),context);
  await listeners.load();
  assert.equal(elements.status.textContent,message);
  assert.equal(elements.recognize.disabled,true);assert.match(elements.recognize.textContent,/等待回传/);
  assert.equal(context.ShijieService.isRunningSnapshot(scene),true);
  assert.doesNotMatch(elements.status.textContent,/尚未产生|重新拆分将发起/);
  const live={source:'live-waiting-image'};
  context.ShijieService.holdPendingDelivery(live);
  assert.equal(context.ShijieService.isRunningSnapshot(live),true);
  assert.equal(context.ShijieService.isRunningSnapshot(scene),false);
});

test('task records label waiting accurately and manual refresh reveals completed delivery', async () => {
  const node=()=>({children:[],textContent:'',append(...children){this.children.push(...children)},replaceChildren(...children){this.children=children}});
  const head=node(),body=node(),notice=node(),refresh=node();let state={id:'same-job',title:'素材',status:'failed',deliveryPending:true,progress:.8,message:'等待回传，无需重新生成'};
  const context={document:{querySelector:selector=>selector==='main'?{dataset:{section:'tasks'}}:selector==='thead'?head:body,
    getElementById:id=>id==='notice'?notice:refresh,createElement:node},SHIJIE:{prefix:''},
    ShijieService:{request:async()=>({jobs:[state]})}};
  vm.runInNewContext(readFileSync(path.join(__dirname,'../shijie/static/server/service.js'),'utf8'),context);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(body.children[0].children[1].textContent,'等待回传');
  state={...state,status:'completed',deliveryPending:false,message:'处理完成，请核对结果'};
  await refresh.onclick();
  assert.equal(body.children[0].children[1].textContent,'处理结束');
  assert.equal(body.children[0].children[3].children[0].href,'/image-editor.html?job=same-job');
});

test('unknown generation submit never automatically resubmits or deletes a job',async()=>{for(const invoke of Object.values(pollInvokers)){const h=pollingHarness([],true);await assert.rejects(invoke(h.api),e=>e.submissionUnknown===true&&/不要重复/.test(e.message));assert.equal(h.calls.filter(c=>c.method==='POST').length,1);assert.equal(h.calls.filter(c=>c.method==='DELETE').length,0)}});
