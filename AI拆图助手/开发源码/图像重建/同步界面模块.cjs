const fs=require('fs'),path=require('path');
const groups={
  "图像重建": [
    "smart-split.js",
    "project-sync.js",
    "codex-settings.js",
    "image-editor.html",
    "image-editor.css",
    "image-editor.js",
    "image-segment-worker.js"
  ],
  "工作台增强": [
    "project-codec.js",
    "app-session.js",
    "store.js",
    "studio-base.js",
    "project-thumbnail.js",
    "layer-style-panel.js",
    "layer-style-panel.css",
    "workspace-ui.js",
    "workspace-ui.css",
    "workspace-polish.js",
    "workspace-polish.css",
    "region-selection.js",
    "studio.js",
    "studio.css",
    "web-studio.js",
    "image-studio.js",
    "refinement-versions.js",
    "selected-refine.js",
    "layer-order.js",
    "image-replace.js",
    "image-replace.css",
    "image-generate.js",
    "image-generate.css",
    "workspace-actions.js",
    "workspace-actions.css",
    "free-assistant.js",
    "free-assistant.css",
    "original-annotations.js",
    "original-annotations.css",
    "canvas-compare.js"
  ],
  "网页抓取": [
    "url-capture.js"
  ]
};
function entries(root){return Object.entries(groups).flatMap(([dir,names])=>names.map(name=>({source:path.join(root,'开发源码',dir,name),target:path.join(root,'插件程序/edge',name)})))}
function validateSources(root){const plan=entries(root);for(const item of plan)if(!fs.existsSync(item.source))throw Error('缺少界面源文件：'+item.source);return plan}
function syncInterfaces(root){const plan=validateSources(root);for(const item of plan)fs.copyFileSync(item.source,item.target);return plan.length}
module.exports={entries,validateSources,syncInterfaces};
