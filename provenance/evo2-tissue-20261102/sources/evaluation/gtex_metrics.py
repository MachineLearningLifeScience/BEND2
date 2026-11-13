"""Original GTEx rank/weighted-bootstrap kernels, unchanged in this handoff."""
import numpy as np
from scipy.stats import rankdata, spearmanr
from numba import njit

@njit(cache=True)
def wrank(order,starts,counts,group_size):
 n=len(order);rank=np.empty(n,np.float64);before=0.
 for g in range(len(starts)-1):
  lo=starts[g];hi=starts[g+1];amount=0.
  for j in range(lo,hi):amount+=counts[order[j]//group_size]
  value=before+(amount+1.)/2.
  for j in range(lo,hi):rank[order[j]]=value
  before+=amount
 return rank
@njit(cache=True)
def corr_weighted(x,y,counts,T):
 sx=0.;sy=0.;sw=0.
 for i in range(len(x)):
  w=counts[i//T];sx+=w*x[i];sy+=w*y[i];sw+=w
 mx=sx/sw;my=sy/sw;xx=0.;yy=0.;xy=0.
 for i in range(len(x)):
  w=counts[i//T];dx=x[i]-mx;dy=y[i]-my;xx+=w*dx*dx;yy+=w*dy*dy;xy+=w*dx*dy
 if xx<=0 or yy<=0:return np.nan
 return xy/np.sqrt(xx*yy)
def ordering(x):
 x=x.ravel();order=np.argsort(x,kind='stable');sorted_x=x[order];starts=np.r_[0,np.flatnonzero(sorted_x[1:]!=sorted_x[:-1])+1,len(x)].astype(np.int64);return order,starts
def contrast(P,partner):return (np.take_along_axis(P,partner,axis=1)-P).ravel()
def ranks_matrix(orders,counts):
 out=np.column_stack([wrank(ix,starts,counts,1) for ix,starts in orders]);out-=(counts.sum()+1)/2;out*=np.sqrt(counts.astype(np.float64))[:,None];norm=np.linalg.norm(out,axis=0);return out/np.where(norm>0,norm,np.nan),int((norm==0).sum())
def retrieval(P,T):
 C=P.T@T
 if not np.isfinite(C).all():return np.nan
 maxima=C.max(axis=1);wins=np.isclose(C,maxima[:,None],atol=1e-12,rtol=0);return float(np.mean(np.diag(wins)/wins.sum(1)))
def validate():
 rng=np.random.default_rng(42)
 for _ in range(15):
  x=rng.integers(0,8,size=(12,4)).astype(float);y=rng.integers(0,8,size=(12,4)).astype(float);sample=rng.integers(0,12,size=12);counts=np.bincount(sample,minlength=12).astype(np.uint16)
  xr=wrank(*ordering(x),counts,4);yr=wrank(*ordering(y),counts,4)
  np.testing.assert_allclose(corr_weighted(xr,yr,counts,4),spearmanr(x[sample].ravel(),y[sample].ravel()).statistic,atol=1e-12,rtol=0)
  X,_=ranks_matrix([ordering(x[:,j]) for j in range(4)],counts);Y,_=ranks_matrix([ordering(y[:,j]) for j in range(4)],counts)
  xx=rankdata(x[sample],axis=0);yy=rankdata(y[sample],axis=0);xx-=xx.mean(0);yy-=yy.mean(0);expected=(xx/np.linalg.norm(xx,axis=0)).T@(yy/np.linalg.norm(yy,axis=0));np.testing.assert_allclose(X.T@Y,expected,atol=1e-12,rtol=0)
