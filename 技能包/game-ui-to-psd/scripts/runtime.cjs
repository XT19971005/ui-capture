const fs=require('fs'),path=require('path');
function runtime(overrides={}){
 const file=process.env.GAME_UI_PSD_RUNTIME||path.join(__dirname,'runtime.json');
 if(!fs.existsSync(file))throw Error('缺少运行配置: '+file);
 const read=f=>JSON.parse(fs.readFileSync(f,'utf8').replace(/^\uFEFF/,''));
 const local=path.join(path.dirname(file),'runtime.local.json');
 const settings={...read(file),...(fs.existsSync(local)?read(local):{}),...overrides};
 const bundle=path.resolve(__dirname,'../..'),roots={'@bundle/':bundle,'@workspace/':path.dirname(bundle),'@skill/':path.dirname(__dirname)};
 for(const key of ['workspaceRoot','agPsd','canvas','svgpath','psdTools','imagegenSkill','imagegenCLI']){
  for(const [prefix,root] of Object.entries(roots))if(typeof settings[key]==='string'&&settings[key].startsWith(prefix)){settings[key]=path.resolve(root,settings[key].slice(prefix.length));break;}
 }
 if(settings.node==='node')settings.node=process.execPath;
 return settings;
}
function libraries(overrides={}){const r=runtime(overrides);return {ag:require(r.agPsd),cv:require(r.canvas),svgpath:require(r.svgpath)};}
module.exports={runtime,libraries};
