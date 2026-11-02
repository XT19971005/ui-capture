const fs=require('fs'),path=require('path');
const root=path.resolve(__dirname,'../..'),nm=path.join(root,'依赖/构建工具/node_modules'),edge=path.join(root,'插件程序/edge');
const interfaces=require(path.join(__dirname,'同步界面模块.cjs'));interfaces.validateSources(root);
const retiredMask=path.join(edge,'studio-mask.js');if(fs.existsSync(retiredMask))fs.unlinkSync(retiredMask);
require(path.join(root,'开发源码/文字排版/构建文字模块.cjs'));
require(path.join(nm,'esbuild')).buildSync({entryPoints:[path.join(__dirname,'layer-style.js')],bundle:true,format:'iife',globalName:'ShijieLayerStyle',platform:'browser',target:'chrome110',minify:true,nodePaths:[nm],outfile:path.join(edge,'layer-style-runtime.js'),legalComments:'eof'});
require(path.join(nm,'esbuild')).buildSync({entryPoints:[path.join(__dirname,'scene-export.js')],bundle:true,format:'iife',globalName:'ShijieScene',platform:'browser',target:'chrome110',minify:true,nodePaths:[nm],outfile:path.join(edge,'image-native.js'),legalComments:'eof'});

require(path.join(nm,'esbuild')).buildSync({entryPoints:[path.join(__dirname,'scene-export.js')],bundle:true,format:'cjs',platform:'node',nodePaths:[nm],outfile:path.join(root,'开发源码/自动拆图/scene-native.cjs'),legalComments:'eof'});

interfaces.syncInterfaces(root);
console.log('PASS: image import/editor/export and interface modules built.');
