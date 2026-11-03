const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const edge=path.join(__dirname,'../legacy/拾界插件/插件程序/edge');
function helpers(){const c={structuredClone,crypto:require('node:crypto').webcrypto,TextEncoder};c.window=c;for(const file of ['original-annotations.js','free-assistant.js'])vm.runInNewContext(fs.readFileSync(path.join(edge,file),'utf8'),c);return c;}
const plain=v=>JSON.parse(JSON.stringify(v));
test('marks stay separate from source pixels, preserve chronology and reject stale source identity',async()=>{
 const c=helpers(),a=c.ShijieOriginalAnnotations,source='clean-source';const hash=require('node:crypto').createHash('sha256').update(source).digest('hex');
 const empty=a.empty({width:200,height:100},hash),one=a.addStroke(empty,'#ffdf24','角色',a.shapeStroke('rect',[[10,20],[50,60]]));
 const two=a.addStroke(one,'#ff5c87','遮挡',[[80,0],[80,60]],'remove');
 assert.equal(empty.items.length,0);assert.deepEqual(plain(a.undoStroke(two)),plain(one));
 const doc={width:200,height:100,source,nodes:[],_sourceAnnotations:two};
 assert.equal((await a.verifiedPayload(doc)).items.length,2);assert.equal(doc.source,source);
 assert.equal(await a.verifiedPayload({...doc,source:'changed'}),null);
 assert.deepEqual(plain(a.exactSelection(one,'#ffdf24')), {type:'polygon',points:[[10,20],[50,20],[50,60],[10,60],[10,20]]});
 const renamed=a.recolorStroke(two,{color:'#ffdf24',index:0},'#39d8ff');
 assert.deepEqual(plain(renamed.state.order),['#39d8ff','#ff5c87']);assert.equal(two.items[0].color,'#ffdf24');
});
test('assistant discussion never executes and stale or cancelled generation plans cannot apply',async()=>{
 const c=helpers(),a=c.ShijieFreeAssistant;let doc={_projectId:'p',width:100,height:80,source:'image',nodes:[]},ids=[],execute=0,resolve;
 const env={get:()=>doc,ids:()=>ids,request:()=>new Promise(r=>resolve=r),execute:async()=>execute++};const flow=a.createFlow(env);
 let promise=flow.send('先讨论','auto','');resolve({reply:'可以先拆人物',action:'discuss'});await promise;assert.equal(execute,0);
 promise=flow.send('确认生成','auto','');doc.title='changed';resolve({reply:'候选',action:'split'});await assert.rejects(promise,/已改变/);assert.equal(execute,0);
 promise=flow.send('生成','auto','');flow.invalidate();resolve({reply:'候选',action:'split'});await assert.rejects(promise,/已改变/);assert.equal(execute,0);
 promise=flow.send('生成','auto','');resolve({reply:'候选',action:'split'});await promise;assert.equal(execute,1);
});
test('re-splitting archives only the chosen layer and preserves position, parent and whole-project baseline',()=>{
 const {ShijieFreeAssistant:a}=helpers();const node={id:'person',name:'角色',type:'image',x:40,y:20,width:100,height:80};
 const original={nodes:[{id:'back'},node,{id:'front'}],groups:[{id:'parent',children:['back','person','front']}],edges:[],_splitBaseline:{keep:true}};
 const result=a.mergeLayerSplit(original,node,{nodes:[{id:'hat',x:10,y:8,width:30,height:20}]},100,80);
 assert.equal(result.nodes[1].versionArchived,true);assert.equal(result.nodes[2].x,50);assert.equal(result.nodes[2].y,28);
 assert.deepEqual(plain(result._splitBaseline),{keep:true});assert.equal(result.groups[0].children[2],result.groups[1].id);
 assert.equal(original.nodes.length,3);assert.equal(original.nodes[1].versionArchived,undefined);
 assert.throws(()=>a.mergeLayerSplit(original,{...node,width:120},{nodes:[]},100,80),/非等比/);
});
function autosave(){const source=fs.readFileSync(path.join(edge,'studio.js'),'utf8'),timers=new Map(),writes=[];let ident=0,doc={_projectId:'p',revision:0},saved=0,fail=false,blocked=false;
 const c={a:{get:()=>doc,status(){}},B:{id:()=> 'id',library:{isDirty:d=>d.revision!==saved,directory:()=>'/user/projects',put:async(d,o,opts)=>{writes.push({doc:d,opts});if(fail)throw Error('磁盘已满');saved=d.revision;return {}}}},rememberTabProject(){},recoveryState:{style:{}},recoverySaved(){},recoveryError(e){c.error=e.message},autoDirectories:new Map(),autoSaving:false,restoringProject:false,busy:()=>blocked,setTimeout:fn=>{timers.set(++ident,fn);return ident},clearTimeout:id=>timers.delete(id),saveTimer:null};
 vm.runInNewContext(source.slice(source.indexOf(' async function persistRecovery('),source.indexOf('\n function sync('))+';this.save=save;',c);
 return {c,writes,edit:()=>doc.revision++,switch:()=>doc={_projectId:'other',revision:2},fail:()=>fail=true,block:()=>blocked=true,async tick(){const queued=[...timers.values()];timers.clear();for(const fn of queued)await fn()},get pending(){return timers.size}};
}
test('autosave debounces edits, does not save reads and does not write a previous project after switching',async()=>{
 const h=autosave();h.c.save();assert.equal(h.pending,0);h.edit();h.c.save();h.edit();h.c.save();assert.equal(h.pending,1);await h.tick();assert.equal(h.writes.length,1);assert.equal(h.writes[0].opts.automatic,true);
 h.edit();h.c.save();h.switch();await h.tick();assert.equal(h.writes.length,1);
});
test('autosave failure preserves dirty work and reports failure without an endless write retry',async()=>{
 const h=autosave();h.edit();h.fail();h.c.save();await h.tick();assert.equal(h.c.error,'磁盘已满');assert.equal(h.pending,0);assert.equal(h.writes.length,1);
});
