#!/usr/bin/env node
// Reuse a previously verified PSD as a project manifest, keeping native edit data.
const fs=require('fs'),path=require('path');
const {libraries}=require('./runtime.cjs'),opts={};
for(let i=2;i<process.argv.length;i+=2)opts[process.argv[i].replace(/^--/,'')]=process.argv[i+1];
if(!opts.psd||!opts.project)throw Error('Usage: node import_psd.cjs --psd FILE --project DIRECTORY');
const root=path.resolve(opts.project),dirs=require('./project_dirs.cjs')(root),planDir=path.join(root,(dirs.plan)),cacheDir=path.join(planDir,'渲染缓存');
const plan=path.join(planDir,'项目.json');if(fs.existsSync(plan))throw Error('项目清单已存在，不覆盖');
const {ag,cv}=libraries();
ag.initializeCanvas(cv.createCanvas);const psd=ag.readPsd(fs.readFileSync(opts.psd));
fs.mkdirSync(cacheDir,{recursive:true});let index=0;
const relative=f=>path.relative(root,f).replace(/\\/g,'/');
function visit(l){
 const common={name:l.name,opacity:l.opacity??1,hidden:!!l.hidden,blendMode:l.blendMode||'normal'};
 if(l.children)return {...common,kind:'group',children:l.children.map(visit)};
 if(!l.canvas)throw Error('图层没有渲染缓存: '+l.name);
 const native={};for(const key of ['text','vectorFill','vectorMask','vectorStroke','effects','transparencyProtected','clipping'])if(l[key]!==undefined)native[key]=l[key];
 const kind=l.text?'text':l.vectorFill?'shape':'bitmap';
 if(l.name===opts['background-layer']||l.name===opts['character-layer']){
  const character=l.name===opts['character-layer'];
  const asset=opts[character?'character-file':'background-file'];if(!asset)throw Error('指定完整素材层时必须同时指定对应 -file');
  const f=path.isAbsolute(asset)?asset:path.resolve(root,asset);
  if(!fs.existsSync(f))throw Error('缺少完整素材: '+f);
  if(l.vectorMask)throw Error('完整人物或背景带错误轮廓蒙版');
  return {...common,kind:'bitmap',role:character?'character':'background',file:relative(f),x:0,y:0,width:psd.width,height:psd.height};
 }
 const file=path.join(cacheDir,String(++index).padStart(3,'0')+'.png');fs.writeFileSync(file,l.canvas.toBuffer('image/png'));
 return {...common,kind,cache:relative(file),x:l.left||0,y:l.top||0,...(Object.keys(native).length?{native}:{})};
}
const sources=fs.readdirSync(path.join(root,(dirs.input))).filter(n=>/\.(png|jpg|jpeg)$/i.test(n));
if(!sources.length)throw Error('01_输入 缺少原图');
const job={format:'game-ui-psd-v1',width:psd.width,height:psd.height,source:(dirs.input+'/')+sources[0],outputName:path.basename(opts.psd),layers:psd.children.map(visit)};
fs.writeFileSync(plan,JSON.stringify(job,null,2),'utf8');
console.log(JSON.stringify({project:root,cacheCount:index,note:'缓存附带原生文字和矢量描述；完整人物与背景引用交付素材。'}));
