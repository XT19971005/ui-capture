const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../legacy/拾界插件/插件程序/edge/studio.js'),'utf8');
const snippet=source.slice(source.indexOf(' async function confirmDiscard('),source.indexOf(' let confirmedNavigation='));
function setup(){let doc={},dirty=true,fail=false;const ctx={a:{get:()=>doc,status:text=>ctx.status=text},B:{library:{isDirty:()=>dirty}},saveCheckpoint:async()=>{if(fail)throw Error('磁盘已满');dirty=false}};vm.runInNewContext(snippet+';this.confirmDiscard=confirmDiscard;',ctx);return {ctx,fail:()=>fail=true};}
test('replacing a document waits for its checkpoint',async()=>{const h=setup();assert.equal(await h.ctx.confirmDiscard(),true)});
test('failed checkpoint prevents replacement and preserves a retryable document',async()=>{const h=setup();h.fail();assert.equal(await h.ctx.confirmDiscard(),false);assert.match(h.ctx.status,/磁盘已满/)});
test('confirmed project navigation skips only its own unload check, then restores dirty protection',()=>{
 const timers=[],warnings=[],urls=[];const ctx={a:{get:()=>({})},B:{library:{isDirty:()=>true}},setTimeout:fn=>timers.push(fn)};
 ctx.location={set href(url){urls.push(url);ctx.warnBeforeUnload({preventDefault:()=>warnings.push('blocked')})}};
 const navigation=source.slice(source.indexOf(' let confirmedNavigation='),source.indexOf('\n const resetButton='));
 vm.runInNewContext(navigation+';this.navigateConfirmed=navigateConfirmed;this.warnBeforeUnload=warnBeforeUnload;',ctx);
 ctx.warnBeforeUnload({preventDefault:()=>warnings.push('blocked')});assert.equal(warnings.length,1);
 ctx.navigateConfirmed('export.html?project=qa');assert.deepEqual(urls,['export.html?project=qa']);assert.equal(warnings.length,1);
 timers.forEach(fn=>fn());ctx.warnBeforeUnload({preventDefault:()=>warnings.push('blocked')});assert.equal(warnings.length,2);
});
