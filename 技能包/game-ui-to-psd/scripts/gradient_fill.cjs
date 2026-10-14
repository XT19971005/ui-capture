// A single geometry definition drives Canvas and native Photoshop gradients.
// ag-psd percentages are normalized: scale 1 means 100%, not scale 100.
function geometry(canvas,cv){const d=canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;let l=canvas.width,t=canvas.height,r=0,b=0;for(let y=0;y<canvas.height;y++)for(let x=0;x<canvas.width;x++)if(d[(y*canvas.width+x)*4+3]){l=Math.min(l,x);t=Math.min(t,y);r=Math.max(r,x+1);b=Math.max(b,y+1);}if(r<=l||b<=t)throw Error('空渐变形状');return {l,t,r,b,w:r-l,h:b-t};}
const rgb=s=>({r:parseInt(s.slice(1,3),16),g:parseInt(s.slice(3,5),16),b:parseInt(s.slice(5,7),16)});
function paintGradient(ctx,mask,s,cv){
 const g=s.gradient,style=g.style||'linear',box=geometry(mask,cv);let gradient,angle,cx,cy,scale;
 if(style==='linear'){
  if(!Array.isArray(g.axis)||g.axis.length!==4)throw Error('线性渐变需要四个轴坐标');
  const [x0,y0,x1,y1]=g.axis,dx=x1-x0,dy=y1-y0,length=Math.hypot(dx,dy);if(!length)throw Error('渐变轴长度为零');
  angle=-Math.atan2(dy,dx)*180/Math.PI;cx=(x0+x1)/2;cy=(y0+y1)/2;
  scale=length/(Math.abs(dx/length)*box.w+Math.abs(dy/length)*box.h);gradient=ctx.createLinearGradient(...g.axis);
 }else if(style==='radial'){
  if(!Array.isArray(g.axis)||g.axis.length!==6||g.axis[2]!==0||g.axis[0]!==g.axis[3]||g.axis[1]!==g.axis[4]||g.axis[5]<=0)throw Error('径向渐变必须使用同心圆，内半径为零');
  [cx,cy]=g.axis;angle=0;scale=2*g.axis[5]/box.w;gradient=ctx.createRadialGradient(...g.axis);
 }else throw Error('未实现的可核对渐变类型：'+style);
 const alpha=g.opacityStops||[[0,1],[1,1]],interpolate=(stops,t)=>{let i=0;while(i<stops.length-2&&t>stops[i+1][0])i++;const a=stops[i],b=stops[i+1],u=Math.max(0,Math.min(1,(t-a[0])/(b[0]-a[0])));return a[1]+(b[1]-a[1])*u;};
 const positions=[...new Set([...g.stops.map(x=>x[0]),...alpha.map(x=>x[0])])].sort((a,b)=>a-b);
 for(const position of positions){const col=['r','g','b'].map(key=>Math.round(interpolate(g.stops.map(([t,c])=>[t,rgb(c)[key]]),position))),opacity=interpolate(alpha,position);gradient.addColorStop(position,`rgba(${col.join(',')},${opacity})`);}ctx.fillStyle=gradient;
 return {type:'solid',name:s.name,style,angle,align:true,scale,smoothness:1,offset:{x:(cx-(box.l+box.r)/2)/box.w,y:(cy-(box.t+box.b)/2)/box.h},colorStops:g.stops.map(([location,col])=>({location,midpoint:.5,color:rgb(col)})),opacityStops:alpha.map(([location,opacity])=>({location,midpoint:.5,opacity}))};
}
// Gradient Overlay preserves an editable text layer and its clean glyph cache.
function overlayCanvas(layer,cv){
 const raw=layer.effects?.gradientOverlay,items=raw?(Array.isArray(raw)?raw:[raw]):[];let canvas=layer.canvas;
 for(const fx of items){if(fx.enabled===false||fx.present===false||layer.effects.disabled)continue;if(fx.blendMode&&fx.blendMode!=='normal')throw Error('渐变叠加预览只支持 normal');if((fx.opacity??1)!==1)throw Error('渐变叠加预览只支持完整不透明度');if(fx.type!=='linear')throw Error('文字渐变叠加当前只支持线性');
  const c=cv.createCanvas(canvas.width,canvas.height),ctx=c.getContext('2d');ctx.drawImage(canvas,0,0);ctx.globalCompositeOperation='source-in';const theta=(fx.angle||0)*Math.PI/180,dx=Math.cos(theta),dy=-Math.sin(theta),span=(Math.abs(dx)*c.width+Math.abs(dy)*c.height)*(fx.scale??1),cx=c.width/2+(fx.offset?.x||0)*c.width,cy=c.height/2+(fx.offset?.y||0)*c.height,g=ctx.createLinearGradient(cx-dx*span/2,cy-dy*span/2,cx+dx*span/2,cy+dy*span/2);
  for(const stop of fx.gradient.colorStops){const color=stop.color;g.addColorStop(fx.reverse?1-stop.location:stop.location,`rgb(${color.r},${color.g},${color.b})`);}ctx.fillStyle=g;ctx.fillRect(0,0,c.width,c.height);canvas=c;
 }return canvas;
}
module.exports={paintGradient,overlayCanvas};
