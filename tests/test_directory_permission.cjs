const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
function setup(state,active,answer='granted'){
 let requested=0;const source=fs.readFileSync(path.join(__dirname,'../shijie/static/server/local-projects.js'),'utf8');
 const c={navigator:{userActivation:{isActive:active}}};vm.runInNewContext(source.slice(source.indexOf('  async function permission('),source.indexOf('  async function current('))+';this.check=permission',c);
 const handle={kind:'directory',queryPermission:async()=>state,requestPermission:async()=>{requested++;return answer}};
 return {run:()=>c.check(handle),get requested(){return requested}};
}
test('a real user action may renew the same folder permission without selecting another folder',async()=>{const h=setup('prompt',true);await h.run();assert.equal(h.requested,1)});
test('background restore or progress never opens a permission prompt',async()=>{const h=setup('prompt',false);await assert.rejects(h.run(),/权限/);assert.equal(h.requested,0)});
test('denied permission is not repeatedly prompted and keeps the saving error explicit',async()=>{for(const [state,answer,count]of [['denied','granted',0],['prompt','denied',1]]){const h=setup(state,true,answer);await assert.rejects(h.run(),/权限/);assert.equal(h.requested,count)}});
test('an already authorized folder needs no additional request',async()=>{const h=setup('granted',true);await h.run();assert.equal(h.requested,0)});

test('folder picker starts synchronously and asks only for reading',async()=>{
 const source=fs.readFileSync(path.join(__dirname,'../shijie/static/server/local-projects.js'),'utf8');let calls=0;
 const c={available(){},window:{showDirectoryPicker(options){calls++;assert.equal(options.mode,'read');return Promise.resolve({kind:'directory'})}}};
 vm.runInNewContext(source.slice(source.indexOf('  function pickDirectory('),source.indexOf('  async function setDirectory('))+';this.pick=pickDirectory;',c);
 const result=c.pick();assert.equal(calls,1);assert.equal((await result).kind,'directory');
});

test('read-only directory permissions allow opening without asking for write access',async()=>{
 const source=fs.readFileSync(path.join(__dirname,'../shijie/static/server/local-projects.js'),'utf8'),seen=[];
 const c={navigator:{userActivation:{isActive:true}}};vm.runInNewContext(source.slice(source.indexOf('  async function permission('),source.indexOf('  async function current('))+';this.check=permission',c);
 const handle={kind:'directory',queryPermission:async({mode})=>{seen.push(mode);return mode==='read'?'granted':'denied'}};
 await c.check(handle,'read');assert.deepEqual(seen,['read']);
 await assert.rejects(c.check(handle,'readwrite'),/写入|读写/);
});
