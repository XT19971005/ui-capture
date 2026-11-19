const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
function api(){const c={window:{},structuredClone};vm.runInNewContext(fs.readFileSync(path.join(__dirname,'free-assistant.js'),'utf8'),c);return c.window.ShijieFreeAssistant;}
test('batch dropdown lists only current remaining independent resources and clamps its default',()=>{const a=api(),six=a.batchOptions(6);assert.deepEqual(Array.from(six.options),[1,2,3,4,5,6,0]);assert.equal(six.selected,'4');assert.equal(a.batchOptions(3).selected,'3');assert.equal(a.batchOptions(6,'128').selected,'6');assert.equal(a.batchOptions(6,'0').selected,'0');const empty=a.batchOptions(0);assert.equal(empty.disabled,true);assert.equal(empty.options.length,0)});
test('eight independent images with two complete permit only six while same-resource positions count once',()=>{const a=api(),layers=Array.from({length:8},(_,i)=>({name:'图片'+i,layerType:'image'})),schedule={plan:{layers},completed:[{_generationPlanIndex:0},{_generationPlanIndex:1}],scope:{}};assert.equal(a.imageBatchMaximum(schedule),6);layers.push({name:'同款位置',layerType:'image',reuseOf:2});assert.equal(a.imageBatchMaximum(schedule),6);schedule.completed.push({_generationPlanIndex:2});assert.equal(a.imageBatchMaximum(schedule),6,'the unfinished linked position is still one processable resource');schedule.completed.push({_generationPlanIndex:8});assert.equal(a.imageBatchMaximum(schedule),5)});
test('all is bounded by the actual current maximum before transmission',()=>{const a=api();assert.equal(a.imageBatchLimit(6,'0'),6);assert.equal(a.imageBatchLimit(6,'128'),6);assert.equal(a.imageBatchLimit(0,'0'),0);assert.equal(a.imageBatchLimit(3,undefined),3);assert.equal(a.imageBatchLimit(6,'bad'),4);});
test('UI never constructs a fixed 128-entry material list',()=>{const source=fs.readFileSync(path.join(__dirname,'free-assistant.js'),'utf8');assert(!source.includes("Array.from({length:128},(_,i)=>'<option"));assert(source.includes('proposal.totalResources'));});

test('ordinary remaining images are not disabled by unrelated or negative annotation reuse evidence',()=>{const a=api(),layers=Array.from({length:8},(_,i)=>({name:'图片'+i,layerType:'image'})),schedule={plan:{layers},completed:[{_generationPlanIndex:0},{_generationPlanIndex:1}],scope:{annotations:{items:[{layerType:'vector',reuseEvidence:'不是同款，不可复用'},{layerType:'image',reuseEvidence:'此处无相同素材'}]}}};assert.equal(a.imageBatchMaximum(schedule),6);const options=a.batchOptions(a.imageBatchMaximum(schedule));assert.equal(options.disabled,false);assert.deepEqual(Array.from(options.options),[1,2,3,4,5,6,0]);});

test('image fit keeps the same scroll world when an ordinary layer is hidden or shown',()=>{const source=fs.readFileSync(path.join(__dirname,'../图像重建/image-editor.js'),'utf8'),start=source.indexOf('function fit('),end=source.indexOf('\n',start),node={id:'background',x:-2000,y:-1500,width:3000,height:2300},view={clientWidth:600,clientHeight:500,_left:100,_top:100,get scrollLeft(){return this._left},set scrollLeft(v){this._left=Math.max(0,v)},get scrollTop(){return this._top},set scrollTop(v){this._top=Math.max(0,v)}},els={viewport:view,'image-world':{style:{}},board:{style:{}},zoom:{value:'1'},zoomlabel:{},dimensions:{}},scope={scene:{source:'source',width:1000,height:800,nodes:[node]},scale:1,imageOrigin:{x:2300,y:1750},imageDisplayScale:1,imageViewSource:'source',$:id=>els[id],selection(){},window:{studio:{overlay(){}}}};vm.runInNewContext(source.slice(start,end),scope);scope.fit();const read=()=>JSON.stringify({origin:scope.imageOrigin,world:els['image-world'].style,board:els.board.style,scroll:[view.scrollLeft,view.scrollTop],scale:scope.scale,zoom:els.zoom.value}),before=read();node.visible=false;scope.fit();assert.equal(read(),before);node.visible=true;scope.fit();assert.equal(read(),before);assert.deepEqual([node.x,node.y,node.width,node.height],[-2000,-1500,3000,2300]);});
test('layer control pointerdown preserves the current focus instead of focusing a soon-rebuilt eye button',()=>{const source=fs.readFileSync(path.join(__dirname,'studio.js'),'utf8'),line=source.split('\n').find(line=>line.includes("layerRoot.addEventListener('pointerdown',e=>{if(e.target.closest('.studio-layer-controls'))"));let listener,prevented=0,stopped=0;vm.runInNewContext(line,{a:{layerRoot:{addEventListener:(_name,fn)=>listener=fn}}});listener({target:{closest:()=>({})},preventDefault:()=>prevented++,stopImmediatePropagation:()=>stopped++});assert.equal(prevented,1);assert.equal(stopped,1);});

