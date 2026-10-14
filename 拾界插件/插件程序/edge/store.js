const CaptureStore={
 async get(){return ShijieSession.drafts.web?structuredClone(ShijieSession.drafts.web):null},
 async set(data){ShijieSession.drafts.web=structuredClone(data)},
 async clear(){ShijieSession.drafts.web=null},
 async setRegion(data){const id=await ShijieSmartSplit.storeCapture(data);ShijieSession.drafts.region=id;return id},
 async getRegion(id){return ShijieSmartSplit.capture(id)},
 async clearRegion(){const id=ShijieSession.drafts.region;ShijieSession.drafts.region=null;if(id)await ShijieSmartSplit.clearCapture(id)}
};
