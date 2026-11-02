"""Track a hand-turned base from per-frame depth samples and fuse them into one model.
Assumes: scanner fixed, object on a base that turns about one fixed axis."""
import numpy as np, glob, sys
from scipy.spatial import cKDTree
from scipy.optimize import minimize_scalar

# camera parameters are loaded from the user's own calib.txt (not stored in the repo)
fx=fy=cx=cy=k1=k2=p1=p2=k3=C=None
ZREF=327.5   # reference distance (mm) of the reference frame; device-specific, see README

def load_camera(calib_path):
    global fx,fy,cx,cy,k1,k2,p1,p2,k3,C
    L=open(calib_path).read().split("\n")
    cam=list(map(float,L[4].split())); proj=list(map(float,L[6].split()))
    fx,fy,cx,cy,k1,k2,p1,p2,k3=cam[:9]
    C=fx*proj[12]      # focal length (px) x camera-projector baseline (mm)

def und(x,y):
    xd=(x-cx)/fx; yd=(y-cy)/fy; xu,yu=xd.copy(),yd.copy()
    for _ in range(12):
        r2=xu*xu+yu*yu; rad=1+k1*r2+k2*r2**2+k3*r2**3
        dx=2*p1*xu*yu+p2*(r2+2*xu*xu); dy=p1*(r2+2*yu*yu)+2*p2*xu*yu
        xu=(xd-dx)/rad; yu=(yd-dy)/rad
    return xu,yu

def load_ref(path):
    ref={int(l.split(",")[0]):float(l.split(",")[1]) for l in open(path).read().split("\n")[1:] if l}
    rows=np.array(sorted(ref)); return rows,np.array([ref[r] for r in rows])

def smooth_depth(y,x,z,rxy=9.0,maxdz=1.0):
    """Edge-preserving smoothing across neighbouring image rows and stripes: each sample takes the mean depth of neighbours within rxy pixels whose depth differs < maxdz mm (depth steps are kept)."""
    if len(z)<5: return z
    t=cKDTree(np.c_[x,y]); L=t.query_ball_point(np.c_[x,y],rxy); out=z.copy()
    for i,ix in enumerate(L):
        zz=z[ix]; w=np.abs(zz-z[i])<maxdz; out[i]=zz[w].mean()
    return out

