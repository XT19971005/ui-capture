"use strict";
const fs=require('fs'),path=require('path');const app=path.resolve(__dirname,'../..');let svgpath;
try{svgpath=require(path.join(app,'依赖/构建工具/node_modules/svgpath'))}catch{svgpath=require('svgpath')}
const input=JSON.parse(fs.readFileSync(0,'utf8')),n=input.node,b=input.box,a=input.rotation||0,w=n.width,h=n.height;
let d=n.d;if(n.type==='ellipse')d=`M${w} ${h/2}A${w/2} ${h/2} 0 1 0 0 ${h/2}A${w/2} ${h/2} 0 1 0 ${w} ${h/2}Z`;
if(n.type==='rect'){const r=Math.min(n.radius||0,w/2,h/2);d=r?`M${r} 0H${w-r}A${r} ${r} 0 0 1 ${w} ${r}V${h-r}A${r} ${r} 0 0 1 ${w-r} ${h}H${r}A${r} ${r} 0 0 1 0 ${h-r}V${r}A${r} ${r} 0 0 1 ${r} 0Z`:`M0 0H${w}V${h}H0Z`}
const master=input.master||{x:n.x,y:n.y,width:w,height:h},angle=a*Math.PI/180,c=Math.abs(Math.cos(angle)),s=Math.abs(Math.sin(angle)),scale=Math.min(b.width/(master.width*c+master.height*s),b.height/(master.width*s+master.height*c));
const dx=n.x+w/2-master.x-master.width/2,dy=n.y+h/2-master.y-master.height/2,ow=(w*c+h*s)*scale,oh=(w*s+h*c)*scale;
const box={x:b.x+b.width/2+(dx*Math.cos(angle)-dy*Math.sin(angle))*scale-ow/2,y:b.y+b.height/2+(dx*Math.sin(angle)+dy*Math.cos(angle))*scale-oh/2,width:ow,height:oh};
const result=svgpath(d).translate(-w/2,-h/2).rotate(a).scale(scale).translate(ow/2,oh/2).round(5);
if(result.err)throw Error('Invalid path');process.stdout.write(JSON.stringify({d:result.toString(),scale,box}));
