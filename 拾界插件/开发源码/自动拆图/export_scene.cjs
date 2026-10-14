'use strict';
const fs=require('fs'),path=require('path'),root=path.resolve(__dirname,'../..'),nm=path.join(root,'依赖/构建工具/node_modules');
const cv=require(path.join(nm,'@napi-rs/canvas')),ag=require(path.join(nm,'ag-psd'));
globalThis.document={createElement(tag){if(tag!=='canvas')throw Error('Unsupported element');return cv.createCanvas(1,1)}};
cv.GlobalFonts.registerFromPath('C:/Windows/Fonts/arial.ttf','Arial');globalThis.Path2D=cv.Path2D;globalThis.ShijieNodeCanvas=cv;ag.initializeCanvas(cv.createCanvas);
cv.GlobalFonts.registerFromPath('C:/Windows/Fonts/msyh.ttc','Microsoft YaHei');
cv.GlobalFonts.registerFromPath('C:/Windows/Fonts/msyhbd.ttc','Microsoft YaHei');
const S=require('./scene-native.cjs');
async function main(){
 const [source,target,preview]=process.argv.slice(2);if(!source||!target||!preview)throw Error('Missing paths');
 const scene=S.validate(JSON.parse(fs.readFileSync(source,'utf8'))),bytes=await S.psd(scene),psd=ag.readPsd(Buffer.from(bytes));
 const counts={text:0,vector:0,bitmap:0,groups:0};function walk(ls){for(const l of ls){if(l.children){counts.groups++;walk(l.children)}else if(l.text)counts.text++;else if(l.vectorFill&&l.vectorMask)counts.vector++;else counts.bitmap++;}}walk(psd.children);
 const expected={text:scene.nodes.filter(n=>n.type==='text'&&n.visible!==false).length,vector:scene.nodes.filter(n=>['rect','ellipse','path'].includes(n.type)&&n.visible!==false).length};
 if(counts.text<expected.text||counts.vector<expected.vector)throw Error('Native edit data missing');
 const temp=target+'.writing';fs.writeFileSync(temp,Buffer.from(bytes));fs.renameSync(temp,target);fs.writeFileSync(preview,psd.canvas.toBuffer('image/png'));
 console.log(JSON.stringify({status:'PASS',counts,width:psd.width,height:psd.height,checks:['PSD successfully read back','native text and vectors present'],visualReview:'REQUIRED'}));
}main().catch(e=>{console.error(e.message);process.exitCode=1});
