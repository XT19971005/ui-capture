const path=require('path');
const root=path.resolve(__dirname,'..');
const libs='D:/@谢涛/@TUSY/麻将/2026_8_24AI/2026_10_9UI拆分/拾界插件/依赖/构建工具/node_modules/';
require(libs+'esbuild').buildSync({entryPoints:[root+'/插件程序/edge/psd-source.js'],bundle:true,format:'iife',globalName:'ShijiePSD',platform:'browser',target:'chrome110',minify:true,nodePaths:[libs],outfile:root+'/插件程序/edge/psd-exporter.js',legalComments:'eof'});
