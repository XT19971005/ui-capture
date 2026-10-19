const fs=require('fs'),path=require('path'),assert=require('assert'),{pathToFileURL}=require('url');
const root=path.resolve(__dirname,'../..'),edge=path.join(root,'插件程序/edge'),out=path.join(root,'自检记录/框选与背景'),{chromium}=require(path.join(root,'依赖/构建工具/node_modules/playwright'));
(async()=>{
 const tempRoot=path.resolve(root,'依赖/运行临时'),profile=fs.mkdtempSync(path.join(tempRoot,'edge-entry-'));
 const context=await chromium.launchPersistentContext(profile,{executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true,viewport:{width:1440,height:900},args:['--enable-unsafe-extension-debugging','--disable-extensions-except='+edge,'--load-extension='+edge]});
 const results=[],errors=[];
 try{
  const control=await context.newPage();await control.goto('chrome-extension://lhlcjkecgdccgcheeoalhdibgcldngdf/export.html');
  const source=await context.newPage();await source.goto(pathToFileURL(path.join(out,'框选测试页.html')).href);
  const session=await context.browser().newBrowserCDPSession();
  for(const scope of ['viewport','page','region']){
   console.log('TEST',scope);
   await source.bringToFront();await source.evaluate(()=>scrollTo(0,500));
   const targets=await session.send('Target.getTargets',{filter:[{type:'tab'},{exclude:true}]});const target=targets.targetInfos.find(t=>t.url===source.url());
   await session.send('Extensions.triggerAction',{id:'lhlcjkecgdccgcheeoalhdibgcldngdf',targetId:target.targetId});
   await control.waitForFunction(()=>chrome.extension.getViews({type:'popup'}).some(p=>typeof p.document.getElementById('capture')?.onclick==='function'));
   const opened=context.waitForEvent('page',{timeout:10000});
   await control.evaluate(scope=>{const popup=chrome.extension.getViews({type:'popup'})[0];const select=popup.document.getElementById('scope');if(select.value!=='viewport')throw Error('Default scope must be viewport');if(popup.document.querySelector('#capture span').textContent!=='抓取当前屏幕')throw Error('Default button mismatch');if(scope!=='viewport'){popup.document.querySelector('[data-scope='+scope+']').click();}popup.document.getElementById('capture').click()},scope);
   let editor;try{editor=await opened}catch(e){console.error('POPUP',await control.evaluate(()=>chrome.extension.getViews({type:'popup'}).map(p=>({status:p.document.getElementById('status')?.textContent,handler:typeof p.document.getElementById('capture')?.onclick}))));throw e}editor.on('pageerror',e=>errors.push(e.message));
   if(scope==='region'){
    await source.locator('#shijie-region-selector').waitFor();
    await source.mouse.move(100,100);await source.mouse.down();await source.mouse.move(400,280,{steps:5});await source.mouse.up();await source.keyboard.press('Enter');
   }
   await editor.waitForFunction(()=>typeof busy!=='undefined'&&!busy&&document.getElementById('status').textContent.length>0);
   const info=await editor.evaluate(()=>({status:document.getElementById('status').textContent,ok:!!current,width:current?.width,height:current?.height,scope:current?.scope,texts:current?[...D.index(current).values()].filter(v=>v.node.type==='text').map(v=>v.node.text):[]}));
   results.push({requestedScope:scope,...info});await editor.close();
  }
  fs.writeFileSync(path.join(out,'抓取入口验收.json'),JSON.stringify({defaultScope:'viewport',defaultPopupCaptureTested:true,status:results.every(x=>x.ok)&&!errors.length?'PASS':'FAIL',results,errors},null,2));
  for(const result of results){assert(result.ok,result.requestedScope+': '+result.status);assert(result.texts.includes('框内文字'));assert.equal(result.width,result.requestedScope==='region'?300:1440);assert.equal(result.height,result.requestedScope==='page'?2400:result.requestedScope==='region'?180:900);assert.equal(result.texts.includes('范围之外'),result.requestedScope==='page')}
  assert.deepEqual(errors,[]);console.log('PASS real popup → executeScript → workbench for page, viewport and region/layers');
 }finally{await context.close();const resolved=path.resolve(profile);if(!resolved.startsWith(tempRoot+path.sep))throw Error('Unsafe cleanup target');fs.rmSync(resolved,{recursive:true,force:true})}
})().catch(e=>{console.error(e);process.exitCode=1});
