const fs=require('fs'),path=require('path');
const root=path.resolve(__dirname,'../..');
const source=fs.readFileSync(path.join(root,'插件程序/示例/素材/服饰商城_参考图.png')).toString('base64');
const html=fs.readFileSync(path.join(__dirname,'服饰商城.template.html'),'utf8').replace('__SOURCE_URI__','data:image/png;base64,'+source);
const output=path.join(root,'插件程序/示例/服饰商城_图片还原.html');
fs.writeFileSync(output,html);console.log(output);
