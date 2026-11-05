"""Reserve transparent room without shrinking the original content."""
import math

def margins(width,height,max_pixels=36000000):
 def size(mx,my):return width+2*mx,height+2*my
 def valid(mx,my):
  w,h=size(mx,my);return max(w,h)<=6000 and w*h<=max_pixels
 mx=max(16,math.ceil(width*.25));my=max(16,math.ceil(height*.25))
 if valid(mx,my):return mx,my
 lo,hi=0.,1.
 for _ in range(40):
  mid=(lo+hi)/2
  if valid(math.floor(mx*mid),math.floor(my*mid)):lo=mid
  else:hi=mid
 mx,my=math.floor(mx*lo),math.floor(my*lo)
 if min(mx,my)<1:raise ValueError('原图已达当前画布上限，无法保真向外扩展；未缩小或裁切')
 return mx,my
