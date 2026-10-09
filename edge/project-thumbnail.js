/* Small, local previews. Render the canvas once; do not allocate per-layer PSD caches. */
window.ProjectThumbnail=(()=>{
 const scripts=new Map();
 function ensure(file,key){if(window[key])return Promise.resolve(window[key]);if(!scripts.has(file))scripts.set(file,new Promise((ok,no)=>{const s=document.createElement('script');s.src=file;s.onload=()=>ok(window[key]);s.onerror=()=>{scripts.delete(file);no(Error('预览模块未加载'))};document.head.append(s)}));return scripts.get(file)}
 function aborted(signal){if(signal?.aborted)throw new DOMException('已取消','AbortError')}
 function image(source,signal){return new Promise((ok,no)=>{const im=new Image();let timer;const stop=()=>{clearTimeout(timer);signal?.removeEventListener('abort',cancel);im.onload=im.onerror=null},cancel=()=>{stop();im.src='';no(new DOMException('已取消','AbortError'))};im.onload=()=>{stop();ok(im)};im.onerror=()=>{stop();no(Error('无法生成缩略图'))};timer=setTimeout(()=>{stop();im.src='';no(Error('缩略图生成超时'))},10000);signal?.addEventListener('abort',cancel,{once:true});im.src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(source)})}
 async function render(project,signal){
  aborted(signal);const doc=structuredClone(project.doc),w=+doc.width,h=+doc.height;if(!Number.isFinite(w)||!Number.isFinite(h)||w<=0||h<=0||Math.max(w,h)>30000)throw Error('画板尺寸无效');const scale=Math.min(1,480/w,300/h),width=Math.max(1,Math.round(w*scale)),height=Math.max(1,Math.round(h*scale));let source;
  if(project.kind==='web'){
   await ensure('text-layout.js','ShijieText');const D=await ensure('capture-design.js','CaptureDesign');aborted(signal);D.prepare(doc);const data=D.exportData(doc),host=document.createElement('div');host.setAttribute('xmlns','http://www.w3.org/1999/xhtml');host.style.cssText='position:relative;overflow:hidden;box-sizing:border-box;margin:0;padding:0;';await D.render(data,host,()=>{},signal);aborted(signal);source='<svg xmlns="http://www.w3.org/2000/svg" width="'+width+'" height="'+height+'" viewBox="0 0 '+w+' '+h+'"><foreignObject width="'+w+'" height="'+h+'">'+new XMLSerializer().serializeToString(host)+'</foreignObject></svg>';
  }else{throw Error('此版本支持网页工程');
  }
  aborted(signal);const im=await image(source,signal);aborted(signal);const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;canvas.getContext('2d').drawImage(im,0,0,width,height);return canvas.toDataURL('image/webp',.84);
 }
 return {render};
})();
