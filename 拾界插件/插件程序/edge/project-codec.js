/* Portable project files share image bytes without changing document metadata. */
(()=>{
 'use strict';
 const MiB=1024*1024,LIMITS=Object.freeze({uniqueImageBytes:256*MiB,metadataBytes:16*MiB,logicalBytes:1024*MiB,fileBytes:276*MiB,imageBytes:36000000,imageCount:4096,items:200000,depth:40}),IMAGE_KEYS=new Set(['image','original','src','source','originalSource','comparisonSource']);
 const utf8=value=>/^[\x00-\x7f]*$/.test(value)?value.length:new TextEncoder().encode(value).byteLength;
 const jsonBytes=value=>utf8(JSON.stringify(value));
 const fail=message=>{throw Error(message)};
 function transform(doc,table=null){
  const images=[],indexes=new Map(),sizes=[],used=new Set(),stack=new Set();let metadata=0,logical=0,unique=0,items=0;
  function budgets(){if(metadata>LIMITS.metadataBytes)fail('工程文字与结构超过16MiB限制。');if(logical>LIMITS.logicalBytes)fail('工程图片引用总量超过1GiB安全限制。')}
  function charge(bytes){metadata+=bytes;logical+=bytes;budgets()}
  function register(value){
   if(typeof value!=='string'||!value.startsWith('data:image/'))fail('工程图片表包含无效图片。');
   let index=indexes.get(value);if(index!==undefined)return index;
   if(value.length>LIMITS.imageBytes)fail('单张工程图片超过36MB限制。');const bytes=utf8(value);if(bytes>LIMITS.imageBytes)fail('单张工程图片超过36MB限制。');
   if(images.length>=LIMITS.imageCount)fail('工程独立图片数量超过4096限制。');unique+=bytes;if(unique>LIMITS.uniqueImageBytes)fail('工程独立图片数据超过256MiB容量限制。');
   index=images.length;images.push(value);indexes.set(value,index);sizes.push(jsonBytes(value));return index;
  }
  if(table!==null){if(!Array.isArray(table)||table.length>LIMITS.imageCount)fail('工程图片表格式无效。');for(const value of table){if(indexes.has(value))fail('工程图片表包含重复图片。');register(value)}}
  function reference(index,key){if(!IMAGE_KEYS.has(key)||!Number.isSafeInteger(index)||index<0||index>=images.length)fail('工程图片引用无效。');used.add(index);metadata+=jsonBytes({$image:index});logical+=sizes[index];budgets();return table===null?{$image:index}:images[index]}
  function walk(value,key=null,depth=0){
   if(++items>LIMITS.items)fail('工程结构条目过多。');if(depth>LIMITS.depth)fail('工程结构层级超过40层限制。');
   if(typeof value==='string'&&IMAGE_KEYS.has(key)&&value.startsWith('data:image/')){if(table!==null)fail('工程图片引用格式无效。');return reference(register(value),key)}
   if(value&&typeof value==='object'){
    if(Object.hasOwn(value,'$image')){if(table===null)fail('工程包含保留的图片引用字段。');if(Array.isArray(value)||Object.keys(value).length!==1)fail('工程图片引用无效。');return reference(value.$image,key)}
    if(stack.has(value))fail('工程结构存在循环引用。');if(!['[object Object]','[object Array]'].includes(Object.prototype.toString.call(value)))fail('工程包含无法保存的数据类型。');stack.add(value);
    let result;if(Array.isArray(value)){charge(2+Math.max(0,value.length-1));result=Array.from(value,item=>walk(item,null,depth+1))}else{result=Object.create(null);charge(2);let count=0;for(const [name,item] of Object.entries(value)){if(item===undefined||typeof item==='function'||typeof item==='symbol')continue;if(count++)charge(1);charge(jsonBytes(name)+1);result[name]=walk(item,name,depth+1)}}
    stack.delete(value);return result;
   }
   if(value===undefined||typeof value==='function'||typeof value==='symbol')value=null;
   if(typeof value==='bigint'||typeof value==='number'&&!Number.isFinite(value))fail('工程包含无效数值。');if(typeof value==='string'&&value.length>LIMITS.metadataBytes)fail('工程文字与结构超过16MiB限制。');charge(jsonBytes(value));return value;
  }
  const result=walk(doc);if(table!==null&&used.size!==images.length)fail('工程图片表包含未引用图片。');return {result,images,logical,metadata,encodedImageBytes:sizes.reduce((sum,n)=>sum+n,0)};
 }
 function encode(doc){const packed=transform(doc);return {format:'shijie-project',version:1,doc:packed.result,images:packed.images}}
 function decode(value){
  if(value?.format==='shijie-project'){
   if(value.version!==1||!Array.isArray(value.images)||Object.keys(value).sort().join(',')!=='doc,format,images,version'||!value.doc||typeof value.doc!=='object')fail('工程文件格式或版本不支持。');return transform(value.doc,value.images).result;
  }
  // The same accounting validates legacy documents without converting their data.
  const packed=transform(value);return transform(packed.result,packed.images).result;
 }
 function stringify(doc){const packed=transform(doc);if(packed.logical<=4*MiB)return JSON.stringify(doc);if(packed.metadata+packed.encodedImageBytes+packed.images.length+128>LIMITS.fileBytes)fail('去重工程文件超过276MiB容量限制。');return JSON.stringify({format:'shijie-project',version:1,doc:packed.result,images:packed.images})}
 function fileLimit(){fail('工程文件超过276MiB容量限制；请先从新版导出去重工程文件，再导入。')}
 function parse(text){if(typeof text!=='string')fail('工程文件内容无效。');if(text.length>LIMITS.fileBytes||utf8(text)>LIMITS.fileBytes)fileLimit();let value;try{value=JSON.parse(text.charCodeAt(0)===0xfeff?text.slice(1):text)}catch(_){fail('工程文件不是有效JSON。')}return decode(value)}
 async function readFile(file){if(!file||!Number.isFinite(file.size)||file.size>LIMITS.fileBytes)fileLimit();return parse(await file.text())}
 window.ShijieProjectCodec={LIMITS,encode,decode,stringify,parse,readFile};
})();
