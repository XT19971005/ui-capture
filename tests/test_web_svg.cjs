const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const edge=path.join(__dirname,'../legacy/拾界插件/插件程序/edge');
const runtime=require('../legacy/技能包/game-ui-to-psd/scripts/style_runtime.cjs');
const context={window:{ShijieLayerStyle:runtime},ShijieSession:{library:{}},structuredClone};
vm.runInNewContext(fs.readFileSync(path.join(edge,'studio-base.js'),'utf8'),context);
const box={x:20,y:20,width:100,height:60};
const outline={operation:'combine',knots:[[20,20],[120,20],[120,80],[20,80]].map(([x,y])=>({points:[x,y,x,y,x,y]}))};
test('web SVG keeps native gradients, masks, effects, blend mode and hidden ancestors',()=>{
 const gradient={kind:'linear',angle:0,scale:1,stops:[[0,'#ff0000'],[1,'#0000ff']]};
 const shape={name:'gradient',left:20,top:20,right:120,bottom:80,_bounds:box,vectorFill:runtime.gradientData(gradient),vectorMask:{paths:[outline]},
  effects:runtime.nativeEffects({dropShadow:{enabled:true,color:'#000000',size:6,opacity:.4,distance:8,angle:120}}),blendMode:'multiply',_displayMask:{enabled:true,type:'ellipse',...box}};
 const svg=context.window.StudioBase.renderedSVG({psd:{width:160,height:120,children:[shape,{name:'hidden-parent',hidden:true,children:[{...shape,name:'must-not-render'}]}]}});
 assert.match(svg,/<linearGradient/);assert.match(svg,/rgb\(255,0,0\)/);assert.match(svg,/rgb\(0,0,255\)/);
 assert.match(svg,/<feGaussianBlur/);assert.match(svg,/mix-blend-mode:multiply/);assert.match(svg,/<clipPath/);assert.doesNotMatch(svg,/must-not-render/);
});
test('web PNG and PSD preview retain gradients away from the origin',async()=>{
 const cv=require('@napi-rs/canvas'),c={document:{createElement:()=>cv.createCanvas(1,1)},Path2D:cv.Path2D,ShijieNodeCanvas:cv,structuredClone,TextEncoder,TextDecoder};
 const api=vm.runInNewContext(fs.readFileSync(path.join(edge,'psd-exporter.js'),'utf8')+';ShijiePSD',c);
 const r=await api.renderCapture({format:'shijie-ui-capture',version:1,width:160,height:120,root:{type:'group',children:[{type:'box',name:'gradient',...box,gradient:{kind:'linear',angle:0,scale:1,stops:[[0,'#ff0000'],[1,'#0000ff']]}}]}});
 const pixel=(x,y)=>r.canvas.getContext('2d').getImageData(x,y,1,1).data;
 assert.equal(pixel(25,45)[3],255);assert.equal(pixel(115,45)[3],255,'translated canvas must not erase the right side');
 assert(pixel(25,45)[0]>pixel(25,45)[2]);assert(pixel(115,45)[2]>pixel(115,45)[0]);
});
