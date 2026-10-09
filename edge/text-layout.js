window.ShijieText = (/* Shared browser typography for capture, preview and native export. */
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
