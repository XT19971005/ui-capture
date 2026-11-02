// Offline evidence/geometry kernel. No browser, model, server or PSD export.
const fs=require('node:fs'),path=require('node:path'),root=path.resolve(__dirname,'../..'),nm=path.join(root,'依赖/构建工具/node_modules'),cv=require(path.join(nm,'@napi-rs/canvas'));
const input=JSON.parse(fs.readFileSync(0,'utf8'));
(async()=>{if(input.operation==='union'){
 let union=null;for(const n of input.nodes){const p=new cv.Path2D(n.d);p.setFillType(cv.FillType.EvenOdd);const moved=p.transform({a:1,b:0,c:0,d:1,e:n.x-input.box.x,f:n.y-input.box.y});union=union?union.op(moved,cv.PathOp.Union):moved;}if(!union)throw Error('没有可联合的原生路径');process.stdout.write(JSON.stringify({d:union.toSVGString(),bounds:union.computeTightBounds()}));return;
 }
 if(input.operation!=='preview')throw Error('未知选集原生操作');globalThis.document={createElement:()=>cv.createCanvas(1,1)};globalThis.Path2D=cv.Path2D;globalThis.ShijieNodeCanvas=cv;
 for(const [file,name] of [['arial.ttf','Arial'],['msyh.ttc','Microsoft YaHei'],['msyhbd.ttc','Microsoft YaHei'],['simhei.ttf','SimHei'],['impact.ttf','Impact'],['arialn.ttf','Arial Narrow']])cv.GlobalFonts.registerFromPath('C:/Windows/Fonts/'+file,name);
 const S=require('./scene-native.cjs'),image=await cv.loadImage(Buffer.from(S.svg(input.scene))),{x,y,width,height}=input.box;
 for(const [label,fill] of [['dark','#18191c'],['light','#f0f0f0']]){const c=cv.createCanvas(width,height),ctx=c.getContext('2d');ctx.fillStyle=fill;ctx.fillRect(0,0,width,height);ctx.drawImage(image,-x,-y);fs.writeFileSync(input.prefix+'-'+label+'.png',c.toBuffer('image/png'));}process.stdout.write(JSON.stringify({status:'RENDERED_SELECTION_ONLY'}));
})().catch(e=>{console.error(e.message);process.exitCode=1});
