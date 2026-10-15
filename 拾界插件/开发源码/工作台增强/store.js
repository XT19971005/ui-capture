let regionCaptureRevision=0;
const CaptureStore={
 async get(){return ShijieSession.drafts.web?structuredClone(ShijieSession.drafts.web):null},
 async set(data){ShijieSession.drafts.web=structuredClone(data)},
 async clear(){ShijieSession.drafts.web=null},
 async setRegion(data){const revision=++regionCaptureRevision,id=await ShijieSmartSplit.storeCapture(data);if(revision===regionCaptureRevision)ShijieSession.drafts.region=id;else if(id!==ShijieSession.drafts.region)await ShijieSmartSplit.clearCapture(id);return id},
 async getRegion(id){const revision=++regionCaptureRevision,entry=await ShijieSmartSplit.capture(id);if(revision===regionCaptureRevision)ShijieSession.drafts.region=id;return entry},
 async clearRegion(){++regionCaptureRevision;const id=ShijieSession.drafts.region;ShijieSession.drafts.region=null;if(id)await ShijieSmartSplit.clearCapture(id)}
};
