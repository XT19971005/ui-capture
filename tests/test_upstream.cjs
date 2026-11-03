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

function expansionHarness(){
 const canvas=require('@napi-rs/canvas'),c={structuredClone,crypto:require('node:crypto').webcrypto,TextEncoder};c.window=c;
 vm.runInNewContext(fs.readFileSync(path.join(edge,'image-replace.js'),'utf8'),c);
 c.document={createElement:()=>canvas.createCanvas(1,1)};
 c.Image=class extends canvas.Image{constructor(){super();this.ready=new Promise((resolve,reject)=>{this.onload=resolve;this.onerror=reject});this.ready.catch(()=>{})}set src(v){super.src=v.startsWith('data:image/svg+xml;charset=utf-8,')?Buffer.from(decodeURIComponent(v.split(',').slice(1).join(','))):v}decode(){return this.ready}};
 c.ShijieLayerStyle=require('../legacy/技能包/game-ui-to-psd/scripts/style_runtime.cjs');
 return {api:c.ShijieImageReplacement,canvas};
}
test('canvas expansion ignores transparent padding and hidden groups without altering any asset pixels',async()=>{
 const {api,canvas}=expansionHarness(),asset=canvas.createCanvas(400,400);asset.getContext('2d').fillRect(100,100,50,80);const src=asset.toDataURL('image/png');
 const doc={width:200,height:200,source:canvas.createCanvas(200,200).toDataURL('image/png'),nodes:[{id:'a',type:'image',src,x:-100,y:-100,width:400,height:400},{id:'hidden',type:'rect',x:-999,y:-999,width:500,height:500}],groups:[{id:'hidden-group',visible:false,children:['hidden']}]};
 const before=JSON.stringify(doc);await api.growToFit(doc);assert.equal(JSON.stringify(doc),before);
});
test('canvas expansion retains alpha=1 edges, moves marks and archived geometry together, and pads original pixels',async()=>{
 const {api,canvas}=expansionHarness(),asset=canvas.createCanvas(40,40),ax=asset.getContext('2d');ax.fillRect(10,10,20,20);const dot=ax.createImageData(1,1);dot.data.set([255,0,0,1]);ax.putImageData(dot,0,4);
 const original=canvas.createCanvas(20,20);original.getContext('2d').fillStyle='#336699';original.getContext('2d').fillRect(0,0,20,20);const source=original.toDataURL('image/png'),src=asset.toDataURL('image/png');
 const marks={version:1,width:20,height:20,sourceHash:require('node:crypto').createHash('sha256').update(source).digest('hex'),items:[{strokes:[[[2,3],[4,5]]]}]};
 const doc={width:20,height:20,source,nodes:[{id:'a',type:'image',src,x:-10,y:-10,width:40,height:40},{id:'old',versionArchived:true,x:-100,y:-100,width:400,height:400}],groups:[],_sourceAnnotations:marks};
 await api.growToFit(doc);assert.deepEqual([doc.width,doc.height],[30,26]);assert.deepEqual([doc.nodes[0].x,doc.nodes[0].y],[0,-4]);assert.equal(doc.nodes[0].src,src);assert.deepEqual([doc.nodes[1].x,doc.nodes[1].y],[-90,-94]);assert.deepEqual(plain(doc._sourceAnnotations.items[0].strokes[0]),[[12,9],[14,11]]);assert.deepEqual(marks.items[0].strokes[0],[[2,3],[4,5]]);
 const image=await canvas.loadImage(doc.source),out=canvas.createCanvas(30,26);out.getContext('2d').drawImage(image,0,0);assert.deepEqual([...out.getContext('2d').getImageData(10,6,1,1).data],[51,102,153,255]);assert.equal(out.getContext('2d').getImageData(0,0,1,1).data[3],0);
});
test('unreadable expanded image fails before changing the project',async()=>{
 const {api,canvas}=expansionHarness(),doc={width:20,height:20,source:canvas.createCanvas(20,20).toDataURL('image/png'),nodes:[{id:'a',type:'image',src:'data:image/png;base64,bad',x:-10,y:-10,width:40,height:40}],groups:[]},before=JSON.stringify(doc);
 await assert.rejects(api.growToFit(doc));assert.equal(JSON.stringify(doc),before);
});

