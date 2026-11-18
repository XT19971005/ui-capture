import {createFigmaConverter} from '@figit/dom-to-figma';
const fallbackUrl=new URL('vendor/figma-font.js',location.href);
async function loadFont(){if(!fontBytes)fontBytes=import(fallbackUrl.href).then(({default:data})=>Uint8Array.from(atob(data),c=>c.charCodeAt(0)).buffer);return fontBytes}
let fontBytes;
const rgba=c=>c?`rgba(${Math.round(c.r*255)},${Math.round(c.g*255)},${Math.round(c.b*255)},${c.a??1})`:'transparent';
export async function prepare(scene){
 const S=window.ShijieScene;S.validate(scene);
 const payload=S.figma(scene),host=document.createElement('div');
 Object.assign(host.style,{position:'fixed',left:'-100000px',top:'0',width:scene.width+'px',height:scene.height+'px',pointerEvents:'none',zIndex:'-1'});
 const hasText=n=>n.type==='text'||(n.children||[]).some(hasText);let fontFace;if(hasText(payload.root)){fontFace=new FontFace('AI拆图导出字体',await loadFont());await fontFace.load();document.fonts.add(fontFace);}
 const board=document.createElement('div');board.id='figma-export-board';board.dataset.figmaName=scene.title||'工程图层';Object.assign(board.style,{position:'relative',width:scene.width+'px',height:scene.height+'px',background:scene.background||'transparent'});host.append(board);document.body.append(host);
 let textCount=0,imageCount=0;
 function append(n,parent,origin={x:0,y:0}){
  const el=document.createElement(n.type==='image'?'img':'div');el.id=String(n.name||n.type);el.dataset.figmaName=el.id;
  Object.assign(el.style,{position:'absolute',left:(n.x-origin.x)+'px',top:(n.y-origin.y)+'px',width:n.width+'px',height:n.height+'px',opacity:String(n.opacity??1),boxSizing:'border-box'});
  if(n.type==='text'){
   textCount++;el.textContent=n.text||'';Object.assign(el.style,{fontFamily:'AI拆图导出字体',fontSize:(n.fontSize||14)+'px',fontWeight:String(n.fontWeight||400),fontStyle:n.fontStyle||'normal',lineHeight:(n.lineHeight||n.fontSize*1.2)+'px',color:rgba(n.color),whiteSpace:'pre-wrap',overflow:'visible',textAlign:n.align||'left',letterSpacing:(n.letterSpacing||0)+'px'});
   if(n.textStroke&&n.textStrokeWidth)el.style.webkitTextStroke=n.textStrokeWidth+'px '+rgba(n.textStroke);
  }else if(n.type==='image'){
   imageCount++;el.src=n.image;el.style.objectFit='fill';
  }else if(n.type==='svg'){
   const parsed=new DOMParser().parseFromString(n.svg,'image/svg+xml');if(parsed.querySelector('parsererror'))throw Error('矢量素材无效：'+n.name);
   el.append(document.importNode(parsed.documentElement,true));el.firstChild.setAttribute('width',n.width);el.firstChild.setAttribute('height',n.height);
  }else{el.style.background=rgba(n.background);el.style.borderRadius=(n.radii||[0]).map(x=>x+'px').join(' ');el.style.overflow=n.clip?'hidden':'visible';}
  parent.append(el);for(const child of n.children||[])append(child,el,{x:n.x,y:n.y});
 }
 try{
  for(const child of payload.root.children||[])append(child,board);
  await Promise.all([...host.querySelectorAll('img')].map(im=>im.decode()));
  const converter=createFigmaConverter({layout:'absolute',trace:true,fontLoader:async()=>({bytes:await loadFont(),resolvedFamily:'Noto Sans CJK SC',resolvedWeight:400,resolvedItalic:false}),imageLoader:async({src})=>{if(!src.startsWith('data:image/'))throw Error('图片必须嵌入工程');const response=await fetch(src);return {bytes:await response.arrayBuffer(),mimeType:response.headers.get('content-type')||'image/png'}}});
  const result=await converter.convert({element:board,width:scene.width,height:scene.height,name:scene.title||'AI拆图工程'});
  const nodes=result.document.nodeChanges||[],texts=nodes.filter(n=>n.type==='TEXT');
  for(const entry of result.trace?.entries||[]){const node=nodes.find(n=>n.guid.localID===entry.guid.localID);const selector=entry.domPath.replace(/::text\[\d+\]$/,'');let source;try{source=selector===':scope'?board:board.querySelector(selector)}catch{}if(node&&source?.dataset.figmaName){node.name=source.dataset.figmaName;node.autoRename=false;}}
  for(const n of nodes)if(n.type==='FRAME')n.stackMode='NONE';
  const images=nodes.filter(n=>(n.fillPaints||[]).some(p=>p.type==='IMAGE'));if(images.length<imageCount)throw Error('部分图片未能建立素材层，未复制。');
  if(texts.length<textCount)throw Error('部分文字未能建立原生文字层，未复制。');
  for(const n of texts){n.fontName.family='Noto Sans SC';n.fontName.style='Regular';n.fontName.postscript='NotoSansSC-Regular';}
  // Conversion serializes before font-name normalization; re-encode the final document.
  const {encodeFigmaData,composeClipboardHtml}=await import('@figit/fig-kiwi');
  const html=composeClipboardHtml(encodeFigmaData(result.document).base64);
  if(new Blob([html]).size>64*1024*1024)throw Error('复制数据超过64MB，请选择部分图层分批复制。');
  return {html,textCount,imageCount,warnings:textCount?'普通文字使用思源黑体兼容字体，可在 Figma 中继续修改字体。':''};
 }finally{host.remove();if(fontFace)document.fonts.delete(fontFace)}
}
export async function copy(scene){
 if(!navigator.clipboard?.write||typeof ClipboardItem==='undefined')throw Error('当前浏览器不支持分层复制，请使用 HTTPS 或本机 localhost 入口。');
 const data=await prepare(scene);await navigator.clipboard.write([new ClipboardItem({'text/html':new Blob([data.html],{type:'text/html'})})]);return data;
}
