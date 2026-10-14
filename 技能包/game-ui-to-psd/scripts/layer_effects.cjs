// Store effects in native PSD descriptors; rasterize an independent preview only.
const memo=new WeakMap();
const px=v=>typeof v==='number'?v:(v?.value||0);
const css=c=>`rgb(${c?.r??0},${c?.g??0},${c?.b??0})`;
function previewStyle(layer,effect,kind,cv){
 const size=px(effect.size),distance=kind==='dropShadow'?px(effect.distance):0,angle=(effect.angle??120)*Math.PI/180;
 const offsetX=kind==='dropShadow'?-distance*Math.cos(angle):0,offsetY=kind==='dropShadow'?distance*Math.sin(angle):0;
 const pad=Math.ceil(Math.max(size*4,distance)+5),w=layer.canvas.width+pad*2,h=layer.canvas.height+pad*2,c=cv.createCanvas(w,h),ctx=c.getContext('2d');
 if(kind==='stroke'){
  if(effect.fillType&&effect.fillType!=='color')throw Error('预览器尚未实现非纯色描边，请使用实际 Photoshop 生成并检查缓存。');
  const radius=effect.position==='center'?size/2:size;if(effect.position==='inside')throw Error('预览器尚未实现内描边，请使用实际 Photoshop 生成并检查缓存。');
  const steps=Math.max(16,Math.ceil(Math.PI*radius*2));for(let i=0;i<steps;i++){const a=i/steps*Math.PI*2;ctx.drawImage(layer.canvas,pad+Math.cos(a)*radius,pad+Math.sin(a)*radius);}
  ctx.globalCompositeOperation='destination-out';ctx.drawImage(layer.canvas,pad,pad);
 }else{
  ctx.shadowBlur=size*2;ctx.shadowColor='#ffffff';ctx.shadowOffsetX=offsetX;ctx.shadowOffsetY=offsetY;ctx.drawImage(layer.canvas,pad,pad);ctx.shadowBlur=0;ctx.shadowOffsetX=0;ctx.shadowOffsetY=0;
  ctx.globalCompositeOperation='destination-out';ctx.drawImage(layer.canvas,pad,pad);
 }
 ctx.globalCompositeOperation='source-in';ctx.fillStyle=css(effect.color);ctx.fillRect(0,0,w,h);
 return {canvas:c,x:layer.left-pad,y:layer.top-pad,opacity:effect.opacity??1,blend:effect.blendMode||'normal'};
}
function paintEffects(target,layer,cv){
 const effects=layer.effects;if(!effects||effects.disabled)return;
 let styles=memo.get(layer);
 if(!styles){styles=[];for(const [kind,value] of Object.entries(effects)){
  if(['scale','disabled','gradientOverlay'].includes(kind))continue;
  for(const effect of Array.isArray(value)?value:[value]){
   if(effect?.enabled===false||effect?.present===false)continue;
   if(!['outerGlow','dropShadow','stroke'].includes(kind))throw Error('该图层样式尚无可靠本地预览：'+kind+'；请在 Photoshop 生成并核对显示缓存，不能静默丢弃。');
   styles.push(previewStyle(layer,effect,kind,cv));
  }
 }memo.set(layer,styles);}
 for(const style of styles){target.save();target.globalAlpha*=style.opacity;target.globalCompositeOperation=style.blend==='normal'?'source-over':style.blend;target.drawImage(style.canvas,style.x,style.y);target.restore();}
}
module.exports={paintEffects};
