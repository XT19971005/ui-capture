const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');

test('standalone HTML preserves text spacing and group opacity in its rendered artwork',()=>{
  const cv=require('@napi-rs/canvas');
  globalThis.document||={createElement:()=>cv.createCanvas(1,1)};
  globalThis.Path2D||=cv.Path2D;globalThis.ShijieNodeCanvas||=cv;
  const root=path.join(__dirname,'../legacy/拾界插件');
  const native=require(path.join(root,'开发源码/自动拆图/scene-native.cjs'));
  const browser=vm.runInNewContext(fs.readFileSync(path.join(root,'插件程序/edge/image-native.js'),'utf8')+';ShijieScene',
    {document:{createElement:()=>cv.createCanvas(1,1)},Path2D:cv.Path2D,ShijieNodeCanvas:cv,structuredClone,TextEncoder,TextDecoder});
  const scene={format:'shijie-scene',version:2,title:'<unsafe>',width:400,height:200,edges:[],
    groups:[{id:'group',name:'Faded group',children:['text'],opacity:0.4}],
    nodes:[{id:'text',type:'text',text:'A B',fontFamily:'Arial',fontSize:30,fontWeight:700,letterSpacing:12,wordSpacing:9,x:10,y:20,width:160,height:40,fill:'#33ccff'}]};
  for(const renderer of [native,browser]){
    const html=renderer.html(scene),art=html.split('<script>')[0];
    assert.match(art,/data-group="group"[^>]*opacity="0.4"/);
    assert.match(art,/letter-spacing="12"/);
    assert.match(art,/word-spacing="9"/);
    assert.match(art,/<title>&lt;unsafe&gt;<\/title>/);
    assert.match(art,/id="fit"/);
  }
});
