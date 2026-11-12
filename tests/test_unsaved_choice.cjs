const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../legacy/拾界插件/插件程序/edge/studio.js'),'utf8');
const snippet=source.slice(source.indexOf(' async function confirmDiscard('),source.indexOf(' let confirmedNavigation='));
function setup(){let doc={},dirty=true,fail=false;const ctx={a:{get:()=>doc,status:text=>ctx.status=text},B:{library:{isDirty:()=>dirty}},saveBeforeLeaving:async()=>{if(fail)throw Error('磁盘已满');dirty=false}};vm.runInNewContext(snippet+';this.confirmDiscard=confirmDiscard;',ctx);return {ctx,fail:()=>fail=true};}
test('replacing a document waits for its checkpoint',async()=>{const h=setup();assert.equal(await h.ctx.confirmDiscard(),true)});
test('failed checkpoint prevents replacement and preserves a retryable document',async()=>{const h=setup();h.fail();assert.equal(await h.ctx.confirmDiscard(),false);assert.match(h.ctx.status,/磁盘已满/)});
test('confirmed project navigation skips only its own unload check, then restores dirty protection',()=>{
 const timers=[],warnings=[],urls=[];const ctx={reloadRecovery:null,a:{get:()=>({})},B:{library:{isDirty:()=>true}},setTimeout:fn=>timers.push(fn)};
 ctx.location={set href(url){urls.push(url);ctx.warnBeforeUnload({preventDefault:()=>warnings.push('blocked')})}};
 const navigation=source.slice(source.indexOf(' let confirmedNavigation='),source.indexOf('\n const resetButton='));
 vm.runInNewContext(navigation+';this.navigateConfirmed=navigateConfirmed;this.warnBeforeUnload=warnBeforeUnload;',ctx);
 ctx.warnBeforeUnload({preventDefault:()=>warnings.push('blocked')});assert.equal(warnings.length,1);
 ctx.navigateConfirmed('export.html?project=qa');assert.deepEqual(urls,['export.html?project=qa']);assert.equal(warnings.length,1);
 timers.forEach(fn=>fn());ctx.warnBeforeUnload({preventDefault:()=>warnings.push('blocked')});assert.equal(warnings.length,2);
});