test('unprepared annotated images show a selectable pending batch, never completed',()=>{
 const a=api(),marks={items:Array.from({length:4},(_,i)=>({color:'#00000'+i,label:'图片'+i,layerType:'image',purpose:'keep',strokes:[[[0,0],[1,1]]]}))};
 const display=a.imageBatchDisplay({plan:null,coverage:{total:4}},marks,[]);assert.equal(display.maximum,4);assert.equal(display.emptyLabel,'待分析');assert.equal(a.batchOptions(display.maximum).selected,'4');
 marks.items.push({layerType:'image',purpose:'remove',strokes:[[[0,0],[1,1]]]});marks.items.push({layerType:'image',strokes:[]});assert.equal(a.imageBatchDisplay({plan:null},marks,[]).maximum,4);
});
test('batch only says generated after plan images are delivered, and distinguishes incomplete plans',()=>{
 const a=api(),plan={layers:[{name:'01 图片',layerType:'image'}]},view={plan,missing:0};
 assert.equal(a.imageBatchDisplay(view,null,[]).maximum,1);
 assert.equal(a.imageBatchDisplay(view,null,[{_generationPlanIndex:0}]).emptyLabel,'图片已生成');
 assert.equal(a.imageBatchDisplay({...view,missing:2},null,[{_generationPlanIndex:0}]).emptyLabel,'待补齐方案');
 assert.equal(a.imageBatchDisplay({plan:{layers:[]}},null,[]).emptyLabel,'待分析');
});
test('assistant has no standalone split-and-keep checklist UI',()=>{
 const source=fs.readFileSync(path.join(__dirname,'free-assistant.js'),'utf8');assert(!source.includes("objectReport.setAttribute('aria-label'"));assert(!source.includes('renderObjectReport();'));
});

test('stationary pointer dots do not turn four delivered annotated images into three',()=>{
 const a=api(),colors=['#ffdf24','#ff5c87','#39d8ff','#a78bfa'],marks={items:colors.map((color,i)=>({color,layerType:'image',strokes:[[[i*30,0],[i*30+20,0],[i*30+20,20],[i*30,20],[i*30,0]]]}))},layers=colors.map((_,i)=>({name:String(i+1).padStart(2,'0')+' image',layerType:'image',box:{x:i*30,y:0,width:20,height:20}})),completed=layers.map((_,i)=>({_generationPlanIndex:i}));
 marks.items[0].strokes.push([[-90,296.4],[-90,296.4],[-90,296.4]]);
 const coverage=a.stageCoverage(marks,layers,'image',completed);assert.equal(coverage.covered,4);assert.equal(coverage.missing.length,0);
 assert.equal(a.stageCoverage(marks,layers,'image',completed.slice(0,3)).covered,3,'a truly undelivered object still remains incomplete');
});

test('incomplete image plans cannot silently submit only one when four were marked',()=>{
 const a=api(),marks={items:['#ffdf24','#ff5c87','#39d8ff','#a78bfa'].map((color,i)=>({color,layerType:'image',strokes:[[[i*30,0],[i*30+20,0],[i*30+20,20],[i*30,20],[i*30,0]]]}))},layers=[{name:'01 background',layerType:'image',box:{x:0,y:0,width:20,height:20}}];
 assert.throws(()=>a.requireImagePlanCoverage(marks,layers),/02.*03.*04/);
 assert.doesNotThrow(()=>a.requireImagePlanCoverage({items:[marks.items[0]]},layers));
 const request=a.annotationRequest(marks,null,{preferredStage:'image'});assert.match(request,/4个/);assert.match(request,/当前选中/);
});

test('continue repairs missing marked images after the only prepared image was already delivered',()=>{
 const a=api(),marks={items:['#ffdf24','#ff5c87'].map((color,i)=>({color,layerType:'image',strokes:[[[i*30,0],[i*30+20,0],[i*30+20,20],[i*30,20],[i*30,0]]]}))},d={_projectId:'p',source:'original',width:100,height:100,nodes:[],_sourceAnnotations:marks},s={version:1,projectId:'p',bindingSource:'original',bindingWidth:100,bindingHeight:100,bindingAnnotations:structuredClone(marks),analysisStage:'image',scope:{node:null,annotations:marks},plan:{layers:[{name:'01 image',layerType:'image',box:{x:0,y:0,width:20,height:20}}]},completed:[{_generationPlanIndex:0}]};d._generationStages=s;
 assert.equal(a.continuationStage(d,'继续拆分'),s);assert.equal(a.continuationStage(d,'继续拆分',null,{src:'reference'}),null);
});
