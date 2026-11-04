const {test}=require('node:test'),assert=require('node:assert/strict'),path=require('node:path'),{spawnSync}=require('node:child_process'),cv=require('@napi-rs/canvas');
test('source fitting recovers widely tracked subtitle without collapsing width',()=>{
  const file=path.join(__dirname,'../shijie/static/server/fonts/LiberationSans-Bold.woff2'),family='Liberation Sans';cv.GlobalFonts.registerFromPath(file,family);
  const c=cv.createCanvas(500,90).getContext('2d');c.font='700 36px "Liberation Sans"';c.textAlign='left';c.letterSpacing='24px';c.wordSpacing='20px';c.fillStyle='white';c.fillText('UI DESIN',10,60);
  const rgba=c.getImageData(0,0,500,90).data;let x0=500,y0=90,x1=0,y1=0;
  for(let y=0;y<90;y++)for(let x=0;x<500;x++)if(rgba[(y*500+x)*4+3]>128){x0=Math.min(x0,x);x1=Math.max(x1,x+1);y0=Math.min(y0,y);y1=Math.max(y1,y+1);}
  const w=x1-x0,h=y1-y0,mask=Buffer.alloc(w*h);for(let y=0;y<h;y++)for(let x=0;x<w;x++)mask[y*w+x]=rgba[((y+y0)*500+x+x0)*4+3]>128?1:0;
  const input={text:'UI DESIN',width:w,height:h,mask:mask.toString('base64'),fonts:[{family,weight:700,file}],skews:[0]};
  const run=spawnSync(process.execPath,[path.join(__dirname,'../legacy/拾界插件/开发源码/自动拆图/text_candidates.cjs')],{input:JSON.stringify(input),encoding:'utf8'});assert.equal(run.status,0,run.stderr);
  const fit=JSON.parse(run.stdout);assert(fit.styleMatch>.85,JSON.stringify(fit));assert(Math.abs(fit.letterSpacing-24)<1);assert(Math.abs(fit.fontSize-36)<2);assert(Math.abs(fit.wordSpacing-20)<2);
});