def sample_points(f,rows,xr,zmin=250,zmax=400,dense=False,maxdz=1.5,step=2.5,smooth=False,rowfill=False,step_y=1.3):
    """samples (y,x,row,Z0) -> 3D points (mm, camera frame) of the object (Z below zmax)."""
    S=np.load(f)
    if S.ndim<2 or len(S)<10: return None
    xu,yu=und(S[:,1],S[:,0]); xr_,_=und(np.interp(S[:,2],rows,xr),np.full(len(S),360.0))
    inv=1/ZREF+((xu*fx+cx)-(xr_*fx+cx))/C; Z=1/inv
    m=(Z<zmax)&(Z>zmin)
    if not dense: return np.c_[xu*Z,yu*Z,Z][m]
    # fill in depth BETWEEN neighbouring decoded stripes on the same image row (only where the surface is smooth)
    y=S[:,0][m]; x=S[:,1][m]; z=Z[m]; o=np.lexsort((x,y)); y,x,z=y[o],x[o],z[o]
    if smooth: z=smooth_depth(y,x,z)
    nx=[x]; ny=[y]; nz=[z]
    ok=(y[1:]==y[:-1])&((x[1:]-x[:-1])<=17.5)&((x[1:]-x[:-1])>=8.0)&(abs(z[1:]-z[:-1])<=maxdz)
    for i in np.where(ok)[0]:
        k=int((x[i+1]-x[i])//step)
        if k>=2:
            t=np.arange(1,k)/k; nx.append(x[i]+t*(x[i+1]-x[i])); ny.append(np.full(k-1,y[i])); nz.append(z[i]+t*(z[i+1]-z[i]))
    x=np.concatenate(nx); y=np.concatenate(ny); z=np.concatenate(nz)
    if rowfill:
        # also fill BETWEEN the sampled image rows: pair each point with the nearest point in the next sampled row (same stripe) and add the midpoints
        ys=np.unique(y); gx=[x]; gy=[y]; gz=[z]
        for y0,y1 in zip(ys[:-1],ys[1:]):
            if not (1.5<=y1-y0<=8): continue
            a=np.where(y==y0)[0]; b=np.where(y==y1)[0]
            if len(a)==0 or len(b)==0: continue
            tb=cKDTree(x[b][:,None]); d,j=tb.query(x[a][:,None]); ok=(d<=2.5)&(abs(z[a]-z[b][j])<=maxdz)
            a=a[ok]; j=b[j[ok]]
            for t in np.arange(1,int((y1-y0)//step_y))/max(int((y1-y0)//step_y),1):
                gx.append(x[a]+t*(x[j]-x[a])); gy.append(y[a]+t*(y[j]-y[a])); gz.append(z[a]+t*(z[j]-z[a]))
        x=np.concatenate(gx); y=np.concatenate(gy); z=np.concatenate(gz)
    xu2,yu2=und(x,y); return np.c_[xu2*z,yu2*z,z]

def normals(P,k=8):
    t=cKDTree(P); _,I=t.query(P,k=k); N=np.zeros_like(P)
    for i,ix in enumerate(I):
        q=P[ix]-P[ix].mean(0); w,v=np.linalg.eigh(q.T@q); n=v[:,0]; N[i]=n if n[2]<0 else -n
    return N

def _rotvec(w):
    th=np.linalg.norm(w)
    if th<1e-12: return np.eye(3)
    K=np.array([[0,-w[2],w[1]],[w[2],0,-w[0]],[-w[1],w[0],0]])/th
    return np.eye(3)+np.sin(th)*K+(1-np.cos(th))*K@K

def icp(A,B,NB,it=40,dmax=8.0):
    R=np.eye(3);t=np.zeros(3);T=cKDTree(B)
    for _ in range(it):
        Ap=A@R.T+t; d,i=T.query(Ap); m=d<dmax
        if m.sum()<15: return None,None
        a=Ap[m];b=B[i[m]];n=NB[i[m]]
        J=np.c_[np.cross(a,n),n]; r=((b-a)*n).sum(1)
        x=np.linalg.lstsq(J.T@J+1e-3*np.eye(6),J.T@r,rcond=None)[0]
        dR=_rotvec(x[:3]); R=dR@R; t=dR@t+x[3:]
    return R,t

def axis_of(R):
    w,v=np.linalg.eig(R); a=np.real(v[:,np.argmin(abs(w-1))]); return a/np.linalg.norm(a)

def estimate_axis_steps(P):
    """Robust fallback: per-step ICP (consecutive frames), keep steps with typical angle and a consistent axis, solve the pivot jointly."""
    S=[]
    for k in range(len(P)-1):
        A,B=P[k],P[k+1]
        if A is None or B is None or len(A)<30 or len(B)<30: continue
        R,t=icp(A,B,normals(B))
        if R is None: continue
        ang=np.degrees(np.arccos(np.clip((np.trace(R)-1)/2,-1,1))); a=axis_of(R); S.append((ang,a if a[1]<0 else -a,R,t))
    if len(S)<8: raise RuntimeError("too few frame pairs could be aligned to estimate the turning axis")
    med=np.median([s[0] for s in S]); S=[s for s in S if 0.6*med<s[0]<1.6*med]
    a=np.median([s[1] for s in S],0); a/=np.linalg.norm(a); S=[s for s in S if abs(s[1]@a)>0.97]
    if len(S)<8: raise RuntimeError("too few consistent steps (%d) to estimate the turning axis"%len(S))
    p=np.linalg.lstsq(np.vstack([np.eye(3)-s[2] for s in S]),np.concatenate([s[3] for s in S]),rcond=None)[0]; p=p-(p@a)*a
    if np.linalg.norm(p)>1500 or not (200<p[2]<800): raise RuntimeError("turning-axis estimate is unreliable (pivot %s mm)"%np.round(p,0))
    return a,p

def estimate_axis(P):
    try: return estimate_axis_chain(P)
    except RuntimeError: return estimate_axis_steps(P)

def estimate_axis_chain(P):
    """Frame-to-frame ICP chain, then axis/pivot from the poses once the turn is 10-60 degrees."""
    Cm=np.eye(4); ax=[];pv=[]
    for k in range(len(P)-1):
        A,B=P[k],P[k+1]
        if A is None or B is None or len(A)<30 or len(B)<30: continue
        R,t=icp(A,B,normals(B))
        if R is None: continue
        M=np.eye(4);M[:3,:3]=R;M[:3,3]=t; Cm=Cm@np.linalg.inv(M)
        ang=np.degrees(np.arccos(np.clip((np.trace(Cm[:3,:3])-1)/2,-1,1)))
        if 10<=ang<=60:
            a=axis_of(Cm[:3,:3]); ax.append(a if a[1]<0 else -a)
            pv.append(np.linalg.lstsq(np.eye(3)-Cm[:3,:3],Cm[:3,3],rcond=None)[0])
        if ang>60: break
    if len(ax)<3: raise RuntimeError("could not estimate the turning axis: the object did not turn 10-60 degrees in the first frames")
    a=np.median(ax,0); a/=np.linalg.norm(a); p=np.median(pv,0); p=p-(p@a)*a
    spread=np.degrees(np.arccos(np.clip(np.min([abs(x@a) for x in ax]),-1,1)))
    if np.linalg.norm(p)>1500 or not (200<p[2]<800) or spread>25:
        raise RuntimeError("turning-axis estimate is unreliable (pivot %s mm, axis spread %.0f deg): the object probably did not turn about a fixed axis, or turned too little/too fast in the first frames"%(np.round(p,0),spread))
    return a,p

def track(P,a,p,min_overlap=0.6,max_rms=2.0):
    def rot(th):
        K=np.array([[0,-a[2],a[1]],[a[2],0,-a[0]],[-a[1],a[0],0]]); return np.eye(3)+np.sin(th)*K+(1-np.cos(th))*K@K
    tf=lambda X,th:(X-p)@rot(th).T+p
    first=next(k for k,x in enumerate(P) if x is not None)
    model=[P[first]]; th=[0.0]*(first+1); last=0.0; vel=0.0
    q=[(1.0,0.0,True)]*(first+1)   # per frame: overlap fraction, rms (mm), tracking ok
    # the model is indexed after EVERY accepted frame (normals come from each frame's own points), so that frame k is always
    # compared with frame k-1 even when the turn between frames is large; rebuilding only every 5th frame made fast turns look "lost"
    mnorm=[normals(model[0])]
    def rebuild():
        Mp=np.vstack(model); Mn=np.vstack(mnorm); return Mp,Mn,cKDTree(Mp)
    Mp,Mn,Mt=rebuild()
    for k in range(first+1,len(P)):
        X=P[k]
        if X is None or len(X)<30: th.append(last); q.append((0.0,float('nan'),False)); continue
        def cost(t):
            Y=tf(X,t); d,i=Mt.query(Y); m=d<6
            if m.sum()<20: return 9.0
            r=((Y[m]-Mp[i[m]])*Mn[i[m]]).sum(1); return np.mean(np.minimum(r*r,4.0))+0.5*(1-m.mean())
        # search around where a constant turning speed would put this frame; wider if the previous frames were not tracked well
        pred=last+0.8*vel; span=8.0 if (len(q)<2 or q[-1][2]) else 20.0
        cands=pred+np.radians(np.arange(-span,span+0.01,0.5)); c0=cands[int(np.argmin([cost(c) for c in cands]))]
        t=minimize_scalar(cost,bounds=(c0-np.radians(0.6),c0+np.radians(0.6)),method='bounded').x
        Y=tf(X,t); d,i=Mt.query(Y); m=d<6
        ov=float(m.mean()); rms=float(np.sqrt(np.mean(((Y[m]-Mp[i[m]])*Mn[i[m]]).sum(1)**2))) if m.sum()>=10 else float('nan')
        ok=bool(ov>=min_overlap and rms<=max_rms)
        th.append(t); q.append((ov,rms,ok))
        vel=t-last if ok else 0.0
        last=t                       # the angle prior always follows the frame ...
        if ok:                       # ... but only well-tracked frames are added to the model
            model.append(Y); mnorm.append(normals(Y)); Mp,Mn,Mt=rebuild()
    return np.array(th),tf,q

def write_ply(path,X,N=None):
    with open(path,'wb') as f:
        f.write(("ply\nformat binary_little_endian 1.0\nelement vertex %d\nproperty float x\nproperty float y\nproperty float z\nend_header\n"%len(X)).encode())
        f.write(X.astype('<f4').tobytes())
