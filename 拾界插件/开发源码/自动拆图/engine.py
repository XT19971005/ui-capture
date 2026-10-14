"""Deterministic native text/ink construction; complex assets require Codex ImageGen."""
from runtime import ROOT
import base64,io,json,re,time,uuid
from pathlib import Path
import cv2,numpy as np
from PIL import Image,ImageDraw,ImageFont
import planner
from design_properties import design_fields,attach_groups
from plan_contract import vector,link_art_text
FONT=Path('C:/Windows/Fonts/msyhbd.ttc')
def png(image):
 stream=io.BytesIO();image.save(stream,format='PNG');return 'data:image/png;base64,'+base64.b64encode(stream.getvalue()).decode('ascii')
def load_source(value):
 if not isinstance(value,str) or len(value)>36000000 or not re.fullmatch(r'data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+',value):raise ValueError('图片数据无效或过大')
 with Image.open(io.BytesIO(base64.b64decode(value.split(',',1)[1],validate=True))) as im:
  if im.width*im.height>6000000 or max(im.size)>6000:raise ValueError('图片尺寸超限')
  return im.convert('RGB')
def ink_mask(rgb,row):
    h,w=rgb.shape[:2];x0,y0,x1,y1=row['bbox'];patch=rgb[y0:y1,x0:x1]
    allowed=np.zeros(patch.shape[:2],np.uint8)
    cv2.fillPoly(allowed,[np.round(np.array(row['quad'])-[x0,y0]).astype('int32')],255)
    ring=np.zeros_like(allowed);r=max(1,min(3,min(patch.shape[:2])//4));ring[:r]=255;ring[-r:]=255;ring[:,:r]=255;ring[:,-r:]=255
    pixels=patch[(ring>0)&(allowed>0)];bg=np.median(pixels if len(pixels) else patch.reshape(-1,3),axis=0)
    distance=np.linalg.norm(patch.astype(float)-bg,axis=2);d=np.clip(distance*3,0,255).astype('uint8')
    threshold,_=cv2.threshold(d,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    ink=((d>=max(12,.65*threshold))&(allowed>0)).astype('uint8')*255
    coverage=np.count_nonzero(ink)/max(1,np.count_nonzero(allowed))
    if not .015<coverage<.68:ink=allowed.copy()
    # Estimated foreground colour, weighted by contrast to the local material.
    colors=patch[ink>0];fill=np.array([245,245,245])
    if len(colors):
        buckets=(colors//32)*32+16;keys,counts=np.unique(buckets,axis=0,return_counts=True)
        scores=counts*(24+np.linalg.norm(keys-bg,axis=1));fill=keys[np.argmax(scores)]
        same=np.all(buckets==fill,axis=1);fill=np.median(colors[same],axis=0)
    rad=max(2,min(6,round((y1-y0)*.08)))
    expanded=cv2.dilate(ink,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(rad*2+1,rad*2+1)))
    full=np.zeros((h,w),np.uint8);full[y0:y1,x0:x1]=expanded
    return full,np.clip(fill,0,255).astype('uint8'),bg,coverage

def text_nodes(rows,rgb,art_ids):
    nodes=[];mask=np.zeros(rgb.shape[:2],np.uint8)
    for row in rows:
        if row['id'] in art_ids:continue
        ink,fill,bg,coverage=ink_mask(rgb,row);mask=cv2.bitwise_or(mask,ink)
        x0,y0,x1,y1=row['bbox'];text=row['text'];bw,bh=x1-x0,y1-y0
        if bh>bw*1.8 and re.fullmatch(r'[A-Za-z0-9 /+.-]+',text):
            pixels=rgb[y0:y1,x0:x1];dark=pixels[np.linalg.norm(pixels.astype(float)-bg,axis=2)>65];color=np.median(dark,axis=0) if len(dark) else fill
            nodes.append({'id':uuid.uuid4().hex,'name':text,'type':'text','text':text,'x':x0,'y':y0,'width':bw,'height':bh,'fontSize':max(8,round(bw*.8,2)),'fontWeight':400,'fontFamily':'Arial','rotation':90,'fill':'#'+''.join(f'{int(v):02x}' for v in color),'strokeWidth':0,'review':True,'sourceTextId':row['id'],'sourceBox':{'x0':x0,'y0':y0,'x1':x1,'y1':y1}});continue
        vertical=bh>bw*1.4 and len(text)>1 and all('\u4e00'<=c<='\u9fff' for c in text)
        parts=[(ch,x0,y0+i*bh/len(text),bw,bh/len(text)) for i,ch in enumerate(text)] if vertical else [(text,x0,y0,bw,bh)]
        for value,x,y,width,height in parts:
            size=max(8,round(height*.84))
            while size>6:
                font=ImageFont.truetype(str(FONT),size);box=font.getbbox(value)
                if box[2]-box[0]<=width and box[3]-box[1]<=height:break
                size-=1
            contrast=np.linalg.norm(fill-bg);stroke_width=min(2,max(0,round(height*.035))) if contrast>60 else 0
            luminance=float(np.dot(fill,[.2126,.7152,.0722]))
            nodes.append({'id':uuid.uuid4().hex,'name':value,'type':'text','text':value,'x':round(x+max(0,(width-(box[2]-box[0]))/2),2),'y':round(y+max(0,(height-(box[3]-box[1]))/2),2),'width':round(width,2),'height':round(height,2),'fontSize':size,'fontWeight':700,'fill':'#'+''.join(f'{v:02x}' for v in fill),'stroke':'#161919' if luminance>130 else '#fff8e8','strokeWidth':stroke_width,'confidence':round(row['confidence']*100,1),'review':row['confidence']<.9,'provenance':'rapidocr','sourceTextId':row['id'],'sourceBox':{'x0':int(round(x)),'y0':int(round(y)),'x1':int(round(x+width)),'y1':int(round(y+height))}})
    # Fit genuine editable glyphs rather than treating padded OCR boxes as their size.
    from text_style import estimate
    for n in nodes:
        if n.get('rotation')==90:continue
        b=n['sourceBox'];fitted=estimate(rgb[b['y0']:b['y1'],b['x0']:b['x1']],n['text'])
        if fitted:
            n.update({k:fitted[k] for k in ('fontFamily','fontWeight','fontStyle','textSkew','fontSize','fitWidth','fill','strokeWidth','styleMatch')})
            n.update(x=b['x0']+fitted['offsetX'],y=b['y0']+fitted['offsetY'],width=fitted['glyphWidth'],height=fitted['glyphHeight'])
    # Connected vertical Chinese remains one editable text object, not one layer per glyph.
    # Glyph fitting above is retained, but its independent draft nodes are merged before export.
    for row in rows:
        x0,y0,x1,y1=row['bbox'];text=row['text']
        vertical=(y1-y0)>(x1-x0)*1.4 and len(text)>1 and all('\u4e00'<=c<='\u9fff' for c in text)
        if not vertical or row['id'] in art_ids:continue
        members=[n for n in nodes if n.get('sourceTextId')==row['id']]
        if len(members)!=len(text):raise ValueError('连续竖排文字构造不完整')
        first=members[0];merged={**first,'name':text,'text':'\n'.join(text),'lineHeight':(y1-y0)/len(text),'sourceTextId':row['id'],
          'width':max(n['width'] for n in members),'height':y1-first['y'],
          'sourceBox':{'x0':x0,'y0':y0,'x1':x1,'y1':y1}}
        member_ids={n['id'] for n in members};insert=nodes.index(first)
        nodes=[n for n in nodes if n['id'] not in member_ids];nodes.insert(insert,merged)
    # Ordinary text may carry a real colour gradient even over a plain white panel.
    # Sample only foreground core pixels across the row, excluding anti-aliasing and paper.
    for n in nodes:
        b=n['sourceBox'];patch=rgb[b['y0']:b['y1'],b['x0']:b['x1']].astype(float)
        # OCR boxes can touch glyphs. The most common material colour is a safer
        # background estimate than a border median polluted by the letters.
        buckets=(patch.reshape(-1,3).astype('uint8')//16)*16
        keys,counts=np.unique(buckets,axis=0,return_counts=True);dominant=keys[np.argmax(counts)]
        material=np.all(buckets==dominant,axis=1);bg=np.median(patch.reshape(-1,3)[material],axis=0)
        if np.mean(material)<.2:continue
        contrast=np.linalg.norm(patch-bg,axis=2)
        cutoff,_=cv2.threshold(np.clip(contrast,0,255).astype('uint8'),0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
        ys,xs=np.where(contrast>max(50,cutoff*.85))
        if len(xs)<20:continue
        # Fit colour against both axes, using only actual foreground cores.
        # A small/vertical word has exactly the same gradient semantics as a title.
        coordinates=np.column_stack([np.ones(len(xs)),xs,ys]);colors=patch[ys,xs]
        fit=np.linalg.lstsq(coordinates,colors,rcond=None)[0]
        slopes=fit[1:];direction=np.linalg.svd(slopes,full_matrices=False)[0][:,0]
        if direction[0]<-1e-6 or (abs(direction[0])<1e-6 and direction[1]<0):direction=-direction
        projections=np.column_stack([xs,ys])@direction;span=float(projections.max()-projections.min())
        delta=span*(direction@slopes)
        residual=np.linalg.norm(colors-coordinates@fit,axis=1)
        if np.linalg.norm(delta)>22 and float(np.median(residual))<12:
            # Gradient bounds are the actual exported glyph bounds, not OCR padding.
            center=np.array([n['x']-b['x0']+n['width']/2,n['y']-b['y0']+n['height']/2])
            fullspan=abs(direction[0])*n['width']+abs(direction[1])*n['height']
            ends=[center-direction*fullspan/2,center+direction*fullspan/2]
            hexc=lambda c:'#'+''.join(f'{int(round(v)):02x}' for v in np.clip(c,0,255))
            n['gradient']={'angle':round(float(-np.degrees(np.arctan2(direction[1],direction[0]))),3),'stops':[[i,hexc(np.r_[1,p]@fit)] for i,p in enumerate(ends)]};n['strokeWidth']=0
    return nodes,mask

def logo_background(patch,inner=None):
    """Fit the surrounding material, so its gradient inside letter holes stays empty."""
    h,w=patch.shape[:2];ys,xs=np.indices((h,w))
    left,top,right,bottom=inner or (0,0,w,h)
    border=(((xs==left)|(xs==right-1))&(ys>=top)&(ys<bottom))|(((ys==top)|(ys==bottom-1))&(xs>=left)&(xs<right))
    coords=np.stack([np.ones((h,w)),xs/max(1,w),ys/max(1,h)],axis=-1)
    design=coords[border];colors=patch[border].astype(float)
    corners=patch[[top,top,bottom-1,bottom-1],[left,right-1,left,right-1]].astype(float)
    # A neighboring panel can cover the entire lower boundary. Upper corner
    # material anchors avoid interpreting that foreground panel as a gradient.
    anchor=np.median(corners[:2],axis=0);limit=max(50,float(np.median(np.linalg.norm(corners[:2]-anchor,axis=1)))*2.5)
    keep=np.linalg.norm(colors-anchor,axis=1)<limit
    if np.count_nonzero(keep)<6:keep=np.ones(len(colors),bool)
    eligible=keep.copy()
    for _ in range(3):
        fit=np.linalg.lstsq(design[keep],colors[keep],rcond=None)[0]
        residual=np.linalg.norm(colors-design@fit,axis=1)
        selected=eligible&(residual<max(20,float(np.quantile(residual[eligible],.8))))
        if np.count_nonzero(selected)<6:break
        keep=selected
    return np.clip(coords@fit,0,255)

def flat_ink_parts(patch,ink):
    """Separate a small flat palette without merging holes or disconnected dots."""
    pixels=patch[ink>0].astype(float)
    if not len(pixels):return []
    remaining=np.ones(len(pixels),bool);palette=[]
    for _ in range(6):
        if not np.any(remaining):break
        quant=(pixels[remaining].astype('uint8')//24)*24
        keys,counts=np.unique(quant,axis=0,return_counts=True);key=keys[np.argmax(counts)]+12
        selected=remaining&(np.linalg.norm(pixels-key,axis=1)<42)
        if not np.any(selected):break
        center=np.median(pixels[selected],axis=0);palette.append(center)
        remaining&=np.linalg.norm(pixels-center,axis=1)>=42
    # A broad continuous palette denotes texture/material, not a flat mark.
    if not palette or np.mean(remaining)>.04:return None
    nearest=np.argmin(np.linalg.norm(pixels[:,None,:]-np.array(palette)[None,:,:],axis=2),axis=1)
    # JPEG/anti-alias transition colours are not additional flat inks. Only
    # secondary regions with an actual interior become separate native layers.
    genuine=[];_,components=cv2.connectedComponents((ink>0).astype('uint8'))
    for index,center in enumerate(palette):
        part=np.zeros(ink.shape,np.uint8);part[ink>0]=(nearest==index).astype('uint8')
        core=cv2.erode(part,np.ones((5,5),np.uint8))>0
        isolated=any(np.all(nearest[components[ink>0]==label]==index) for label in np.unique(components[part>0]) if label)
        if index==0 or np.count_nonzero(core)>=8 or isolated:
            genuine.append(np.median(patch[core],axis=0) if np.any(core) else center)
    palette=genuine
    nearest=np.argmin(np.linalg.norm(pixels[:,None,:]-np.array(palette)[None,:,:],axis=2),axis=1)
    parts=[]
    for index,center in enumerate(palette):
        part=np.zeros(ink.shape,bool);part[ink>0]=nearest==index
        if np.any(part):parts.append((part,center))
    return parts

def assets_without_native_duplicates(assets,vectors):
    kept=[]
    for a in assets:
        duplicate=False
        if a['kind'] in ('panel','button','icon'):
            x,y,right,bottom=a['box'];area=(right-x)*(bottom-y)
            for v in vectors:
                try:
                    vx,vy,vw,vh=(v[k] for k in ('x','y','width','height'))
                    overlap=max(0,min(right,vx+vw)-max(x,vx))*max(0,min(bottom,vy+vh)-max(y,vy))
                    if overlap/max(1,area+vw*vh-overlap)>.85:duplicate=True;break
                except (KeyError,TypeError):continue
        if not duplicate:kept.append(a)
    return kept

def art_rows_for_assets(rows,rgb,assets):
    art=set()
    for row in rows:
        rx,ry,rr,rb=row['bbox'];area=(rr-rx)*(rb-ry);ink=None
        for a in assets:
            if a['kind'] not in ('logo','person','icon','decoration'):continue
            x,y,right,bottom=a['box'];overlap=max(0,min(rr,right)-max(rx,x))*max(0,min(rb,bottom)-max(ry,y))
            if overlap>=.85*area:art.add(row['id']);break
            if overlap>=.3*area:
                if ink is None:ink=ink_mask(rgb,row)[0]
                if np.count_nonzero(ink[y:bottom,x:right])/max(1,np.count_nonzero(ink))>=.8:art.add(row['id']);break
    return art

def expanded_logo_assets(rows,rgb,assets):
    result=[];inks={}
    for a in assets:
        if a['kind']!='logo':result.append(a);continue
        box=list(a['box'])
        for row in rows:
            rx,ry,rr,rb=row['bbox'];x,y,right,bottom=a['box']
            overlap=max(0,min(rr,right)-max(rx,x))*max(0,min(rb,bottom)-max(ry,y))
            if overlap<.3*(rr-rx)*(rb-ry):continue
            if row['id'] not in inks:inks[row['id']]=ink_mask(rgb,row)[0]
            ink=inks[row['id']]
            if np.count_nonzero(ink[y:bottom,x:right])/max(1,np.count_nonzero(ink))>=.75:
                box=[min(box[0],rx),min(box[1],ry),max(box[2],rr),max(box[3],rb)]
        result.append({**a,'box':box})
    return result

def segment(image,assets,progress,cancelled,exclude_boxes=None):
    # Art text and flat marks must retain all disconnected strokes; SAM alone can select just one glyph.
    logos=[a for a in assets if a['kind']=='logo'];assets=[a for a in assets if a['kind']!='logo'];logo_results=[]
    h,w=image.shape[:2];owned_ink=np.zeros((h,w),bool)
    for a in logos:
        x0,y0,x1,y1=a['box'];px=max(3,round((x1-x0)*.08));py=max(3,round((y1-y0)*.08));x0=max(0,x0-px);y0=max(0,y0-py);x1=min(w,x1+px);y1=min(h,y1+py);patch=image[y0:y1,x0:x1]
        ax,ay,ar,ab=a['box'];bg=logo_background(patch,(ax-x0,ay-y0,ar-x0,ab-y0))
        distance=np.linalg.norm(patch.astype(float)-bg,axis=2).clip(0,255).astype('uint8')
        threshold,_=cv2.threshold(distance,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
        ink=(distance>max(18,threshold*.5)).astype('uint8')*255
        # Padding is for full edge recovery, never ownership of a neighboring panel.
        support=np.zeros_like(ink);support[max(0,ay-y0-2):min(ink.shape[0],ab-y0+2),max(0,ax-x0-2):min(ink.shape[1],ar-x0+2)]=255
        ink=cv2.bitwise_and(ink,support)
        for ox,oy,orr,obb in exclude_boxes or []:
            left,top,right,bottom=max(x0,ox),max(y0,oy),min(x1,orr),min(y1,obb)
            overlap=max(0,min(ar,orr)-max(ax,ox))*max(0,min(ab,obb)-max(ay,oy))
            if right>left and bottom>top and overlap/max(1,(ar-ax)*(ab-ay))<.4:
                ink[top-y0:bottom-y0,left-x0:right-x0]=0
        # Ownership applies to confirmed ink pixels, never another object's box.
        # One same-box mark can yield several colour layers without mutually
        # deleting every stroke when the planner lists its colour channels.
        ink[owned_ink[y0:y1,x0:x1]]=0
        # A logo label does not establish a flat material. Printed white surfaces,
        # 3-D objects and multicolour banners must retain their whole silhouette.
        parts=flat_ink_parts(patch,ink)
        if parts is None:
            assets.append({**a,'kind':'decoration','classificationNote':'复杂彩色材质保留完整轮廓，不能只提取墨迹'})
            continue
        if .003<np.count_nonzero(ink)/max(1,ink.size)<.85:
            owned_ink[y0:y1,x0:x1]|=ink>0
            for part,color in parts:
                mask=np.zeros((h,w),np.uint8);mask[y0:y1,x0:x1]=part.astype('uint8')*255
                suffix=' · #'+''.join(f'{int(v):02x}' for v in color) if len(parts)>1 else ''
                logo_results.append({**a,'name':a['name']+suffix,'mask':mask,'flatColor':color})
    if not assets:return logo_results
    # Complex material remains an explicitly unapproved placement proposal.
    # No local neural model is loaded; complete_asset must replace it before export.
    results=[]
    for i,a in enumerate(assets):
        if cancelled():raise InterruptedError('已取消')
        x0,y0,x1,y1=a['box'];mask=np.zeros((h,w),np.uint8);mask[y0:y1,x0:x1]=255
        results.append({**a,'mask':mask,'pendingGeneration':True})
    return logo_results+results

def text_rows(plan,width,height):
 rows=[];used=set()
 for n in plan.get('texts',[])[:200]:
  ident=str(n.get('id',''))[:60];text=str(n.get('text','')).strip()[:1000];b=n.get('box') or n.get('bbox')
  if isinstance(b,dict):b=[b.get(k) for k in ('left','top','right','bottom')]
  if not ident or ident in used or not text or not isinstance(b,list) or len(b)!=4:raise ValueError('Codex文字规划无效')
  if any(not isinstance(v,(int,float)) or isinstance(v,bool) for v in b):raise ValueError('文字框坐标无效')
  x,y,right,bottom=map(lambda v:int(round(v)),b)
  if not(0<=x<right<=width and 0<=y<bottom<=height):raise ValueError('文字框超出原图')
  used.add(ident);rows.append({'id':ident,'text':text,'bbox':[x,y,right,bottom],'quad':[[x,y],[right,y],[right,bottom],[x,bottom]],'confidence':1.0,'provenance':'codex-vision-text'})
 return rows

def build_scene(source,title,plan_override,progress,cancelled):
 if cancelled():raise InterruptedError('已取消')
 im=load_source(source);rgb=np.array(im);w,h=im.size
 plan=planner.parse_plan(json.dumps(plan_override),w,h,(w,h));rows=text_rows(plan_override,w,h)
 vectors=[vector(a,w,h,i) for i,a in enumerate(plan_override.get('vectors',[]))]
 art=set(plan.get('art_text_ids',[]))
 link_art_text(plan['assets'],rows,art)
 assets=expanded_logo_assets(rows,rgb,assets_without_native_duplicates(plan['assets'],vectors))
 # The visual planner explicitly excludes material lettering. Mere overlap
 # with a character or icon must not swallow independent UI labels/costs.
 texts,_=text_nodes(rows,rgb,art)
 for n in texts:
  n.pop('confidence',None);n.update(provenance='codex-vision-text',review=True)
  for row in plan_override.get('texts',[]):
   if n.get('sourceTextId')==row['id'] or (n.get('sourceBox') and row['id'] in {r['id'] for r in rows if r['bbox'][0]<=n['sourceBox']['x0']<n['sourceBox']['x1']<=r['bbox'][2] and r['bbox'][1]<=n['sourceBox']['y0']<n['sourceBox']['y1']<=r['bbox'][3]}):
    n['sourceTextId']=row['id'];n.update(design_fields(row));break
 exclude=[[int(v['x']),int(v['y']),int(v['x']+v['width']),int(v['y']+v['height'])] for v in vectors if v.get('type')=='rect']
 results=segment(rgb,assets,progress,cancelled,exclude_boxes=exclude)
 results.sort(key=lambda a:np.count_nonzero(a['mask']),reverse=True)
 layers=[{'id':uuid.uuid4().hex,'name':'背景补全候选','type':'image','x':0,'y':0,'width':w,'height':h,'src':source,'provenance':'pending-image-generation','review':True}]
 for a in results:
  if cancelled():raise InterruptedError('已取消')
  mask=a['mask'];ys,xs=np.where(mask>0)
  if not len(xs):continue
  x,y,right,bottom=int(xs.min()),int(ys.min()),int(xs.max())+1,int(ys.max())+1
  alpha=mask[y:bottom,x:right];crop=rgb[y:bottom,x:right]
  n={'id':uuid.uuid4().hex,'name':a['name'],'x':x,'y':y,'width':right-x,'height':bottom-y,'assetKind':a['kind'],'sourceAssetId':a['id'],'sourceEntityId':a.get('entityId') or a['id'],'sourceEntityParts':a.get('entityParts',[a['id']]),'review':True}
  if 'flatColor' in a:
   from vector_trace import trace
   n.update(type='path',d=trace(alpha),fill='#'+''.join(f'{int(v):02x}' for v in a['flatColor']),provenance='observed-flat-ink')
  else:n.update(type='image',src=png(Image.fromarray(np.dstack([crop,alpha]))),provenance='pending-image-generation')
  n.update(design_fields(a));n['sourceTextParts']=a.get('sourceTextParts',[]);layers.append(n)
 for i,a in enumerate(vectors):
  if a.get('type') not in ('rect','ellipse','path') or not re.fullmatch(r'#[0-9a-fA-F]{6}',a.get('fill','')):raise ValueError('原生矢量规划无效')
  if not all(isinstance(a.get(k),(int,float)) and not isinstance(a.get(k),bool) and np.isfinite(a[k]) for k in ['x','y','width','height']) or not (0<=a['x']<a['x']+a['width']<=w and 0<=a['y']<a['y']+a['height']<=h):raise ValueError('原生矢量框超出原图')
  if a['type']=='path' and (not a.get('d') or not re.fullmatch(r'[MmLlHhVvCcSsQqTtAaZz\s\d.eE,+\-]+',a['d'])):raise ValueError('原生矢量路径无效')
  layers.append({k:a[k] for k in ['name','type','x','y','width','height','fill','radius','d'] if k in a}|{'id':uuid.uuid4().hex,'sourceVectorId':a.get('id') or 'vector:'+str(i),'provenance':'codex-native-vector','review':True}|design_fields(a))
 layers.extend(texts)
 if len(layers)==1 and not vectors:raise ValueError('未发现可拆分的文字或素材')
 return attach_groups({'format':'shijie-scene','version':2,'title':title,'width':w,'height':h,'source':source,'nodes':layers,'edges':[],'groups':[],'provenance':'codex-native-scene','recognition':{'engine':'Codex vision + native text/vector','automatic':True,'warnings':[]}},plan_override.get('groups',[]))
