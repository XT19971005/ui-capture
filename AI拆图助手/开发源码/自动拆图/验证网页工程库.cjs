const fs=require('fs'),path=require('path'),assert=require('assert');
const root=path.resolve(__dirname,'../..'),nm=path.join(root,'依赖/构建工具/node_modules');
const {chromium}=require(path.join(nm,'playwright')),tmp=path.join(root,'依赖/运行临时'),out=path.join(root,'自检记录/Codex图片拆分');
process.env.TEMP=process.env.TMP=tmp;
(async()=>{
 const profile=fs.mkdtempSync(path.join(tmp,'library-web-'));
 const c=await chromium.launchPersistentContext(profile,{executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true,acceptDownloads:true,viewport:{width:1920,height:1080}});
 const p=await c.newPage(),errors=[];p.on('pageerror',e=>errors.push(e.message));
 try{
  await p.goto('http://127.0.0.1:19217/image-editor.html?library=1');
  await p.getByRole('button',{name:'打开工程 测试',exact:true}).waitFor({timeout:60000});
  await p.screenshot({path:path.join(out,'网页工程库.png')});
  await p.getByRole('button',{name:'打开工程 测试',exact:true}).click();
  await p.waitForFunction(()=>typeof scene!=='undefined'&&scene?.delivery);
  const project=await p.evaluate(()=>({id:scene._projectId,title:scene.title,delivery:scene.delivery,nodes:scene.nodes.length}));assert(project.nodes>3);
  await p.locator('#codex-settings').click();
  await p.waitForFunction(()=>document.querySelector('#codex-connection').textContent.startsWith('已连接'),null,{timeout:90000});
  await p.locator('.codex-dialog form button').click();
  await p.locator('#tab-export').click();await p.locator('#image-export-format').selectOption('psd');
  const event=p.waitForEvent('download',{timeout:90000});await p.locator('#image-export-run').click();const dl=await event;await dl.saveAs(project.delivery.psd);
  const psd=require(path.join(nm,'ag-psd')).readPsd(fs.readFileSync(project.delivery.psd),{skipLayerImageData:true,skipCompositeImageData:true});assert.equal(psd.width,1920);assert.equal(psd.height,896);
  await p.goto('http://127.0.0.1:19217/image-editor.html?project='+project.id);
  await p.waitForFunction(()=>typeof scene!=='undefined'&&scene?.delivery);
  assert.equal(await p.evaluate(()=>scene._projectId),project.id);assert.deepEqual(errors,[]);
  await p.screenshot({path:path.join(out,'直接网页完成.png')});
  fs.writeFileSync(path.join(out,'网页工程库验收.json'),JSON.stringify({status:'PASS',url:'http://127.0.0.1:19217/image-editor.html',library:'http://127.0.0.1:19217/image-editor.html?library=1',project,checks:['fresh browser without extension','durable project imported into library','project opened from visible card','own Codex connected through HTTP','PSD downloaded through visible export button','direct project link reload'],errors},null,2));
  console.log('PASS: direct webpage, library card, own Codex connection, PSD export and direct project reload');
 }catch(e){console.error('PAGE',await p.locator('body').innerText());throw e}
 finally{await c.close();assert(path.resolve(profile).startsWith(path.resolve(tmp)+path.sep));fs.rmSync(profile,{recursive:true,force:true})}
})().catch(e=>{console.error(e);process.exitCode=1});
