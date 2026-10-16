/* Shared geometry, local project library and selected-layer exports. */
window.StudioBase=(()=>{
 const clone=v=>structuredClone(v),id=()=>crypto.randomUUID();
 const recoveryTime=entry=>{for(const key of ['persistedAt','updated','savedAt']){const value=entry?.[key];if(typeof value!=='number'&&typeof value!=='string')continue;if(value==='')continue;const time=typeof value==='number'?value:Date.parse(value);if(Number.isFinite(time)&&time>0&&Number.isFinite(new Date(time).getTime()))return time}return null};
 const bounds=items=>{if(!items.length)return null;const x=Math.min(...items.map(b=>b.x)),y=Math.min(...items.map(b=>b.y));return {x,y,width:Math.max(.01,Math.max(...items.map(b=>b.x+b.width))-x),height:Math.max(.01,Math.max(...items.map(b=>b.y+b.height))-y)}};
 const overlap=(a,b)=>a.x<b.x+b.width&&a.x+a.width>b.x&&a.y<b.y+b.height&&a.y+a.height>b.y;
 const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const memory=ShijieSession.library,hidden=new Set(),persisted=new Map(),retired=new Map();let writeQueue=Promise.resolve(),sequence=0;
 const localWeb=typeof location!=='undefined'&&location.protocol==='http:'&&['127.0.0.1:19217','localhost:19217'].includes(location.host);
 let legacyLoaded=false,localLoaded=false;
 const localError=e=>Error('本地工程库不可用：'+(e?.message||'请连接本机引擎后重试')+'。当前编辑仍在页面中，可导出工程文件。');
 function sameDoc(a,b){if(a===b)return true;if(!a||!b||typeof a!=='object'||typeof b!=='object')return false;if(Array.isArray(a)!==Array.isArray(b))return false;const keys=Object.keys(a);return keys.length===Object.keys(b).length&&keys.every(k=>Object.prototype.hasOwnProperty.call(b,k)&&sameDoc(a[k],b[k]))}
 async function restoreSaved(){if(localWeb&&legacyLoaded)return;try{for(const p of await ShijieSession.legacySaved()){if(!persisted.has(p.id)&&!retired.has(p.id))persisted.set(p.id,clone(p));if(!hidden.has(p.id)&&!memory.has(p.id)){const entry=clone(p);if(localWeb)entry.source='browser-legacy';if(entry.doc)entry.doc._projectId=entry.id;memory.set(entry.id,entry)}}legacyLoaded=true;ShijieSession.legacyLibraryError=null}catch(e){if(!localWeb)throw e;ShijieSession.legacyLibraryError=e.message}}
 async function localProjects(refresh=false){
  if(!localWeb||localLoaded&&!refresh)return;
  try{
   if(!window.ShijieSmartSplit?.savedProjects)throw Error('本机引擎需要更新');
   const observed=new Map(memory),data=await ShijieSmartSplit.savedProjects();
   if(!Array.isArray(data.projects))throw Error('本地工程列表响应无效');
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
   localLoaded=true;ShijieSession.localLibraryError=null;
  }catch(e){ShijieSession.localLibraryError=e.message;throw localError(e)}
 }
 async function deliveries(){if(!window.ShijieSmartSplit?.projects)return;try{const data=await ShijieSmartSplit.projects();ShijieSession.libraryError=null;for(const p of data.items||[])if(!hidden.has(p.id)&&!memory.has(p.id))memory.set(p.id,{...p,kind:p.kind||'image',saveMode:'saved',source:'delivery',revision:p.revision||String(p.updated||0)})}catch(e){ShijieSession.libraryError=e.message}}
 function expectedVersion(key){const old=retired.get(key);return old?{version:old.version,allowMissing:old.version===old.removedVersion}:persisted.get(key)?.persistedVersion||persisted.get(key)?.revision||null}
 function retire(removed){if(!removed)return;const known=persisted.get(removed.id),old=retired.get(removed.id),version=known?.persistedVersion||known?.revision||old?.version||null;retired.set(removed.id,{version,removedVersion:removed.version});persisted.delete(removed.id)}
 const library={
  async list(){await restoreSaved();try{await localProjects(true)}catch(e){}await deliveries();return [...memory.values()].map(p=>{if(!localWeb)return clone(p);const {doc,...meta}=p;return clone(meta)})},
  async get(key){await restoreSaved();try{await localProjects()}catch(e){if(!memory.has(key))throw e}let entry=memory.get(key);if(!entry&&!hidden.has(key)){await deliveries();entry=memory.get(key)}if(entry?.source==='local-disk'&&!entry.doc){try{const result=await ShijieSmartSplit.savedProject(key);entry={...result.project,source:'local-disk'};if(!entry.doc)throw Error('工程正文无效');memory.set(key,entry);persisted.set(key,clone(entry))}catch(e){throw localError(e)}}if(entry?.source==='delivery'&&!entry.doc){const doc=await ShijieSmartSplit.project(key);entry={...entry,doc:clone(doc)};memory.set(key,entry)}return entry?clone(entry):undefined},
  async update(key,change){const previous=await library.get(key),value=change(previous);if(value)return library.put(value.doc,value.kind,{manual:true})},
  hasSaved(key){return persisted.has(key)||memory.get(key)?.source==='delivery'||memory.get(key)?.source==='local-disk'},
  isDirty(doc){const saved=persisted.get(doc?._projectId);return !!doc&&(!saved||!sameDoc(doc,saved.doc))},
  put(doc,kind,options={}){
   // Callers from old edit/flush paths are intentionally inert. Only explicit saves write.
   if(options.manual!==true)return Promise.resolve(undefined);
   if(!doc._projectId)doc._projectId=id();const snapshot=clone(doc),key=doc._projectId,entry={id:key,kind,title:snapshot.title||'未命名工程',updated:Date.now(),sequence:++sequence,revision:id(),doc:snapshot,saveMode:'saved',savedAt:Date.now()};
   const task=writeQueue.catch(()=>{}).then(async()=>{
    await restoreSaved();let saved;if(localWeb){try{await localProjects();const previous=persisted.get(key),result=await ShijieSmartSplit.saveProject({...entry,_expectedVersion:previous?.source==='local-disk'?previous.persistedVersion:null});if(!result.project?.persistedVersion)throw Error('磁盘未返回保存确认');saved={...entry,...result.project,source:'local-disk'}}catch(e){throw localError(e)}}else saved=await ShijieSession.saveManual(entry,expectedVersion(key));
    retired.delete(key);persisted.set(key,clone(saved));hidden.delete(key);memory.set(key,clone(saved));return clone(saved);
   });writeQueue=task;return task;
  },
  remove(key){
   const entry=memory.get(key),seq=++sequence;const task=writeQueue.catch(()=>{}).then(async()=>{
    await restoreSaved();if(entry?.source==='local-disk'){try{await ShijieSmartSplit.deleteSavedProject(key,entry.persistedVersion);persisted.delete(key)}catch(e){throw localError(e)}}else if(entry?.source!=='delivery'){const removed=await ShijieSession.removeManual(key,expectedVersion(key));retire(removed)}
    const current=memory.get(key);if(!current||!Number.isFinite(current.sequence)||current.sequence<=seq){hidden.add(key);memory.delete(key)}
   });writeQueue=task;return task;
  },
  async retain(key){const entry=await library.get(key);if(!entry)throw Error('本次工程已关闭');return library.put(entry.doc,entry.kind,{manual:true})},
  async cacheThumbnail(key,revision,thumbnail){const p=memory.get(key);if(p?.revision===revision){p.thumbnail=thumbnail;p.thumbnailRevision=revision}}
 };
 // The baseline is embedded once so project codec/image deduplication also covers it.
 function completedSplit(doc){const r=doc?.recognition;return !!doc&&doc.format==='shijie-scene'&&Array.isArray(doc.nodes)&&doc.nodes.length>0&&!doc._partial&&!!r&&(r.extractionStatus==='COMPLETED'||r.automatic===true)&&r.extractionStatus!=='INCOMPLETE'&&!r.pendingGenerationIds?.length&&!r.resumePendingNodes?.length&&!doc.nodes.some(n=>!n.versionArchived&&(n.pendingGeneration||['pending-image-generation','source-crop-fallback'].includes(n.provenance)||n.type==='image'&&n.generationRecord?.actualImageGeneration===false))}
 const splitBaseline={
  capture(doc){if(!completedSplit(doc))return false;const snapshot=clone(doc);delete snapshot._splitBaseline;delete snapshot._sessionId;delete snapshot.delivery;delete snapshot._studioStep;doc._splitBaseline={version:1,kind:'completed-split',createdAt:new Date().toISOString(),scene:snapshot};return true},
  read(doc){const baseline=doc?._splitBaseline;if(baseline?.version!==1||baseline.kind!=='completed-split'||!baseline.scene||Object.hasOwn(baseline.scene,'_splitBaseline')||!completedSplit(baseline.scene))return null;try{const snapshot=clone(baseline.scene);window.ShijieScene?.validate(snapshot);snapshot._projectId=doc._projectId;snapshot._splitBaseline=clone(baseline);return snapshot}catch{return null}}
 };
 function snap(box,targets,threshold){let dx=0,dy=0,bestX=threshold,bestY=threshold,gx=null,gy=null;const xs=[box.x,box.x+box.width/2,box.x+box.width],ys=[box.y,box.y+box.height/2,box.y+box.height];for(const t of targets){for(const tx of [t.x,t.x+t.width/2,t.x+t.width])for(const x of xs){const d=tx-x;if(Math.abs(d)<bestX){bestX=Math.abs(d);dx=d;gx=tx}}for(const ty of [t.y,t.y+t.height/2,t.y+t.height])for(const y of ys){const d=ty-y;if(Math.abs(d)<bestY){bestY=Math.abs(d);dy=d;gy=ty}}}return {dx,dy,gx,gy}}
 function path(p){const k=p.knots;if(!k?.length)return '';let d=`M${k[0].points[2]} ${k[0].points[3]}`;for(let i=1;i<k.length+(p.open?0:1);i++){const a=k[(i-1)%k.length].points,b=k[i%k.length].points;d+=`C${a[4]} ${a[5]} ${b[0]} ${b[1]} ${b[2]} ${b[3]}`}return d+(p.open?'':'Z')}
 function renderedSVG(render){let seq=0,defs=[];const w=render.psd.width,h=render.psd.height,rgb=c=>`rgb(${c?.r||0},${c?.g||0},${c?.b||0})`;
  function clips(body,paths){for(const p of paths){const key='clip-'+(++seq);defs.push(`<clipPath id="${key}" clipPathUnits="userSpaceOnUse"><path d="${path(p)}" clip-rule="${p.fillRule==='even-odd'?'evenodd':'nonzero'}"/></clipPath>`);body=`<g clip-path="url(#${key})">${body}</g>`}return body}
  function layer(n){let body;if(n.children)body=n.children.map(layer).join('');else if(n.text){const t=n.text,st=t.style||{};function attributes(style){const font=style.font?.name||'Arial',family=/MicrosoftYaHei/.test(font)?'Microsoft YaHei':/ArialNarrow/i.test(font)?'Arial Narrow':/Impact/i.test(font)?'Impact':/Haettenschweiler/i.test(font)?'Haettenschweiler':/Arial/.test(font)?'Arial':/TimesNewRoman/.test(font)?'Times New Roman':/SegoeUIEmoji/.test(font)?'Segoe UI Emoji':/SegoeUISymbol/.test(font)?'Segoe UI Symbol':/SegoeUI/.test(font)?'Segoe UI':font;return 'font-family="'+escape(family)+'" font-size="'+(style.fontSize||14)+'" font-weight="'+(/Bold/.test(font)||style.fauxBold?700:400)+'" font-style="'+(/Italic/.test(font)||style.fauxItalic?'italic':'normal')+'" letter-spacing="'+(style.tracking||0)*(style.fontSize||14)/1000+'"';}let content=escape(t.text);if(t.styleRuns?.length){let offset=0;content=t.styleRuns.map(r=>{const text=t.text.slice(offset,offset+r.length);offset+=r.length;return '<tspan '+attributes({...st,...r.style})+'>'+escape(text)+'</tspan>'}).join('');}body='<text transform="matrix('+(t.transform||[1,0,0,1,n.left,n.top]).join(' ')+')" '+attributes(st)+' text-decoration="'+[st.underline?'underline':'',st.strikethrough?'line-through':''].filter(Boolean).join(' ')+'" fill="'+rgb(st.fillColor)+'" xml:space="preserve">'+content+'</text>';body=clips(body,n.vectorMask?.paths||[])} else if(n.vectorFill||n.vectorStroke){const paths=n.vectorMask?.paths||[],base=paths.filter(p=>p.operation!=='intersect'),inter=paths.filter(p=>p.operation==='intersect');if(n.vectorStroke?.strokeEnabled){const s=n.vectorStroke;body=`<path d="${base.map(path).join(' ')}" fill="none" stroke="${rgb(s.content?.color)}" stroke-width="${s.lineWidth?.value||1}" stroke-linecap="${s.lineCapType||'butt'}" stroke-linejoin="${s.lineJoinType||'miter'}"/>`}else{const key='mask-'+(++seq);defs.push(`<mask id="${key}" maskUnits="userSpaceOnUse" x="0" y="0" width="${w}" height="${h}"><rect width="${w}" height="${h}" fill="black"/>${base.map(p=>`<path d="${path(p)}" fill="${p.operation==='subtract'?'black':'white'}" fill-rule="${p.fillRule==='even-odd'?'evenodd':'nonzero'}"/>`).join('')}</mask>`);body=`<rect width="${w}" height="${h}" fill="${rgb(n.vectorFill?.color)}" mask="url(#${key})"/>`}body=clips(body,inter)}else if(n.canvas)body=`<image x="${n.left||0}" y="${n.top||0}" width="${n.canvas.width}" height="${n.canvas.height}" href="${n.canvas.toDataURL('image/png')}"/>`;else body='';return `<g opacity="${n.opacity??1}" data-name="${escape(n.name)}">${body}</g>`}
  const body=render.psd.children.map(layer).join('');return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"><defs>${defs.join('')}</defs>${body}</svg>`;
 }
 return {clone,id,bounds,overlap,escape,library,snap,renderedSVG,recoveryTime,splitBaseline};
})();
