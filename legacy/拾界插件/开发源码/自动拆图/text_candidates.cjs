// Compare actual native glyphs at a uniform scale, never stretch a broad font.
const fs=require('fs'),path=require('path'),root=path.resolve(__dirname,'../..'),cv=require('@napi-rs/canvas');
const input=JSON.parse(fs.readFileSync(0,'utf8')),target=Buffer.from(input.mask,'base64'),w=input.width,h=input.height;
const defaults=require('./fonts.json');
let fonts=input.fonts||defaults.filter(([family])=>!/[\u4e00-\u9fff]/.test(input.text)||family==='Noto Sans CJK SC').map(([family,weight,file])=>({file,family,weight}));
fonts=fonts.filter(f=>fs.existsSync(f.file)&&cv.GlobalFonts.registerFromPath(f.file,f.family));
const lines=String(input.text).replace(/\r\n?/g,'\n').split('\n'),skews=input.skews||[input.skew||0];
const measure=cv.createCanvas(1,1).getContext('2d');let best=null;const candidates=[];
function metrics(family,weight,size,spacing=0,wordSpacing=0){
 measure.textAlign="left";measure.letterSpacing="0px";measure.wordSpacing="0px";
 measure.font=`${weight} ${size}px "${family}"`;const rows=lines.map(t=>{const m=measure.measureText(t);return {left:m.actualBoundingBoxLeft||0,right:(m.actualBoundingBoxRight||m.width)+Math.max(0,Array.from(t).length-1)*spacing+(t.match(/ /g)||[]).length*wordSpacing,ascent:m.actualBoundingBoxAscent,descent:m.actualBoundingBoxDescent};});
 const ascent=rows[0].ascent||size*.85,descent=rows.at(-1).descent||0,leading=input.lineHeight||size*1.2;
 return {ascent,descent:descent+(lines.length-1)*leading,leading,left:Math.max(...(lines.length>1?[0]:[]),...rows.map(m=>m.left)),right:Math.max(...rows.map(m=>m.right))};
}
const starts=[];let active=false;
for(let x=0;x<w;x++){let ink=false;for(let y=0;y<h;y++)if(target[y*w+x]){ink=true;break;}if(ink&&!active)starts.push(x);active=ink;}
function observedSpacing(size){
 const chars=Array.from(lines[0]);if(lines.length!==1||!/[ ]/.test(lines[0])||!/^[A-Za-z0-9 ]+$/.test(lines[0])||starts.length!==chars.filter(c=>c!==' ').length)return null;
 let aa=0,ab=0,bb=0,ay=0,by=0,j=0,spaces=0,origin;
 chars.forEach((char,i)=>{if(char===' '){spaces++;return;}const at=measure.measureText(chars.slice(0,i).join('')).width-measure.measureText(char).actualBoundingBoxLeft;origin??=at;const delta=starts[j++]-starts[0]-(at-origin);aa+=i*i;ab+=i*spaces;bb+=spaces*spaces;ay+=i*delta;by+=spaces*delta;});
 const det=aa*bb-ab*ab;if(det<=0)return null;const letter=(ay*bb-by*ab)/det,word=(by*aa-ay*ab)/det;
 return letter>=0&&letter<size*2&&word>=0&&word<size*4?[letter,word]:null;
}
for(const {family,weight} of fonts)for(const skew of skews){
 const ref=metrics(family,weight,100),fixedLines=input.lineHeight?(lines.length-1)*input.lineHeight:0;
 const denominator=input.lineHeight?ref.ascent+ref.descent-(lines.length-1)*ref.leading:ref.ascent+ref.descent;
 const nominal=Math.max(6,Math.round((h-fixedLines)*100/Math.max(1,denominator)));
 for(let size=Math.max(6,nominal-2);size<=Math.min(6000,nominal+2);size++){
  const plain=metrics(family,weight,size),count=Array.from(lines[0]).length;
  // ponytail: single-line uniform tracking only; irregular word spacing remains reviewable.
  const tracked=(w-plain.left-plain.right-skew*(plain.ascent+plain.descent))/Math.max(1,count-1);
  const spacings=lines.length===1&&count>1&&tracked>0.5&&tracked<size*2?[[0,0],[tracked,0]]:[[0,0]];
  const observed=observedSpacing(size);if(observed)spacings.push(observed);
  for(const [letterSpacing,wordSpacing] of spacings){
  const m=metrics(family,weight,size,letterSpacing,wordSpacing),bw=m.left+m.right+skew*(m.ascent+m.descent),bh=m.ascent+m.descent;
  const cw=Math.max(w,Math.ceil(bw))+2,ch=Math.max(h,Math.ceil(bh))+2;
  if(cw>6000||ch>6000||cw*ch>6000000)continue;
  const canvas=cv.createCanvas(cw,ch),c=canvas.getContext('2d');c.font=`${weight} ${size}px "${family}"`;c.textAlign="left";c.letterSpacing=letterSpacing+"px";c.wordSpacing=wordSpacing+"px";
  c.setTransform(1,0,-skew,1,m.left+skew*m.descent,m.ascent);c.fillStyle='white';
  lines.forEach((text,i)=>c.fillText(text,0,i*m.leading));
  const rgba=c.getImageData(0,0,cw,ch).data;let intersection=0,union=0,area=0,targetArea=0;
  for(let y=0;y<ch;y++)for(let x=0;x<cw;x++){
   const actual=rgba[(y*cw+x)*4+3]>128,expected=x<w&&y<h&&target[y*w+x]>0;
   if(actual)area++;if(expected)targetArea++;if(actual&&expected)intersection++;if(actual||expected)union++;
  }
  const iou=intersection/Math.max(1,union),densityError=Math.abs(area-targetArea)/Math.max(1,targetArea);
  const aspectError=Math.abs(bw-w)/Math.max(1,w)+Math.abs(bh-h)/Math.max(1,h),score=iou-.5*densityError-.1*aspectError;
  candidates.push({family,weight,size,skew,letterSpacing,wordSpacing,iou,densityError,aspectError,score});
  if(!best||score>best.score)best={score,fontFamily:family,fontWeight:weight,fontSize:size,letterSpacing,wordSpacing,textSkew:skew,styleMatch:iou,nativeDensityError:densityError,nativeAspectError:aspectError,baselineOffsetX:m.left+skew*m.descent};
  }
 }
}
process.stdout.write(JSON.stringify({...best,candidates}));