test('recovering an expanded generated task keeps completed feet inside the restored canvas and export bounds',async()=>{
 const {api,canvas}=expansionHarness(),source=canvas.createCanvas(20,20),asset=canvas.createCanvas(20,30);asset.getContext('2d').fillRect(5,0,10,30);
 const src=asset.toDataURL('image/png'),scene={format:'shijie-scene',version:2,width:20,height:20,source:source.toDataURL('image/png'),nodes:[{id:'person',type:'image',src,x:0,y:0,width:20,height:30,generationRecord:{expandedCanvas:true}}],groups:[]};
 let onLoad,restored,initial;const status={},studio={adapter:{load:async doc=>{restored=structuredClone(doc);}},setInitial:doc=>{initial=structuredClone(doc);},sync(){}};
 const context={URLSearchParams,location:{search:'?job=complete'},studio,ShijieImageReplacement:api,
  document:{currentScript:{dataset:{prefix:'',user:'2',csrf:'test'}},querySelector:()=>null,getElementById:()=>status},
  fetch:async()=>({ok:true,json:async()=>({status:'completed',result:structuredClone(scene)})})};
 context.window=context;context.addEventListener=(_,callback)=>{onLoad=callback;};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../shijie/static/server/bootstrap.js'),'utf8'),context);
 await onLoad();assert(restored,status.textContent);assert.deepEqual([restored.width,restored.height],[20,30]);assert.equal(restored.nodes[0].src,src);assert.deepEqual(initial,restored);
 assert.equal((await canvas.loadImage(restored.source)).height,30);assert.equal(scene.height,20);
});

test('expanded split preview puts the original at the same origin and scale as the candidate',async()=>{
 const {api,canvas}=expansionHarness(),source=canvas.createCanvas(20,20);source.getContext('2d').fillStyle='#336699';source.getContext('2d').fillRect(0,0,20,20);
 const doc={format:'shijie-scene',version:2,width:20,height:20,source:source.toDataURL('image/png'),nodes:[{id:'original',type:'rect',fill:'#336699',x:0,y:0,width:20,height:20,src:source.toDataURL('image/png')}],groups:[],edges:[]},candidate=structuredClone(doc);
 candidate.nodes[0].type='image';candidate.nodes[0].x=-10;candidate.nodes[0].y=-6;
 const S=require('../legacy/拾界插件/开发源码/自动拆图/scene-native.cjs'),script=fs.readFileSync(path.join(edge,'free-assistant.js'),'utf8');
 const start=script.indexOf('if(result._partial)candidate._partial=true;'),end=script.indexOf("if(!isCurrent())throw Error('工程或选区已改变');",start);
 const context={result:{},candidate,doc,scope:{annotations:{allowExpand:true}},ShijieImageReplacement:api,sceneImage:d=>'data:image/svg+xml;charset=utf-8,'+encodeURIComponent(S.svg(d))};
 const before=await vm.runInNewContext('(async()=>{'+script.slice(start,end)+';return comparisonBefore})()',context);
 const im=await canvas.loadImage(before);assert.deepEqual([im.width,im.height],[30,26]);
 const out=canvas.createCanvas(30,26),cx=out.getContext('2d');cx.drawImage(im,0,0);assert.deepEqual([...cx.getImageData(10,6,1,1).data],[51,102,153,255]);assert.equal(cx.getImageData(0,0,1,1).data[3],0);assert.deepEqual([candidate.nodes[0].x,candidate.nodes[0].y],[0,0]);assert.equal(doc.width,20);
});
