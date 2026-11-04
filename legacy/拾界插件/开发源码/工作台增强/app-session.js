/* Only explicit manual project saves persist; working edits stay in RAM. */
window.ShijieSession=(()=>{
 // ponytail: HTTP omits randomUUID; this UUID v4 fallback still requires native getRandomValues.
 if(typeof crypto.randomUUID!=='function')crypto.randomUUID=()=>{
  const bytes=crypto.getRandomValues(new Uint8Array(16));bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;
  const hex=Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');
  return [hex.slice(0,8),hex.slice(8,12),hex.slice(12,16),hex.slice(16,20),hex.slice(20)].join('-');
 };
 // SHA-256 for source identity on explicitly supported HTTP deployments.
 // HTTPS retains native WebCrypto; no credentials or network requests are involved.
 async function digest(algorithm,input){
  if(crypto.subtle)return crypto.subtle.digest(algorithm,input);
  if(algorithm!=='SHA-256')throw Error('Unsupported digest');
  const bytes=new Uint8Array(input.buffer||input,input.byteOffset||0,input.byteLength),length=bytes.length;
  const data=new Uint8Array(Math.ceil((length+9)/64)*64);data.set(bytes);data[length]=128;
  const view=new DataView(data.buffer);view.setUint32(data.length-8,Math.floor(length/0x20000000));view.setUint32(data.length-4,(length*8)>>>0);
  const k=[0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
  const h=new Uint32Array([0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19]),w=new Uint32Array(64),rot=(x,n)=>(x>>>n)|(x<<(32-n));
  for(let offset=0;offset<data.length;offset+=64){
   for(let i=0;i<16;i++)w[i]=view.getUint32(offset+i*4);
   for(let i=16;i<64;i++){const a=w[i-15],b=w[i-2];w[i]=(w[i-16]+(rot(a,7)^rot(a,18)^(a>>>3))+w[i-7]+(rot(b,17)^rot(b,19)^(b>>>10)))>>>0}
   let [a,b,c,d,e,f,g,j]=h;
   for(let i=0;i<64;i++){const t1=(j+(rot(e,6)^rot(e,11)^rot(e,25))+((e&f)^(~e&g))+k[i]+w[i])>>>0,t2=((rot(a,2)^rot(a,13)^rot(a,22))+((a&b)^(a&c)^(b&c)))>>>0;j=g;g=f;f=e;e=(d+t1)>>>0;d=c;c=b;b=a;a=(t1+t2)>>>0}
   for(const [i,v] of [a,b,c,d,e,f,g,j].entries())h[i]=(h[i]+v)>>>0;
  }
  const out=new DataView(new ArrayBuffer(32));for(let i=0;i<8;i++)out.setUint32(i*4,h[i]);return out.buffer;
 }
 const session={digest,library:new Map(),drafts:{web:null,image:null,region:null},workspaceColor:'#12151c',writerId:crypto.randomUUID()};
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
 function open(){return new Promise((resolve,reject)=>{const r=indexedDB.open('shijie-library-user-'+window.SHIJIE.user);r.onupgradeneeded=()=>{if(!r.result.objectStoreNames.contains('projects'))r.result.createObjectStore('projects',{keyPath:'id'})};r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);r.onblocked=()=>reject(Error('工程库被其他页面占用，请关闭旧版本页面后重试'))})}
 session.legacySaved=async()=>{const db=await open();return new Promise((resolve,reject)=>{const tx=db.transaction('projects'),r=tx.objectStore('projects').getAll();let rows=[];r.onsuccess=()=>{rows=r.result};tx.oncomplete=()=>{db.close();resolve(rows.map(unpack))};tx.onerror=tx.onabort=()=>{db.close();reject(tx.error||Error('工程恢复读取失败'))}})};
 function versionOf(entry){return entry?.persistedVersion||entry?.revision||null}
 function assertVersion(old,expected){const wanted=expected&&typeof expected==='object'?expected.version:expected;if(versionOf(old)!==wanted&&!(expected?.allowMissing===true&&!old)){const conflict=Error('工程已在另一个页面更新；当前修改仍在页面中，请下载或另存副本。');conflict.name='RecoveryConflictError';throw conflict}}
 session.saveEntry=async (entry,expectedVersion=null)=>{
  if(entry.saveMode!=='saved')throw Error('工程仅在点击保存工程时写入');
  const value=structuredClone(entry),db=await open();
  return new Promise((resolve,reject)=>{
   const tx=db.transaction('projects','readwrite'),store=tx.objectStore('projects'),get=store.get(value.id),evictions=[];let failure;
   get.onsuccess=()=>{try{
    const old=get.result;assertVersion(old,expectedVersion);value.persistedVersion=value.revision;value.writerId=session.writerId;if(old?.saveMode==='saved'){value.saveMode='saved';value.savedAt=old.savedAt||value.savedAt}value.storageVersion='recovery-v3';value.persistedAt=Date.now();store.put(pack(value));
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
