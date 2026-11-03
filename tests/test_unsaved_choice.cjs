const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../legacy/拾界插件/插件程序/edge/studio.js'),'utf8');
const snippet=source.slice(source.indexOf(' let discardPending='),source.indexOf('\n const resetButton='));
function setup(){let doc={},dirty=true,fail=false,shown=0;const nodes=new Map();const node=id=>{if(!nodes.has(id))nodes.set(id,{});return nodes.get(id)};let onclose;const dialog={querySelector:node,addEventListener:(k,f)=>{if(k==='close')onclose=f},close:()=>onclose?.()};const ctx={a:{get:()=>doc},B:{library:{isDirty:()=>dirty}},modal:()=>{shown++;return dialog},saveProject:async()=>{if(fail)throw Error('磁盘已满');dirty=false}};vm.runInNewContext(snippet+';this.confirmDiscard=confirmDiscard;',ctx);return {ctx,node,dialog,get shown(){return shown},fail:()=>fail=true,change:()=>doc={},saved:()=>dirty=false};}
test('unsaved replacement offers cancel, discard and save; repeated requests do not race',async()=>{const h=setup(),p=h.ctx.confirmDiscard();assert.equal(h.shown,1);assert.equal(await h.ctx.confirmDiscard(),false);h.node('#discard-stay').onclick();assert.equal(await p,false);const retry=h.ctx.confirmDiscard();h.node('#discard-continue').onclick();assert.equal(await retry,true);const save=h.ctx.confirmDiscard();await h.node('#discard-save').onclick();assert.equal(await save,true);assert.equal(await h.ctx.confirmDiscard(),true);});
test('failed saves and changed document preserve the current work',async()=>{const h=setup(),p=h.ctx.confirmDiscard();h.fail();await h.node('#discard-save').onclick();assert.match(h.node('#discard-note').textContent,/磁盘已满/);assert.equal(h.node('#discard-save').disabled,false);h.change();h.node('#discard-continue').onclick();assert.equal(await p,false);});
test('confirmed project navigation skips only its own unload check, then restores dirty protection',()=>{
 const timers=[],warnings=[],urls=[];const ctx={a:{get:()=>({})},B:{library:{isDirty:()=>true}},setTimeout:fn=>timers.push(fn)};
 ctx.location={set href(url){urls.push(url);ctx.warnBeforeUnload({preventDefault:()=>warnings.push('blocked')})}};
 const navigation=source.slice(source.indexOf(' let confirmedNavigation='),source.indexOf('\n const resetButton='));
 vm.runInNewContext(navigation+';this.navigateConfirmed=navigateConfirmed;this.warnBeforeUnload=warnBeforeUnload;',ctx);
 ctx.warnBeforeUnload({preventDefault:()=>warnings.push('blocked')});assert.equal(warnings.length,1);
 ctx.navigateConfirmed('export.html?project=qa');assert.deepEqual(urls,['export.html?project=qa']);assert.equal(warnings.length,1);
 timers.forEach(fn=>fn());ctx.warnBeforeUnload({preventDefault:()=>warnings.push('blocked')});assert.equal(warnings.length,2);
});
