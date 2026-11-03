const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.join(__dirname, '../legacy/拾界插件');
const browser = vm.runInNewContext(fs.readFileSync(path.join(root, '插件程序/edge/image-native.js'), 'utf8') + ';ShijieScene');
const fonts = require(path.join(root, '开发源码/自动拆图/fonts.json'));

test('browser and PSD scene validators accept the deployed fonts and still reject unknown families', () => {
  const native = require(path.join(root, '开发源码/自动拆图/scene-native.cjs'));
  const scene = family => ({format:'shijie-scene', version:2, title:'Font check', width:100, height:80,
    nodes:[{id:'caption', type:'text', name:'组件库', text:'组件库', x:5, y:5, width:80, height:30, fontFamily:family, fontSize:20, fill:'#ffffff'}], groups:[], edges:[]});
  for (const validator of [browser, native]) {
    for (const family of new Set(fonts.map(([family]) => family))) assert.doesNotThrow(() => validator.validate(scene(family)));
    assert.throws(() => validator.validate(scene('Unregistered Font')), /字体无效/);
  }
});

test('web PSD and SVG retain deployed Noto and serif font identity and weight', async () => {
  const cv=require('@napi-rs/canvas'),ag=require('ag-psd');
  cv.GlobalFonts.registerFromPath('/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc','Noto Sans CJK SC');
  ag.initializeCanvas(cv.createCanvas,(w,h)=>new cv.ImageData(w,h));
  const context={window:{},ShijieSession:{library:{}},document:{createElement:()=>cv.createCanvas(1,1)},Path2D:cv.Path2D,ShijieNodeCanvas:cv,TextEncoder,TextDecoder,structuredClone};
  const capture=vm.runInNewContext(fs.readFileSync(path.join(root,'插件程序/edge/psd-exporter.js'),'utf8')+';ShijiePSD',context);
  vm.runInNewContext(fs.readFileSync(path.join(root,'插件程序/edge/studio-base.js'),'utf8'),context);
  for(const [family,weight,text,postscript] of [['Noto Sans CJK SC',700,'组件库','NotoSansCJKsc-Bold'],['Noto Serif CJK SC',400,'遗迹背包','NotoSerifCJKsc-Regular'],['Noto Serif CJK SC',700,'装备','NotoSerifCJKsc-Bold'],['Liberation Serif',400,'11.03','LiberationSerif'],['Liberation Serif',700,'11.03','LiberationSerif-Bold']]) {
    if(family==='Noto Serif CJK SC') assert(cv.GlobalFonts.registerFromPath('/usr/share/fonts/opentype/noto/NotoSerifCJK-'+(weight===700?'Bold':'Regular')+'.ttc',family));
    if(family==='Liberation Serif') assert(cv.GlobalFonts.registerFromPath('/usr/share/fonts/truetype/liberation/LiberationSerif-'+(weight===700?'Bold':'Regular')+'.ttf',family));
    const n={type:'text',text,name:'caption',x:10,y:10,width:150,height:45,fontSize:32,fontFamily:family,fontWeight:weight,color:{r:1,g:1,b:1,a:1},runs:[{text,x:10,y:10,width:100,height:45}]};
    const rendered=await capture.renderCapture({format:'shijie-ui-capture',version:1,title:'web',width:200,height:80,root:{type:'group',name:'root',children:[n]}});
    const layer=rendered.psd.children[0].children[0];assert.equal(layer.text.style.font.name,postscript);assert.equal(layer.text.style.fauxBold,false);
    assert(context.window.StudioBase.renderedSVG(rendered).includes('font-family="'+family+'"'));
  }
});
