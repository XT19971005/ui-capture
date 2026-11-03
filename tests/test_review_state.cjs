const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../legacy/拾界插件/插件程序/edge/image-editor.js'),'utf8');
const c={};vm.runInNewContext(source.slice(source.indexOf('function needsReview('),source.indexOf('function viewSource(')),c);
test('local review findings cannot be hidden by a completed unreviewed extraction',()=>{
 assert.equal(c.needsReview({recognition:{reviewStatus:'NOT_REVIEWED',selectedRefine:{status:'NEEDS_REVIEW'}},nodes:[]}),true);
 assert.equal(c.needsReview({recognition:{reviewStatus:'PASS'},nodes:[{reviewIssue:'牌面不一致'}]}),true);
 assert.equal(c.needsReview({recognition:{reviewStatus:'PASS'},nodes:[{versionArchived:true,reviewIssue:'旧版本'}]}),false);
 assert.equal(c.needsReview({recognition:{reviewStatus:'NOT_REVIEWED'},nodes:[]}),false);
});
