#!/usr/bin/env node
// Save review sheets to the project folder; never display images in chat.
const fs=require('fs'),path=require('path');
const {libraries}=require('./runtime.cjs');
async function main(project){
 const root=path.resolve(project),dirs=require('./project_dirs.cjs')(root),job=JSON.parse(fs.readFileSync(path.join(root,(dirs.plan+'/项目.json')),'utf8')),{cv}=libraries(job.runtime||{});
 const qa=path.join(root,(dirs.qa));fs.mkdirSync(qa,{recursive:true});
 {
  const collect=(items,invisible=false)=>items.flatMap(s=>s.kind==='group'?collect(s.children||[],invisible||s.hidden):!invisible&&!s.hidden&&s.kind==='bitmap'&&(s.role==='character'||s.reviewKind==='character')?[s]:[]),actors=collect(job.layers);
  if(actors.length){const c=cv.createCanvas(job.width,job.height),ctx=c.getContext('2d');for(const s of actors){const im=await cv.loadImage(path.resolve(root,s.file));ctx.drawImage(im,s.x||0,s.y||0,s.width??im.width,s.height??im.height);}fs.writeFileSync(path.join(root,dirs.compact?dirs.qa:dirs.output,'完整人物.png'),c.toBuffer('image/png'));}
 }
 const actorFile=path.join(root,dirs.compact?dirs.qa:dirs.output,'完整人物.png');
 const w=1400,h=Math.round(w*job.height/job.width);
 if(fs.existsSync(actorFile)){const actor=await cv.loadImage(actorFile);for(const mode of ['浅色','深色','棋盘格']){const c=cv.createCanvas(w,h),ctx=c.getContext('2d');ctx.fillStyle=mode==='深色'?'#242424':'#fafafa';ctx.fillRect(0,0,w,h);if(mode==='棋盘格'){ctx.fillStyle='#b9b9b9';for(let y=0;y<h;y+=20)for(let x=0;x<w;x+=20)if((x/20+y/20)%2===0)ctx.fillRect(x,y,20,20)}ctx.drawImage(actor,0,0,w,h);fs.writeFileSync(path.join(qa,'角色透明检查_'+mode+'.png'),c.toBuffer('image/png'));}}
 if(!job.source){console.log('Review backgrounds saved; no original source comparison.');return;}
 const original=await cv.loadImage(path.resolve(root,job.source)),composite=await cv.loadImage(path.join(root,dirs.compact?dirs.qa:dirs.output,'合成预览.png'));
 const pw=1000,ph=Math.round(pw*job.height/job.width),c=cv.createCanvas(pw*2,ph+32),ctx=c.getContext('2d');ctx.fillStyle='#222';ctx.fillRect(0,0,c.width,c.height);ctx.fillStyle='#fff';ctx.font='20px Arial';ctx.fillText('Original',10,23);ctx.fillText('PSD composite',pw+10,23);ctx.drawImage(original,0,32,pw,ph);ctx.drawImage(composite,pw,32,pw,ph);fs.writeFileSync(path.join(qa,'原图与合成_并排检查.png'),c.toBuffer('image/png'));
 console.log('Review files saved; visual review remains REQUIRED.');
}
module.exports=main;
if(require.main===module)main(process.argv[2]||'').catch(e=>{console.error(e);process.exitCode=1});
