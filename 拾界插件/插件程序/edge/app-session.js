/* Recovery projects persist in IndexedDB; temporary previews stay in RAM. */
window.ShijieSession=(()=>{
 const session={library:new Map(),drafts:{web:null,image:null,region:null},workspaceColor:'#12151c',writerId:crypto.randomUUID()};
 session.cleanup=(async()=>{if(globalThis.caches)for(const name of await caches.keys())if(name.startsWith('shijie-temporary-'))await caches.delete(name)})().catch(()=>{});
 function pack(entry){
  const assets={},keys=new Map();
  function walk(v){
   if(typeof v==='string'&&v.startsWith('data:image/')){let key=keys.get(v);if(!key){key='asset-'+keys.size;keys.set(v,key);assets[key]=v}return {__shijieRecoveryAsset:key}}
   if(Array.isArray(v))return v.map(walk);
   if(v&&typeof v==='object'){const entries=Object.entries(v).map(([k,value])=>[k,walk(value)]);return Object.hasOwn(v,'__shijieRecoveryAsset')||Object.hasOwn(v,'__shijieRecoveryObject')?{__shijieRecoveryObject:entries}:Object.fromEntries(entries)}
   return v;
  }
  return {...entry,doc:walk(entry.doc),recoveryAssets:assets};
 }
 function unpack(entry){
  if(!entry.recoveryAssets)return entry;
  function walk(v){
   if(v&&typeof v==='object'&&!Array.isArray(v)){
    if(entry.storageVersion==='recovery-v3'&&Object.keys(v).length===1&&Object.hasOwn(v,'__shijieRecoveryObject')&&Array.isArray(v.__shijieRecoveryObject))return Object.fromEntries(v.__shijieRecoveryObject.map(([k,value])=>[k,walk(value)]));
    if(Object.keys(v).length===1&&Object.hasOwn(v,'__shijieRecoveryAsset')&&Object.hasOwn(entry.recoveryAssets,v.__shijieRecoveryAsset))return entry.recoveryAssets[v.__shijieRecoveryAsset];
    return Object.fromEntries(Object.entries(v).map(([k,value])=>[k,walk(value)]));
   }
   return Array.isArray(v)?v.map(walk):v;
  }
  const value={...entry,doc:walk(entry.doc)};delete value.recoveryAssets;return value;
 }
 function open(){return new Promise((resolve,reject)=>{const r=indexedDB.open('shijie-library');r.onupgradeneeded=()=>{if(!r.result.objectStoreNames.contains('projects'))r.result.createObjectStore('projects',{keyPath:'id'})};r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);r.onblocked=()=>reject(Error('工程库被其他页面占用，请关闭旧版本页面后重试'))})}
 session.legacySaved=async()=>{const db=await open();return new Promise((resolve,reject)=>{const tx=db.transaction('projects'),r=tx.objectStore('projects').getAll();let rows=[];r.onsuccess=()=>{rows=r.result};tx.oncomplete=()=>{db.close();resolve(rows.map(unpack))};tx.onerror=tx.onabort=()=>{db.close();reject(tx.error||Error('工程恢复读取失败'))}})};
 function versionOf(entry){return entry?.persistedVersion||entry?.revision||null}
 function assertVersion(old,expected){const wanted=expected&&typeof expected==='object'?expected.version:expected;if(versionOf(old)!==wanted&&!(expected?.allowMissing===true&&!old)){const conflict=Error('工程已在另一个页面更新；当前修改仍在页面中，请下载或另存副本。');conflict.name='RecoveryConflictError';throw conflict}}
 session.saveEntry=async (entry,expectedVersion=null)=>{
  const value=structuredClone(entry),db=await open();
  return new Promise((resolve,reject)=>{
   const tx=db.transaction('projects','readwrite'),store=tx.objectStore('projects'),get=store.get(value.id),evictions=[];let failure;
   get.onsuccess=()=>{try{
    const old=get.result;assertVersion(old,expectedVersion);value.persistedVersion=value.revision;value.writerId=session.writerId;if(old?.saveMode==='saved'){value.saveMode='saved';value.savedAt=old.savedAt||value.savedAt}value.storageVersion='recovery-v3';value.persistedAt=Date.now();store.put(pack(value));
    const all=store.getAll();all.onsuccess=()=>{try{const recent=all.result.filter(p=>p.saveMode==='auto'&&p.id!==value.id).sort((a,b)=>(b.updated||0)-(a.updated||0)||(b.sequence||0)-(a.sequence||0));for(const p of recent.slice(value.saveMode==='auto'?19:20)){store.delete(p.id);evictions.push({id:p.id,version:versionOf(p)})}}catch(e){failure=e;tx.abort()}};
   }catch(e){failure=e;tx.abort()}};
   tx.oncomplete=()=>{db.close();Object.defineProperty(value,'recoveryEvictions',{value:evictions});resolve(value)};
   tx.onerror=tx.onabort=()=>{db.close();reject(failure||tx.error||Error('工程恢复保存失败；请立即下载工程文件'))};
  });
 };
 session.saveManual=(entry,version)=>session.saveEntry({...entry,saveMode:'saved'},version);
 session.removeManual=async (key,expectedVersion=null)=>{
  const db=await open();return new Promise((resolve,reject)=>{
   const tx=db.transaction('projects','readwrite'),store=tx.objectStore('projects'),get=store.get(key);let failure,removed;
   get.onsuccess=()=>{try{const old=get.result;assertVersion(old,expectedVersion);removed={id:key,version:versionOf(old)};store.delete(key)}catch(e){failure=e;tx.abort()}};
   tx.oncomplete=()=>{db.close();resolve(removed)};tx.onerror=tx.onabort=()=>{db.close();reject(failure||tx.error||Error('工程删除失败'))};
  });
 };
 return session;
})();
