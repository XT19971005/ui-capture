// Compare actual native glyphs at a uniform scale, never stretch a broad font.
const fs=require('fs'),path=require('path'),root=path.resolve(__dirname,'../..'),cv=require(path.join(root,'依赖/构建工具/node_modules/@napi-rs/canvas'));
const input=JSON.parse(fs.readFileSync(0,'utf8')),target=Buffer.from(input.mask,'base64'),w=input.width,h=input.height;
const defaults=[['arial.ttf','Arial',400],['arialbd.ttf','Arial',700],['msyh.ttc','Microsoft YaHei',400],['msyhbd.ttc','Microsoft YaHei',700],['simhei.ttf','SimHei',400],['impact.ttf','Impact',400],['arialn.ttf','Arial Narrow',400],['arialnb.ttf','Arial Narrow',700],['HATTEN.TTF','Haettenschweiler',400]];
let fonts=input.fonts||defaults.filter(([,family])=>!/[\u4e00-\u9fff]/.test(input.text)||['Microsoft YaHei','SimHei'].includes(family)).map(([file,family,weight])=>({file:'C:/Windows/Fonts/'+file,family,weight}));
fonts=fonts.filter(f=>fs.existsSync(f.file)&&cv.GlobalFonts.registerFromPath(f.file,f.family));
const lines=String(input.text).replace(/\r\n?/g,'\n').split('\n'),skews=input.skews||[input.skew||0];
const measure=cv.createCanvas(1,1).getContext('2d');let best=null;const candidates=[];
function metrics(family,weight,size){
 measure.font=`${weight} ${size}px "${family}"`;const rows=lines.map(t=>measure.measureText(t));
 const ascent=rows[0].actualBoundingBoxAscent||size*.85,descent=rows.at(-1).actualBoundingBoxDescent||0;
 const leading=input.lineHeight||size*1.2;
 return {ascent,descent:descent+(lines.length-1)*leading,leading,left:Math.max(...(lines.length>1?[0]:[]),...rows.map(m=>m.actualBoundingBoxLeft||0)),right:Math.max(...rows.map(m=>m.actualBoundingBoxRight||m.width))};
}
for(const {family,weight} of fonts)for(const skew of skews){
 const ref=metrics(family,weight,100),fixedLines=input.lineHeight?(lines.length-1)*input.lineHeight:0;
 const denominator=input.lineHeight?ref.ascent+ref.descent-(lines.length-1)*ref.leading:ref.ascent+ref.descent;
 const nominal=Math.max(6,Math.round((h-fixedLines)*100/Math.max(1,denominator)));
 for(let size=Math.max(6,nominal-2);size<=Math.min(6000,nominal+2);size++){
  const m=metrics(family,weight,size),bw=m.left+m.right+skew*(m.ascent+m.descent),bh=m.ascent+m.descent;
  const cw=Math.max(w,Math.ceil(bw))+2,ch=Math.max(h,Math.ceil(bh))+2;
  if(cw>6000||ch>6000||cw*ch>6000000)continue;
  const canvas=cv.createCanvas(cw,ch),c=canvas.getContext('2d');c.font=`${weight} ${size}px "${family}"`;
  c.setTransform(1,0,-skew,1,m.left+skew*m.descent,m.ascent);c.fillStyle='white';
  lines.forEach((text,i)=>c.fillText(text,0,i*m.leading));
  const rgba=c.getImageData(0,0,cw,ch).data;let intersection=0,union=0,area=0,targetArea=0;
  for(let y=0;y<ch;y++)for(let x=0;x<cw;x++){
   const actual=rgba[(y*cw+x)*4+3]>128,expected=x<w&&y<h&&target[y*w+x]>0;
   if(actual)area++;if(expected)targetArea++;if(actual&&expected)intersection++;if(actual||expected)union++;
  }
  const iou=intersection/Math.max(1,union),densityError=Math.abs(area-targetArea)/Math.max(1,targetArea);
  const aspectError=Math.abs(bw-w)/Math.max(1,w)+Math.abs(bh-h)/Math.max(1,h),score=iou-.5*densityError-.1*aspectError;
  candidates.push({family,weight,size,skew,iou,densityError,aspectError,score});
  if(!best||score>best.score)best={score,fontFamily:family,fontWeight:weight,fontSize:size,textSkew:skew,styleMatch:iou,nativeDensityError:densityError,nativeAspectError:aspectError,baselineOffsetX:m.left+skew*m.descent};
 }
}
process.stdout.write(JSON.stringify({...best,candidates}));
