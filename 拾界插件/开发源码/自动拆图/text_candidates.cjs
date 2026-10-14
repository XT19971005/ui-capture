// Candidate glyphs use the identical renderer and font registration as PSD export.
const fs=require('fs'),path=require('path'),root=path.resolve(__dirname,'../..'),cv=require(path.join(root,'依赖/构建工具/node_modules/@napi-rs/canvas'));
for(const [file,name] of [['arial.ttf','Arial'],['msyh.ttc','Microsoft YaHei'],['msyhbd.ttc','Microsoft YaHei'],['simhei.ttf','SimHei']])cv.GlobalFonts.registerFromPath('C:/Windows/Fonts/'+file,name);
const input=JSON.parse(fs.readFileSync(0,'utf8')),target=Buffer.from(input.mask,'base64'),w=input.width,h=input.height,skew=input.skew||0;
const fonts=/[\u4e00-\u9fff]/.test(input.text)?[['Microsoft YaHei',400],['Microsoft YaHei',700],['SimHei',400]]:[['Arial',400],['Arial',700],['Microsoft YaHei',400]];
let best=null;const candidates=[];
for(const [family,weight] of fonts){
 const canvas=cv.createCanvas(w,h),c=canvas.getContext('2d');c.font=`${weight} 100px "${family}"`;let m=c.measureText(input.text);
 const size=Math.max(6,Math.round(h*100/Math.max(1,m.actualBoundingBoxAscent+m.actualBoundingBoxDescent)));c.font=`${weight} ${size}px "${family}"`;m=c.measureText(input.text);
 const a=m.actualBoundingBoxAscent,d=m.actualBoundingBoxDescent,sx=w/Math.max(1,m.actualBoundingBoxLeft+m.actualBoundingBoxRight+skew*(a+d));
 c.setTransform(sx,0,-skew*sx,1,(m.actualBoundingBoxLeft+skew*d)*sx,a);c.fillStyle='white';c.fillText(input.text,0,0);
 const rgba=c.getImageData(0,0,w,h).data;let intersection=0,union=0,area=0,targetArea=0;
 for(let i=0;i<w*h;i++){const actual=rgba[i*4+3]>128,expected=target[i]>0;if(actual)area++;if(expected)targetArea++;if(actual&&expected)intersection++;if(actual||expected)union++;}
 const iou=intersection/Math.max(1,union),densityError=Math.abs(area-targetArea)/Math.max(1,targetArea),score=iou-densityError;
 candidates.push({family,weight,size,iou,area,targetArea,densityError,score});if(!best||score>best.score)best={score,fontFamily:family,fontWeight:weight,fontSize:size,styleMatch:iou,nativeDensityError:densityError};
}
process.stdout.write(JSON.stringify({...best,candidates}));