const path=require('node:path'),edge=path.join(__dirname,'../legacy/拾界插件/插件程序/edge');
const webSource=fs.readFileSync(path.join(edge,'web-studio.js'),'utf8');
const exportSource=fs.readFileSync(path.join(edge,'export.js'),'utf8');
function importHarness(manual,{failure=false,hold=false}={}){
 const original={_projectId:'old',title:'未保存网页',root:{children:[]}},past=[{title:'撤销记录'}],events=[];
 let release;
 const pending=hold?new Promise(resolve=>release=resolve):Promise.resolve();
 const c={current:original,undo:past,busy:false,events,begin:()=>events.push('read'),finish(){},status:t=>events.push(t),
  StudioBase:{library:{requiresManualExport:manual,isDirty:()=>false},prepareImportedProject:doc=>({...doc,_projectId:'fresh'})},
  ShijieProjectCodec:{readFile:async()=>({_projectId:'existing-on-disk',title:'用户原名',root:{children:[]}})}};
 c.accept=async doc=>{events.push('replace');c.current=doc;c.undo=[]};
 c.window={studio:{adapter:{get:()=>c.current},flush:async options=>{assert.equal(options.leaving,true);events.push('flush');await pending;if(failure)throw Error('磁盘已满')}}};
 const openFile=exportSource.match(/async function importFile\(file\).*?\}\}\$\('file'\)/)[0].replace(/\$\('file'\)$/,'');
 const guard=webSource.slice(webSource.indexOf('/* Manual HTTP imports'),webSource.indexOf('/* Webpage model adapter'));
 vm.runInNewContext(openFile+'\n'+guard,c);return {c,original,past,release:()=>release?.()};
}
for(const manual of [false,true]){
 test((manual?'HTTP':'local-folder')+' external file/drop import waits for the old document checkpoint',async()=>{
  const h=importHarness(manual,{hold:true}),opening=h.c.importFile({name:'outside.json'});
  await Promise.resolve();assert.equal(h.c.current,h.original);assert.deepEqual(h.c.events,['flush']);
  h.release();await opening;assert.equal(h.c.current.title,'用户原名');assert.equal(h.c.current._projectId,'fresh');assert.deepEqual(h.c.events,['flush','read','replace']);
 });
 test((manual?'HTTP':'local-folder')+' failed checkpoint preserves the old document and undo history',async()=>{
  const h=importHarness(manual,{failure:true});await h.c.importFile({name:'outside.json'});
  assert.equal(h.c.current,h.original);assert.equal(h.c.undo,h.past);assert.equal(h.c.events.includes('replace'),false);assert(h.c.events.some(e=>/磁盘已满/.test(e)));
 });
}
test('an edit or project switch during checkpoint cannot be overwritten by the pending import',async()=>{
 for(const switched of [false,true]){
  const h=importHarness(false,{hold:true}),opening=h.c.importFile({name:'outside.json'});
  await Promise.resolve();
  const current=switched?{_projectId:'other',title:'后来打开的工程'}:h.original;
  h.c.current=current;h.c.StudioBase.library.isDirty=()=>!switched;
  h.release();await opening;
  assert.equal(h.c.current,current);assert.equal(h.c.undo,h.past);assert.equal(h.c.events.includes('replace'),false);
 }
});
test('an external project becomes a new local copy with its title, baseline and candidates intact',async()=>{
 const crypto=require('node:crypto').webcrypto,old={_projectId:'existing',title:'用户准确标题',nodes:[],_splitBaseline:{scene:{source:'baseline'}},_assistantCandidates:[{id:'candidate'}]},writes=[];
 const meta={id:'existing',title:old.title,kind:'image',persistedVersion:'disk-v1',source:'local-disk',saveMode:'saved'};
 const c={structuredClone,crypto,ShijieSession:{library:new Map(),legacySaved:async()=>[]},SHIJIE:{sharedCodex:true,user:1},ShijieBrowserProjects:{supported:()=>true},
  ShijieSmartSplit:{savedProjects:async()=>({directory:'folder',projects:[meta]}),projects:async()=>({items:[]}),saveProject:async record=>{writes.push(record);assert.notEqual(record.id,meta.id);assert.equal(record._expectedVersion,null);return {project:{id:record.id,persistedVersion:'new-v1'}}}}};
 c.window=c;vm.runInNewContext(fs.readFileSync(path.join(edge,'studio-base.js'),'utf8'),c);
 assert.equal(typeof c.StudioBase.prepareImportedProject,'function');
 const copy=c.StudioBase.prepareImportedProject(old);assert.notEqual(copy._projectId,old._projectId);assert.equal(copy.title,old.title);assert.deepEqual(copy._splitBaseline,old._splitBaseline);assert.deepEqual(copy._assistantCandidates,old._assistantCandidates);
 await c.StudioBase.library.list();await c.StudioBase.library.put(copy,'image',{manual:true});assert.equal(writes.length,1);assert.equal(old._projectId,'existing');assert.equal(meta.persistedVersion,'disk-v1');
});
test('the image external-file entry point opens a fresh copy while keeping the supplied title',async()=>{
 const imageSource=fs.readFileSync(path.join(edge,'image-editor.js'),'utf8'),fields={};
 const c={$:id=>fields[id]||=( {} ),scene:{_projectId:'old'},task:0,window:{studio:{flush:async()=>{},setInitial(){}}},S:{validate:doc=>doc},
  ShijieProjectCodec:{readFile:async()=>({_projectId:'on-disk',title:'原文件标题'})},StudioBase:{prepareImportedProject:doc=>({...doc,_projectId:'fresh'})},
  ShijieSmartSplit:{releaseSession(){}},checkpoint(){},clearProjectFeedback(){},refresh(){},changed(){},status(){},report(){}};
 vm.runInNewContext(imageSource.slice(imageSource.indexOf("$('project-file').onchange="),imageSource.indexOf("$('save-project').onclick=",imageSource.indexOf("$('project-file').onchange="))),c);
 await fields['project-file'].onchange({target:{files:[{name:'saved.shijie-project'}],value:'saved.shijie-project'}});
 assert.equal(c.scene._projectId,'fresh');assert.equal(c.scene.title,'原文件标题');
});

