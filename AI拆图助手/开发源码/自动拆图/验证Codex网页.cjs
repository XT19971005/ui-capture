// Real acceptance: upload the user-selected new JPG through the extension, then export through its UI.
const fs=require('fs'),path=require('path'),assert=require('assert'),crypto=require('crypto');
const root=path.resolve(__dirname,'../..'),nm=path.join(root,'依赖/构建工具/node_modules'),{chromium}=require(path.join(nm,'playwright'));
const out=path.join(root,'自检记录/Codex图片拆分'),tmp=path.join(root,'依赖/运行临时'),edge=path.join(root,'插件程序/edge');
fs.mkdirSync(out,{recursive:true});fs.mkdirSync(tmp,{recursive:true});process.env.TEMP=process.env.TMP=tmp;
const source=process.argv[2]||'D:/设计素材/设计素材.library/images/L163JLNXQ57J8.info/IMG_4008.jpg';
(async()=>{
 const profile=fs.mkdtempSync(path.join(tmp,'codex-web-')),c=await chromium.launchPersistentContext(profile,{executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true,acceptDownloads:true,viewport:{width:1920,height:1080}});
 const p=await c.newPage(),errors=[],auditedDownloads=[];p.on('pageerror',e=>errors.push(e.message));p.on('response',r=>{if(/\/projects\/codex-[^/]+\/psd$/.test(r.url())){auditedDownloads.push(r.status());console.log('WEB audited PSD response '+r.status())}});let nextLog=0;
 try{
  await p.goto('http://127.0.0.1:19217/image-editor.html');await p.waitForFunction(()=>!!window.studio);
  assert.equal(await p.locator('#recognition-mode').inputValue(),'codex');assert.equal(await p.locator('#yichuang-settings').count(),0);
  await p.locator('#codex-settings').click();await p.waitForFunction(()=>document.querySelector('#codex-connection').textContent.startsWith('已连接'),null,{timeout:90000});
  console.log('WEB: own Codex connected');await p.locator('.codex-dialog form button').click();
  await p.locator('#image-file').setInputFiles(source);const started=Date.now();
  for(;;){
   const state=await p.evaluate(()=>({busy,delivery:scene?.delivery,recognition:scene?.recognition,message:document.getElementById('status').textContent}));
   if(Date.now()>=nextLog){console.log('WEB: '+state.message);nextLog=Date.now()+15000;}
   if(!state.busy){if(!state.delivery)throw Error(state.message);break;}
   if(Date.now()-started>1800000)throw Error('Web pipeline timeout');await p.waitForTimeout(1500);
  }
  const result=await p.evaluate(()=>scene);assert(result.recognition.engine.startsWith('game-ui-to-psd'));assert(result.nodes.length>3);
  await p.screenshot({path:path.join(out,'网页完成.png')});
  // Save through the visible export form, not by calling the exporter directly.
  await p.locator('#tab-export').click();await p.locator('#image-export-format').selectOption('psd');
  const event=p.waitForEvent('download',{timeout:90000});await p.locator('#image-export-run').click();const dl=await event;
  const final=result.delivery.psd,downloaded=path.join(out,'网页下载验收.psd');await dl.saveAs(downloaded);assert(auditedDownloads.includes(200),'visible export did not download audited backend PSD');
  const ag=require(path.join(nm,'ag-psd')),psd=ag.readPsd(fs.readFileSync(final),{skipLayerImageData:true,skipCompositeImageData:true});
  const counts={text:0,vector:0,bitmap:0};function walk(ls){for(const l of ls){if(l.children)walk(l.children);else if(l.text)counts.text++;else if(l.vectorMask)counts.vector++;else counts.bitmap++;}}walk(psd.children);
  assert.equal(psd.width,result.width);assert.equal(psd.height,result.height);assert(counts.bitmap>0);assert.deepEqual(errors,[]);
  const sha=f=>crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex');assert.equal(sha(source),sha(result.delivery.original));
  const auditFile=path.join(result.delivery.project,'1_过程/03_检查/检查结果.json'),audit=JSON.parse(fs.readFileSync(auditFile,'utf8'));
  assert.equal(audit.structuralChecks,'PASS');assert.equal(audit.assetChecks,'PASS');assert.equal(sha(final),audit.psdSHA256,'final PSD differs from independently audited bytes');assert.equal(sha(downloaded),audit.psdSHA256,'web download must be the actual audited PSD');assert.equal(result.recognition.reviewStatus,'PASS','actual per-layer visual review still needs correction');
  fs.writeFileSync(path.join(out,'网页全流程验收.json'),JSON.stringify({status:'PASS',method:'real Edge UI + own signed-in Codex, no mock',delivery:result.delivery,psdSHA256:sha(final),downloadSHA256:sha(downloaded),auditFile,auditSHA256:sha(auditFile),originalPreserved:true,counts,recognition:result.recognition,errors,checks:['own Codex connection via page','new JPG uploaded via page','actual Codex vision planning','actual own built-in ImageGen complete transparent assets','source SHA registration + shared skill workflow','actual per-layer independent PSD dark/light visual comparison','PSD downloaded by visible web export control','download/final/independent audit SHA agree','native PSD readback','original file bytes unchanged']},null,2));
  fs.unlinkSync(downloaded);console.log('WEB COMPLETED '+JSON.stringify({psd:final,counts,review:result.recognition.reviewStatus}));
 }catch(e){await p.screenshot({path:path.join(out,'网页失败检查.png')}).catch(()=>{});fs.writeFileSync(path.join(out,'网页错误.json'),JSON.stringify({error:e.message,errors},null,2));throw e}
 finally{await c.close();assert(path.resolve(profile).startsWith(path.resolve(tmp)+path.sep));fs.rmSync(profile,{recursive:true,force:true})}
})().catch(e=>{console.error(e.message);process.exitCode=1});
