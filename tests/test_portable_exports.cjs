const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
function setup(fetch){
  class Reader{readAsDataURL(blob){blob.arrayBuffer().then(b=>{this.result='data:font/woff2;base64,'+Buffer.from(b).toString('base64');this.onload();},e=>{this.error=e;this.onerror();});}}
  const context={fetch,FileReader:Reader,document:{currentScript:{dataset:{prefix:'/shijie',user:'2',csrf:'test'}}},window:{addEventListener(){}},URLSearchParams};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../shijie/static/server/bootstrap.js'),'utf8'),context);return context.window.ShijieService;
}
test('portable SVG embeds its deployed font once and does not depend on browser font installation',async()=>{
  let calls=0;
  const service=setup(async url=>{calls++;assert.equal(url,'/shijie/static/server/fonts/NotoSansCJKsc-Bold.woff2');return {ok:true,blob:async()=>new Blob(['wOF2test'])};});
  const art='<svg xmlns="http://www.w3.org/2000/svg"><text font-family="Noto Sans CJK SC" font-weight="700">组件库</text></svg>';
  assert.equal(await service.portableArtwork('<svg><path/></svg>'),'<svg><path/></svg>');assert.equal(calls,0);
  const output=await service.portableArtwork(art);assert.match(output,/data:font\/woff2;base64,d09GMnRlc3Q=/);
  assert.match(output,/<svg[^>]*><style>/);assert.match(output,/组件库/);
  await service.portableArtwork(art);assert.equal(calls,1);
});
test('failed or non-font responses cannot silently produce a broken export',async()=>{
  let ok=false;const service=setup(async()=>({ok:true,blob:async()=>new Blob([ok?'wOF2test':'<html>login</html>'])}));
  const art='<svg><text font-family="Noto Sans CJK SC" font-weight="700">A</text></svg>';
  await assert.rejects(service.portableArtwork(art),/字体/);ok=true;
  assert.match(await service.portableArtwork(art),/data:font/);
});
test('portable exports embed the used regular and bold faces separately',async()=>{
 const urls=[];const service=setup(async url=>{urls.push(url);return {ok:true,blob:async()=>new Blob(['wOF2test'])};});
 const art='<svg><text font-family="Noto Sans CJK SC" font-weight="400">常规</text><text font-family="Noto Sans CJK SC" font-weight="700">粗体</text></svg>';
 const result=await service.portableArtwork(art);assert.match(result,/font-weight:400/);assert.match(result,/font-weight:700/);assert.equal(urls.length,2);assert(urls.some(u=>u.endsWith('Regular.woff2')));await service.portableArtwork(art);assert.equal(urls.length,2);
});
test('portable exports preserve serif and sans identity at the same weight',async()=>{
 const urls=[];const service=setup(async url=>{urls.push(url);return {ok:true,blob:async()=>new Blob(['wOF2test'])};});
 const art='<svg><text font-family="Liberation Serif" font-weight="400">11.03</text><text font-family="Liberation Sans" font-weight="400">LABEL</text></svg>';
 const result=await service.portableArtwork(art);assert.match(result,/@font-face\{font-family:"Liberation Serif"/);assert.match(result,/@font-face\{font-family:"Liberation Sans"/);
 assert.equal(urls.length,2);assert(urls.some(u=>u.endsWith('LiberationSerif-Regular.woff2')));assert(urls.some(u=>u.endsWith('LiberationSans-Regular.woff2')));
 await service.portableArtwork(art);assert.equal(urls.length,2);
});
test('portable Chinese serif exports use the actual deployed serif font',async()=>{
 const urls=[];const service=setup(async url=>{urls.push(url);return {ok:true,blob:async()=>new Blob(['wOF2test'])};});
 const art='<svg><text font-family="Noto Serif CJK SC" font-weight="700">遗迹背包</text></svg>';
 assert.match(await service.portableArtwork(art),/@font-face\{font-family:"Noto Serif CJK SC"/);
 assert.deepEqual(urls,['/shijie/static/server/fonts/NotoSerifCJKsc-Bold.woff2']);
});
test('opening a running task labels its recovered layers as a snapshot, not completion',async()=>{
 let loaded,sceneLoaded,feedback;const elements={status:{},recognize:{textContent:'拆分完成'},badge:{textContent:'可继续拆分'}};
 const studio={adapter:{load:async scene=>{sceneLoaded=scene;}},setInitial(){},sync(){}};
 const context={URLSearchParams,location:{search:'?job=active'},studio,
  splitFeedback:(kind,message)=>{feedback={kind,message};},
  document:{currentScript:{dataset:{prefix:'',user:'2',csrf:'test'}},querySelector:selector=>selector==='.document-bar .doc-tag'?elements.badge:null,getElementById:id=>elements[id]},
  fetch:async()=>({ok:true,json:async()=>({status:'running',message:'正在补绘腿脚',partial:{nodes:[]}})})};
 context.window=context;context.addEventListener=(_,callback)=>{loaded=callback;};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../shijie/static/server/bootstrap.js'),'utf8'),context);
 await loaded();assert(sceneLoaded);assert.match(elements.status.textContent,/仍在运行/);
 assert.match(elements.status.textContent,/快照/);assert.equal(elements.recognize.disabled,true);
 assert.notEqual(elements.recognize.textContent,'拆分完成');
 assert.equal(feedback?.kind,'running');assert.match(feedback.message,/补绘腿脚/);
 assert.equal(elements.badge.textContent,'后台拆分中');
});
