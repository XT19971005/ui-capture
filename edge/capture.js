async function capturePage(includeImages,scope='page',region=null) {
  const Text=(/* Shared browser typography for capture, preview and native export. */
function textLayoutTools(){
 const fontCache=new Map(),probe=document.createElement('canvas').getContext('2d');
 const generic=/^(serif|sans-serif|monospace|system-ui|cursive|fantasy|ui-serif|ui-sans-serif|ui-monospace)$/i;
 function family(n){const value=String(n.fontFamily||'Arial, "Microsoft YaHei", sans-serif').replace(/[;{}<>]/g,'');return value||'sans-serif'}
 function font(n){return (n.fontStyle==='italic'?'italic ':'')+(n.fontWeight||400)+' '+(n.fontSize||14)+'px '+family(n)}
 function resolveFamily(n){const f=family(n),key=f+'|'+(n.fontWeight||400)+'|'+(n.fontStyle||'normal');if(fontCache.has(key))return fontCache.get(key);const candidates=f.match(/(?:"[^"]*"|'[^']*'|[^,])+/g)||['sans-serif'],sample='mmmmWWiiii0123汉字';let result='sans-serif';function width(face){probe.font=(n.fontWeight||400)+' 32px '+face;return probe.measureText(sample).width}for(let name of candidates){name=name.trim().replace(/^['"]|['"]$/g,'');if(generic.test(name)){result=name;break}const quoted='"'+name.replace(/["\\]/g,'')+'"';if(['monospace','serif'].some(fallback=>Math.abs(width(quoted+','+fallback)-width(fallback))>.01)){result=name;break}}fontCache.set(key,result);return result}
 function transform(value,style){const mode=style.textTransform||'none';if(mode==='uppercase')return value.toUpperCase();if(mode==='lowercase')return value.toLowerCase();if(mode==='capitalize')return value.replace(/(^|[\s-])(\p{L})/gu,(_,space,c)=>space+c.toUpperCase());return value}
 function whiteSpace(n){return n.whiteSpace||((n.height||0)<=(n.fontSize||14)*1.55?'pre':'pre-wrap')}
 function normalized(value,style){if(style.whiteSpace==='pre-line')value=value.replace(/\r\n?/g,'\n').replace(/[\t\f ]+/g,' ');else if(!/^(pre|pre-wrap|break-spaces)$/.test(style.whiteSpace||''))value=value.replace(/[\t\r\n\f ]+/g,' ');return transform(value,style)}
 function measureLines(child,style){
  const value=child.textContent||'',indices=[0];for(const c of value)indices.push(indices.at(-1)+c.length);const range=document.createRange(),runs=[];let start=0;
  const rects=(a,b)=>{range.setStart(child,indices[a]);range.setEnd(child,indices[b]);return [...range.getClientRects()].filter(r=>r.width>.001&&r.height>.001)};
  while(start<indices.length-1){let first=rects(start,start+1);if(!first.length){start++;continue}const y=first[0].top;let lo=start+1,hi=indices.length-1;
   while(lo<hi){const mid=Math.ceil((lo+hi)/2),rs=rects(start,mid);if(rs.every(r=>Math.abs(r.top-y)<.75))lo=mid;else hi=mid-1}
   const rs=rects(start,lo).filter(r=>Math.abs(r.top-y)<.75);if(rs.length){const x=Math.min(...rs.map(r=>r.left)),right=Math.max(...rs.map(r=>r.right)),bottom=Math.max(...rs.map(r=>r.bottom));let raw=value.slice(indices[start],indices[lo]);if(/^(pre|pre-wrap|pre-line|break-spaces)$/.test(style.whiteSpace||''))raw=raw.replace(/[\r\n]+$/,'');const text=normalized(raw,style);if(text.length)runs.push({text,x:x+scrollX,y:y+scrollY,width:right-x,height:bottom-y})}start=lo;
  }
  return runs;
 }
 function apply(el,n){Object.assign(el.style,{fontFamily:family(n),fontSize:(n.fontSize||14)+'px',fontWeight:String(n.fontWeight||400),fontStyle:n.fontStyle||'normal',letterSpacing:(n.letterSpacing||0)+'px',wordSpacing:(n.wordSpacing||0)+'px',lineHeight:(n.lineHeight||n.fontSize*1.2||18)+'px',whiteSpace:whiteSpace(n),overflowWrap:n.overflowWrap||'normal',wordBreak:n.wordBreak||'normal',textAlign:n.align||'left',direction:n.direction||'ltr',textDecorationLine:n.textDecoration||'none',fontKerning:n.fontKerning||'auto',fontVariantLigatures:n.fontVariantLigatures||'normal'});}
 function lines(n){if(n.runs?.length)return n.runs;const host=document.createElement('div');host.style.cssText='all:initial;position:fixed;left:0;top:0;visibility:hidden;pointer-events:none;box-sizing:content-box;margin:0;padding:0;border:0;width:'+Math.max(.01,n.width)+'px;';apply(host,n);const child=document.createTextNode(n.text||'');host.append(child);document.documentElement.append(host);try{const b=host.getBoundingClientRect();return measureLines(child,{...n,whiteSpace:whiteSpace(n),textTransform:'none'}).map(r=>({...r,x:r.x-scrollX-b.x+n.x,y:r.y-scrollY-b.y+n.y}))}finally{host.remove()}}
 function baseline(n,run){probe.font=font(n);return probe.measureText(run.text||'Ag').fontBoundingBoxAscent||(n.fontSize||14)*.85}
 function properties(s){return {fontFamily:s.fontFamily,fontStyle:s.fontStyle,fontSize:parseFloat(s.fontSize)||14,fontWeight:parseInt(s.fontWeight)||400,lineHeight:parseFloat(s.lineHeight)||parseFloat(s.fontSize)*1.2,letterSpacing:parseFloat(s.letterSpacing)||0,wordSpacing:parseFloat(s.wordSpacing)||0,whiteSpace:s.whiteSpace,wordBreak:s.wordBreak,overflowWrap:s.overflowWrap,direction:s.direction,align:s.textAlign,textDecoration:s.textDecorationLine,fontKerning:s.fontKerning,fontVariantLigatures:s.fontVariantLigatures}}
 return {family,font,resolveFamily,measureLines,apply,lines,baseline,properties,normalized,whiteSpace};
}
)();
  const warnings=new Set(),maxNodes=6000;let count=0,imageBytes=0;
  const color=value=>{const m=value.match(/^rgba?\(([^)]+)\)$/);if(!m)return null;const a=m[1].split(/[,\s/]+/).filter(Boolean).map(Number);return a.length>=3&&a.every(Number.isFinite)?{r:a[0]/255,g:a[1]/255,b:a[2]/255,a:a[3]??1}:null;};
  const area=scope==='region'&&region?{x:region.documentX,y:region.documentY,width:region.width,height:region.height}:scope==='viewport'?{x:scrollX,y:scrollY,width:innerWidth,height:innerHeight}:null;
  const intersects=(x,y,w,h)=>!area||(x<area.x+area.width&&y<area.y+area.height&&x+w>area.x&&y+h>area.y);
  const styleKeys=['background-color','background-image','background-size','background-position','background-repeat','border-top','border-right','border-bottom','border-left','border-top-left-radius','border-top-right-radius','border-bottom-right-radius','border-bottom-left-radius','box-shadow'];
  function imageData(img){try{if(!img.complete||!img.naturalWidth)return null;const scale=Math.min(1,1800/Math.max(img.naturalWidth,img.naturalHeight),Math.sqrt(2000000/(img.naturalWidth*img.naturalHeight))),c=document.createElement('canvas');c.width=Math.max(1,Math.round(img.naturalWidth*scale));c.height=Math.max(1,Math.round(img.naturalHeight*scale));c.getContext('2d').drawImage(img,0,0,c.width,c.height);const alpha=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let transparent=false;for(let i=3;i<alpha.length;i+=4){if(alpha[i]<255){transparent=true;break}}const result=c.toDataURL(transparent?'image/png':'image/jpeg',.94);imageBytes+=result.length;if(imageBytes>24000000){warnings.add('图片总量超过 24 MB，后续图片未嵌入。');return null;}return result;}catch{return null;}}
  function walk(el){
    if(count>=maxNodes){warnings.add('页面超过 6000 个图层，已截断。');return null;}
    if(el.hasAttribute('data-shijie-overlay'))return null;
    if(['SCRIPT','STYLE','NOSCRIPT','TEMPLATE','HEAD','LINK','META'].includes(el.tagName))return null;
    const s=getComputedStyle(el),r=el.getBoundingClientRect();
    if(s.display==='none'||+s.opacity===0||el.hidden||el.inert)return null;
    if(el.getAttribute('aria-hidden')==='true'&&(el.getAttribute('role')==='dialog'||el.tagName==='DIALOG'||el.classList.contains('pswp')))return null;
    if(!r.width||!r.height)return {type:'group',children:[...el.children].map(walk).filter(Boolean)};
    if(!intersects(r.left+scrollX,r.top+scrollY,r.width,r.height)&&(!el.children.length||['hidden','clip','scroll','auto'].includes(s.overflow)))return null;
    const visible=s.visibility==='visible';if(!visible&&!el.children.length)return null;
    const node={type:'box',name:el.getAttribute('aria-label')||el.id||el.tagName.toLowerCase()+(el.classList.length?'.'+el.classList[0]:''),x:r.left+scrollX,y:r.top+scrollY,width:r.width,height:r.height,opacity:+s.opacity,z:parseInt(s.zIndex)||0,background:visible?color(s.backgroundColor):null,radii:[s.borderTopLeftRadius,s.borderTopRightRadius,s.borderBottomRightRadius,s.borderBottomLeftRadius].map(v=>Math.max(0,v.includes('%')?parseFloat(v)*Math.min(r.width,r.height)/100:parseFloat(v)||0)),borders:['Top','Right','Bottom','Left'].map(side=>({width:parseFloat(s['border'+side+'Width'])||0,color:color(s['border'+side+'Color']),style:s['border'+side+'Style']})),clip:['hidden','clip','scroll','auto'].includes(s.overflowX)||['hidden','clip','scroll','auto'].includes(s.overflowY),children:[],rasterStyle:visible?Object.fromEntries(styleKeys.map(k=>[k,s.getPropertyValue(k)])):{}};
    count++;
    if(s.transform!=='none')warnings.add('CSS 旋转和倾斜暂按外接边界转换。');
    if(s.backgroundImage.includes('url('))warnings.add('部分 CSS 背景图片需要进一步嵌入，暂不保证还原。');
    if(s.filter!=='none')warnings.add('复杂滤镜暂不保证还原。');
    if(['CANVAS','VIDEO','IFRAME'].includes(el.tagName))warnings.add('画布、视频和嵌入页面暂仅保留占位框。');
    if(visible&&el.tagName==='IMG'){
      node.type='image';node.name=el.alt||'图片';node.fit=s.objectFit==='contain'?'FIT':s.objectFit==='fill'?'STRETCH':'FILL';
      node.objectFit=s.objectFit;node.objectPosition=s.objectPosition;node.maskImage=s.maskImage;node.imageSource=el.currentSrc||el.src;
      if(includeImages)node.image=imageData(el);else node.imageOmitted=true;
      return node;
    }
    if(visible&&el.tagName.toLowerCase()==='svg'){
      const clone=el.cloneNode(true),originals=[el,...el.querySelectorAll('*')],copies=[clone,...clone.querySelectorAll('*')];
      originals.forEach((original,i)=>{const cs=getComputedStyle(original);for(const key of ['fill','stroke','stroke-width','stroke-linecap','stroke-linejoin','fill-rule','fill-opacity','stroke-opacity','opacity','font-family','font-size'])copies[i].setAttribute(key,cs.getPropertyValue(key));});
      clone.setAttribute('opacity','1');clone.style.opacity='1';clone.setAttribute('xmlns','http://www.w3.org/2000/svg');clone.setAttribute('width',r.width);clone.setAttribute('height',r.height);node.type='svg';node.svg=new XMLSerializer().serializeToString(clone);return node;
    }
    function text(value,bounds,runs){
      if(!intersects(bounds.left+scrollX,bounds.top+scrollY,bounds.width,bounds.height)||!value.trim()||!bounds.width||!bounds.height||count>=maxNodes)return;count++;
      node.children.push({type:'text',name:value.slice(0,30),text:value,x:bounds.left+scrollX,y:bounds.top+scrollY,width:bounds.width,height:bounds.height,...Text.properties(s),fontResolved:Text.resolveFamily(Text.properties(s)),color:color(s.color),runs});
    }
    function runsFor(child){return Text.measureLines(child,s)}
    if(visible&&['INPUT','TEXTAREA','SELECT'].includes(el.tagName)){
      const value=el.type==='password'?'••••••':el.tagName==='SELECT'?el.options[el.selectedIndex]?.text:el.value||el.placeholder;
      const left=r.left+(parseFloat(s.paddingLeft)||0)+(parseFloat(s.borderLeftWidth)||0),top=r.top+(parseFloat(s.paddingTop)||0)+(parseFloat(s.borderTopWidth)||0);
      text(value||'',{left,top,width:Math.max(1,r.width-(left-r.left)-(parseFloat(s.paddingRight)||0)),height:Math.max(parseFloat(s.fontSize)*1.2,r.height-(top-r.top)-(parseFloat(s.paddingBottom)||0))});
    }else for(const child of el.childNodes){if(child.nodeType===Node.TEXT_NODE&&visible){const range=document.createRange();range.selectNodeContents(child);const bounds=range.getBoundingClientRect();let value=child.textContent;value=Text.normalized(value,s);text(value,bounds,runsFor(child));}else if(child.nodeType===Node.ELEMENT_NODE){const c=walk(child);if(c)node.children.push(c);}}

    if(visible&&count<maxNodes&&s.display==='list-item'&&s.listStyleType!=='none'){
      const markerStyle=getComputedStyle(el,'::marker');let label,kind=s.listStyleType;const content=markerStyle.content;if(content&&content!=='normal'&&content!=='none')label=content.replace(/^['"]|['"]$/g,'');
      const first=(function firstText(n){if(n.type==='text')return n;for(const c of n.children||[]){const found=firstText(c);if(found)return found}})(node),line=first?.runs?.[0],props=Text.properties(markerStyle);props.fontFamily=markerStyle.fontFamily||s.fontFamily;props.fontSize=parseFloat(markerStyle.fontSize)||parseFloat(s.fontSize)||14;const f=props.fontSize,ctx=document.createElement('canvas').getContext('2d');ctx.font=Text.font(props);
      if(!label&&!['disc','circle','square'].includes(kind)){const siblings=[...el.parentElement.children].filter(n=>getComputedStyle(n).display==='list-item'),reverse=el.parentElement.hasAttribute('reversed');let ordinal=Number(el.parentElement.getAttribute('start'))||(reverse?siblings.length:1);for(const item of siblings){if(item.hasAttribute('value'))ordinal=Number(item.getAttribute('value'));if(item===el)break;ordinal+=reverse?-1:1}let value=String(ordinal);if(kind==='decimal-leading-zero')value=value.padStart(2,'0');if(/alpha|latin/.test(kind)){let v=Math.max(1,ordinal);value='';while(v){v--;value=String.fromCharCode(97+v%26)+value;v=Math.floor(v/26)}if(kind.startsWith('upper'))value=value.toUpperCase()}if(/roman/.test(kind)){let v=Math.max(1,ordinal);value='';for(const [num,roman] of [[1000,'M'],[900,'CM'],[500,'D'],[400,'CD'],[100,'C'],[90,'XC'],[50,'L'],[40,'XL'],[10,'X'],[9,'IX'],[5,'V'],[4,'IV'],[1,'I']])while(v>=num){value+=roman;v-=num}if(kind.startsWith('lower'))value=value.toLowerCase()}label=value+'.';}
      const inside=s.listStylePosition==='inside',left=r.left+scrollX+(parseFloat(s.paddingLeft)||0),y=line?.y??r.top+scrollY+(parseFloat(s.paddingTop)||0),ink=color(markerStyle.color||s.color);
      if(!label&&['disc','circle','square'].includes(kind)){const size=Math.max(2,f*.32),x=inside?left:left-f*.75,yc=y+Text.baseline(props,{text:'Ag'})-f*.28;const css='rgba('+[ink?.r||0,ink?.g||0,ink?.b||0].map(v=>Math.round(v*255)).join(',')+','+(ink?.a??1)+')',shape=kind==='square'?'<rect x="0" y="0" width="'+size+'" height="'+size+'" fill="'+css+'"/>':'<circle cx="'+size/2+'" cy="'+size/2+'" r="'+(size/2-(kind==='circle'?.5:0))+'" fill="'+(kind==='circle'?'none':css)+'" stroke="'+css+'" stroke-width="'+(kind==='circle'?1:0)+'"/>';node.children.unshift({type:'svg',name:'列表符号',x,y:yc-size/2,width:size,height:size,svg:'<svg xmlns="http://www.w3.org/2000/svg" width="'+size+'" height="'+size+'">'+shape+'</svg>',children:[]});count++;}
      else if(label){const width=ctx.measureText(label).width,x=inside?left:left-width-f*.5;node.children.unshift({type:'text',name:'列表序号 '+label,text:label,x,y,width:Math.max(1,width),height:line?.height||f*1.2,...props,fontResolved:Text.resolveFamily(props),color:ink,whiteSpace:'pre',runs:[{text:label,x,y,width:Math.max(1,width),height:line?.height||f*1.2}],children:[]});count++;}
    }

    node.children.sort((a,b)=>(a.z||0)-(b.z||0));return node;
  }
  try{
    await Promise.race([document.fonts.ready,new Promise(r=>setTimeout(r,2000))]);
    const root=walk(document.body),body=color(getComputedStyle(document.body).backgroundColor),html=color(getComputedStyle(document.documentElement).backgroundColor);
    if(area){function offset(n){if(!n)return null;const inside=n.type==='group'||intersects(n.x,n.y,n.width,n.height);n.children=(n.children||[]).map(offset).filter(Boolean);if(!inside&&!n.children.length)return null;if(n.type!=='group'){n.x-=area.x;n.y-=area.y}if(n.runs)n.runs.forEach(r=>{r.x-=area.x;r.y-=area.y});return n}offset(root);}
    return {format:'gugu-page-to-figma',version:1,captureVersion:'0.7.6',scope,captureRegion:area,title:document.title||'网页',url:location.href,background:body?.a?body:html,width:area?area.width:Math.min(30000,Math.max(innerWidth,document.documentElement.scrollWidth)),height:area?area.height:Math.min(30000,Math.max(innerHeight,document.documentElement.scrollHeight)),count,root,warnings:[...warnings],capturedAt:new Date().toISOString()};
  }catch(error){return {error:error.message};}
}
