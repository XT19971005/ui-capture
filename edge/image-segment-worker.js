/* Local pixel segmentation and tracing. Runs off the editor thread. */
importScripts('vendor/imagetracer.js');
const hex=(r,g,b)=>'#'+[r,g,b].map(v=>Math.round(v).toString(16).padStart(2,'0')).join('');
function trace(image,options={}){return ImageTracer.imagedataToSVG(image,{ltres:1,qtres:1,pathomit:3,strokewidth:0,roundcoords:1,colorsampling:0,colorquantcycles:1,...options});}
function paths(svg){return [...svg.matchAll(/<path\s[^>]*>/g)].map(m=>{const fill=m[0].match(/fill="rgb\((\d+),(\d+),(\d+)\)"/),d=m[0].match(/ d="([^"]+)"/);const alpha=m[0].match(/opacity="([^"]+)"/);if(alpha&&+alpha[1]<.01)return null;return fill&&d?{opacity:alpha?+alpha[1]:1,fill:hex(+fill[1],+fill[2],+fill[3]),d:d[1]}:null;}).filter(Boolean);}
self.onmessage=({data:m})=>{try{const {width:w,height:h,data}=m.image,N=w*h;if(N>6000000)throw Error('图片太大，请先裁切');const px=new Uint8ClampedArray(data);
 if(m.mode==='trace'){const result=paths(trace({width:w,height:h,data:px},{numberofcolors:m.colors||8,colorsampling:2,colorquantcycles:3,pathomit:5}));if(result.length>300)throw Error('轮廓过于复杂，请缩小选区或减少描摹颜色');postMessage({paths:result});return;}
 const seen=new Uint8Array(N),labels=new Int32Array(N),queue=new Int32Array(N),components=[];
 const key=i=>(px[i*4]>>2)*4096+(px[i*4+1]>>2)*64+(px[i*4+2]>>2);
 for(const b of m.exclude||[])for(let y=Math.max(0,b.y0-3);y<=Math.min(h-1,b.y1+3);y++)for(let x=Math.max(0,b.x0-3);x<=Math.min(w-1,b.x1+3);x++)seen[y*w+x]=1;
 const min=Math.max(128,Math.round(N/1800));let label=0;
 for(let start=0;start<N;start++){if(seen[start]||px[start*4+3]<250)continue;const k=key(start);let head=0,tail=1,minx=w,miny=h,maxx=0,maxy=0,r=0,g=0,b=0,exact=new Map();queue[0]=start;seen[start]=1;label++;
 while(head<tail){const i=queue[head++],x=i%w,y=(i/w)|0;labels[i]=label;minx=Math.min(minx,x);maxx=Math.max(maxx,x);miny=Math.min(miny,y);maxy=Math.max(maxy,y);r+=px[i*4];g+=px[i*4+1];b+=px[i*4+2];const ek=px[i*4]*65536+px[i*4+1]*256+px[i*4+2];exact.set(ek,(exact.get(ek)||0)+1);const visit=j=>{if(j<0||j>=N||seen[j]||px[j*4+3]<250||key(j)!==k)return;seen[j]=1;queue[tail++]=j;};if(x)visit(i-1);if(x<w-1)visit(i+1);visit(i-w);visit(i+w);}
 const bw=maxx-minx+1,bh=maxy-miny+1;if(tail>=min&&bw>=8&&bh>=8&&tail/(bw*bh)>.2&&Math.max(...exact.values())/tail>.93)components.push({label,count:tail,x:minx,y:miny,width:bw,height:bh,fill:hex(r/tail,g/tail,b/tail)});
 }
 if(m.mode==='regions'){postMessage({regions:components.filter(c=>c.count/(c.width*c.height)>.65&&c.width>40&&c.height>20&&c.width*c.height<N*.45).sort((a,b)=>b.count-a.count).slice(0,16).map(c=>({x0:c.x,y0:c.y,x1:c.x+c.width,y1:c.y+c.height,background:c.fill}))});return;}
 components.sort((a,b)=>b.count-a.count);const chosen=components.slice(0,250),nodes=[],cleared=new Uint8Array(N);let index=0;
 for(const c of chosen){const cw=c.width+2,ch=c.height+2,mask=new Uint8ClampedArray(cw*ch*4);mask.fill(255);for(let y=0;y<c.height;y++)for(let x=0;x<c.width;x++){const i=(c.y+y)*w+c.x+x;if(labels[i]===c.label){const j=((y+1)*cw+x+1)*4;for(const off of [0,-4,4,-cw*4,cw*4]){mask[j+off]=mask[j+off+1]=mask[j+off+2]=0;}}}
 const ps=paths(trace({width:cw,height:ch,data:mask},{pal:[{r:0,g:0,b:0,a:255},{r:255,g:255,b:255,a:255}]})).filter(p=>p.fill==='#000000');if(!ps.length)continue;
 const d=ps.map(p=>p.d).join(' ');if(d.length>100000)continue;nodes.push({type:'path',x:c.x-1,y:c.y-1,width:cw,height:ch,d,fill:c.fill,name:'纯色形状 '+(++index),provenance:'local-flat-region'});
 for(let y=0;y<c.height;y++)for(let x=0;x<c.width;x++){const i=(c.y+y)*w+c.x+x;if(labels[i]===c.label)cleared[i]=1;}
 if(index%20===0)postMessage({progress:index/Math.max(1,chosen.length)});
 }
 // Residuals keep photos, gradients and unclassified details, not a full screenshot cover.
 let remaining=0;for(let i=0;i<N;i++){if(cleared[i])px[i*4+3]=0;if(px[i*4+3])remaining++;}
 postMessage({nodes,residual:px.buffer,remaining,omitted:Math.max(0,components.length-250)},[px.buffer]);
 }catch(e){postMessage({error:e.message});}};
