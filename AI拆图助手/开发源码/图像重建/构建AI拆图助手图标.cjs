const fs=require('fs'),path=require('path');
const root=path.resolve(__dirname,'../..'),{createCanvas,loadImage}=require(path.join(root,'依赖/构建工具/node_modules/@napi-rs/canvas'));
(async()=>{const base=path.join(root,'插件程序/edge/icons'),source=fs.readFileSync(path.join(base,'ai-split.svg'),'utf8'),buffers=[];
for(const size of [16,32,48,64,128,256]){const svg=await loadImage(Buffer.from(source.replace('width="64" height="64"',`width="${size}" height="${size}"`)));const c=createCanvas(size,size);c.getContext('2d').drawImage(svg,0,0,size,size);const bytes=c.toBuffer('image/png');fs.writeFileSync(path.join(base,'ai-split-'+size+'.png'),bytes);buffers.push({size,bytes})}
const header=Buffer.alloc(6+16*buffers.length);header.writeUInt16LE(1,2);header.writeUInt16LE(buffers.length,4);let offset=header.length;
buffers.forEach(({size,bytes},i)=>{const pos=6+i*16;header[pos]=header[pos+1]=size===256?0:size;header.writeUInt16LE(1,pos+4);header.writeUInt16LE(32,pos+6);header.writeUInt32LE(bytes.length,pos+8);header.writeUInt32LE(offset,pos+12);offset+=bytes.length});
fs.writeFileSync(path.join(root,'插件程序/edge/favicon.ico'),Buffer.concat([header,...buffers.map(b=>b.bytes)]));console.log('Built SVG, six PNG sizes and multi-size ICO');
})().catch(e=>{console.error(e);process.exitCode=1});
