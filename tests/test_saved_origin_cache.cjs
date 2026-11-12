const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
test('saved indicator waits for the refresh cache to include the acknowledged disk origin',async()=>{
 const source=fs.readFileSync(path.join(__dirname,'../legacy/拾界插件/插件程序/edge/studio.js'),'utf8'),doc={_projectId:'p',nodes:[]};let cached=false,saved=false,release;
 const gate=new Promise(r=>release=r),c={window:{},a:{get:()=>doc,kind:'image',status(){}},B:{library:{put:async()=>({id:'p'}),isDirty:()=>false}},recoveryState:{style:{}},rememberTabProject(){},recoverySaved(){saved=true},recoveryError(){},save(){},reloadRecovery:{schedule(d){assert.equal(d,doc);cached=true},flush:()=>gate}};
 vm.runInNewContext(source.slice(source.indexOf(' async function persistRecovery('),source.indexOf(' function save(){'))+';this.persist=persistRecovery',c);
 const result=c.persist(doc,{manual:true});await new Promise(r=>setImmediate(r));assert.equal(cached,true);assert.equal(saved,false);release();await result;assert.equal(saved,true);
});
