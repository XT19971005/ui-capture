// Regression: independent PSD readers must see the same strokes, holes and gradients.
const fs=require('fs'),path=require('path'),assert=require('assert'),cp=require('child_process');
const root=path.resolve(__dirname,'../..'),nm=path.join(root,'依赖/构建工具/node_modules'),cv=require(path.join(nm,'@napi-rs/canvas')),ag=require(path.join(nm,'ag-psd'));
globalThis.document={createElement:()=>cv.createCanvas(1,1)};globalThis.Path2D=cv.Path2D;globalThis.ShijieNodeCanvas=cv;ag.initializeCanvas(cv.createCanvas);cv.GlobalFonts.registerFromPath('C:/Windows/Fonts/arial.ttf','Arial');
const S=require('./scene-native.cjs'),out=path.join(root,'自检记录/Codex图片拆分/原生导出回归');fs.mkdirSync(out,{recursive:true});
(async()=>{
 const scene={format:'shijie-scene',version:2,title:'native',width:320,height:200,nodes:[
  {id:'stroke',name:'Stroke',type:'text',text:'TEST',x:10,y:10,width:180,height:50,fontSize:40,fontFamily:'Arial',fill:'#ffffff',stroke:'#ff0000',strokeWidth:3},
  {id:'hole',name:'Hole with island',type:'path',x:10,y:80,width:90,height:90,fill:'#ff0000',d:'M0 0L90 0L90 90L0 90Z M20 20L70 20L70 70L20 70Z M35 35L55 35L55 55L35 55Z'},
  {id:'gradient',name:'Gradient',type:'text',text:'TEST',x:110,y:90,width:200,height:50,fontSize:40,fontFamily:'Arial',fill:'#ff0000',gradient:{angle:0,stops:[[0,'#ff0000'],[1,'#0000ff']]}},
  {id:'shapegradient',name:'Vector gradient',type:'rect',x:210,y:10,width:90,height:60,fill:'#ff0000',gradient:{angle:0,stops:[[0,'#ff0000'],[1,'#0000ff']]}},
  {id:'italic',name:'Fitted italic',type:'text',text:'STRETCH',x:110,y:150,width:140,height:40,fontSize:40,fontFamily:'Arial',fontWeight:400,fontStyle:'italic',fitWidth:true,fill:'#333333'}
 ],edges:[]};
 fs.writeFileSync(path.join(out,'native.psd'),Buffer.from(await S.psd(scene)));
 const fitted=ag.readPsd(fs.readFileSync(path.join(out,'native.psd'))).children[4];assert(fitted.text.transform[0]<.9,'native fitted text width transform missing');assert(fitted.text.style.font.name.includes('Italic'),'native italic font missing');assert(S.nodeSvg(scene.nodes[4]).includes('font-style="italic"'),'SVG italic missing');
 const python='C:/Users/tuyou/AppData/Local/Programs/Python/Python310/python.exe';
 const script="import sys;sys.path.insert(0,sys.argv[1]);from psd_tools import PSDImage;p=PSDImage.open(sys.argv[2]);stroke=list(p[0].effects);assert any(type(e).__name__=='Stroke' and e.enabled for e in stroke), 'native Stroke missing';paths=list(p[1].vector_mask.paths);assert [q.operation for q in paths]==[1,2,1],str([q.operation for q in paths]);im=p[1].composite(force=True);assert im.getpixel((10,10))[3]>240;assert im.getpixel((25,25))[3]<10;assert im.getpixel((45,45))[3]>240;assert any(type(e).__name__=='GradientOverlay' and e.enabled for e in p[2].effects),'gradient missing';g=p[3].composite(force=True);assert g.getpixel((10,30))[0]>200 and g.getpixel((80,30))[2]>200,'native vector gradient colours wrong';p.composite(force=True).save(sys.argv[3]);print('PASS independent Stroke, subtract hole, combine island, text and vector gradients')";
 const r=cp.spawnSync(python,['-B','-c',script,path.join(root,'../技能包/依赖/python'),path.join(out,'native.psd'),path.join(out,'独立回读.png')],{cwd:root,encoding:'utf8',windowsHide:true});
 assert.equal(r.status,0,r.stderr);console.log(r.stdout.trim());
})().catch(e=>{console.error(e);process.exitCode=1});
