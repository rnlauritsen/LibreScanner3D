"""Pose refinement experiment: starting from the fixed-axis tracking, let every frame correct its pose in all six degrees of freedom
against all the other frames (point-to-plane ICP, small steps only), a few passes. Reports how well the frames agree before/after."""
import os, numpy as np, glob, sys, time
from scipy.spatial import cKDTree
import track as T

def rotvec(w):
    th=np.linalg.norm(w)
    if th<1e-12: return np.eye(3)
    k=w/th; K=np.array([[0,-k[2],k[1]],[k[2],0,-k[0]],[-k[1],k[0],0]]); return np.eye(3)+np.sin(th)*K+(1-np.cos(th))*K@K

def world_points(P,th,ax,pv):
    def rot(t):
        K=np.array([[0,-ax[2],ax[1]],[ax[2],0,-ax[0]],[-ax[1],ax[0],0]]); return np.eye(3)+np.sin(t)*K+(1-np.cos(t))*K@K
    return [None if p is None else (p-pv)@rot(t).T+pv for p,t in zip(P,th)]

def residuals(W):
    """median point-to-point distance of each frame to the nearest point of any OTHER frame (frames close in turn angle excluded by label only)"""
    allp=np.vstack([w for w in W if w is not None]); lab=np.concatenate([np.full(len(w),k) for k,w in enumerate(W) if w is not None])
    tr=cKDTree(allp); out={}
    for k,w in enumerate(W):
        if w is None: continue
        d,i=tr.query(w,k=8); ok=lab[i]!=k; dd=np.where(ok,d,np.inf).min(1); dd=dd[np.isfinite(dd)]
        out[k]=np.median(dd) if len(dd)>20 else np.nan
    return out

def refine(W,passes=3,maxrot=np.radians(1.5),maxtr=2.0,minpts=40):
    W=[None if w is None else w.copy() for w in W]; poses=[(np.eye(3),np.zeros(3)) for _ in W]
    for p in range(passes):
        allp=np.vstack([w for w in W if w is not None]); lab=np.concatenate([np.full(len(w),k) for k,w in enumerate(W) if w is not None])
        N=T.normals(allp,k=10); tr=cKDTree(allp)
        for k,w in enumerate(W):
            if w is None: continue
            R=np.eye(3); t=np.zeros(3)
            for it in range(8):
                x=w@R.T+t; d,i=tr.query(x,k=6); ok=(lab[i]!=k)&(d<3.0)
                first=np.argmax(ok,1); has=ok.any(1)
                if has.sum()<minpts: break
                idx=i[np.arange(len(x)),first][has]; a=x[has]; b=allp[idx]; n=N[idx]
                r=((b-a)*n).sum(1); keep=np.abs(r)<np.quantile(np.abs(r),0.8); a,n,r=a[keep],n[keep],r[keep]
                J=np.c_[np.cross(a,n),n]; s=np.linalg.lstsq(J.T@J+1e-2*np.eye(6),J.T@r,rcond=None)[0]
                dR=rotvec(s[:3]); R=dR@R; t=dR@t+s[3:]
            ang=np.linalg.norm(np.linalg.lstsq(np.eye(3),np.array([R[2,1]-R[1,2],R[0,2]-R[2,0],R[1,0]-R[0,1]])/2,rcond=None)[0])
            if ang>maxrot or np.linalg.norm(t)>maxtr: continue          # refuse big jumps: keep the fixed-axis pose
            W[k]=w@R.T+t; poses[k]=(R@poses[k][0],R@poses[k][1]+t)
    return W,poses

if __name__=="__main__":
    run=sys.argv[1]; calib='/root/.claude/uploads/b724fa22-1a23-595b-ad62-1994bc7e8bb3/35f6e8c1-calib.txt'
    T.load_camera(calib); rows,xr=T.load_ref(os.path.join(os.path.dirname(os.path.abspath(__file__)),'ref30.csv'))
    fs=sorted(glob.glob('../../%s/samples/d_*_samples.npy'%run)); P=[T.sample_points(f,rows,xr) for f in fs]
    tk=np.load('../../%s/tracking.npz'%run); ang=np.radians(np.loadtxt('../../%s/angles_deg.csv'%run))
    W=world_points(P,ang,tk['axis'],tk['pivot'])
    r0=residuals(W); print("before: median frame-to-frame residual %.3f mm (mean of per-frame medians), 90th pct %.3f"%(np.nanmean(list(r0.values())),np.nanpercentile(list(r0.values()),90)))
    t0=time.time(); W2,poses=refine(W); r1=residuals(W2)
    print("after : median frame-to-frame residual %.3f mm, 90th pct %.3f   (%.0fs)"%(np.nanmean(list(r1.values())),np.nanpercentile(list(r1.values()),90),time.time()-t0))
    rots=[np.degrees(np.arccos(np.clip((np.trace(R)-1)/2,-1,1))) for R,t in poses]; trs=[np.linalg.norm(t) for R,t in poses]
    print("corrections: median %.2f deg / %.2f mm, max %.2f deg / %.2f mm"%(np.median(rots),np.median(trs),max(rots),max(trs)))
    np.savez('../../%s/refined_poses.npz'%run,R=np.array([p[0] for p in poses]),t=np.array([p[1] for p in poses]))