/* Project filename compatibility regression coverage. */
(()=>{
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),zlib=require('node:zlib');
const crypto=require('node:crypto').webcrypto,edge=path.join(__dirname,'../legacy/拾界插件/插件程序/edge');
function setup(){
 const files=new Map(),settings=new Map();let queue=Promise.resolve();
 const fileHandle=name=>({kind:'file',getFile:async()=>files.get(name),createWritable:async()=>{let content;return {write:async value=>{content=value},close:async()=>files.set(name,content),abort:async()=>{}}}});
 const directory={kind:'directory',name:'自己的工程文件',queryPermission:async()=> 'granted',isSameEntry:async other=>other===directory,
  async *entries(){for(const name of files.keys())yield [name,fileHandle(name)]},getFileHandle:async(name,{create}={})=>{if(!files.has(name)){if(!create)throw Error('missing');files.set(name,new Blob())}return fileHandle(name)},removeEntry:async name=>{files.delete(name)}};
 const database={transaction(){const tx={};tx.objectStore=()=>({get:key=>request(settings.get(key)),put:(value,key)=>{settings.set(key,value);return request(value)}});function request(result){const req={};queueMicrotask(()=>{req.result=result;req.onsuccess();queueMicrotask(()=>tx.oncomplete())});return req}return tx},close(){}};
 const c={crypto,TextEncoder,TextDecoder,CompressionStream,DecompressionStream,Blob,Response,URL,Uint8Array,structuredClone,isSecureContext:true,SHIJIE:{sharedCodex:true,user:1},
  showDirectoryPicker:async()=>directory,indexedDB:{open(){const req={};queueMicrotask(()=>{req.result=database;req.onsuccess()});return req}},
  navigator:{locks:{request(_name,fn){const result=queue.then(fn);queue=result.catch(()=>{});return result}}}};
 c.window=c;vm.createContext(c);vm.runInContext(fs.readFileSync(path.join(edge,'project-codec.js'),'utf8'),c);vm.runInContext(fs.readFileSync(path.join(__dirname,'../shijie/static/server/local-projects.js'),'utf8'),c);
 const record=(id,title='准确中文标题',version='disk-v1',updated=1)=>({id,title,kind:'image',saveMode:'saved',persistedVersion:version,updated,doc:{format:'shijie-scene',version:2,_projectId:id,title,width:12,height:10,nodes:[],edges:[]}});
 function fixture(name,value){const packed=c.ShijieProjectCodec.encode(value),meta={id:value.id,title:value.title,kind:value.kind,saveMode:'saved',storageVersion:'local-disk-v1',persistedVersion:value.persistedVersion,updated:value.updated};const blob=new Blob([JSON.stringify(meta)+'\n',zlib.gzipSync(JSON.stringify({wireFormat:'shijie-image-table',wireVersion:1,job:packed.doc,images:packed.images}))]);files.set(name,blob);return blob}
 const api=c.ShijieBrowserProjects;
 return {c,api,files,record,fixture,connect:()=>api.setDirectory(directory),save:(value,folder,version=null)=>api.request('/saved-projects/'+value.id,{method:'PUT',body:JSON.stringify({...value,_expectedDirectory:folder,_expectedVersion:version})})};
}
test('AI拆图助手工程列表同时读取新旧后缀，外部导入仍按内容兼容',async()=>{
 const h=setup();h.fixture('旧工程.shijie-project',h.record('old'));h.fixture('新工程.aisplit-project',h.record('new'));h.files.set('忽略.txt',new Blob(['not a project']));
 await h.connect();const list=await h.api.request('/saved-projects');assert.deepEqual(Array.from(list.projects,p=>p.id).sort(),['new','old']);
 for(const id of ['old','new']){const result=await h.api.request('/saved-projects/'+id);assert.equal(result.project.id,id)}
 for(const name of ['旧工程.shijie-project','新工程.aisplit-project']){const doc=await h.c.ShijieProjectCodec.readFile(h.files.get(name));assert.equal(doc.title,'准确中文标题')}
});
test('新建使用.aisplit-project，同名不同ID和重复导入不覆盖已有文件',async()=>{
 const h=setup(),old=h.fixture('准确中文标题.aisplit-project',h.record('old')),folder=(await h.connect()).directory;
 await h.save(h.record('new'),folder);assert(h.files.has('准确中文标题（2）.aisplit-project'));assert.equal(h.files.get('准确中文标题.aisplit-project'),old);
 const list=await h.api.request('/saved-projects');assert.equal(list.projects.length,2);assert.equal(h.files.size,2);
});
test('旧后缀显式保存只更新原路径，改变标题也不迁名或生成第二份',async()=>{
 const h=setup();h.fixture('旧文件名.shijie-project',h.record('old'));const folder=(await h.connect()).directory;
 const saved=await h.save(h.record('old','用户修改后的标题'),folder,'disk-v1');assert.equal(h.files.size,1);assert(h.files.has('旧文件名.shijie-project'));
 const opened=await h.api.request('/saved-projects/old');assert.equal(opened.project.title,'用户修改后的标题');assert.equal(opened.project.persistedVersion,saved.project.persistedVersion);
});
test('用户明确改名将单个旧工程改为中文新文件名，不影响其他旧工程',async()=>{
 const h=setup();h.fixture('旧文件名.shijie-project',h.record('old'));const retained=h.fixture('其他旧工程.shijie-project',h.record('other'));
 const folder=(await h.connect()).directory,value=h.record('old','专业中文名称');value.doc._titleSource='manual';
 await h.save(value,folder,'disk-v1');assert(h.files.has('专业中文名称.aisplit-project'));assert.equal(h.files.has('旧文件名.shijie-project'),false);assert.equal(h.files.get('其他旧工程.shijie-project'),retained);
});
test('AI内容识别改变标题时迁移单个旧英文文件，同标题内容编辑仍保留旧路径',async()=>{
 const h=setup();h.fixture('gd-hbimg-edge.shijie-project',h.record('old','gd-hbimg-edge'));const retained=h.fixture('其他旧工程.shijie-project',h.record('other'));
 const folder=(await h.connect()).directory,value=h.record('old','春日麻将活动');value.doc._titleSource='ai';
 await assert.rejects(h.save(value,folder,'stale-version'),/另一个页面/);assert(h.files.has('gd-hbimg-edge.shijie-project'));
 await h.save(value,folder,'disk-v1');assert(h.files.has('春日麻将活动.aisplit-project'));assert.equal(h.files.has('gd-hbimg-edge.shijie-project'),false);assert.equal(h.files.get('其他旧工程.shijie-project'),retained);
 h.fixture('already-ai.shijie-project',h.record('same-title','原有中文标题'));const unchanged=h.record('same-title','原有中文标题');unchanged.doc._titleSource='ai';unchanged.doc.width=20;
 await h.save(unchanged,folder,'disk-v1');assert(h.files.has('already-ai.shijie-project'));assert.equal(h.files.has('原有中文标题.aisplit-project'),false);
});
test('混合后缀中的同ID按最新版本检查冲突，旧版本及同名他人工程保持原样',async()=>{
 const h=setup(),old=h.fixture('旧版.shijie-project',h.record('same','中文标题','v1',1)),other=h.fixture('中文标题.aisplit-project',h.record('other'));
 h.fixture('新版.aisplit-project',h.record('same','新版','v2',2));const folder=(await h.connect()).directory;
 const list=await h.api.request('/saved-projects');assert.equal(list.projects.length,2);assert.equal(list.projects.find(p=>p.id==='same').persistedVersion,'v2');
 await assert.rejects(h.save(h.record('same'),folder,'v1'),/另一个页面/);await assert.rejects(h.save(h.record('same'),folder,null),/另一个页面/);
 await h.save(h.record('same','新版'),folder,'v2');assert.equal(h.files.size,3);assert.equal(h.files.get('旧版.shijie-project'),old);assert.equal(h.files.get('中文标题.aisplit-project'),other);
});
test('refresh cache restores the original save version while real concurrent changes and directory changes stay protected',async()=>{
 const h=setup();h.fixture('旧工程.shijie-project',h.record('old'));await h.connect();
 const makeLibrary=()=>{const c={...h.c,ShijieSession:{library:new Map(),legacySaved:async()=>[]},ShijieSmartSplit:{savedProjects:()=>h.api.request('/saved-projects'),savedProject:(id,directory)=>h.api.request('/saved-projects/'+id+'?directory='+encodeURIComponent(directory)),projects:async()=>({items:[]}),saveProject:record=>h.api.request('/saved-projects/'+record.id,{method:'PUT',body:JSON.stringify(record)})}};c.window=c;vm.runInNewContext(fs.readFileSync(path.join(edge,'studio-base.js'),'utf8'),c);return c.StudioBase.library};
 let library=makeLibrary();const entry=await library.get('old'),doc=entry.doc;doc.title='未保存编辑';
 const data=new Map(),sessionMap=new Map(),session={getItem:k=>sessionMap.get(k),setItem:(k,v)=>sessionMap.set(k,v)},storage=async(k,v,write)=>{if(write){if(v)data.set(k,structuredClone(v));else data.delete(k)}return structuredClone(data.get(k))};
 const scope={window:{},structuredClone,crypto,setTimeout,clearTimeout,Date};vm.runInNewContext(source.slice(0,source.indexOf('/* One interaction model')),scope);
 const cache=scope.window.ShijieReloadRecovery.create({key:'audit',session,storage,delay:5000,snapshotOrigin:doc=>library.snapshotOrigin?.(doc)});
 cache.schedule(doc);await library.put(doc,'image',{checkpoint:true});await library.put(doc,'image',{checkpoint:true});await cache.flush();
 const restored=await cache.read(),origin=cache.origin?.();assert.equal(Object.hasOwn(doc,'origin'),false);
 library=makeLibrary();library.restoreOrigin?.(restored,origin);
 await library.put(restored,'image',{checkpoint:true});
 const stale=makeLibrary();stale.restoreOrigin?.(restored,origin);await assert.rejects(stale.put(restored,'image',{manual:true}),/另一个页面/);
 const legacy=makeLibrary();legacy.restoreOrigin?.(restored);await assert.rejects(legacy.put(restored,'image',{manual:true}),/另存副本|保存版本/);
 const moved=makeLibrary();moved.restoreOrigin?.(restored,{...origin,directory:'different-folder'});await assert.rejects(moved.put(restored,'image',{checkpoint:true}),/目录已切换/);
 const fresh={...doc,_projectId:'new-copy'};await legacy.put(fresh,'image',{manual:true});
});

test('successful persistence schedules refresh cache even when no further edit follows',async()=>{
 const body=source.slice(source.indexOf(' async function persistRecovery('),source.indexOf('\n function save(){'));
 const doc={_projectId:'p'},scheduled=[];
 const c={a:{get:()=>doc,kind:'image',status(){}},B:{library:{put:async()=>({}),isDirty:()=>false}},reloadRecovery:{schedule:value=>scheduled.push(value),flush:async()=>{}},rememberTabProject(){},recoveryState:{style:{}},recoverySaved(){},recoveryError(){},save(){},window:{SHIJIE:{sharedCodex:true}}};
 vm.runInNewContext(body+';this.persist=persistRecovery',c);await c.persist(doc,{checkpoint:true});assert.deepEqual(scheduled,[doc]);
});

test('unknown-origin manual recovery creates a same-title disk version and failures leave the original untouched',async()=>{
 const h=setup(),original=h.fixture('准确中文标题.aisplit-project',h.record('old'));await h.connect();
 let fail=false;const c={...h.c,ShijieSession:{library:new Map(),legacySaved:async()=>[]},ShijieSmartSplit:{savedProjects:()=>h.api.request('/saved-projects'),projects:async()=>({items:[]}),saveProject:record=>{if(fail)throw Error('disk full');return h.api.request('/saved-projects/'+record.id,{method:'PUT',body:JSON.stringify(record)})}}};c.window=c;
 vm.runInNewContext(fs.readFileSync(path.join(edge,'studio-base.js'),'utf8'),c);const lib=c.StudioBase.library,doc=h.record('old').doc,before=structuredClone(doc);lib.restoreOrigin(doc);
 assert.equal(lib.unknownOrigin(doc),true);await assert.rejects(lib.put(doc,'image',{checkpoint:true}),/保存版本/);assert.equal(h.files.size,1);
 fail=true;await assert.rejects(lib.saveRecoveredCopy(doc,'image'),/disk full/);assert.deepEqual(doc,before);assert.equal(h.files.size,1);
 fail=false;const saved=await lib.saveRecoveredCopy(doc,'image');assert.notEqual(saved.id,'old');assert.equal(saved.title,'准确中文标题');assert.deepEqual(doc,before);assert.equal(h.files.get('准确中文标题.aisplit-project'),original);assert(h.files.has('准确中文标题（2）.aisplit-project'));assert.equal(lib.snapshotOrigin(saved.doc).version,saved.persistedVersion);
});

test('网页下载名称只取工程内容标题，空标题使用未命名工程，不加产品前缀',()=>{
 const source=fs.readFileSync(path.join(edge,'export.js'),'utf8'),snippet=source.split(/\r?\n/).find(line=>line.startsWith('function filename('));
 const c={current:{title:'春日麻将活动'}};vm.runInNewContext(snippet+';this.filename=filename',c);
 assert.equal(c.filename('json'),'春日麻将活动.json');c.current.title=' ';assert.equal(c.filename('json'),'未命名工程.json');
});
test('工程库明确改名记录manual来源，后续AI不得覆盖用户标题',async()=>{
 const source=fs.readFileSync(path.join(edge,'studio.js'),'utf8'),start=source.indexOf('const apply=async()=>{const name=input.value.trim();'),end=source.indexOf(";edit.querySelector('#project-name-save').onclick=apply;",start),doc={_projectId:'p',title:'旧标题'},writes=[];
 const c={input:{value:'用户准确中文标题'},edit:{querySelector:()=>({}),close(){}},a:{get:()=>doc,kind:'image',flush:async()=>{},status(){}},p:{id:'p'},clearTimeout(){},saveTimer:null,commit:async(_label,fn)=>fn(),B:{library:{put:async value=>writes.push(structuredClone(value))}},persistRecovery:async value=>writes.push(structuredClone(value)),show(){}};
 vm.runInNewContext(source.slice(start,end)+';this.apply=apply',c);await c.apply();assert.equal(writes[0].title,'用户准确中文标题');assert.equal(writes[0]._titleSource,'manual');
});

test('active rename refresh cache follows the acknowledged disk version after a slow save',async()=>{
 const h=setup();h.fixture('旧工程.shijie-project',h.record('old'));await h.connect();
 const c={...h.c,setTimeout,clearTimeout,ShijieSession:{library:new Map(),legacySaved:async()=>[]},ShijieSmartSplit:{savedProjects:()=>h.api.request('/saved-projects'),savedProject:(id,directory)=>h.api.request('/saved-projects/'+id+'?directory='+encodeURIComponent(directory)),saveProject:record=>h.api.request('/saved-projects/'+record.id,{method:'PUT',body:JSON.stringify(record)})}};c.window=c;
 vm.createContext(c);vm.runInContext(fs.readFileSync(path.join(edge,'studio-base.js'),'utf8'),c);vm.runInContext(source.slice(0,source.indexOf('/* One interaction model')),c);
 const doc=(await c.StudioBase.library.get('old')).doc;let cached,release,closed=false,failed=false;
 const cache=c.ShijieReloadRecovery.create({key:'rename',session:{getItem:()=> 'tab',setItem(){}},storage:async(k,value,write)=>write?(cached=structuredClone(value)):cached,delay:60000,snapshotOrigin:d=>c.StudioBase.library.snapshotOrigin(d)});
 Object.assign(c,{B:c.StudioBase,input:{value:'用户新名称'},edit:{querySelector:()=>({}),close(){closed=true}},a:{get:()=>doc,kind:'image',flush:async()=>{},status(){}},p:{id:'old'},saveTimer:null,commit:async(_label,fn)=>{fn();cache.schedule(doc)},show(){},rememberTabProject(){},reloadRecovery:cache,recoveryState:{style:{}},recoverySaved(){},recoveryError(){failed=true},save(){}});
 vm.runInContext(source.slice(source.indexOf(' async function persistRecovery('),source.indexOf('\n function save(){')),c);
 const start=source.indexOf('const apply=async()=>{const name=input.value.trim();'),end=source.indexOf(";edit.querySelector('#project-name-save').onclick=apply;",start);vm.runInContext(source.slice(start,end)+';this.rename=apply',c);
 c.ProjectThumbnail={render:()=>new Promise(resolve=>release=resolve)};const saving=c.rename();while(!release)await new Promise(resolve=>setImmediate(resolve));await cache.flush();assert.equal(cached.origin.version,'disk-v1');release(undefined);await saving;await cache.flush();
 const disk=await h.api.request('/saved-projects/old');assert.equal(closed,true);assert.equal(cached.origin.version,disk.project.persistedVersion);assert.equal(cached.doc._titleSource,'manual');
 c.ProjectThumbnail=undefined;c.StudioBase.library.restoreOrigin(doc,cached.origin);await c.StudioBase.library.put(doc,'image',{manual:true});
 // A genuine external update must still fail and keep the rename dialog retryable.
 closed=false;await c.rename();assert.equal(failed,false);const stale=c.StudioBase.library.snapshotOrigin(doc);await c.StudioBase.library.put(doc,'image',{manual:true});const externalVersion=c.StudioBase.library.snapshotOrigin(doc).version;c.StudioBase.library.restoreOrigin(doc,stale);closed=false;await c.rename();assert.equal(failed,true);assert.equal(closed,false);assert.equal((await h.api.request('/saved-projects/old')).project.persistedVersion,externalVersion);
 await cache.flush();
});
test('图片导入标题记录import来源，允许已有AI回复按内容识别替换英文文件名',()=>{
 const source=fs.readFileSync(path.join(edge,'image-editor.js'),'utf8'),start=source.indexOf("scene={format:'shijie-scene'"),end=source.indexOf(';selected=',start);
 const c={file:{name:'gd-hbimg-edge.png'},w:12,h:10,source:'image',src:'original',im:{width:12,height:10},uid:()=> 'image'};
 vm.runInNewContext(source.slice(start,end),c);assert.equal(c.scene._titleSource,'import');assert.equal(c.scene.title,'gd-hbimg-edge');
});

})();


