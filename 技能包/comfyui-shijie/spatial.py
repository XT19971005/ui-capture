"""Tight RGBA storage with absolute document coordinates."""
import numpy as np

def validate_asset(asset,width,height):
 a=asset.get('rgba');x=asset.get('left',0);y=asset.get('top',0)
 if asset.get('kind') not in ('bitmap','text','shape') or not isinstance(a,np.ndarray) or a.dtype!=np.uint8 or a.ndim!=3 or a.shape[2]!=4:raise ValueError('Invalid prepared branch asset')
 if type(x) is not int or type(y) is not int or not 0<=x<x+a.shape[1]<=width or not 0<=y<y+a.shape[0]<=height:raise ValueError('Asset placement outside canvas')
 return asset

def compact_asset(asset):
 a=asset['rgba'];ys,xs=np.nonzero(a[...,3]);out=dict(asset)
 if not len(xs):raise ValueError('Empty asset')
 x=int(xs.min());y=int(ys.min());r=int(xs.max())+1;b=int(ys.max())+1
 tight=np.array(a[y:b,x:r],dtype=np.uint8,order='C',copy=True)
 tight[tight[...,3]==0,:3]=0
 out.update(rgba=tight,left=asset.get('left',0)+x,top=asset.get('top',0)+y,width=r-x,height=b-y)
 return out

def materialize(asset,width,height):
 validate_asset(asset,width,height);out=np.zeros((height,width,4),np.uint8);a=asset['rgba'];x=asset.get('left',0);y=asset.get('top',0)
 out[y:y+a.shape[0],x:x+a.shape[1]]=a
 return out
