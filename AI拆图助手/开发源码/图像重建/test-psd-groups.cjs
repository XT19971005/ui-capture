// Real PSD encoding/readback: semantic folders may contain only one leaf.
// Compile source in memory for this test; never rebuild deployed bundles.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),cp=require('node:child_process');
const root=path.resolve(__dirname,'../..'),nm=path.join(root,'依赖/构建工具/node_modules'),cv=require(path.join(nm,'@napi-rs/canvas')),ag=require(path.join(nm,'ag-psd')),esbuild=require(path.join(nm,'esbuild'));
globalThis.document={createElement:()=>cv.createCanvas(1,1)};globalThis.Path2D=cv.Path2D;globalThis.ShijieNodeCanvas=cv;ag.initializeCanvas(cv.createCanvas,(w,h)=>new cv.ImageData(w,h));cv.GlobalFonts.registerFromPath('C:/Windows/Fonts/arial.ttf','Arial');
function source(relative){const filename=path.join(root,relative),result=esbuild.buildSync({entryPoints:[filename],bundle:true,write:false,platform:'node',format:'cjs',nodePaths:[nm],external:['ag-psd'],logLevel:'silent'}),m=new Module(filename,module);m.filename=filename;m.paths=[nm];m._compile(result.outputFiles[0].text,filename);return m.exports;}
const capture=source('插件程序/edge/psd-source.js'),sceneExport=source('开发源码/图像重建/scene-export.js');
const asset=cv.createCanvas(12,10),ctx=asset.getContext('2d');ctx.fillStyle='#e64d33';ctx.fillRect(1,1,10,8);ctx.clearRect(5,4,2,2);const src=asset.toDataURL('image/png');
const image={type:'image',name:'Independent transparent image',x:8,y:8,width:12,height:10,image:src,fit:'STRETCH'};
const text={type:'text',name:'Editable caption',text:'Folder text',x:28,y:25,width:90,height:20,fontFamily:'Arial',fontSize:14,lineHeight:18,color:{r:0,g:0,b:0,a:1},runs:[{text:'Folder text',x:28,y:25,width:90,height:20}]};
const captured={format:'gugu-page-to-figma',version:1,title:'Folder regression',width:140,height:80,root:{type:'group',name:'Semantic root',children:[
 {type:'group',name:'Single-child folder',locked:true,children:[image]},
 {type:'box',name:'Nested semantic folder',x:25,y:20,width:100,height:30,children:[{type:'group',name:'Text subgroup',children:[text]}]},
 {type:'group',name:'Hidden history',visible:false,locked:true,children:[{...image,name:'Hidden image',x:90,y:55},{...text,name:'Hidden editable caption',visible:false,y:50}]}
]}};
const imageScene={format:'shijie-scene',version:2,title:'Image folder regression',width:140,height:80,nodes:[
 {id:'art',type:'image',name:'Independent transparent image',x:8,y:8,width:12,height:10,src},
 {id:'caption',type:'text',name:'Editable caption',text:'Folder text',x:28,y:25,width:90,height:20,fontFamily:'Arial',fontSize:14,fill:'#000000'},
 {id:'history',type:'image',name:'Hidden image',x:90,y:55,width:12,height:10,src,visible:false}
],groups:[{id:'single',name:'Single-child folder',children:['art'],locked:true},{id:'text',name:'Text subgroup',children:['caption']},{id:'nested',name:'Nested semantic folder',children:['text']},{id:'history-group',name:'Hidden history',children:['history'],visible:false,locked:true},{id:'root',name:'Semantic root',children:['single','nested','history-group']}],edges:[]};
function check(bytes,hasHiddenText){const p=ag.readPsd(bytes),top=p.children[0];assert.equal(top.name,'Semantic root');assert.equal(top.children.length,3);const [single,nested,hidden]=top.children;assert.equal(single.name,'Single-child folder');assert(single.children?.length===1,'single-child semantic folder must remain a PSD group');assert(single.protected?.position,'group lock must survive');assert.equal(nested.name,'Nested semantic folder');assert.equal(nested.children[0].name,'Text subgroup');const caption=nested.children[0].children[0];assert.equal(caption.text.text,'Folder text','caption must remain native editable type');assert.equal(hidden.name,'Hidden history');assert(hidden.hidden,'hidden ancestor must remain a hidden PSD group');assert(hidden.protected?.position);assert.equal(hidden.children.length,hasHiddenText?2:1);if(hasHiddenText)assert.equal(hidden.children[1].text.text,'Folder text');const layer=single.children[0],rgba=layer.canvas.getContext('2d').getImageData(0,0,layer.canvas.width,layer.canvas.height).data;assert(rgba.some((v,i)=>i%4===3&&v===0),'image alpha hole must survive');assert(rgba.some((v,i)=>i%4===3&&v===255),'image opaque content must survive');return p;}
(async()=>{const tempRoot=path.join(root,'自检记录');fs.mkdirSync(tempRoot,{recursive:true});const temporary=fs.mkdtempSync(path.join(tempRoot,'psd-group-regression-'));try{
 const rendered=await capture.renderCapture(structuredClone(captured));
 assert.equal(rendered.canvas.getContext('2d').getImageData(92,57,1,1).data[3],0,'hidden image must not enter composite preview');
 assert.equal(rendered.canvas.getContext('2d').getImageData(10,10,1,1).data[3],255,'visible image must remain in composite preview');
 const revealed=structuredClone(captured);revealed.root.children[2].visible=true;
 assert.equal(capture.exportPlan(captured).estimatedPixels,capture.exportPlan(revealed).estimatedPixels,'hidden retained layers must count toward allocation budget');
 const capturedBytes=Buffer.from(capture.encodePSD(rendered));check(capturedBytes,true);fs.writeFileSync(path.join(temporary,'capture.psd'),capturedBytes);
 const imageBytes=Buffer.from(await sceneExport.psd(imageScene));check(imageBytes,false);fs.writeFileSync(path.join(temporary,'image.psd'),imageBytes);
 const script="import sys;sys.path.insert(0,sys.argv[1]);from psd_tools import PSDImage\nfor filename in sys.argv[2:]:\n p=PSDImage.open(filename);r=p[0];assert r.is_group() and r.name=='Semantic root';s,n,h=list(r);assert s.is_group() and len(s)==1;assert n.is_group() and n[0].is_group() and n[0][0].kind=='type';assert n[0][0].text=='Folder text';assert h.is_group() and not h.visible;im=s[0].topil();assert im.mode=='RGBA' and im.getchannel('A').getextrema()==(0,255);print(filename.rsplit('\\\\',1)[-1]+': groups, native type and independent alpha verified')";
 const result=cp.spawnSync('C:/Users/tuyou/AppData/Local/Programs/Python/Python310/python.exe',['-B','-c',script,path.join(root,'../技能包/依赖/python'),path.join(temporary,'capture.psd'),path.join(temporary,'image.psd')],{cwd:root,encoding:'utf8',windowsHide:true});assert.equal(result.status,0,result.stderr);console.log(result.stdout.trim());
 console.log('PASS both source exporters preserve PSD folder hierarchy, hidden history, native text, locks and transparent image leaves');
 }finally{const relative=path.relative(tempRoot,temporary);assert(relative&&!relative.startsWith('..')&&!path.isAbsolute(relative));fs.rmSync(temporary,{recursive:true,force:true});}
})().catch(error=>{console.error(error);process.exitCode=1});
