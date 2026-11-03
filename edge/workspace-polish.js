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
 const clear=document.createElement('button');clear.id='clear-image';clear.textContent='关闭工程';clear.title='关闭当前工程，已保存工程保留';clear.onclick=async()=>{if(!scene||busy||!window.studio.confirmDiscard())return;const owned=scene,ownerTask=task,snapshot=JSON.stringify(owned);clear.disabled=true;try{await window.studio.flush();if(scene!==owned||task!==ownerTask)return;if(JSON.stringify(scene)!==snapshot){status('工程已有新修改，未清空。');return}await window.studio.adapter.closeProject();if(scene)return;window.studio.setInitial(null);$('layer-count').textContent='0';$('image-source-title').textContent='尚未导入图片';$('image-source-size').textContent='PNG / JPG / WebP';for(const key of ['text','vector','raster'])$('stat-'+key).textContent='—';window.studio.sync(false)}catch(e){status('关闭工程未完成：'+e.message+'。当前工程保留。')}finally{clear.disabled=!scene||busy}};
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
 byId('clear').onclick=async()=>{if(!current||busy||!studio.confirmDiscard())return;const owned=current;try{await studio.flush();if(current!==owned||busy)return;await close();studio.setInitial(null);studio.sync(false);status('已关闭工程，已保存工程保留')}catch(e){status('关闭工程未完成：'+e.message)}};
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
 const panel=document.createElement('dialog');panel.className='codex-dialog shared-ai-settings';panel.setAttribute('aria-label','AI 设置');panel.innerHTML='<form method="dialog"><strong>AI 设置</strong><button aria-label="关闭AI设置">×</button></form><section><h3>理解与分析</h3><label>模型来源<select data-provider><option value="codex">Codex 订阅</option><option value="taishi">太石网关</option></select></label><label>分析模型<select data-model></select></label><label data-text-key-label hidden>本人太石 Key<input data-text-key type="password" autocomplete="new-password" placeholder="留空保留现有连接"></label><div class="ai-connection-actions"><button type="button" data-check>检查连接</button><button type="button" data-login>登录 Codex</button><a data-login-link hidden target="_blank" rel="noopener noreferrer">打开登录页</a></div><p data-text-status role="status"></p></section><section><h3>图片生成与补全</h3><label>图片来源<select data-image-provider><option value="codex">Codex · 内置生图</option><option value="aimake">亿创 · GPT Image 2</option></select></label><label data-image-key-label hidden>本人亿创 Key<input data-image-key type="password" autocomplete="new-password" placeholder="留空保留现有连接"></label><p data-image-status></p></section><footer><span data-result role="status"></span><button type="button" class="primary" data-apply>应用设置</button></footer>';document.body.append(panel);
 const q=s=>panel.querySelector(s),provider=q('[data-provider]'),model=q('[data-model]'),image=q('[data-image-provider]');let revision=0;
 const visibility=()=>{q('[data-text-key-label]').hidden=provider.value!=='taishi';q('[data-login]').hidden=provider.value!=='codex';q('[data-image-key-label]').hidden=image.value!=='aimake';q('[data-login-link]').hidden=true};
 async function models(){const rev=++revision,source=provider.value;model.disabled=true;q('[data-text-status]').textContent='正在检查连接…';try{const value=await ShijieSmartSplit.assistantModels(source);if(rev!==revision)return;const pref=JSON.parse(localStorage.getItem('shijie.assistant.text-model')||'null');model.replaceChildren(...(value.models||[]).map(m=>new Option(m.name||m.id,m.id)));const chosen=pref?.provider===source?pref.model:value.model;if([...model.options].some(o=>o.value===chosen))model.value=chosen;model.disabled=!value.ready||!model.options.length;q('[data-text-status]').textContent=value.ready?'已连接':'尚未连接，请检查账号配置'}catch(e){if(rev===revision)q('[data-text-status]').textContent=e.message}}
 provider.onchange=()=>{visibility();void models()};image.onchange=visibility;q('[data-check]').onclick=()=>void models();
 q('[data-login]').onclick=async()=>{try{const result=await ShijieSmartSplit.login(),url=new URL(result.url);if(url.protocol!=='https:'&&!(url.protocol==='http:'&&['localhost','127.0.0.1'].includes(url.hostname)))throw Error('登录地址无效');q('[data-login-link]').href=url.href;q('[data-login-link]').hidden=false;q('[data-text-status]').textContent='完成登录后点击检查连接'}catch(e){q('[data-text-status]').textContent=e.message}};
 button.onclick=async()=>{if(window.studio?.isBusy()||window.ShijieFreeAssistant?.isBusy?.())return;q('[data-result]').textContent='';q('[data-text-key]').value=q('[data-image-key]').value='';try{const pref=JSON.parse(localStorage.getItem('shijie.assistant.text-model')||'null');provider.value=pref?.provider==='taishi'?'taishi':'codex'}catch{provider.value='codex'}visibility();window.ShijieInlinePanels.open(panel);void models();try{const value=await ShijieSmartSplit.imageProvider();image.value=value.provider;visibility();q('[data-image-status]').textContent=value.provider==='codex'?'使用当前电脑的 Codex 账号':'使用本人亿创账号'}catch(e){q('[data-image-status]').textContent=e.message}};
 q('[data-apply]').onclick=async e=>{const apply=e.currentTarget;apply.disabled=true;try{if(q('[data-text-key]').value.trim()){await ShijieSmartSplit.assistantKey(q('[data-text-key]').value.trim());await models();}await ShijieSmartSplit.imageProvider({provider:image.value,model:'gpt-image-2',...(q('[data-image-key]').value.trim()?{key:q('[data-image-key]').value.trim()}:{})});if(!model.disabled&&model.value){const pref={provider:provider.value,model:model.value};if(pref.provider==='codex')await ShijieSmartSplit.setModel(pref.model);localStorage.setItem('shijie.assistant.text-model',JSON.stringify(pref));window.dispatchEvent(new CustomEvent('shijie-ai-settings-changed',{detail:pref}));}q('[data-result]').textContent='已应用，之后的任务使用新设置';await models()}catch(error){q('[data-result]').textContent='应用未完成：'+error.message}finally{q('[data-text-key]').value=q('[data-image-key]').value='';apply.disabled=false}};
 panel.addEventListener('close',()=>{q('[data-text-key]').value=q('[data-image-key]').value='';++revision});
});

/* View commands remain direct buttons; their targets are different. */
document.addEventListener('DOMContentLoaded',()=>{
 const labels={fit:['适应画布','完整显示整个画布'], 'fit-width':['适应宽度','按工作区宽度缩放，长画布可上下滚动'], 'fit-selected':['适应所选','按选中图层的可见范围缩放'], actual:['100%','按原始像素比例显示']};
 for(const [id,[text,title]] of Object.entries(labels)){const button=document.getElementById(id);if(button){button.hidden=false;button.textContent=text;button.title=title+'；只调整显示，不改变设计尺寸'}}
});
