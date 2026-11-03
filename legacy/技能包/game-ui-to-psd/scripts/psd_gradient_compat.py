"""Compatibility for bundled psd-tools' missing native gradient offset branch.
Reads actual Adobe descriptors; leaves color interpolation and all other effects
with the independent reader. Photoshop rendering/editing remains a separate test.
"""
import numpy as np
from psd_tools.composite import paint
from psd_tools.terminology import Key,Enum

def install():
 if getattr(paint.draw_gradient_fill,'_shijie_offset',False):return
 original=paint.draw_gradient_fill
 def draw(viewport,color_mode,desc):
  angle=float(desc.get(Key.Angle,0));offset=desc.get(Key.Offset,{})
  ox=float(offset.get(b'Hrzn',0))/100;oy=float(offset.get(b'Vrtc',0))/100
  # Exact90 has a modulo discontinuity in this bundled reader.
  if abs((angle%180)-90)<1e-7:angle-=1e-6
  if not ox and not oy:
   copy=dict(desc.items());copy[Key.Angle]=angle;return original(viewport,color_mode,copy)
  height,width=viewport[3]-viewport[1],viewport[2]-viewport[0]
  ratio=angle%90;scale=float(desc.get(Key.Scale,100))/100*((90-ratio)/90*width+ratio/90*height)
  X,Y=np.meshgrid(np.linspace(-width/scale,width/scale,width,dtype=np.float32)-2*ox*width/scale,np.linspace(-height/scale,height/scale,height,dtype=np.float32)-2*oy*height/scale)
  kind=desc.get(Key.Type).enum
  if kind==Enum.Linear:Z=paint._make_linear_gradient(X,Y,angle)
  elif kind==Enum.Radial:Z=paint._make_radial_gradient(X,Y)
  else:return original(viewport,color_mode,desc)
  Z=np.clip(Z,0,1)
  if bool(desc.get(Key.Reverse,False)):Z=1-Z
  G,Ga=paint._make_gradient_color(color_mode,desc.get(Key.Gradient))
  return G(Z) if G is not None else None,np.expand_dims(Ga(Z),2) if Ga is not None else None
 draw._shijie_offset=True;paint.draw_gradient_fill=draw
