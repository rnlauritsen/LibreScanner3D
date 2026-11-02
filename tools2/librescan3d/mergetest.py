import sys, numpy as np, time
sys.path.insert(0,'.')
import merge as M
from scipy.spatial.transform import Rotation as Rot
from scipy.spatial import cKDTree
X,N=M.read_ply('../../bigfig2_run/points_normals.ply')
rng=np.random.default_rng(1)
sel=rng.choice(len(X),60000,replace=False); X=X[sel];N=N[sel]
c=X.mean(0); u,s,vt=np.linalg.svd(X-c,full_matrices=False); ax=vt[0]; h=(X-c)@ax
lo,hi=np.percentile(h,[0,100])
print("overlap  rot_err_deg  trans_err_mm  within2mm")
for ov in (0.7,0.5,0.35,0.2,0.1):
    # A = lower part, B = upper part; fraction ov of the whole length shared
    cut=lo+(hi-lo)*(0.5-ov/2*0+0.0); a_end=lo+(hi-lo)*(0.5+ov/2); b_start=lo+(hi-lo)*(0.5-ov/2)
    A=X[h<=a_end];NA=N[h<=a_end];mB=h>=b_start;B0=X[mB];NB0=N[mB]
    Rt=Rot.from_euler('xyz',[rng.uniform(40,170),rng.uniform(-60,60),rng.uniform(-60,60)],degrees=True).as_matrix(); tt=rng.uniform(-30,30,3)
    B=(B0-c)@Rt.T+c+tt+rng.normal(0,0.2,B0.shape)
    t0=time.time(); R,t,s_=M.register(A,B,120); R,t=M.icp_plane(B,A,NA,R,t)
    # recovered maps B back onto A; true map is inverse of (x-c)Rt^T+c+tt
    Rinv=Rt.T; tinv=-(Rt.T@(c+tt))+c   # x' = Rinv x + tinv  (since x=(y-c-tt)@Rt ... )
    Bt=B@R.T+t; err=np.linalg.norm(Bt-B0,axis=1); 
    Rrel=R@Rt  # should be identity-ish about center; use point error instead
    d,_=cKDTree(A).query(Bt)
    print("%.2f  point_err_median %.2f mm   within2mm(of A) %.0f%%   (%.0fs)"%(ov,np.median(err),100*(d<2).mean(),time.time()-t0),flush=True)
