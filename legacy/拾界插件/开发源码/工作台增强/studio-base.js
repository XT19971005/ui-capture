/* Shared geometry, local project library and selected-layer exports. */
window.StudioBase=(()=>{
 const clone=v=>structuredClone(v),id=()=>crypto.randomUUID();
 function prepareImportedProject(doc){const copy=clone(doc);if(!copy||typeof copy!=='object'||Array.isArray(copy))throw Error('导入工程文档无效');copy._projectId=id();return copy}
 const recoveryTime=entry=>{for(const key of ['persistedAt','updated','savedAt']){const value=entry?.[key];if(typeof value!=='number'&&typeof value!=='string')continue;if(value==='')continue;const time=typeof value==='number'?value:Date.parse(value);if(Number.isFinite(time)&&time>0&&Number.isFinite(new Date(time).getTime()))return time}return null};
 const bounds=items=>{if(!items.length)return null;const x=Math.min(...items.map(b=>b.x)),y=Math.min(...items.map(b=>b.y));return {x,y,width:Math.max(.01,Math.max(...items.map(b=>b.x+b.width))-x),height:Math.max(.01,Math.max(...items.map(b=>b.y+b.height))-y)}};
 const overlap=(a,b)=>a.x<b.x+b.width&&a.x+a.width>b.x&&a.y<b.y+b.height&&a.y+a.height>b.y;
 const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const memory=ShijieSession.library,hidden=new Set(),persisted=new Map(),retired=new Map();let writeQueue=Promise.resolve(),sequence=0;
 const localWeb=!!window.SHIJIE,sharedLocal=!!window.SHIJIE?.sharedCodex,projectOrigins=new Map();
 const manualFiles=()=>sharedLocal&&!window.ShijieBrowserProjects?.supported();
 let legacyLoaded=false,localLoaded=false,activeDirectory=null,directoryEpoch=0;
 function clearLocalEntries(){for(const [key,value] of memory)if(value.source==='local-disk')memory.delete(key);for(const [key,value] of persisted)if(value.source==='local-disk')persisted.delete(key)}
 const localError=e=>Error((sharedLocal?'本地工程目录不可用：':'服务器工程库不可用：')+(e?.message||(sharedLocal?'请选择自己电脑上的工程文件夹':'请连接服务器后重试'))+'。当前编辑仍在页面中，可导出工程文件。');
 function sameDoc(a,b){if(a===b)return true;if(!a||!b||typeof a!=='object'||typeof b!=='object')return false;if(Array.isArray(a)!==Array.isArray(b))return false;const keys=Object.keys(a);return keys.length===Object.keys(b).length&&keys.every(k=>Object.prototype.hasOwnProperty.call(b,k)&&sameDoc(a[k],b[k]))}
 async function restoreSaved(){if(manualFiles()||localWeb&&legacyLoaded)return;try{for(const p of await ShijieSession.legacySaved()){if(!persisted.has(p.id)&&!retired.has(p.id))persisted.set(p.id,clone(p));if(!hidden.has(p.id)&&!memory.has(p.id)){const entry=clone(p);if(localWeb)entry.source='browser-legacy';if(entry.doc)entry.doc._projectId=entry.id;memory.set(entry.id,entry)}}legacyLoaded=true;ShijieSession.legacyLibraryError=null}catch(e){if(!localWeb)throw e;ShijieSession.legacyLibraryError=e.message}}
 async function localProjects(refresh=false){
  if(manualFiles()){ShijieSession.localLibraryError=null;return}if(!localWeb||localLoaded&&!refresh&&!sharedLocal)return;
  try{
   if(!window.ShijieSmartSplit?.savedProjects)throw Error('服务器需要更新');
   const epoch=directoryEpoch,observed=new Map(memory),data=await ShijieSmartSplit.savedProjects();
   if(epoch!==directoryEpoch)return;
   if(!Array.isArray(data.projects))throw Error('服务器工程列表响应无效');
   if(typeof data.directory==='string'){if(activeDirectory&&activeDirectory!==data.directory){clearLocalEntries();for(const p of data.projects)hidden.delete(p.id)}activeDirectory=data.directory}
   else if(sharedLocal&&data.directory===null&&activeDirectory){++directoryEpoch;clearLocalEntries();activeDirectory=null}
   const found=new Set(data.projects.map(p=>p.id));
   // A late list must not retire or replace a save completed while it was in flight.
   for(const [key,entry] of memory)if(entry.source==='local-disk'&&!found.has(key)&&entry===observed.get(key)){
    memory.delete(key);if(persisted.get(key)?.source==='local-disk')persisted.delete(key);
   }
   for(const p of data.projects){
    if(hidden.has(p.id))continue;const old=memory.get(p.id);
    if(old?.source==='local-disk'&&old!==observed.get(p.id))continue;
    if(old?.source!=='local-disk'||old.persistedVersion!==p.persistedVersion)memory.set(p.id,{...p,source:'local-disk'});
    if(!persisted.has(p.id)||persisted.get(p.id)?.source!=='local-disk')persisted.set(p.id,{...p,source:'local-disk'});
   }
   localLoaded=true;ShijieSession.localLibraryError=data.unreadable?'所选目录中有 '+data.unreadable+' 个工程文件无法读取，原文件已保留。':null;
  }catch(e){ShijieSession.localLibraryError=e.message;throw localError(e)}
 }
 async function deliveries(){if(manualFiles()||!window.ShijieSmartSplit?.projects)return;try{const data=await ShijieSmartSplit.projects();ShijieSession.libraryError=null;for(const p of data.items||[])if(!hidden.has(p.id)&&!memory.has(p.id))memory.set(p.id,{...p,kind:p.kind||'image',saveMode:'saved',source:'delivery',revision:p.revision||String(p.updated||0)})}catch(e){ShijieSession.libraryError=e.message}}
 function expectedVersion(key){const old=retired.get(key);return old?{version:old.version,allowMissing:old.version===old.removedVersion}:persisted.get(key)?.persistedVersion||persisted.get(key)?.revision||null}
 function retire(removed){if(!removed)return;const known=persisted.get(removed.id),old=retired.get(removed.id),version=known?.persistedVersion||known?.revision||old?.version||null;retired.set(removed.id,{version,removedVersion:removed.version});persisted.delete(removed.id)}
 function memoryEntry(doc,kind){
  if(!doc._projectId)doc._projectId=id();
  const snapshot=clone(doc),entry={id:doc._projectId,kind,title:snapshot.title||'未命名工程',updated:Date.now(),sequence:++sequence,revision:id(),doc:snapshot,source:'manual-export',saveMode:'unsaved',manualExportRequired:true};
  hidden.delete(entry.id);memory.set(entry.id,entry);return entry;
 }
 const unknownOrigins=new Set();
 const library={
  snapshotOrigin(doc){return projectOrigins.get(doc?._projectId)||null},
  restoreOrigin(doc,origin){const key=doc?._projectId;if(!key)return null;if(origin?.projectId===key&&origin.directory&&origin.version){projectOrigins.set(key,clone(origin));unknownOrigins.delete(key);return clone(origin)}unknownOrigins.add(key);return null},
  unknownOrigin(doc){return unknownOrigins.has(doc?._projectId)},
  async saveRecoveredCopy(doc,kind){const copy=clone(doc);copy._projectId=id();return library.put(copy,kind,{manual:true})},
  get requiresManualExport(){return manualFiles()},
  matchesExport(doc,entry){return !!entry&&sameDoc(doc,entry.doc)},
  stageExport(doc,kind){if(!manualFiles())throw Error('当前入口使用工程库保存');return clone(memoryEntry(doc,kind))},
  confirmExport(entry){
   if(!manualFiles()||entry?.source!=='manual-export'||!entry.doc||entry.doc._projectId!==entry.id)throw Error('导出确认无效');
   const previous=persisted.get(entry.id);if(previous?.sequence>entry.sequence)return;
   const saved={...clone(entry),saveMode:'saved',manualExportRequired:false,savedAt:Date.now(),userConfirmed:true};persisted.set(entry.id,saved);
   if(memory.get(entry.id)?.sequence===entry.sequence)memory.set(entry.id,saved);
  },
  hasPendingExports(){return manualFiles()&&[...memory.values()].some(entry=>entry.source==='manual-export'&&library.isDirty(entry.doc))},
  get canConnectDirectory(){return sharedLocal&&!!window.ShijieBrowserProjects?.supported()},
  directory:()=>activeDirectory,
  directoryName:()=>sharedLocal?window.ShijieBrowserProjects?.directoryName()||'':activeDirectory,
  setDirectory(directory){
   // Start the browser picker synchronously while the button's user activation is live.
   const picked=sharedLocal?(window.ShijieBrowserProjects?.pickDirectory()||Promise.reject(Error('本地工程模块尚未加载，请刷新页面'))):null;
   if(picked)picked.catch(()=>{});
   const task=writeQueue.catch(()=>{}).then(async()=>{if(!localWeb)throw Error('请在本机网页版连接目录');const result=await ShijieSmartSplit.setProjectDirectory(picked?await picked:directory);if(typeof result.directory!=='string')throw Error('工程目录响应无效');if(activeDirectory!==result.directory){++directoryEpoch;clearLocalEntries();localLoaded=false;hidden.clear()}activeDirectory=result.directory;ShijieSession.localLibraryError=null;return result});writeQueue=task;return task;
  },
  canClearBrowser:false,
  clearMigratedBrowser(){
   const task=writeQueue.catch(()=>{}).then(async()=>{
    if(!localWeb)throw Error('请在本机网页版清理');
    const originals=await ShijieSession.legacySaved(),disk=await ShijieSmartSplit.savedProjects(),localIds=new Set(disk.projects.map(p=>p.id));
    for(const original of originals)if(!localIds.has(original.id))throw Error('还有未迁入本地的工程：'+original.title+'，未清理任何记录');
    // Archive exact original bytes/metadata, then read them back before any deletion.
    for(const original of originals){const result=await ShijieSmartSplit.archiveBrowserProject(original,disk.directory);if(result.verified!==true||result.id!==original.id)throw Error('旧工程备份未确认，浏览器记录保留')}
    let removed=0;
    for(const original of originals){await ShijieSession.removeManual(original.id,original.persistedVersion||original.revision||null);removed++}
    legacyLoaded=true;return {removed};
   });writeQueue=task;return task;
  },
  async list(){await restoreSaved();await Promise.all([localProjects(true).catch(()=>{}),deliveries()]);return [...memory.values()].map(p=>{if(!localWeb)return clone(p);const {doc,...meta}=p;return clone(meta)})},
  async get(key){await restoreSaved();try{await localProjects()}catch(e){if(sharedLocal||!memory.has(key))throw e}let entry=memory.get(key);if(!entry&&!hidden.has(key)){await deliveries();entry=memory.get(key)}if(entry?.source==='local-disk'&&!entry.doc){try{const epoch=directoryEpoch,directory=activeDirectory,result=await ShijieSmartSplit.savedProject(key,directory);if(epoch!==directoryEpoch||directory!==activeDirectory||result.directory&&result.directory!==directory)throw Error('工程目录已切换，请刷新列表后重试');entry={...result.project,source:'local-disk'};if(!entry.doc)throw Error('工程正文无效');memory.set(key,entry);persisted.set(key,entry)}catch(e){throw localError(e)}}if(localWeb&&entry?.source==='local-disk'){projectOrigins.set(key,{projectId:key,directory:activeDirectory,version:entry.persistedVersion});unknownOrigins.delete(key)}if(entry?.source==='delivery'&&!entry.doc){const doc=await ShijieSmartSplit.project(key);entry={...entry,doc:clone(doc)};memory.set(key,entry)}return entry?clone(entry):undefined},
  async update(key,change){const previous=await library.get(key),value=change(previous);if(value)return library.put(value.doc,value.kind,{manual:true})},
  hasSaved(key){return persisted.has(key)||memory.get(key)?.source==='delivery'||memory.get(key)?.source==='local-disk'},
  isDirty(doc){const saved=persisted.get(doc?._projectId);return !!doc&&(!saved||!sameDoc(doc,saved.doc))},
  put(doc,kind,options={}){
   // Only explicit saves and named checkpoints may write.
   if(options.manual!==true&&options.checkpoint!==true)return Promise.resolve(undefined);
   // HTTP cannot grant directory writes. Retain complete results in RAM without claiming persistence.
   if(manualFiles())return Promise.resolve(clone(memoryEntry(doc,kind)));
   if(!doc._projectId)doc._projectId=id();const requestedDirectory=activeDirectory,snapshot=clone(doc),key=doc._projectId,entry={id:key,kind,title:snapshot.title||'未命名工程',updated:Date.now(),sequence:++sequence,revision:id(),doc:snapshot,saveMode:'saved',savedAt:Date.now()};
   const task=writeQueue.catch(()=>{}).then(async()=>{
    if(window.ProjectThumbnail?.render){try{entry.thumbnail=await ProjectThumbnail.render({kind,doc:snapshot});entry.thumbnailRevision=entry.revision}catch(error){entry.coverWarning='封面未生成：'+String(error.message||error).slice(0,160)}}
    await restoreSaved();let saved;if(localWeb){try{await localProjects();if(requestedDirectory&&requestedDirectory!==activeDirectory)throw Error('工程目录已切换，请确认保存目录后重试');if(unknownOrigins.has(key))throw Error('缺少原保存版本，请另存副本');const previous=persisted.get(key),origin=projectOrigins.get(key);if(origin&&origin.directory!==activeDirectory)throw Error('工程目录已切换');const version=origin?.directory===activeDirectory?origin.version:(previous?.source==='local-disk'?previous.persistedVersion:null),result=await ShijieSmartSplit.saveProject({...entry,_expectedDirectory:requestedDirectory||activeDirectory,_expectedVersion:version});if(!result.project?.persistedVersion)throw Error('磁盘未返回保存确认');saved={...entry,...result.project,source:'local-disk'}}catch(e){throw localError(e)}}else saved=await ShijieSession.saveManual(entry,expectedVersion(key));
    if(localWeb&&saved.source==='local-disk'){projectOrigins.set(key,{projectId:key,directory:activeDirectory,version:saved.persistedVersion});unknownOrigins.delete(key)}retired.delete(key);persisted.set(key,saved);hidden.delete(key);memory.set(key,saved);if(sharedLocal)projectOrigins.set(key,{projectId:key,directory:activeDirectory,version:saved.persistedVersion});return clone(saved);
   });writeQueue=task;return task;
  },
  remove(key){
   const entry=memory.get(key),requestedDirectory=activeDirectory,seq=++sequence;const task=writeQueue.catch(()=>{}).then(async()=>{
    await restoreSaved();if(manualFiles()||entry?.source==='manual-export'){persisted.delete(key)}else if(entry?.source==='local-disk'){try{if(requestedDirectory!==activeDirectory)throw Error('工程目录已切换，请刷新后重试');await ShijieSmartSplit.deleteSavedProject(key,entry.persistedVersion,requestedDirectory);persisted.delete(key)}catch(e){throw localError(e)}}else if(entry?.source!=='delivery'){const removed=await ShijieSession.removeManual(key,expectedVersion(key));retire(removed)}
    const current=memory.get(key);if(!current||!Number.isFinite(current.sequence)||current.sequence<=seq){hidden.add(key);memory.delete(key)}
   });writeQueue=task;return task;
  },
  async retain(key){const entry=await library.get(key);if(!entry)throw Error('本次工程已关闭');return library.put(entry.doc,entry.kind,{manual:true})},
  async cacheThumbnail(key,revision,thumbnail){const p=memory.get(key);if(p?.revision===revision){p.thumbnail=thumbnail;p.thumbnailRevision=revision}}
 };
 // The baseline is embedded once so project codec/image deduplication also covers it.
 function completedSplit(doc){const r=doc?.recognition;return !!doc&&doc.format==='shijie-scene'&&Array.isArray(doc.nodes)&&doc.nodes.length>0&&!doc._partial&&!!r&&(r.extractionStatus==='COMPLETED'||r.automatic===true)&&r.extractionStatus!=='INCOMPLETE'&&!r.pendingGenerationIds?.length&&!r.resumePendingNodes?.length&&!doc.nodes.some(n=>!n.versionArchived&&(n.pendingGeneration||['pending-image-generation','source-crop-fallback'].includes(n.provenance)||n.type==='image'&&n.generationRecord?.actualImageGeneration===false))}
 function generatedResults(doc){return !!doc&&doc.format==='shijie-scene'&&Array.isArray(doc.nodes)&&doc.nodes.some(n=>!n.versionArchived&&!n.pendingGeneration&&(n.generationRecord?.actualImageGeneration===true||['codex-image-generation','aimake-image-generation'].includes(n.provenance)))}
 const splitBaseline={
  capture(doc,options={}){const partial=options.generatedResults===true;if(!(partial?generatedResults(doc):completedSplit(doc)))return false;const snapshot=clone(doc);delete snapshot._splitBaseline;delete snapshot._sessionId;delete snapshot.delivery;delete snapshot._studioStep;doc._splitBaseline={version:1,kind:partial?'generated-results':'completed-split',createdAt:new Date().toISOString(),scene:snapshot};return true},
  read(doc){const baseline=doc?._splitBaseline;if(baseline?.version!==1||!['completed-split','generated-results'].includes(baseline.kind)||!baseline.scene||Object.hasOwn(baseline.scene,'_splitBaseline')||!(baseline.kind==='generated-results'?generatedResults(baseline.scene):completedSplit(baseline.scene)))return null;try{const snapshot=clone(baseline.scene);window.ShijieScene?.validate(snapshot);snapshot._projectId=doc._projectId;snapshot._splitBaseline=clone(baseline);return snapshot}catch{return null}}
 };
 function snap(box,targets,threshold){let dx=0,dy=0,bestX=threshold,bestY=threshold,gx=null,gy=null;const xs=[box.x,box.x+box.width/2,box.x+box.width],ys=[box.y,box.y+box.height/2,box.y+box.height];for(const t of targets){for(const tx of [t.x,t.x+t.width/2,t.x+t.width])for(const x of xs){const d=tx-x;if(Math.abs(d)<bestX){bestX=Math.abs(d);dx=d;gx=tx}}for(const ty of [t.y,t.y+t.height/2,t.y+t.height])for(const y of ys){const d=ty-y;if(Math.abs(d)<bestY){bestY=Math.abs(d);dy=d;gy=ty}}}return {dx,dy,gx,gy}}
 function path(p){const k=p.knots;if(!k?.length)return '';let d=`M${k[0].points[2]} ${k[0].points[3]}`;for(let i=1;i<k.length+(p.open?0:1);i++){const a=k[(i-1)%k.length].points,b=k[i%k.length].points;d+=`C${a[4]} ${a[5]} ${b[0]} ${b[1]} ${b[2]} ${b[3]}`}return d+(p.open?'':'Z')}
 function renderedSVG(render){let seq=0,defs=[];const w=render.psd.width,h=render.psd.height,rgb=c=>`rgb(${c?.r||0},${c?.g||0},${c?.b||0})`;
  function clips(body,paths){for(const p of paths){const key='clip-'+(++seq);defs.push(`<clipPath id="${key}" clipPathUnits="userSpaceOnUse"><path d="${path(p)}" clip-rule="${p.fillRule==='even-odd'?'evenodd':'nonzero'}"/></clipPath>`);body=`<g clip-path="url(#${key})">${body}</g>`}return body}
  function layerBounds(n){if(n._bounds)return n._bounds;const pts=(n.vectorMask?.paths||[]).flatMap(p=>p.knots||[]).map(k=>k.points.slice(2,4));if(pts.length){const xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1]);return {x:Math.min(...xs),y:Math.min(...ys),width:Math.max(...xs)-Math.min(...xs),height:Math.max(...ys)-Math.min(...ys)}}return {x:n.left||0,y:n.top||0,width:n.canvas?.width||w,height:n.canvas?.height||h}}
  function fill(n){const g=n.vectorFill;if(!g||g.type==='color')return rgb(g?.color);if(!g.colorStops?.length)throw Error('SVG 不支持此渐变，请导出 PSD');const b=layerBounds(n),a=(g.angle||0)*Math.PI/180,dx=Math.cos(a),dy=-Math.sin(a),span=(Math.abs(dx)*b.width+Math.abs(dy)*b.height)*(g.scale??1),cx=b.x+b.width/2,cy=b.y+b.height/2,key='gradient-'+(++seq),tag=g.style==='radial'?'radialGradient':'linearGradient',attrs=g.style==='radial'?`cx="${cx}" cy="${cy}" r="${b.width*(g.scale??1)/2}"`:`x1="${cx-dx*span/2}" y1="${cy-dy*span/2}" x2="${cx+dx*span/2}" y2="${cy+dy*span/2}"`;defs.push(`<${tag} id="${key}" gradientUnits="userSpaceOnUse" ${attrs}>${g.colorStops.map(s=>`<stop offset="${s.location}" stop-color="${rgb(s.color)}"/>`).join('')}</${tag}>`);return `url(#${key})`}
  function layer(n){if(n.hidden)return '';let body;if(n.children)body=n.children.map(layer).join('');else if(n.text){const t=n.text,st=t.style||{};function attributes(style){const font=style.font?.name||'Arial',family=/NotoSerifCJKsc/i.test(font)?'Noto Serif CJK SC':/NotoSansCJKsc/i.test(font)?'Noto Sans CJK SC':/LiberationSerif/i.test(font)?'Liberation Serif':/LiberationSans/i.test(font)?'Liberation Sans':/MicrosoftYaHei/.test(font)?'Microsoft YaHei':/ArialNarrow/i.test(font)?'Arial Narrow':/Impact/i.test(font)?'Impact':/Haettenschweiler/i.test(font)?'Haettenschweiler':/Arial/.test(font)?'Arial':/TimesNewRoman/.test(font)?'Times New Roman':/SegoeUIEmoji/.test(font)?'Segoe UI Emoji':/SegoeUISymbol/.test(font)?'Segoe UI Symbol':/SegoeUI/.test(font)?'Segoe UI':font;return 'font-family="'+escape(family)+'" font-size="'+(style.fontSize||14)+'" font-weight="'+(/Bold/.test(font)||style.fauxBold?700:400)+'" font-style="'+(/Italic/.test(font)||style.fauxItalic?'italic':'normal')+'" letter-spacing="'+(style.tracking||0)*(style.fontSize||14)/1000+'"';}let content=escape(t.text);if(t.styleRuns?.length){let offset=0;content=t.styleRuns.map(r=>{const text=t.text.slice(offset,offset+r.length);offset+=r.length;return '<tspan '+attributes({...st,...r.style})+'>'+escape(text)+'</tspan>'}).join('');}body='<text transform="matrix('+(t.transform||[1,0,0,1,n.left,n.top]).join(' ')+')" '+attributes(st)+' text-decoration="'+[st.underline?'underline':'',st.strikethrough?'line-through':''].filter(Boolean).join(' ')+'" fill="'+rgb(st.fillColor)+'" xml:space="preserve">'+content+'</text>';body=clips(body,n.vectorMask?.paths||[])} else if(n.vectorFill||n.vectorStroke){const paths=n.vectorMask?.paths||[],base=paths.filter(p=>p.operation!=='intersect'),inter=paths.filter(p=>p.operation==='intersect');if(n.vectorStroke?.strokeEnabled){const s=n.vectorStroke;body=`<path d="${base.map(path).join(' ')}" fill="none" stroke="${rgb(s.content?.color)}" stroke-width="${s.lineWidth?.value||1}" stroke-linecap="${s.lineCapType||'butt'}" stroke-linejoin="${s.lineJoinType||'miter'}"/>`}else{const key='mask-'+(++seq);defs.push(`<mask id="${key}" maskUnits="userSpaceOnUse" x="0" y="0" width="${w}" height="${h}"><rect width="${w}" height="${h}" fill="black"/>${base.map(p=>`<path d="${path(p)}" fill="${p.operation==='subtract'?'black':'white'}" fill-rule="${p.fillRule==='even-odd'?'evenodd':'nonzero'}"/>`).join('')}</mask>`);body=`<rect width="${w}" height="${h}" fill="${fill(n)}" mask="url(#${key})"/>`}body=clips(body,inter)}else if(n.canvas)body=`<image x="${n.left||0}" y="${n.top||0}" width="${n.canvas.width}" height="${n.canvas.height}" href="${n.canvas.toDataURL('image/png')}"/>`;else body='';if(n.effects||n._displayMask||n.blendMode&&n.blendMode!=='normal'){const runtime=window.ShijieLayerStyle;if(!runtime)throw Error('样式渲染尚未加载，请重试');body=runtime.styleSvg(body,{id:'export-'+(++seq),layerStyle:runtime.nativeToStyle(n.effects,n.blendMode)||{blendMode:n.blendMode||'normal'},displayMask:n._displayMask},layerBounds(n));}return `<g opacity="${n.opacity??1}" data-name="${escape(n.name)}">${body}</g>`}
  const body=render.psd.children.map(layer).join('');return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"><defs>${defs.join('')}</defs>${body}</svg>`;
 }
 return {clone,id,prepareImportedProject,bounds,overlap,escape,library,snap,renderedSVG,recoveryTime,splitBaseline};
})();
