const CaptureStore={
  async transaction(mode,action){
    const db=await new Promise((resolve,reject)=>{const req=indexedDB.open('shijie-capture',1);req.onupgradeneeded=()=>req.result.createObjectStore('captures');req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error);});
    return new Promise((resolve,reject)=>{const tx=db.transaction('captures',mode);const req=action(tx.objectStore('captures'));let result;req.onsuccess=()=>{result=req.result};tx.oncomplete=()=>{db.close();resolve(result)};tx.onerror=()=>{db.close();reject(tx.error)};tx.onabort=()=>{db.close();reject(tx.error||Error('本地存储操作未完成'))};});
  },
  setRegion(data){return this.transaction('readwrite',store=>store.put(data,'region-import'));},
  getRegion(){return this.transaction('readonly',store=>store.get('region-import'));},
  clearRegion(){return this.transaction('readwrite',store=>store.delete('region-import'));},
  get(){return this.transaction('readonly',store=>store.get('latest'));},
  set(data){return this.transaction('readwrite',store=>store.put(data,'latest'));},
  clear(){return this.transaction('readwrite',store=>store.delete('latest'));}
};
