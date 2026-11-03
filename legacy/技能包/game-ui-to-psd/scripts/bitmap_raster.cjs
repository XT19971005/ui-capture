// Keep the source transform in the sole image sampling step. Raster-layer
// origins must be integers; drawing a resized cache at a fractional origin
// filters it a second time and no longer matches the confirmed source RGBA.
function rasterTransform(image,matrix,cv){
 if(!Array.isArray(matrix)||matrix.length!==6||!matrix.every(Number.isFinite))throw Error('完整素材变换矩阵无效');
 const [a,b,c,d,x,y]=matrix,points=[[0,0],[image.width,0],[image.width,image.height],[0,image.height]].map(([px,py])=>[a*px+c*py+x,b*px+d*py+y]);
 const left=Math.floor(Math.min(...points.map(p=>p[0]))),top=Math.floor(Math.min(...points.map(p=>p[1]))),right=Math.ceil(Math.max(...points.map(p=>p[0]))),bottom=Math.ceil(Math.max(...points.map(p=>p[1])));
 if(right<=left||bottom<=top)throw Error('完整素材变换没有有效覆盖范围');
 const canvas=cv.createCanvas(right-left,bottom-top),context=canvas.getContext('2d');context.setTransform(a,b,c,d,x-left,y-top);context.drawImage(image,0,0);
 return {canvas,left,top,right,bottom};
}
function bitmapLayer(image,spec,cv){
 const x=spec.x??0,y=spec.y??0,width=spec.width??image.width,height=spec.height??image.height;
 if(![x,y,width,height].every(Number.isFinite)||width<=0||height<=0)throw Error('位图坐标或尺寸无效');
 return rasterTransform(image,[width/image.width,0,0,height/image.height,x,y],cv);
}
module.exports={bitmapLayer,rasterTransform};
