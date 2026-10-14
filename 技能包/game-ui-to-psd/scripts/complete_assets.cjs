const fs=require('fs'),crypto=require('crypto');
const sha=file=>crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
async function checkSource(spec,job,cv,resolveFile,rendered){
 const ref=spec.completeAssetSource;if(!ref)return null;
 if(sha(resolveFile(ref.file))!==ref.sha256.toLowerCase())throw Error('完整源底稿发生改写: '+spec.name);
 const W=job.width,H=job.height,expected=cv.createCanvas(W,H),ec=expected.getContext('2d');
 if(ref.transform)ec.setTransform(...ref.transform);ec.drawImage(await cv.loadImage(resolveFile(ref.file)),0,0);ec.resetTransform();
 const actual=rendered||cv.createCanvas(W,H);
 if(!rendered){const im=await cv.loadImage(resolveFile(spec.file));actual.getContext('2d').drawImage(im,spec.x||0,spec.y||0,spec.width??im.width,spec.height??im.height);}
 const e=ec.getImageData(0,0,W,H).data,r=actual.getContext('2d').getImageData(0,0,W,H).data;let changed=0;
 for(let i=0;i<e.length;i+=4){if(!e[i+3]&&!r[i+3])continue;if(Math.abs(e[i+3]-r[i+3])>1||Math.max(Math.abs(e[i]-r[i]),Math.abs(e[i+1]-r[i+1]),Math.abs(e[i+2]-r[i+2]))>1)changed++;}
 if(changed)throw Error('完整素材与同源 RGBA 底稿不一致，可能混入文字或背景: '+spec.name+'，差异像素 '+changed);
 return {canvas:expected,sourceSHA256:sha(resolveFile(ref.file)),assetSHA256:sha(resolveFile(spec.file)),changedPixels:changed};
}
module.exports={checkSource,sha};
