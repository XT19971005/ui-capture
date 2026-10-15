const fs=require('fs'),crypto=require('crypto');
const {bitmapLayer,rasterTransform}=require('./bitmap_raster.cjs');
const sha=file=>crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
async function checkSource(spec,job,cv,resolveFile,rendered){
 const ref=spec.completeAssetSource;if(!ref)return null;
 if(sha(resolveFile(ref.file))!==ref.sha256.toLowerCase())throw Error('完整源底稿发生改写: '+spec.name);
 const W=job.width,H=job.height,expected=cv.createCanvas(W,H),ec=expected.getContext('2d');
 // Compare the confirmed affine source in the same integer raster frame as
 // PSD layer channels. Global-vs-local fractional draws can differ by one
 // premultiplied quantization step, greatly amplified in low-alpha RGB.
 const source=await cv.loadImage(resolveFile(ref.file)),reference=rasterTransform(source,ref.transform||[1,0,0,1,0,0],cv);ec.drawImage(reference.canvas,reference.left,reference.top);
 const actual=rendered||cv.createCanvas(W,H);
 if(!rendered){const im=await cv.loadImage(resolveFile(spec.file)),layer=bitmapLayer(im,spec,cv);actual.getContext('2d').drawImage(layer.canvas,layer.left,layer.top);}
 const e=ec.getImageData(0,0,W,H).data,r=actual.getContext('2d').getImageData(0,0,W,H).data;let changed=0;
 for(let i=0;i<e.length;i+=4){if(!e[i+3]&&!r[i+3])continue;if(Math.abs(e[i+3]-r[i+3])>1||Math.max(Math.abs(e[i]-r[i]),Math.abs(e[i+1]-r[i+1]),Math.abs(e[i+2]-r[i+2]))>1)changed++;}
 if(changed)throw Error('完整素材与同源 RGBA 底稿不一致，可能混入文字或背景: '+spec.name+'，差异像素 '+changed);
 return {canvas:expected,sourceSHA256:sha(resolveFile(ref.file)),assetSHA256:sha(resolveFile(spec.file)),changedPixels:changed};
}
module.exports={checkSource,sha};
