const fs=require('fs'),path=require('path');
const root=path.resolve(__dirname,'../..'),nm=path.join(root,'依赖/构建工具/node_modules'),edge=path.join(root,'插件程序/edge');
const retiredMask=path.join(edge,'studio-mask.js');if(fs.existsSync(retiredMask))fs.unlinkSync(retiredMask);
require(path.join(root,'开发源码/文字排版/构建文字模块.cjs'));
require(path.join(nm,'esbuild')).buildSync({entryPoints:[path.join(__dirname,'layer-style.js')],bundle:true,format:'iife',globalName:'ShijieLayerStyle',platform:'browser',target:'chrome110',minify:true,nodePaths:[nm],outfile:path.join(edge,'layer-style-runtime.js'),legalComments:'eof'});
require(path.join(nm,'esbuild')).buildSync({entryPoints:[path.join(__dirname,'scene-export.js')],bundle:true,format:'iife',globalName:'ShijieScene',platform:'browser',target:'chrome110',minify:true,nodePaths:[nm],outfile:path.join(edge,'image-native.js'),legalComments:'eof'});
for(const name of ['smart-split.js','project-sync.js','codex-settings.js','image-editor.html','image-editor.css','image-editor.js','image-segment-worker.js'])fs.copyFileSync(path.join(__dirname,name),path.join(edge,name));
console.log('PASS: image import/editor/export module built.');

for(const name of ['project-codec.js','app-session.js','store.js','studio-base.js','project-thumbnail.js','layer-style-panel.js','layer-style-panel.css','workspace-ui.js','workspace-ui.css','workspace-polish.js','workspace-polish.css','studio.js','studio.css','web-studio.js','image-studio.js','refinement-versions.js','selected-refine.js','layer-order.js'])fs.copyFileSync(path.join(root,'开发源码/工作台增强',name),path.join(edge,name));

require(path.join(nm,'esbuild')).buildSync({entryPoints:[path.join(__dirname,'scene-export.js')],bundle:true,format:'cjs',platform:'node',nodePaths:[nm],outfile:path.join(root,'开发源码/自动拆图/scene-native.cjs'),legalComments:'eof'});

fs.copyFileSync(path.join(root,'开发源码/网页抓取/url-capture.js'),path.join(edge,'url-capture.js'));
