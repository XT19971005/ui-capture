/* Runs before application scripts, including in older Chromium browsers. */
(function (w, d) {
  'use strict';
  function install(object, name, value) {
    if (typeof object[name] !== 'function') Object.defineProperty(object, name, {value:value, configurable:true, writable:true});
  }
  function warn(message) {
    function show() {
      var banner=d.getElementById('browser-compat-notice');
      if (!banner) {
        banner=d.createElement('div'); banner.id='browser-compat-notice';
        banner.setAttribute('role','alert');
        banner.style.cssText='position:fixed;left:12px;right:12px;top:64px;z-index:2147483647;background:#34252a;color:#ffe0cc;border:1px solid #aa775e;padding:12px;font:14px/1.6 system-ui;white-space:pre-wrap';
        (d.body||d.documentElement).appendChild(banner);
      }
      banner.textContent=message;
    }
    if (d.readyState==='loading') d.addEventListener('DOMContentLoaded',show); else show();
  }
  if (w.crypto && typeof w.crypto.getRandomValues==='function') {
    install(w.crypto,'randomUUID',function () {
      var bytes=new Uint8Array(16), text=[],i;
      w.crypto.getRandomValues(bytes); bytes[6]=(bytes[6]&15)|64; bytes[8]=(bytes[8]&63)|128;
      for (i=0;i<16;i++) text.push(('0'+bytes[i].toString(16)).slice(-2));
      return text.slice(0,4).join('')+'-'+text.slice(4,6).join('')+'-'+text.slice(6,8).join('')+'-'+text.slice(8,10).join('')+'-'+text.slice(10).join('');
    });
  }
  install(w,'structuredClone',function (value, options) {
    var seen=[], copies=[];
    function invalid() {var error=new Error('当前内容无法安全复制，原工程保留。');error.name='DataCloneError';throw error;}
    if (options && options.transfer && options.transfer.length) invalid();
    function clone(item) {
      if (typeof item==='function'||typeof item==='symbol') return invalid();
      if (item===null||typeof item!=='object') return item;
      var known=seen.indexOf(item),out,tag=Object.prototype.toString.call(item),i;
      if (known>=0) return copies[known];
      if (tag==='[object Date]') out=new Date(item.getTime());
      else if (tag==='[object RegExp]') out=new RegExp(item.source,item.flags);
      else if (tag==='[object ArrayBuffer]') out=item.slice(0);
      else if (typeof ArrayBuffer!=='undefined' && ArrayBuffer.isView(item)) {
        var buffer=clone(item.buffer);
        out=tag==='[object DataView]'?new DataView(buffer,item.byteOffset,item.byteLength):new item.constructor(buffer,item.byteOffset,item.length);
      }
      else if (tag==='[object Blob]') out=item.slice(0,item.size,item.type);
      else if (tag==='[object File]' && typeof w.File==='function') out=new w.File([item],item.name,{type:item.type,lastModified:item.lastModified});
      else if (tag==='[object Map]') out=new Map();
      else if (tag==='[object Set]') out=new Set();
      else if (tag==='[object Array]') out=new Array(item.length);
      else if (tag==='[object Object]') out={};
      else return invalid();
      seen.push(item);copies.push(out);
      if (tag==='[object Map]') item.forEach(function(v,k){out.set(clone(k),clone(v));});
      else if (tag==='[object Set]') item.forEach(function(v){out.add(clone(v));});
      else if (tag==='[object Array]'||tag==='[object Object]') {
        var keys=Object.keys(item);
        for(i=0;i<keys.length;i++) Object.defineProperty(out,keys[i],{value:clone(item[keys[i]]),writable:true,enumerable:true,configurable:true});
      }
      return out;
    }
    return clone(value);
  });
  function at(index) {
    if(this===null||this===undefined)throw new TypeError('Invalid receiver');
    var value=Object(this),length=value.length>>>0,n=Number(index)||0;
    n=n<0?Math.ceil(n):Math.floor(n);if(n<0)n+=length;
    return n<0||n>=length?undefined:value[n];
  }
  install(Array.prototype,'at',at);install(String.prototype,'at',at);
  install(Object,'hasOwn',function(value,key){return Object.prototype.hasOwnProperty.call(value,key);});
  function replaceChildren() {
    var owner=this.ownerDocument||this,fragment=owner.createDocumentFragment(),i,node;
    for(i=0;i<arguments.length;i++) {
      node=arguments[i];fragment.appendChild(node&&typeof node==='object'&&node.nodeType?node:owner.createTextNode(String(node)));
    }
    while(this.firstChild)this.removeChild(this.firstChild);
    this.appendChild(fragment);
  }
  if(w.Element)install(w.Element.prototype,'replaceChildren',replaceChildren);
  if(w.DocumentFragment)install(w.DocumentFragment.prototype,'replaceChildren',replaceChildren);
  install(String.prototype,'replaceAll',function(search,replacement){
    if(search instanceof RegExp){if(!search.global)throw new TypeError('replaceAll requires global RegExp');return String(this).replace(search,replacement);}
    return String(this).replace(new RegExp(String(search).replace(/[.*+?^${}()|[\]\\]/g,'\\$&'),'g'),replacement);
  });
  var baseline=typeof w.Promise==='function'&&typeof w.FileReader==='function'&&typeof w.fetch==='function'&&w.crypto&&typeof w.crypto.randomUUID==='function';
  if (!baseline) warn('当前浏览器缺少图片编辑所需功能。请更新浏览器；360／QQ等双核浏览器请切换“极速模式”。工程和原图不会被修改。');
  w.addEventListener('error',function(event){
    var target=event.target, filename=String(event.filename||'');
    if(target&&String(target.tagName).toLowerCase()==='script'&&target.src){
      warn('页面脚本未能加载，图片和工程按钮可能无法使用。请检查连接后按 Ctrl+F5 重载；仍失败时反馈此脚本：'+String(target.src).split('?')[0]);
    } else if ((event.error&&event.error.name==='SyntaxError')&&filename) {
      warn('当前浏览器内核无法解析页面脚本。请更新浏览器；双核浏览器请切换“极速模式”。文件：'+filename.split('?')[0]);
    } else if (/randomUUID|structuredClone|\.at is not a function|showModal is not a function/.test(String(event.message||''))) {
      warn('浏览器功能兼容错误：'+String(event.message)+ '\n请更新浏览器或切换极速模式；已有工程保留。');
    }
  },true);
})(window,document);
