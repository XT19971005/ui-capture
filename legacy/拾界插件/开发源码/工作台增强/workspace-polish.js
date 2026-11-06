/* Shared workbench hierarchy; mode differences stay in the import controls. */
(()=>{
 const imageMode=!!document.getElementById('image-file'),header=document.querySelector('.app-header');if(!header)return;
 document.body.classList.add('unified-workbench');
 document.querySelector('.local-badge')?.setAttribute('hidden','');
 document.getElementById('demo')?.setAttribute('hidden','');
 const noSelection=document.getElementById('no-selection');
 if(noSelection){noSelection.querySelector('.section-title').textContent='未选择图层';noSelection.querySelector('.tip').textContent='';noSelection.querySelector('.tip').hidden=true;noSelection.querySelector('.stats').hidden=true;noSelection.querySelector('.shortcut-list')?.remove()}
 const relation=document.querySelector('.relation-settings');if(relation)document.getElementById('design-panel').append(relation);
 const webOpen=document.querySelector('.header-actions .filebutton');webOpen?.classList.add('project-open');
 function viewSettings(){
  const target=document.getElementById('inspector-edit')||document.getElementById('design-panel'),settings=document.createElement('section');settings.className='inline-view-settings';settings.setAttribute('aria-label','背景设置');const title=document.createElement('h3');title.textContent='背景设置';settings.append(title,document.getElementById('background-settings'));target?.append(settings);
  ShijieSession.legacySaved().then(rows=>{if(!rows.length)return;const list=document.createElement('details'),summary=document.createElement('summary');summary.textContent='旧版已保存工程';list.append(summary);for(const p of rows){const save=document.createElement('button');save.type='button';save.textContent='下载 · '+(p.title||p.doc?.title||'未命名工程');save.onclick=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(p.doc)],{type:'application/json'})),link=document.createElement('a');link.href=url;link.download=(p.title||'旧工程').replace(/[\\/:*?"<>|]/g,'-').slice(0,120)+'.scene.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),60000)};list.append(save)}settings.append(list)}).catch(()=>{});

 }
 document.querySelector('[data-action=projects]').hidden=false;
 if(!imageMode){const parent=document.querySelector('.relation-settings');if(parent){const advanced=document.createElement('details');advanced.className='parent-settings';advanced.innerHTML='<summary>分组行为</summary>';advanced.append(parent);document.getElementById('properties').append(advanced);const oldProps=props;props=function(){oldProps();advanced.hidden=!nodes.get(selected)?.node?.children?.length};advanced.hidden=true;}viewSettings();return;}

 const $=id=>document.getElementById(id);
 const intake=document.createElement('div');intake.className='image-intake';intake.hidden=true;intake.setAttribute('role','group');intake.setAttribute('aria-label','图片导入');
 intake.append($('upload'),$('codex-settings'));header.querySelector('.header-actions').before(intake);
 const summary=$('recognition-summary');const splitDetails=document.createElement('dialog');splitDetails.className='studio-dialog studio-small-dialog split-status-dialog';splitDetails.innerHTML='<header><strong>复核详情</strong><form method="dialog"><button aria-label="关闭">×</button></form></header><section class="review-details-content"></section>';splitDetails.querySelector('section').append(summary);document.body.append(splitDetails);const reviewButton=document.createElement('button');reviewButton.id='review-info';reviewButton.textContent='复核详情';reviewButton.hidden=true;reviewButton.onclick=()=>window.ShijieInlinePanels.open(splitDetails);document.querySelector('.document-bar>div:first-child').append(reviewButton);
 $('cancel').textContent='取消';$('image-job').querySelector('div').append($('cancel'));
 document.querySelector('.import-formats')?.remove();
 const source=document.createElement('div');source.className='source-info';source.innerHTML='<strong id="image-source-title">尚未导入图片</strong><span id="image-source-size">PNG / JPG / WebP</span>';document.querySelector('.panel-title').after(source);
 const title=document.querySelector('.layers .section-title');title.hidden=true;
 const bottom=document.createElement('div');bottom.className='layer-bottom';const box=document.createElement('button');box.id='add-box';box.textContent='＋ 矩形';box.onclick=()=>{if(!scene||busy)return;checkpoint('添加矩形');const n={id:uid(),name:'矩形',type:'rect',x:Math.max(0,(scene.width-220)/2),y:Math.max(0,(scene.height-120)/2),width:Math.min(220,scene.width),height:Math.min(120,scene.height),radius:8,fill:'#ad9aff',provenance:'manual'};scene.nodes.push(n);selected=n.id;refresh();changed();window.studio?.select([n.id],true)};
 const clear=document.createElement('button');clear.id='clear-image';clear.textContent='关闭工程';clear.title='关闭当前工程，已保存工程保留';clear.onclick=async()=>{if(!scene||busy)return;const owned=scene,ownerTask=task,snapshot=JSON.stringify(owned);clear.disabled=true;try{await window.studio.flush();if(scene!==owned||task!==ownerTask)return;if(JSON.stringify(scene)!==snapshot){status('工程已有新修改，未清空。');return}await window.studio.adapter.closeProject();if(scene)return;window.studio.setInitial(null);$('layer-count').textContent='0';$('image-source-title').textContent='尚未导入图片';$('image-source-size').textContent='PNG / JPG / WebP';for(const key of ['text','vector','raster'])$('stat-'+key).textContent='—';window.studio.sync(false)}catch(e){status('关闭工程未完成：'+e.message+'。当前工程保留。')}finally{clear.disabled=!scene||busy}};
 box.disabled=clear.disabled=!scene||busy;bottom.append($('add-text'),box,clear);document.querySelector('.layers').append(bottom);
 const propertyHead=document.createElement('div');propertyHead.className='property-heading';propertyHead.innerHTML='<span>图层</span>';$('properties').prepend(propertyHead);
 const positionGrid=$('properties').querySelector('.grid');positionGrid.after($('text-label'));$('text').rows=4;
 const order=document.querySelector('.layer-actions');order.classList.add('order-buttons');$('properties').append(order);$('up').textContent='上移一层';$('down').textContent='下移一层';
 const secondOrder=document.createElement('div');secondOrder.className='order-buttons';const duplicate=document.createElement('button');duplicate.textContent='复制';duplicate.onclick=()=>window.studio.run('duplicate');secondOrder.append(duplicate,$('delete'));order.after(secondOrder);
 const originalUpdateButtons=updateButtons;updateButtons=function(){originalUpdateButtons();duplicate.disabled=!node()||busy};
 const strokeDetails=document.createElement('details');strokeDetails.className='text-stroke-details';strokeDetails.innerHTML='<summary>文字描边</summary>';strokeDetails.append($('stroke-props'));secondOrder.after(strokeDetails);
 const refineControls=document.querySelector('.selected-refine-controls');if(refineControls)$('properties').after(refineControls);
 const originalProps=props;props=function(){originalProps();const n=node();propertyHead.querySelector('span').textContent=n?.type==='text'?'文字图层':n?.type==='image'?'图片图层':'形状图层';strokeDetails.hidden=n?.type!=='text';};
 const tools=document.querySelector('.toolbar .tools'),extras=[...tools.querySelectorAll('[data-tool]')].filter(b=>!['select','hand'].includes(b.dataset.tool));
 const more=document.createElement('details');more.className='image-tools-menu';more.innerHTML='<summary>工具 ▾</summary><div></div>';more.querySelector('div').append(...extras);extras.forEach(b=>b.addEventListener('click',()=>more.open=false));tools.append(more);const traceSettings=$('trace-colors').closest('details');traceSettings.querySelector('.tip')?.remove();more.querySelector('div').append(traceSettings);
 const zoom=$('zoom');zoom.hidden=true;const widthOption=new Option('适宽','width');zoom.add(widthOption);
 const viewTools=document.querySelector('.view-tools'),fitButton=$('fit');viewTools.replaceChildren($('view'));
 for(const [id,text,label] of [['zoomout','−','缩小'],['zoomlabel','100%',null],['zoomin','＋','放大'],['fit','适应',null],['fit-width','适宽',null],['actual','原尺寸',null]]){
  const el=id==='fit'?fitButton:document.createElement(id==='zoomlabel'?'output':'button');el.id=id;el.textContent=text;if(label)el.setAttribute('aria-label',label);viewTools.append(el);
 }
 viewTools.append(zoom);
 function custom(value){let option=zoom.querySelector('[data-custom]');if(!option){option=new Option();option.dataset.custom='true';zoom.add(option)}option.value=String(value);option.textContent=Math.round(value*100)+'%';zoom.value=String(value);fit()}
 $('zoomout').onclick=()=>custom(scale/1.25);$('zoomin').onclick=()=>custom(scale*1.25);$('actual').onclick=()=>custom(1);$('fit-width').onclick=()=>{zoom.value='width';fit(false)};
 $('viewport').setAttribute('tabindex','0');$('viewport').setAttribute('aria-label','设计画布');
 const inline=$('image-inline-text');let editing=null;
 function closeInline(apply=true){if(!editing)return;const previous=editing;editing=null;inline.hidden=true;const n=scene?.nodes.find(n=>n.id===previous.id);if(apply&&n&&inline.value!==previous.value){checkpoint('编辑文字');n.text=inline.value;n.name=n.text;refresh();changed()}}
 $('viewport').addEventListener('dblclick',e=>{if(busy||tool!=='select')return;const id=e.target.closest('[data-id]')?.dataset.id,n=scene?.nodes.find(n=>n.id===id);if(!n||n.type!=='text'||n.locked)return;closeInline();window.studio.select([id]);editing={id,value:n.text};inline.value=n.text;inline.hidden=false;Object.assign(inline.style,{left:imageOrigin.x+n.x*scale+'px',top:imageOrigin.y+n.y*scale+'px',width:Math.max(100,n.width*scale)+'px',height:Math.max(42,n.height*scale+8)+'px',fontFamily:n.fontFamily||'Microsoft YaHei',fontSize:Math.max(10,n.fontSize*scale)+'px',fontWeight:n.fontWeight||400,fontStyle:n.fontStyle||'normal'});inline.focus();inline.select()});
 inline.onblur=()=>closeInline();inline.onkeydown=e=>{if(e.key==='Escape'){e.preventDefault();closeInline(false)}if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();closeInline()}};
 $('reset-initial').addEventListener('pointerdown',()=>closeInline(false));
 const originalRefresh=refresh;refresh=function(){originalRefresh();$('recognize').hidden=false;reviewButton.hidden=!scene?.recognition;if(scene){$('image-source-title').textContent=scene.title||'图片工程';$('image-source-size').textContent=scene.width+' × '+scene.height+' px';$('stat-text').textContent=scene.nodes.filter(n=>n.type==='text').length;$('stat-vector').textContent=scene.nodes.filter(n=>['rect','ellipse','path'].includes(n.type)).length;$('stat-raster').textContent=scene.nodes.filter(n=>n.type==='image').length}box.disabled=clear.disabled=!scene||busy};
 viewSettings();if(scene)refresh();
})();

/* Web editor shares the compact image workspace shell. */
(()=>{
 if(window.studio?.adapter.kind!=='web')return;
 const byId=id=>document.getElementById(id),studio=window.studio;
 document.body.classList.add('web-workbench');
 byId('empty').querySelector('h1').textContent='从浏览器抓取网页';byId('empty').querySelector('small').textContent='在目标网页点击插件抓取 · 也可从顶部打开工程';
 const bar=document.querySelector('.studio-bar'),history=document.querySelector('[data-action=history]');
 if(history)document.querySelector('.history-tools').append(history);
 if(bar)bar.hidden=true;
 document.querySelector('.doc-tag')?.remove();
 byId('actual').textContent='原尺寸';
 byId('clear').textContent='关闭工程';byId('clear').title='关闭当前工程，已保存工程保留';
 const close=byId('clear').onclick;
 byId('clear').onclick=async()=>{if(!current||busy)return;const owned=current;try{await studio.flush();if(current!==owned||busy)return;await close();studio.setInitial(null);studio.sync(false);status('已关闭工程，已保存工程保留')}catch(e){status('关闭工程未完成：'+e.message)}};
 const help=document.createElement('p');help.className='workspace-inspector-help';help.textContent='在目标网页点击浏览器插件抓取，或打开已保存工程。选择图层后可编辑文字、位置和样式。';byId('no-selection').append(help);
 const view=document.querySelector('.view-tools'),fit=document.createElement('button');fit.id='fit-selected';fit.textContent='适应所选';fit.title='缩放查看所选图层，不修改设计尺寸';byId('fit-width').after(fit);
 fit.onclick=()=>{if(!current||studio.isBusy())return;const entries=studio.adapter.entries(),box=StudioBase.bounds(studio.roots().map(id=>entries.get(id)).filter(e=>e&&e.visible).map(e=>e.bounds));if(!box)return;const v=byId('preview');zoomMode='custom';scale=Math.min(8,Math.max(.002,Math.min((v.clientWidth-64)/Math.max(1,box.width),(v.clientHeight-64)/Math.max(1,box.height))));applyZoom();v.scrollLeft=origin.x+(box.x+box.width/2)*scale-v.clientWidth/2;v.scrollTop=origin.y+(box.y+box.height/2)*scale-v.clientHeight/2;studio.overlay();status('已适应所选图层；设计尺寸保持')};
 const toggle=document.createElement('button');toggle.id='inspector-toggle';toggle.textContent='设计栏';toggle.setAttribute('aria-controls','design-panel');view.append(toggle);
 toggle.onclick=()=>{document.body.classList.toggle('inspector-collapsed');sync();applyZoom(undefined,true)};
 function sync(){fit.disabled=!current||studio.isBusy()||!studio.ids.size;toggle.setAttribute('aria-expanded',String(!document.body.classList.contains('inspector-collapsed')))}
 const previous=studio.sync;studio.sync=function(...args){const result=previous.apply(this,args);sync();return result};sync();
 const oldExport=window.syncWebUI;
 window.syncWebUI=function(...args){const result=oldExport.apply(this,args),format=byId('output-format').value;const hints={png:'PNG 为合并图片，文字和图层不可单独编辑。',svg:'SVG 保留可支持的文字与矢量；图片和复杂网页效果仍可能为位图。',psd:'PSD 为分层文件；网页复杂效果可能栅格化，请检查字体与层级。',figma:'导出插件数据，需要通过 AI拆图助手的 Figma 导入插件打开。'};byId('output-hint').textContent=hints[format]+(byId('output-range').value==='selected'?' 所选范围不包含画板底色。':'');return result};syncWebUI();
})();

/* One visible entry per action; the empty canvas owns first import/open. */
(()=>{
 const studio=window.studio;if(!studio)return;
 const emptyOpen=document.getElementById('import-empty');
 if(studio.adapter.kind==='web'&&emptyOpen)emptyOpen.onclick=()=>studio.run('projects');
 function syncEntryVisibility(){document.body.classList.toggle('workspace-has-document',!!studio.adapter.get())}
 const previous=studio.sync;studio.sync=function(...args){const result=previous.apply(this,args);syncEntryVisibility();return result};syncEntryVisibility();
})();

/* Both editing modes share the same empty-state structure and panel geometry. */
(()=>{
 const empty=document.getElementById('empty'),oldLogo=empty?.querySelector('.empty-logo');
 if(oldLogo){const art=document.createElement('div');art.className='empty-art';art.innerHTML='<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="3" width="16" height="18" rx="2"/><path d="m4 15 5-5 4 4 3-3 4 4"/><circle cx="15" cy="7" r="1"/></svg>';oldLogo.replaceWith(art)}
 if(window.studio?.adapter.kind==='web'){const width=()=>{try{const saved=Number(localStorage.getItem('shijie.layer-panel-width'));if(saved)document.body.style.setProperty('--layer-panel-width',Math.round(Math.max(200,Math.min(420,innerWidth*.3,saved)))+'px')}catch{}};width();window.addEventListener('resize',width)}
})();

/* A single AI settings entry, shared by both editors. */
document.addEventListener('DOMContentLoaded',()=>{
 const header=document.querySelector('.header-actions');if(!header||!window.ShijieSmartSplit)return;
 document.getElementById('assistant-text-chip')?.remove();document.getElementById('assistant-image-chip')?.remove();
 const button=document.getElementById('assistant-model-settings')||document.createElement('button');button.id='assistant-model-settings';button.type='button';button.textContent='AI 设置';button.setAttribute('aria-haspopup','dialog');header.append(button);
 const controls=header.querySelector('.project-controls'),save=document.getElementById('save-project'),open=document.getElementById('open-project'),state=document.getElementById('save-state')||header.querySelector('.local-badge');
 if(controls){if(open)controls.append(open);if(save)controls.append(save);if(state)controls.append(state);header.prepend(controls)}
 const panel=document.createElement('dialog');panel.className='codex-dialog shared-ai-settings';panel.setAttribute('aria-label','AI 设置');panel.innerHTML='<form method="dialog"><strong>AI 设置</strong><button aria-label="关闭AI设置">×</button></form><section><h3>理解与分析</h3><label>模型来源<select data-provider><option value="codex">Codex 订阅</option><option value="tygpt">TYGPT</option></select></label><label>分析模型<select data-model></select></label><label data-text-key-label hidden>TYGPT Key<span class="assistant-key-row"><input data-text-key type="password" aria-label="TYGPT Key" autocomplete="new-password" placeholder="已有配置无需重复填写；更新时输入新 Key"><button type="button" data-text-key-reveal aria-pressed="false">显示</button></span></label><div class="ai-connection-actions"><button type="button" data-key-save hidden>保存并检查</button><button type="button" data-check>检查已有连接</button><button type="button" data-login>登录 Codex</button><a data-login-link hidden target="_blank" rel="noopener noreferrer">打开登录页</a></div><p data-text-status role="status"></p></section><section><h3>图片生成与补全</h3><label>图片来源<select data-image-provider><option value="codex">Codex · 内置生图</option><option value="aimake">亿创</option></select></label><label data-image-model-label hidden>生图模型<select data-image-model><option value="nano-banana-2">Nano Banana 2</option><option value="gpt-image-2" selected>GPT Image 2</option><option value="nano-banana-pro">Nano Banana Pro</option></select></label><label data-image-key-label hidden>本人亿创 Key<input data-image-key type="password" autocomplete="new-password" placeholder="留空保留现有连接"></label><button type="button" data-image-refresh>读取全部生图模型</button><p data-image-status></p></section><footer><span data-result role="status"></span><button type="button" class="primary" data-apply>应用设置</button></footer>';document.body.append(panel);
 const q=s=>panel.querySelector(s),provider=q('[data-provider]'),model=q('[data-model]'),image=q('[data-image-provider]');let revision=0;
 let operationBusy=false,checking=false,modelReady=false,readyProvider=null;
 function imageModels(value){const select=q('[data-image-model]'),chosen=value.model||select.value;const items=value.models||[];if(items.length)select.replaceChildren(...items.map(m=>new Option((m.name||m.id)+(m.reference===false?' · 仅文生图':''),m.id)));if([...select.options].some(o=>o.value===chosen))select.value=chosen;}
 const safeError=(error,...secrets)=>secrets.filter(Boolean).reduce((message,key)=>message.split(key).join('[已隐藏]'),String(error.message||'连接不可用'));
 function connectionControls(){for(const selector of ['[data-provider]','[data-text-key]','[data-text-key-reveal]','[data-key-save]','[data-login]','[data-image-provider]','[data-image-model]','[data-image-key]'])q(selector).disabled=operationBusy;q('[data-model]').disabled=operationBusy||checking||!modelReady;q('[data-check]').disabled=operationBusy||checking;q('[data-apply]').disabled=operationBusy;q('[data-image-refresh]').disabled=operationBusy;q('[data-image-refresh]').hidden=image.value!=='aimake'}
 const visibility=()=>{q('[data-text-key-label]').hidden=provider.value!=='tygpt';q('[data-key-save]').hidden=provider.value!=='tygpt';q('[data-login]').hidden=provider.value!=='codex';q('[data-image-key-label]').hidden=image.value!=='aimake';q('[data-image-model-label]').hidden=image.value!=='aimake';q('[data-login-link]').hidden=true;q('[data-image-refresh]').hidden=image.value!=='aimake'};
 async function models(redact=''){
  const rev=++revision,source=provider.value;checking=true;modelReady=false;readyProvider=null;connectionControls();q('[data-text-status]').textContent='正在检查连接…';
  try{const value=await ShijieSmartSplit.assistantModels(source);if(rev!==revision||source!==provider.value)return;
   let pref=null;try{pref=JSON.parse(localStorage.getItem('shijie.assistant.text-model:'+window.SHIJIE.user)||'null');if(pref?.provider==='taishi')pref={...pref,provider:'tygpt'}}catch{}
   model.replaceChildren(...(value.models||[]).map(m=>new Option(m.name||m.id,m.id)));const chosen=pref?.provider===source?pref.model:value.model;if([...model.options].some(o=>o.value===chosen))model.value=chosen;
   modelReady=!!value.ready&&!!model.options.length;readyProvider=modelReady?source:null;q('[data-text-status]').textContent=modelReady?(source==='tygpt'?'TYGPT 连接成功，模型已就绪':'Codex 已连接'):(source==='tygpt'?(value.configured?'TYGPT 已配置，但连接检查未通过；请检查网络与 Key 权限':'尚未配置 TYGPT，请填写 Key 后保存并检查'):'Codex 尚未登录，请点击登录 Codex');return value;
  }catch(error){if(rev===revision)q('[data-text-status]').textContent='连接检查失败：'+safeError(error,redact)}finally{if(rev===revision){checking=false;connectionControls()}}
 }
 provider.onchange=()=>{visibility();void models()};image.onchange=()=>{visibility();q('[data-image-status]').textContent=image.value==='aimake'?'亿创 · '+(q('[data-image-model]').selectedOptions[0]?.textContent||'请选择模型')+'；点击应用设置验证并保存':'Codex · 内置生图；点击应用设置保存'};q('[data-check]').onclick=()=>{if(!operationBusy)return models()};
 let savingKey=false;
 const textKey=q('[data-text-key]'),reveal=q('[data-text-key-reveal]');
 reveal.onclick=()=>{const shown=textKey.type==='password';textKey.type=shown?'text':'password';reveal.textContent=shown?'隐藏':'显示';reveal.setAttribute('aria-pressed',String(shown))};
 q('[data-key-save]').onclick=async()=>{
  if(operationBusy||savingKey||provider.value!=='tygpt')return;const secret=textKey.value.trim();if(!secret){q('[data-text-status]').textContent='请先填写 TYGPT Key';return}
  operationBusy=savingKey=true;connectionControls();q('[data-text-status]').textContent='正在保存并检查 TYGPT 连接…';let saved=false;
  try{try{await ShijieService.request('engine/assistant/tygpt-key',{method:'POST',body:JSON.stringify({key:secret})});saved=true}finally{textKey.value=''}const value=await models(secret);if(!value?.ready||!modelReady)q('[data-text-status]').textContent='TYGPT Key 已保存；连接检查未通过，请检查网络与权限后重试检查，无需重复保存 Key';}
  catch(error){q('[data-text-status]').textContent=(saved?'TYGPT Key 已保存；检查失败：':'TYGPT Key 保存失败：')+safeError(error,secret)}
  finally{textKey.value='';operationBusy=savingKey=false;connectionControls()}
 };
 q('[data-login]').onclick=()=>{panel.close();document.getElementById('codex-settings')?.click();document.getElementById('ai-provider-codex')?.click();document.getElementById('codex-method-device')?.click()};
 button.onclick=async()=>{
  if(operationBusy||window.studio?.isBusy()||window.ShijieFreeAssistant?.isBusy?.())return;q('[data-result]').textContent='';textKey.type='password';reveal.textContent='显示';reveal.setAttribute('aria-pressed','false');textKey.value=q('[data-image-key]').value='';
  try{const pref=JSON.parse(localStorage.getItem('shijie.assistant.text-model:'+window.SHIJIE.user)||'null');provider.value=['taishi','tygpt'].includes(pref?.provider)?'tygpt':'codex'}catch{provider.value='codex'}
  visibility();window.ShijieInlinePanels.open(panel);operationBusy=true;connectionControls();void models();const openedRevision=revision;q('[data-image-status]').textContent='正在读取已有图片连接…';
  try{const value=await ShijieSmartSplit.imageProvider();if(openedRevision!==revision)return;image.value=value.provider;imageModels(value);visibility();q('[data-image-status]').textContent=value.provider==='codex'?'使用当前登录用户的 Codex 账号':'亿创 · '+q('[data-image-model]').value+' 已配置'+(value.catalogIncomplete?'；部分模型目录暂未读全，可点击读取全部生图模型重试':'')}catch(error){if(openedRevision===revision)q('[data-image-status]').textContent='图片连接读取失败：'+safeError(error)}finally{operationBusy=false;connectionControls()}
 };
 q('[data-image-refresh]').onclick=async()=>{
  if(operationBusy)return;const openedRevision=revision,secret=q('[data-image-key]').value.trim();operationBusy=true;connectionControls();q('[data-image-status]').textContent='正在读取亿创生图模型，不提交生成…';
  try{const value=await ShijieService.request('engine/image-provider/catalog',{method:'POST',body:JSON.stringify(secret?{key:secret}:{})});if(openedRevision!==revision)return;imageModels(value);q('[data-image-status]').textContent='已读取 '+value.models.length+' 个生图模型'+(value.catalogIncomplete?'，部分模型参数暂未读到，可稍后刷新':'')+'；选择后点击应用设置保存'}
  catch(error){q('[data-image-status]').textContent='读取失败：'+safeError(error,secret)}
  finally{operationBusy=false;connectionControls()}
 };
 q('[data-apply]').onclick=async e=>{
  if(operationBusy)return;
  const applyText=!checking&&modelReady&&readyProvider===provider.value&&!!model.value&&!q('[data-text-key]').value.trim();
  const requested={provider:provider.value,model:model.value,image:image.value,imageModel:image.value==='aimake'?q('[data-image-model]').value:'gpt-image-2',key:q('[data-image-key]').value.trim()};
  operationBusy=true;connectionControls();let imageSaved=false,imageSubmitted=false,textSaved=false,textBackendSaved=false;q('[data-result]').textContent='正在验证并保存图片设置…';
  try{
   imageSubmitted=true;const savedImage=await ShijieSmartSplit.imageProvider({provider:requested.image,model:requested.imageModel,...(requested.key?{key:requested.key}:{})});
   if(savedImage.provider!==requested.image||savedImage.model!==requested.imageModel)throw Error('图片设置保存未确认，请重新检查');imageSaved=true;imageModels(savedImage);
   q('[data-image-status]').textContent='图片设置已保存：'+(requested.image==='aimake'?'亿创 · '+requested.imageModel:'Codex 内置生图');window.dispatchEvent(new CustomEvent('shijie-image-provider-changed',{detail:savedImage}));
   if(!applyText){q('[data-result]').textContent='图片设置已保存；文字模型尚未就绪或有未保存的 Key，可单独连接后再应用';return}
   const check=await ShijieSmartSplit.assistantModels(requested.provider);if(!check.ready||!(check.models||[]).some(m=>m.id===requested.model)){modelReady=false;readyProvider=null;throw Error('文字模型连接检查未通过，请检查所选账号与模型')}
   const pref={provider:requested.provider,model:requested.model};if(pref.provider==='codex'){await ShijieSmartSplit.setModel(pref.model);textBackendSaved=true;}
   localStorage.setItem('shijie.assistant.text-model:'+window.SHIJIE.user,JSON.stringify(pref));textSaved=true;window.dispatchEvent(new CustomEvent('shijie-ai-settings-changed',{detail:pref}));
   provider.value=requested.provider;model.value=requested.model;image.value=requested.image;q('[data-image-model]').value=requested.imageModel;visibility();q('[data-result]').textContent='文字模型与图片设置均已应用，之后的任务使用新设置';
  }catch(error){q('[data-result]').textContent=(imageSaved?'图片设置已保存；':'图片设置未保存或保存未确认；')+(textSaved?'文字模型已应用，但界面更新失败：':textBackendSaved?'Codex 模型已保存，但本页模型偏好未保存：':'文字模型未应用：')+safeError(error,requested.key)}
  finally{if(imageSubmitted)q('[data-image-key]').value='';operationBusy=false;connectionControls()}
 };
 panel.addEventListener('close',()=>{q('[data-text-key]').value=q('[data-image-key]').value='';textKey.type='password';reveal.textContent='显示';reveal.setAttribute('aria-pressed','false');++revision;checking=false;modelReady=false;readyProvider=null;connectionControls()});
});

/* View commands remain direct buttons; their targets are different. */
document.addEventListener('DOMContentLoaded',()=>{
 const labels={fit:['适应画布','完整显示整个画布'], 'fit-width':['适应宽度','按工作区宽度缩放，长画布可上下滚动'], 'fit-selected':['适应所选','按选中图层的可见范围缩放'], actual:['100%','按原始像素比例显示']};
 for(const [id,[text,title]] of Object.entries(labels)){const button=document.getElementById(id);if(button){button.hidden=false;button.textContent=text;button.title=title+'；只调整显示，不改变设计尺寸'}}
});
