"""Stable same-resource links derived from explicit annotation identity evidence."""
import copy,re

def _clean(value):return re.sub(r'\s+','',str(value or '')).casefold()

def image_links(layers,annotations=None):
 from source_annotations import summary
 marks=[m for m in summary(annotations) if m.get('layerType')=='image' and m.get('purpose')=='keep'] if annotations else []
 by_number={m['number']:m for m in marks};parents={m['number']:m['number'] for m in marks}
 def find(n):
  while parents[n]!=n:n=parents[n]
  return n
 keys={};eligible=set()
 for m in marks:
  n=m['number'];key=m.get('reuseKey');proof=_clean(m.get('reuseEvidence'))
  signatures=[]
  if key and proof:signatures.append(('key',key))
  if len(proof)>=10:signatures.append(('proof',_clean(m['name']),proof))
  if signatures:eligible.add(n)
  for signature in signatures:
   if signature in keys:parents[find(n)]=find(keys[signature])
   else:keys[signature]=n
 def mark_for(layer):
  note=str(layer.get('reviewNote',''));match=re.search(r'标注\s*[：:]?\s*0*(\d+)',note) or re.match(r'^\s*0*(\d+)[\s·、._]',layer['name'])
  if match and int(match[1]) in by_number:return by_number[int(match[1])]
  b=layer['box'];scores=[]
  for m in marks:
   for st in m['strokes']:
    xs=[p[0] for p in st];ys=[p[1] for p in st];x,y,w,h=min(xs),min(ys),max(xs)-min(xs),max(ys)-min(ys)
    overlap=max(0,min(b['x']+b['width'],x+w)-max(b['x'],x))*max(0,min(b['y']+b['height'],y+h)-max(b['y'],y))
    score=overlap/max(1,b['width']*b['height']+w*h-overlap)
    scores.append((score,m['number']))
  scores.sort(reverse=True)
  if scores and scores[0][0]>.65 and (len(scores)==1 or scores[1][1]==scores[0][1] or scores[0][0]-scores[1][0]>.2):return by_number[scores[0][1]]
  return None
 refs={};first={}
 for index,layer in enumerate(layers):
  if layer.get('layerType','image')!='image' or layer.get('assetKind')=='background':continue
  m=mark_for(layer);identity=find(m['number']) if m and m['number'] in eligible else None
  explicit=layer.get('reuseOf')
  if explicit is not None:refs[index]=refs.get(explicit,explicit)
  if identity is not None:
   if identity in first:refs[index]=refs.get(first[identity],first[identity])
   else:first[identity]=refs.get(index,index)
 groups={}
 for index,layer in enumerate(layers):
  if layer.get('layerType','image')=='image':groups.setdefault(refs.get(index,index),[]).append(index)
 reference={root:max([i for i in members if abs(layers[i].get('rotation',0))<.001] or [root],key=lambda i:layers[i]['box']['width']*layers[i]['box']['height']) for root,members in groups.items()}
 return refs,reference,groups

def normalize_plan(layers,annotations):
 out=copy.deepcopy(layers);refs,_,_=image_links(out,annotations)
 for index,master in refs.items():out[index].update(reuseOf=master,native=None)
 return out

def statistics(layers,nodes,annotations=None):
 refs,_,groups=image_links(layers,annotations);done={n['_generationPlanIndex'] for n in nodes if n.get('type')=='image' and '_generationPlanIndex' in n}
 return {'resources':len(groups),'positions':sum(len(v) for v in groups.values()),'placed':len(done),'groups':[{'masterIndex':root,'positions':members,'placed':sum(i in done for i in members)} for root,members in groups.items()]}
