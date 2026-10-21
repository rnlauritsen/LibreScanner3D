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

def sample_points(f,rows,xr,zmin=250,zmax=400):
    """samples (y,x,row,Z0) -> 3D points (mm, camera frame) of the object (Z below zmax)."""
    S=np.load(f)
    if S.ndim<2 or len(S)<10: return None
    xu,yu=und(S[:,1],S[:,0]); xr_,_=und(np.interp(S[:,2],rows,xr),np.full(len(S),360.0))
    inv=1/ZREF+((xu*fx+cx)-(xr_*fx+cx))/C; Z=1/inv
    m=(Z<zmax)&(Z>zmin)
    return np.c_[xu*Z,yu*Z,Z][m]

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

def estimate_axis(P):
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
    return a,p

def track(P,a,p):
    def rot(th):
        K=np.array([[0,-a[2],a[1]],[a[2],0,-a[0]],[-a[1],a[0],0]]); return np.eye(3)+np.sin(th)*K+(1-np.cos(th))*K@K
    tf=lambda X,th:(X-p)@rot(th).T+p
    first=next(k for k,x in enumerate(P) if x is not None)
    model=[P[first]]; th=[0.0]*(first+1); last=0.0
    def rebuild():
        Mp=np.vstack(model); Mn=normals(Mp); return Mp,Mn,cKDTree(Mp)
    Mp,Mn,Mt=rebuild()
    for k in range(first+1,len(P)):
        X=P[k]
        if X is None or len(X)<30: th.append(last); continue
        def cost(t):
            Y=tf(X,t); d,i=Mt.query(Y); m=d<6
            if m.sum()<20: return 9.0
            r=((Y[m]-Mp[i[m]])*Mn[i[m]]).sum(1); return np.mean(np.minimum(r*r,4.0))+0.5*(1-m.mean())
        cands=last+np.radians(np.arange(-8,8.01,0.5)); c0=cands[int(np.argmin([cost(c) for c in cands]))]
        t=minimize_scalar(cost,bounds=(c0-np.radians(0.6),c0+np.radians(0.6)),method='bounded').x
        th.append(t); last=t; model.append(tf(X,t))
        if k%5==0: Mp,Mn,Mt=rebuild()
    return np.array(th),tf

def write_ply(path,X,N=None):
    with open(path,'wb') as f:
        f.write(("ply\nformat binary_little_endian 1.0\nelement vertex %d\nproperty float x\nproperty float y\nproperty float z\nend_header\n"%len(X)).encode())
        f.write(X.astype('<f4').tobytes())
