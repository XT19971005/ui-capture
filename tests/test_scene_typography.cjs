const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');

test('letter spacing survives scene metrics, browser SVG and native PSD', async()=>{
  const cv=require('@napi-rs/canvas'),ag=require('ag-psd');
  globalThis.document||={createElement:()=>cv.createCanvas(1,1)};
  globalThis.Path2D||=cv.Path2D;globalThis.ShijieNodeCanvas||=cv;
  ag.initializeCanvas(cv.createCanvas,(w,h)=>new cv.ImageData(w,h));
  const root=path.join(__dirname,'../legacy/拾界插件');
  const native=require(path.join(root,'开发源码/自动拆图/scene-native.cjs'));
  const browser=vm.runInNewContext(fs.readFileSync(path.join(root,'插件程序/edge/image-native.js'),'utf8')+';ShijieScene',
    {document:{createElement:()=>cv.createCanvas(1,1)},Path2D:cv.Path2D,ShijieNodeCanvas:cv,structuredClone,TextEncoder,TextDecoder});
  const base={id:'caption',name:'Subtitle',type:'text',text:'UI DESIN',fontFamily:'Arial',fontSize:32,fontWeight:700,fill:'#ffffff',x:10,y:10,width:420,height:40};
  const spaced={...base,letterSpacing:24,wordSpacing:20};
  const scene=node=>({format:'shijie-scene',version:2,width:460,height:80,title:'Typography',nodes:[node],groups:[],edges:[]});
  for(const renderer of [native,browser]){
    const plain=renderer.metrics(base).width;
    assert(renderer.metrics(spaced).width>plain+180,'tracked text must not collapse to unspaced glyphs');
    assert.equal(renderer.metrics(spaced).actualBoundingBoxLeft,renderer.metrics(base).actualBoundingBoxLeft,'tracking must not move the first glyph');
    assert.equal(renderer.metrics(base).width,plain,'shared canvas spacing must reset');
    assert.match(renderer.svg(scene(spaced)),/letter-spacing="24"/);
    assert.match(renderer.svg(scene(spaced)),/word-spacing="20"/);
    assert.throws(()=>renderer.validate(scene({...spaced,letterSpacing:Infinity})));
  }
  const psd=ag.readPsd(Buffer.from(await native.psd(scene(spaced))));
  assert.equal(psd.children[0].text.text,'UI DESIN');
  assert.equal(psd.children[0].text.styleRuns[0].style.tracking,750);
  assert.equal(psd.children[0].text.styleRuns[1].style.tracking,1375);
  const plainPsd=ag.readPsd(Buffer.from(await native.psd(scene(base))));
  assert(psd.children[0].canvas.width>plainPsd.children[0].canvas.width+180,'PSD bitmap cache must include spaced glyphs');
  for(const renderer of [native,browser]){
    const noto=ag.readPsd(Buffer.from(await renderer.psd(scene({...base,fontFamily:'Noto Sans CJK SC'}))));
    assert.equal(noto.children[0].text.style.font.name,'NotoSansCJKsc-Bold','Photoshop must resolve the real installed PostScript font');
    assert.equal(noto.children[0].text.style.fauxBold,false);
  }
});
