const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../legacy/拾界插件/插件程序/edge/image-editor.js'),'utf8');
const c={};vm.runInNewContext(source.slice(source.indexOf('function needsReview('),source.indexOf('function viewSource(')),c);
test('local review findings cannot be hidden by a completed unreviewed extraction',()=>{
 assert.equal(c.needsReview({recognition:{reviewStatus:'NOT_REVIEWED',selectedRefine:{status:'NEEDS_REVIEW'}},nodes:[]}),true);
 assert.equal(c.needsReview({recognition:{reviewStatus:'PASS'},nodes:[{reviewIssue:'牌面不一致'}]}),true);
 assert.equal(c.needsReview({recognition:{reviewStatus:'PASS'},nodes:[{versionArchived:true,reviewIssue:'旧版本'}]}),false);
 assert.equal(c.needsReview({recognition:{reviewStatus:'NOT_REVIEWED'},nodes:[]}),false);
});
test('unreviewed generated layers stay visible until manually checked, without masking known issues',()=>{
 const element=()=>({children:[],dataset:{},append(...items){this.children.push(...items)},replaceChildren(){this.children=[]},setAttribute(){}}),list=element(),elements={'layer-list':list,'layer-search':{value:''},'layer-count':{}};
 const helperScope={};vm.runInNewContext(source.split('\n').find(l=>l.startsWith('function annotationLayerName(')),helperScope);const context={annotationLayerName:helperScope.annotationLayerName,document:{createElement:element},$:id=>elements[id],window:{},layerFilter:'all',selected:null,scene:{nodes:[
  {id:'pending',name:'红中牌',type:'image',review:true,assetReviewStatus:'NOT_REVIEWED'},
  {id:'issue',name:'标题',type:'image',reviewIssue:'比例不符',assetReviewStatus:'NOT_REVIEWED'},
  {id:'checked',name:'人工确认',type:'image',review:false,assetReviewStatus:'NOT_REVIEWED'},
  {id:'passed',name:'已复核',type:'image',assetReviewStatus:'PASS'},
  {id:'manual',name:'手动导入',type:'image'}]}};
 helperScope.scene=context.scene;vm.runInNewContext(source.slice(source.indexOf('function renderList('),source.indexOf('function props(')),context);context.renderList();
 const row=id=>list.children.find(n=>n.dataset.id===id),badge=id=>row(id).children[2];
 assert.equal(badge('pending')?.textContent,'未复核');assert.match(badge('pending').title,/对照原图/);
 assert.equal(badge('issue')?.textContent,'需校对');
 for(const id of ['checked','passed','manual'])assert.equal(badge(id),undefined);
});
