const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.join(__dirname,'../legacy/拾界插件'),edge=path.join(root,'插件程序/edge');
function setup(){let id=0;const scene={format:'shijie-scene',version:2,width:300,height:200,nodes:['a','b','c'].map((id,i)=>({id,name:id,type:'rect',x:10+i*50,y:20,width:30,height:40,fill:'#ff0000'})),groups:[],edges:[]};const c={document:{createElement:()=>require('@napi-rs/canvas').createCanvas(1,1)},scene,structuredClone,ShijieSession:{library:{}},S:require(path.join(root,'开发源码/自动拆图/scene-native.cjs')),$:()=>({addEventListener(){}}),status(){},point(){},selected:null,busy:false,scale:1,tool:'select',ShijieStudio:{start:adapter=>({adapter})}};c.window=c;vm.runInNewContext(fs.readFileSync(path.join(edge,'studio-base.js'),'utf8'),c);c.StudioBase.id=()=>`new-${++id}`;vm.runInNewContext(fs.readFileSync(path.join(edge,'image-studio.js'),'utf8'),c);return c;}
test('image layers group, duplicate, reorder, hide and delete without touching original members',()=>{
 const c=setup(),a=c.studio.adapter,original=JSON.stringify(c.scene.nodes),[g]=a.mutate('group',['a','b']);
 const [copy]=a.mutate('duplicate',[g]);assert.equal(c.scene.nodes.length,5);assert.equal(c.scene.groups.length,2);assert.notEqual(copy,g);
 assert.equal(JSON.stringify(c.scene.nodes.filter(n=>['a','b','c'].includes(n.id))),original);
 a.mutate('hide',[copy]);assert.equal(a.entries().get(c.scene.groups.find(n=>n.id===copy).children[0]).visible,false);
 a.mutate('delete',[copy]);assert.equal(c.scene.nodes.length,3);a.mutate('ungroup',[g]);assert.equal(c.scene.groups.length,0);
 a.mutate('front',['a']);assert.deepEqual(Array.from(c.scene.nodes,n=>n.id),['b','c','a']);a.mutate('back',['a']);assert.equal(JSON.stringify(c.scene.nodes),original);
});
test('image inherited locks and styled-group ungroup cannot silently alter work',()=>{
 const c=setup(),a=c.studio.adapter,[g]=a.mutate('group',['a','b']);a.mutate('lock',[g]);const before=JSON.stringify(c.scene);
 assert.throws(()=>a.mutate('delete',['a']),/锁定/);assert.equal(JSON.stringify(c.scene),before);
 a.mutate('lock',[g]);c.scene.groups[0].opacity=.5;assert.throws(()=>a.mutate('ungroup',[g]),/外观设置/);
});
test('selected image export keeps parent opacity and exact padding without mutating the scene',()=>{
 const c=setup(),a=c.studio.adapter,[g]=a.mutate('group',['a','b']);c.scene.groups[0].opacity=.5;const before=JSON.stringify(c.scene),d=a.selectionData(['a'],8,true);
 assert.equal(d.width,46);assert.equal(d.height,56);assert.equal(d.nodes.length,1);assert.equal(d.nodes[0].x,8);assert.equal(d.nodes[0].y,8);assert.equal(d.groups[0].opacity,.5);assert.equal(JSON.stringify(c.scene),before);
});

test('canvas and rotation native geometry scripts deploy with image editor and preserve server digest',()=>{
 const context={window:{},structuredClone};
 for(const name of ['canvas-size.js','manual-rotate.js','split-registration.js']){
  assert.equal(fs.readFileSync(path.join(edge,name),'utf8'),fs.readFileSync(path.join(root,'开发源码/工作台增强',name),'utf8'));
  vm.runInNewContext(fs.readFileSync(path.join(edge,name),'utf8'),context);
  for(const html of ['插件程序/edge/image-editor.html','开发源码/图像重建/image-editor.html'])assert.ok(fs.readFileSync(path.join(root,html),'utf8').includes(name));
  assert.ok(require(path.join(root,'开发源码/图像重建/同步界面模块.cjs')).entries(root).some(item=>item.target===path.join(edge,name)));
 }
 assert.doesNotThrow(()=>context.window.ShijieCanvasSize.validateRect({x:0,y:0,width:3000,height:4000},{}));
 assert.throws(()=>context.window.ShijieCanvasSize.validateRect({x:0,y:0,width:6001,height:10},{}),/上限/);
 assert.doesNotThrow(()=>context.window.ShijieManualRotate.validateRasterSize(3000,4000));
 assert.throws(()=>context.window.ShijieManualRotate.validateRasterSize(6001,2),/上限/);
 assert.ok(fs.readFileSync(path.join(edge,'original-annotations.js'),'utf8').includes('(window.ShijieSession||crypto.subtle).digest'));
});
