figma.showUI(__html__,{width:380,height:460});
let busy=false;
figma.ui.onmessage=async message=>{
  if(message.type!=='import'||busy)return;busy=true;let root;
  try{
    const data=JSON.parse(JSON.stringify(message.data));
    if(!['gugu-page-to-figma','shijie-ui-capture'].includes(data?.format)||data.version!==1||!data.root)throw Error('文件格式不正确');
    if(!Number.isFinite(data.width)||!Number.isFinite(data.height)||data.width<=0||data.height<=0||data.width>30000||data.height>30000)throw Error('画布尺寸无效');
    let validated=0;
    function validate(item,depth){if(!item||depth>100||++validated>6000)throw Error('图层数量或嵌套深度超限');if(!['box','image','text','svg','group'].includes(item.type))throw Error('未知图层类型');if(item.type!=='group'){for(const key of ['x','y','width','height'])if(!Number.isFinite(item[key])||Math.abs(item[key])>100000)throw Error('图层坐标无效');if(item.width<=0||item.height<=0)throw Error('图层尺寸无效');}if(item.text?.length>100000||item.svg?.length>2000000||item.image?.length>24000000)throw Error('单个图层数据过大');if(item.children){if(!Array.isArray(item.children))throw Error('子图层无效');item.children.forEach(c=>validate(c,depth+1));}}
    validate(data.root,0);
    if(data._linkChildren===false){const flat=[];function each(n){const own=['text','image','svg'].includes(n.type)||n.background?.a>0||(n.borders||[]).some(b=>b.width>0&&b.color?.a>0)||(n.rasterStyle&&['background-image','box-shadow'].some(k=>n.rasterStyle[k]&&n.rasterStyle[k]!=='none'));if(own)flat.push({...n,children:[],clip:false});(n.children||[]).forEach(each)}each(data.root);data.root={type:'box',name:'画板',x:0,y:0,width:data.width,height:data.height,children:flat}}
    const fonts=await figma.listAvailableFontsAsync(),loaded=new Map(),fallback={family:'Inter',style:'Regular'};
    await figma.loadFontAsync(fallback);
    const paint=c=>c&&c.a>0?[{type:'SOLID',color:{r:Math.max(0,Math.min(1,c.r)),g:Math.max(0,Math.min(1,c.g)),b:Math.max(0,Math.min(1,c.b))},opacity:Math.max(0,Math.min(1,c.a))}]:[];
    async function fontFor(item){const families=[item.fontResolved,...String(item.fontFamily||'').split(',').map(v=>v.trim().replace(/^["']|["']$/g,''))].filter(Boolean),aliases={'serif':'Times New Roman','sans-serif':'Arial','system-ui':'Segoe UI','monospace':'Consolas'};let candidates=[];for(let family of families){family=aliases[family]||family;candidates=fonts.filter(f=>f.fontName.family.toLowerCase()===family.toLowerCase());if(candidates.length)break}const desired=item.fontWeight>=600?(item.fontStyle==='italic'?/bold.*italic/i:/bold|semibold|semi bold/i):(item.fontStyle==='italic'?/italic/i:/regular|normal|book/i),chosen=(candidates.find(f=>desired.test(f.fontName.style))||candidates[0])?.fontName||fallback,key=chosen.family+'/'+chosen.style;if(!loaded.has(key))loaded.set(key,figma.loadFontAsync(chosen));try{await loaded.get(key);return chosen}catch{return fallback}}

    function bounds(node,item,parent,origin){parent.appendChild(node);node.name=String(item.name||item.type).slice(0,120);node.x=item.x-origin.x;node.y=item.y-origin.y;node.resize(Math.max(.01,item.width),Math.max(.01,item.height));node.visible=item.visible!==false;node.locked=!!item.locked;if(Number.isFinite(item.opacity))node.opacity=Math.max(0,Math.min(1,item.opacity));}
    root=figma.createFrame();root.name=String(data.title||'网页导入');root.resize(data.width,data.height);root.fills=paint(data.background);root.clipsContent=data.clipFrame===true;root.x=figma.viewport.center.x-data.width/2;root.y=figma.viewport.center.y-data.height/2;
    let created=0,failedImages=0,failedSVG=0;
    function decode(uri){const encoded=uri.split(',')[1],alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';if(!encoded||!/^[A-Za-z0-9+/]*={0,2}$/.test(encoded))throw Error('图片编码无效');let buffer=0,bits=0;const bytes=[];for(const char of encoded.replace(/=+$/,'')){buffer=(buffer<<6)|alphabet.indexOf(char);bits+=6;if(bits>=8){bits-=8;bytes.push((buffer>>bits)&255)}}return new Uint8Array(bytes)}
    async function build(item,parent,origin){
      if(item.type==='group'){for(const child of item.children||[])await build(child,parent,origin);return}
      let node;
      if(item.type==='text'){
        async function line(part,host,offset,auto){const text=figma.createText();host.appendChild(text);text.fontName=await fontFor(item);text.fontSize=Math.max(1,Math.min(1000,item.fontSize||14));text.characters=String(part.text||'');text.fills=paint(item.color);if(item.textStroke&&Number.isFinite(item.textStrokeWidth)&&item.textStrokeWidth>0){text.strokes=paint(item.textStroke);text.strokeWeight=Math.min(30,item.textStrokeWidth);text.strokeAlign='OUTSIDE';}text.lineHeight={unit:'PIXELS',value:Math.max(1,auto?part.height:item.lineHeight||text.fontSize*1.2)};text.letterSpacing={unit:'PIXELS',value:item.letterSpacing||0};if(item.wordSpacing)for(const match of text.characters.matchAll(/[ \u00a0]/g))text.setRangeLetterSpacing(match.index,match.index+1,{unit:'PIXELS',value:(item.letterSpacing||0)+item.wordSpacing});text.textAlignHorizontal=auto?'LEFT':item.align==='center'?'CENTER':['right','end'].includes(item.align)?'RIGHT':'LEFT';text.textDecoration=(item.textDecoration||'').includes('underline')?'UNDERLINE':(item.textDecoration||'').includes('line-through')?'STRIKETHROUGH':'NONE';bounds(text,{...item,...part},host,offset);text.textAutoResize=auto?'WIDTH_AND_HEIGHT':'HEIGHT';return text}
        if(item.runs?.length>1){node=figma.createFrame();bounds(node,item,parent,origin);node.fills=[];node.clipsContent=false;for(const run of item.runs)await line({...run,name:run.text.slice(0,40),opacity:1,visible:true,locked:false},node,{x:item.x,y:item.y},true)}else if(item.runs?.length){node=await line(item.runs[0],parent,origin,true)}else{node=await line(item,parent,origin,item.whiteSpace==='nowrap'||item.whiteSpace==='pre'||item.height<=(item.fontSize||14)*1.55)}
      }else if(item.type==='svg'){
        try{node=figma.createNodeFromSvg(item.svg);bounds(node,item,parent,origin)}catch{failedSVG++;node=figma.createRectangle();bounds(node,item,parent,origin);node.fills=paint({r:.9,g:.93,b:.95,a:1});}
      }else{
        node=figma.createFrame();bounds(node,item,parent,origin);node.fills=paint(item.background);node.clipsContent=!!item.clip;const radii=item.radii||[0,0,0,0];['topLeftRadius','topRightRadius','bottomRightRadius','bottomLeftRadius'].forEach((key,i)=>node[key]=Math.max(0,Math.min(radii[i]||0,item.width/2,item.height/2)));
        const border=(item.borders||[]).find(b=>b.width>0&&b.color&&b.style!=='none');if(border){node.strokes=paint(border.color);node.strokeAlign='INSIDE';const keys=['strokeTopWeight','strokeRightWeight','strokeBottomWeight','strokeLeftWeight'];keys.forEach((key,i)=>node[key]=Math.max(0,item.borders[i]?.width||0));}
        if(item.type==='image'){if(item.image){try{const image=figma.createImage(decode(item.image));node.fills=[{type:'IMAGE',imageHash:image.hash,scaleMode:item.fit==='FIT'?'FIT':'FILL'}]}catch{failedImages++;node.fills=paint({r:.9,g:.93,b:.95,a:1})}}else{failedImages++;node.fills=paint({r:.9,g:.93,b:.95,a:1})}}
        for(const child of item.children||[])await build(child,node,{x:item.x,y:item.y});
      }
      created++;if(created%100===0)figma.ui.postMessage({type:'progress',text:'已建立 '+created+' 个图层…'});
    }
    await build(data.root,root,{x:0,y:0});figma.currentPage.selection=[root];figma.viewport.scrollAndZoomIntoView([root]);figma.ui.postMessage({type:'done',text:'✓ 已导入 '+created+' 个可编辑图层。'+(failedImages?'\n'+failedImages+' 张图片使用占位框。':'')+(failedSVG?'\n'+failedSVG+' 个 SVG 使用占位框。':'')+'\n复杂样式及字体可能需要手动调整。'});figma.notify('网页导入完成');
  }catch(error){if(root)root.remove();figma.ui.postMessage({type:'error',text:'导入失败：'+error.message});}finally{busy=false;}
};
