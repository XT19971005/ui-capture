const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const edge=path.join(__dirname,'../legacy/拾界插件/插件程序/edge');
function setup(root){let id=0;const c={current:{width:300,height:200,root},structuredClone,ShijieSession:{library:{}},$ :()=>({}),status(){},selected:null,busy:false,scale:1,importFile:async()=>{},ShijieStudio:{start:adapter=>({adapter})}};c.window=c;vm.runInNewContext(fs.readFileSync(path.join(edge,'capture-design.js'),'utf8'),c);c.D=c.CaptureDesign;vm.runInNewContext(fs.readFileSync(path.join(edge,'studio-base.js'),'utf8'),c);c.StudioBase.id=()=>`group-${++id}`;vm.runInNewContext(fs.readFileSync(path.join(edge,'web-studio.js'),'utf8'),c);return c;}
const box=(id,x=0)=>({_sid:id,type:'box',name:id,x,y:10,width:20,height:20,children:[],background:{r:1,g:0,b:0,a:1}});
test('web grouping and ungrouping preserve absolute geometry and layer order',()=>{
 const c=setup({_sid:'root',type:'group',children:[box('a',10),box('b',40),box('c',70)]}),a=c.studio.adapter;
 const before=structuredClone(c.current.root.children),[id]=a.mutate('group',['a','b']);assert.deepEqual(Array.from(c.current.root.children[0].children,n=>n._sid),['a','b']);
 a.mutate('ungroup',[id]);assert.equal(JSON.stringify(c.current.root.children),JSON.stringify(before));
 a.mutate('front',['a']);assert.deepEqual(Array.from(c.current.root.children,n=>n._sid),['b','c','a']);
 a.mutate('back',['a']);assert.deepEqual(Array.from(c.current.root.children,n=>n._sid),['a','b','c']);
});
test('web ungroup refuses to silently discard group appearance',()=>{
 for(const appearance of [{opacity:.5},{visible:false},{clip:true},{displayMask:{enabled:true,type:'rect',x:0,y:0,width:100,height:100}},{layerStyle:{enabled:true,dropShadow:{enabled:true,size:5}}},{background:{r:0,g:0,b:0,a:1}}]){
  const c=setup({_sid:'root',type:'group',children:[{_sid:'g',type:'box',_studioGroup:true,x:0,y:0,width:100,height:100,children:[box('a'),box('b',40)],...appearance}]}),before=JSON.stringify(c.current);
  assert.throws(()=>c.studio.adapter.mutate('ungroup',['g']),/外观设置/);assert.equal(JSON.stringify(c.current),before);
 }
});
test('web cross-parent grouping preserves source ancestry by rejecting the move',()=>{
 const c=setup({_sid:'root',type:'group',children:[{_sid:'clipped',type:'box',clip:true,x:0,y:0,width:30,height:20,children:[box('a')]},box('b',40)]}),before=JSON.stringify(c.current);
 assert.throws(()=>c.studio.adapter.mutate('group',['a','b']),/同一父组/);assert.equal(JSON.stringify(c.current),before);
});
test('duplicating a web child preserves its clipping and opacity ancestry',()=>{
 const c=setup({_sid:'root',type:'group',children:[{_sid:'card',type:'box',clip:true,opacity:.4,x:0,y:0,width:60,height:60,children:[box('a',10)]}]}),a=c.studio.adapter,before=JSON.stringify(c.current.root.children[0].children[0]);
 const [copy]=a.mutate('duplicate',['a']);const item=c.D.index(c.current).get(copy);
 assert.equal(item.parent._sid,'card');assert.equal(item.node.x,34);assert.equal(c.current.root.children.length,1);assert.equal(JSON.stringify(c.current.root.children[0].children[0]),before);
});
test('copy and paste retain the source parent and reject a removed parent without partial insertion',()=>{
 const c=setup({_sid:'root',type:'group',children:[{_sid:'card',type:'box',clip:true,opacity:.4,children:[box('a',10)]}]}),a=c.studio.adapter;
 const copies=a.copy(['a']),[id]=a.paste(structuredClone(copies));assert.equal(c.D.index(c.current).get(id).parent._sid,'card');
 assert.equal(Object.keys(c.D.index(c.current).get(id).node).some(k=>k.includes('Clipboard')),false);
 c.current.root.children=[];const before=JSON.stringify(c.current);
 assert.throws(()=>a.paste(copies),/原父组|重新复制/);assert.equal(JSON.stringify(c.current),before);
});