// Refresh recovery uses an independent per-tab cache, never the saved-project store.
test('refresh cache round-trips unsaved layers/chat/baseline, isolates tabs, clears closed projects and preserves quota failures',async()=>{
 const scope={window:{},structuredClone,crypto:require('node:crypto').webcrypto,setTimeout,clearTimeout,Date};
 vm.runInNewContext(source.slice(0,source.indexOf('/* One interaction model')),scope);
 const data=new Map(),sessionMap=new Map(),session={getItem:k=>sessionMap.get(k),setItem:(k,v)=>sessionMap.set(k,v)};let fail=false;
 const storage=async(k,v,write)=>{if(write){if(fail)throw Error('quota');if(v)data.set(k,structuredClone(v));else data.delete(k)}return structuredClone(data.get(k))};
 const make=key=>scope.window.ShijieReloadRecovery.create({key,session,storage,delay:5000});
 const a=make('user1:image'),doc={_projectId:'unsaved',title:'中文工程',nodes:[{id:'old',x:23,src:'pixels'}],_assistantChat:{messages:['继续编辑']},_splitBaseline:{source:'initial'}};
 a.schedule(doc);await a.flush();assert.equal(a.pending(),false);assert.deepEqual(await make('user1:image').read(),doc);
 assert.equal(await make('user2:image').read(),null);assert.equal(await make('user1:web').read(),null);
 doc.nodes[0].x=41;a.schedule(doc);fail=true;await assert.rejects(a.flush(),/quota/);assert.equal(a.pending(),true);assert.equal((await a.read()).nodes[0].x,23);
 fail=false;await a.flush();assert.equal((await a.read()).nodes[0].x,41);
 a.schedule(null);await a.flush();assert.equal(await a.read(),null);
});
test('refresh loads current cached edits without generating, new navigation stays blank and explicit links win',async()=>{
 const body=source.slice(source.indexOf(' async function restoreTabProject('),source.indexOf(' function setInitial('));
 for(const [nav,requested,cached,expected] of [['reload',null,{_projectId:'draft'},'draft'],['reload',null,null,'saved'],['navigate',null,{_projectId:'draft'},null],['reload','explicit',{_projectId:'draft'},'explicit']]){
  let doc=null;const loads=[];
  const c={window:{performance:{getEntriesByType:()=>[{type:nav}]},history:{replaceState(){}}},location:{pathname:'/image-editor.html'},a:{kind:'image',get:()=>doc,load:async d=>{doc=d;loads.push(d)},status(){}},B:{library:{get:async id=>({id,kind:'image',doc:{_projectId:id}})}},tabProjectRevision:0,restoringProject:true,reloadRecovery:{read:async()=>cached,schedule(){}},readTabProject:()=>({id:cached?._projectId||'saved'}),rememberTabProject(){},sync(){}};
  vm.runInNewContext(body+';this.restore=restoreTabProject',c);await c.restore(requested);assert.equal(doc?._projectId||null,expected);assert.equal(loads.length,expected?1:0);
 }
});

