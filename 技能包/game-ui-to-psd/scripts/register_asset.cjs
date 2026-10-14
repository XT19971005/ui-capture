// Import a complete PNG unchanged, pin its source hash, and emit a bitmap specification.
const fs=require('fs'),path=require('path'),{libraries}=require('./runtime.cjs'),{sha}=require('./complete_assets.cjs');
const opts={};for(let i=2;i<process.argv.length;i++){const k=process.argv[i].replace(/^--/,'');opts[k]=process.argv[i+1]&&!process.argv[i+1].startsWith('--')?process.argv[++i]:true;}
async function main(){
 if(!opts.project||!opts.file||!opts.name||!['character','background','artwork'].includes(opts.role))throw Error('register_asset.cjs --project DIR --file PNG --name NAME --role character|background|artwork [--x N --y N --width N --height N] [--replace]');
 const root=path.resolve(opts.project),dirs=require('./project_dirs.cjs')(root),input=path.resolve(opts.file),job=JSON.parse(fs.readFileSync(path.join(root,(dirs.plan+'/项目.json')),'utf8')),{cv}=libraries(job.runtime||{});
 if(path.extname(input).toLowerCase()!=='.png')throw Error('完整素材使用带 alpha 的 PNG，不伪造透明度');
 const im=await cv.loadImage(input),c=cv.createCanvas(im.width,im.height);c.getContext('2d').drawImage(im,0,0);const data=c.getContext('2d').getImageData(0,0,im.width,im.height).data;
 let transparent=0,opaque=0,notOpaque=0;for(let i=3;i<data.length;i+=4){if(data[i]===0)transparent++;if(data[i]>240)opaque++;if(data[i]<254)notOpaque++;}
 if(opts.role!=='background'&&(!transparent||!opaque))throw Error('人物/艺术字缺少真实透明区域或不透明主体');
 if(opts.role==='background'&&notOpaque)throw Error('完整背景不能留透明洞或半透明区域');
 if(/[\\/:*?"<>|]/.test(opts.name)||opts.name==='.'||opts.name==='..')throw Error('素材名不合法');
 const number=(k,fallback)=>opts[k]===undefined?fallback:Number(opts[k]),x=number('x',0),y=number('y',0),width=number('width',im.width),height=number('height',im.height);
 if(![x,y,width,height].every(Number.isFinite)||width<=0||height<=0)throw Error('定位尺寸无效');
 if(x<0||y<0||x+width>job.width||y+height>job.height)throw Error('整张素材定位超出画布，可能裁掉主体；先重新确认位置');
 const relative=(dirs.assets+'/')+opts.name+'.png',target=path.join(root,relative);fs.mkdirSync(path.dirname(target),{recursive:true});
 if(fs.existsSync(target)&&sha(target)!==sha(input)&&!opts.replace)throw Error('已有同名不同素材；检查后使用 --replace 或新名称');
 if(path.resolve(input)!==path.resolve(target))fs.copyFileSync(input,target);
 const hash=sha(target),spec={kind:'bitmap',name:opts.name,role:opts.role,file:relative,x,y,width,height,completeAssetSHA256:hash,completeAssetSource:{file:relative,sha256:hash,transform:[width/im.width,0,0,height/im.height,x,y]}};
 const manifest=path.join(root,(dirs.plan+'/素材登记.json')),rows=fs.existsSync(manifest)?JSON.parse(fs.readFileSync(manifest,'utf8')):[];const old=rows.findIndex(r=>r.name===spec.name);if(old>=0)rows[old]=spec;else rows.push(spec);fs.writeFileSync(manifest,JSON.stringify(rows,null,2));
 console.log(JSON.stringify({stage:'ASSET_REGISTER',spec,alpha:{transparentPixels:transparent,opaquePixels:opaque},next:'检查完整素材后将 spec 放入项目.json 的对应分组；不要再修改其像素或添加裁切。'},null,2));
}
main().catch(e=>{console.error(e.message);process.exitCode=1});
