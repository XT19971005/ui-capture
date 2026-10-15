"""Versioned local JSON transport; repeated embedded images share immutable bytes."""
import json,math

MIB=1024*1024
MAX_UNIQUE_IMAGE_BYTES=256*MIB
MAX_METADATA_BYTES=16*MIB
MAX_LOGICAL_IMAGE_BYTES=1024*MIB
MAX_IMAGE_BYTES=36000000
MAX_HTTP_BYTES=MAX_UNIQUE_IMAGE_BYTES+MAX_METADATA_BYTES+4*MIB
MAX_ITEMS=200000
MAX_DEPTH=40
MAX_IMAGES=4096
IMAGE_FIELDS=frozenset(('image','original','src','source','originalSource','comparisonSource'))


def _utf8_size(value):
 try:return len(value) if value.isascii() else len(value.encode('utf8'))
 except UnicodeError:raise ValueError('工程文字包含无效的 Unicode 编码') from None


def _image_size(value):
 if not isinstance(value,str) or not value.startswith('data:image/'):raise ValueError('图片表只能包含工程内嵌图片，不能包含文件路径或网络地址')
 if len(value)>MAX_IMAGE_BYTES:raise ValueError('单张内嵌图片超过 36MB 限制，原工程已保留')
 size=_utf8_size(value)
 if size>MAX_IMAGE_BYTES:raise ValueError('单张内嵌图片超过 36MB 限制，原工程已保留')
 return size


def measure(value):
 """Bound unique image data, logical references and real UTF-8 JSON metadata."""
 images={};metadata=0;logical=0;unique=0;items=0
 def add(size):
  nonlocal metadata
  metadata+=size
  if metadata>MAX_METADATA_BYTES:raise ValueError('工程文字与结构超过 16MiB 限制，原工程已保留')
 def walk(item,key=None,depth=0):
  nonlocal logical,unique,items
  items+=1
  if items>MAX_ITEMS:raise ValueError('工程结构条目过多，原工程已保留')
  if depth>MAX_DEPTH:raise ValueError('工程结构层级过多，原工程已保留')
  if isinstance(item,str) and key in IMAGE_FIELDS and item.startswith('data:image/'):
   size=images.get(item)
   if size is None:
    size=_image_size(item);images[item]=size;unique+=size
    if unique>MAX_UNIQUE_IMAGE_BYTES:raise ValueError('工程独立图片数据超过 256MiB 限制，原工程已保留')
   logical+=size
   if logical>MAX_LOGICAL_IMAGE_BYTES:raise ValueError('工程图片引用总量超过 1GiB 安全限制，原工程已保留')
   add(2);return
  if isinstance(item,dict):
   add(2+max(0,len(item)-1))
   for child_key,child in item.items():
    if not isinstance(child_key,str):raise ValueError('工程字段名称无效')
    if len(child_key)>MAX_METADATA_BYTES:raise ValueError('工程字段名称过长')
    add(_utf8_size(json.dumps(child_key,ensure_ascii=False))+1);walk(child,child_key,depth+1)
  elif isinstance(item,list):
   add(2+max(0,len(item)-1))
   for child in item:walk(child,None,depth+1)
  else:
   if not (item is None or isinstance(item,(str,bool,int,float))):raise ValueError('工程包含不能传输的字段类型')
   if isinstance(item,float) and not math.isfinite(item):raise ValueError('工程包含无效数值')
   if isinstance(item,str) and len(item)>MAX_METADATA_BYTES:raise ValueError('工程文字与结构超过 16MiB 限制，原工程已保留')
   add(_utf8_size(json.dumps(item,ensure_ascii=False,separators=(',',':'),allow_nan=False)))
 walk(value)
 return {'uniqueImageBytes':unique,'logicalImageBytes':logical,'metadataBytes':metadata,'uniqueImages':len(images)}


def decode_job(value):
 """Restore references only in image slots, without expanding image strings."""
 if not isinstance(value,dict):raise ValueError('任务参数无效')
 if 'wireFormat' not in value:
  measure(value);return value
 if set(value)!={'wireFormat','wireVersion','images','job'} or value.get('wireFormat')!='shijie-image-table' or type(value.get('wireVersion')) is not int or value['wireVersion']!=1:raise ValueError('不支持的工程图片表格式或版本，请更新拾界后重试')
 table=value['images'];job=value['job']
 if not isinstance(table,list) or len(table)>MAX_IMAGES or not isinstance(job,dict):raise ValueError('工程图片表结构无效')
 seen=set();total=0
 for entry in table:
  size=_image_size(entry)
  if entry in seen:raise ValueError('工程图片表包含重复条目')
  seen.add(entry);total+=size
  if total>MAX_UNIQUE_IMAGE_BYTES:raise ValueError('工程独立图片数据超过 256MiB 限制，原工程已保留')
 used=set();items=0
 def restore(item,key=None,depth=0):
  nonlocal items
  items+=1
  if items>MAX_ITEMS:raise ValueError('工程结构条目过多，原工程已保留')
  if depth>MAX_DEPTH:raise ValueError('工程结构层级过多，原工程已保留')
  if isinstance(item,dict):
   if '$image' in item:
    if key not in IMAGE_FIELDS or set(item)!={'$image'} or type(item['$image']) is not int or not 0<=item['$image']<len(table):raise ValueError('工程图片引用无效或放在了非图片字段中')
    used.add(item['$image']);return table[item['$image']]
   return {name:restore(child,name,depth+1) for name,child in item.items()}
  if isinstance(item,list):return [restore(child,None,depth+1) for child in item]
  if isinstance(item,str) and len(item)>max(MAX_IMAGE_BYTES,MAX_METADATA_BYTES):raise ValueError('工程字段长度超限，原工程已保留')
  return item
 result=restore(job)
 if used!=set(range(len(table))):raise ValueError('工程图片表包含未使用条目')
 measure(result)
 return result
