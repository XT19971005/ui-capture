// ag-psd core is pure JavaScript; all bitmap caches are supplied by Python.
const fs=require('fs'),path=require('path');
const ag=require('./vendor/node_modules/ag-psd');
const svgpath=require('./vendor/node_modules/svgpath');
function paths(d,operation='combine'){
 const p=svgpath(d).abs().unshort().unarc(),ps=[];let cur,x=0,y=0;
 const knot=(x,y,ix=x,iy=y,ox=x,oy=y)=>({linked:false,points:[ix,iy,x,y,ox,oy]});
 p.iterate(s=>{const cmd=s[0];if(cmd==='M'){cur={open:true,operation,fillRule:'even-odd',knots:[knot(s[1],s[2])]};ps.push(cur);x=s[1];y=s[2];return;}
  if(cmd==='Z'){cur.open=false;const a=cur.knots[0],b=cur.knots.at(-1);if(a.points[2]===b.points[2]&&a.points[3]===b.points[3]){a.points[0]=b.points[0];a.points[1]=b.points[1];cur.knots.pop();}x=a.points[2];y=a.points[3];return;}
  let nx,ny,ax=x,ay=y,bx,by;if(cmd==='L'){[nx,ny]=s.slice(1);}else if(cmd==='H'){nx=s[1];ny=y;}else if(cmd==='V'){nx=x;ny=s[1];}else if(cmd==='C'){[ax,ay,bx,by,nx,ny]=s.slice(1);}else if(cmd==='Q'){nx=s[3];ny=s[4];ax=x+(s[1]-x)*2/3;ay=y+(s[2]-y)*2/3;bx=nx+(s[1]-nx)*2/3;by=ny+(s[2]-ny)*2/3;}else throw Error('Unsupported path: '+cmd);
  cur.knots.at(-1).points.splice(4,2,ax,ay);cur.knots.push(knot(nx,ny,bx??nx,by??ny));x=nx;y=ny;
 });return ps;
}
function write(input,output){
 const s=JSON.parse(fs.readFileSync(input,'utf8'));const {width,height}=s;
 const image=(raw,w=width,h=height)=>{const data=new Uint8ClampedArray(Buffer.from(raw,'base64'));if(data.length!==w*h*4)throw Error('RGBA length mismatch');return {width:w,height:h,data};};
 const flatChildren=s.layers.map(l=>{const x=l.left??0,y=l.top??0,w=l.width??width,h=l.height??height;if(![x,y,w,h].every(Number.isInteger)||x<0||y<0||w<1||h<1||x+w>width||y+h>height)throw Error('Invalid layer placement');const result={name:l.name,top:y,left:x,bottom:y+h,right:x+w,imageData:image(l.rgba,w,h),opacity:1,blendMode:'normal'};
  if(l.kind==='text')result.text=l.text;
  if(l.kind==='shape'){result.vectorFill={type:'color',color:{r:l.color[0],g:l.color[1],b:l.color[2]}};result.vectorMask={fillStartsWithAllPixels:false,paths:l.shapes.flatMap(p=>paths(p.d,p.operation))};}
  return result;});
 const children=[];let active=null;for(let i=0;i<flatChildren.length;i++){const group=s.layers[i].group;if(!group){children.push(flatChildren[i]);active=null;}else{if(!active||active.name!==group){active={name:group,opened:false,children:[]};children.push(active);}active.children.push(flatChildren[i]);}}
 const psd={width,height,children,imageData:image(s.merged),imageResources:{thumbnailRaw:{width:s.thumbnail.width,height:s.thumbnail.height,data:Buffer.from(s.thumbnail.data,'base64')},versionInfo:{version:1,hasRealMergedData:true,writerName:'Shijie ComfyUI',readerName:'Shijie ComfyUI',fileVersion:1}}};
 const tmp=output+'.writing';try{fs.writeFileSync(tmp,ag.writePsdBuffer(psd,{noBackground:true,invalidateTextLayers:false}));fs.renameSync(tmp,output);}finally{if(fs.existsSync(tmp))fs.unlinkSync(tmp);}
}
if(require.main===module)write(process.argv[2],process.argv[3]);
module.exports={paths,write};
