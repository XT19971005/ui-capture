'use strict';
// Match fonts_runtime.py: retain installed Linux faces, otherwise load the
// licensed web WOFF2 files directly. Paths never depend on the job's cwd.
const fs=require('fs'),path=require('path');
const bundled=path.resolve(__dirname,'../../../../shijie/static/server/fonts');
const fonts=require('./fonts.json').map(([family,weight,installed,filename])=>{
 const candidates=[installed,path.join(bundled,filename)];
 const file=candidates.find(file=>{try{return fs.statSync(file).isFile()}catch{return false}});
 if(!file)throw Error(`缺少字体 ${family} (${weight})：${candidates.join(' / ')}`);
 return [family,weight,path.resolve(file)];
});
function fontFile(family,weight=400){
 const faces=fonts.filter(face=>face[0]===family).sort((a,b)=>Math.abs(a[1]-weight)-Math.abs(b[1]-weight));
 if(!faces.length)throw Error('未配置字体：'+family);
 return faces[0][2];
}
module.exports={fonts,fontFile};