test('refresh rejects another project cache and resolves the current tab pointer exactly once',async()=>{
 const body=source.slice(source.indexOf(' async function restoreTabProject('),source.indexOf(' function setInitial('));
 for(const [pointer,exists,expected] of [[{id:'B',kind:'image'},true,'B'],[{id:'B',kind:'image'},false,null],[{id:null,kind:'image'},true,null],[{invalid:true},true,null],[null,true,null]]){
  let doc=null,reads=0;const lookups=[],messages=[];
  const c={window:{performance:{getEntriesByType:()=>[{type:'reload'}]}},a:{kind:'image',get:()=>doc,load:async value=>{doc=value},status:text=>messages.push(text)},B:{library:{get:async id=>{lookups.push(id);return exists?{id,kind:'image',doc:{_projectId:id}}:undefined}}},tabProjectRevision:0,restoringProject:true,reloadRecovery:{read:async()=>({_projectId:'A',title:'旧缓存工程'}),schedule(){}},readTabProject:()=>{reads++;return pointer},rememberTabProject(){},sync(){}};
  vm.runInNewContext(body+';this.restore=restoreTabProject',c);await c.restore(null);
  assert.equal(doc?._projectId||null,expected);assert.equal(reads,1);
  assert.deepEqual(lookups,pointer?.id?['B']:[]);
  if(pointer?.id&&!exists)assert(messages.some(text=>/工程|恢复/.test(text)));
 }
});

test('refresh restores cached origin before loading edits and retains the checkpoint directory guard',async()=>{
 const body=source.slice(source.indexOf(' async function restoreTabProject('),source.indexOf(' function setInitial('));
 const draft={_projectId:'p',title:'未保存编辑'},origin={projectId:'p',directory:'original-folder',version:'original-version'},events=[];let doc=null;
 const c={window:{performance:{getEntriesByType:()=>[{type:'reload'}]}},a:{get:()=>doc,load:async value=>{events.push('load');doc=value},status(){}},B:{library:{restoreOrigin:(value,credential)=>{assert.equal(value,draft);assert.equal(credential,origin);events.push('origin');return credential},get:async()=>assert.fail('must not substitute latest disk version')}},tabProjectRevision:0,restoringProject:true,autoDirectories:new Map(),reloadRecovery:{read:async()=>draft,origin:()=>origin},readTabProject:()=>({id:'p'}),rememberTabProject(){},sync(){}};
 vm.runInNewContext(body+';this.restore=restoreTabProject',c);await c.restore(null);assert.deepEqual(events,['origin','load']);assert.equal(doc,draft);assert.equal(c.autoDirectories.get('p'),'original-folder');
});

test('imported owned candidates rebind to the fresh project while unrelated candidates stay isolated',()=>{
 const c={structuredClone,crypto:require('node:crypto').webcrypto,ShijieSession:{library:new Map()}};c.window=c;vm.runInNewContext(fs.readFileSync(path.join(edge,'studio-base.js'),'utf8'),c);
 const old={_projectId:'source',nodes:[],_assistantCandidates:[{version:1,id:'own',projectId:'source',base:{_projectId:'source',nodes:[]},candidate:{_projectId:'source',nodes:[]}},{version:1,id:'foreign',projectId:'other',base:{_projectId:'other'},candidate:{_projectId:'other'}}]};
 const imported=c.StudioBase.prepareImportedProject(old),record=imported._assistantCandidates[0];assert.equal(record.projectId,imported._projectId);assert.equal(record.base._projectId,imported._projectId);assert.equal(record.candidate._projectId,imported._projectId);assert.equal(imported._assistantCandidates[1].projectId,'other');assert.equal(old._assistantCandidates[0].projectId,'source');
});
