#!/usr/bin/env python3
"""EXPERIMENTAL. Writes an oriented-normals point cloud (points_normals.ply, for Poisson in MeshLab/Open3D)
and a rough triangle mesh (implicit surface + marching cubes; not yet good).
usage: python3 mesh.py OUT_DIR [--cloud fused_guided|fused] [--voxel 1.0] [--radius 3.5]
Needs numpy, scipy, scikit-image. Writes OUT_DIR/mesh.obj"""
import argparse, os, numpy as np
from scipy.spatial import cKDTree
ap=argparse.ArgumentParser(); ap.add_argument("out"); ap.add_argument("--cloud",default=None)
ap.add_argument("--voxel",type=float,default=1.0); ap.add_argument("--radius",type=float,default=5.0); ap.add_argument("--crop-radius",type=float,default=120.0,help="keep only points within this distance (mm) of the turning axis (0 = off); needs tracking.npz from run.py")
ap.add_argument("--crop-height",type=float,default=150.0,help="keep only points within this distance (mm) above/below the middle of the points along the axis")
ap.add_argument("--min-density",type=float,default=0.7,help="drop thin streaks: keep points in 2 mm cells holding at least this fraction of the average occupied cell (0 = off)")
ap.add_argument("--no-mesh",action="store_true",help="only write points_normals.ply"); ap.add_argument("--smooth",type=int,default=15,help="Taubin smoothing iterations (0 = off)")
a=ap.parse_args()
name=a.cloud or ("fused_guided" if os.path.exists(os.path.join(a.out,"fused_guided.npz")) else "fused")
d=np.load(os.path.join(a.out,name+".npz")); X,fr,cams=d["X"],d["frame"],d["cams"]
# crop to the object: a cylinder around the turning axis, then drop low-density strays (streaks, turntable edge pieces)
tp=os.path.join(a.out,"tracking.npz")
if a.crop_radius>0 and os.path.exists(tp):
    tk=np.load(tp); ax_,pv_=tk["axis"],tk["pivot"]; dd=X-pv_; hh=dd@ax_; rr=np.linalg.norm(dd-hh[:,None]*ax_,axis=1)
    hh=hh-np.median(hh[rr<a.crop_radius])   # the pivot is only defined up to a shift along the axis, so measure height from the middle of the points
    keep=(rr<a.crop_radius)&(abs(hh)<a.crop_height); X,fr=X[keep],fr[keep]
    n0=len(X)
    if a.min_density>0:
        vx=np.floor(X/2.0).astype(np.int64); _,inv,cnt=np.unique(vx,axis=0,return_inverse=True,return_counts=True); thr=max(3.0,a.min_density*cnt.mean()); keep=cnt[inv.ravel()]>=thr; X,fr=X[keep],fr[keep]
    print("cropped to the figure (radius %.0f mm, height +-%.0f mm, density >= %.0f): %d points kept"%(a.crop_radius,a.crop_height,thr if a.min_density>0 else 0,len(X)))
elif a.crop_radius>0: print("no tracking.npz in",a.out,"- not cropping (run.py writes it)")
# keep the object only (drop far strays), thin out very dense clouds
lo,hi=np.percentile(X,2,axis=0),np.percentile(X,98,axis=0); keep=np.all((X>lo-15)&(X<hi+15),1); X,fr=X[keep],fr[keep]
t=cKDTree(X); _,I=t.query(X,k=30)
N=np.zeros_like(X)
for i,ix in enumerate(I):
    q=X[ix]-X[ix].mean(0); w,v=np.linalg.eigh(q.T@q); n=v[:,0]
    N[i]=n if n@(cams[fr[i]]-X[i])>0 else -n          # orient towards the camera that saw the point
# make orientation consistent: flip a normal if most of its neighbours disagree with it (a few passes)
_,I8=t.query(X,k=10)
for _ in range(4):
    sg=np.sign((N[I8]*N[:,None,:]).sum(-1)); sg[sg==0]=1
    N=np.where((sg.mean(1)<0)[:,None],-N,N)
with open(os.path.join(a.out,"points_normals.ply"),"wb") as f:
    f.write(("ply\nformat binary_little_endian 1.0\nelement vertex %d\nproperty float x\nproperty float y\nproperty float z\nproperty float nx\nproperty float ny\nproperty float nz\nend_header\n"%len(X)).encode())
    f.write(np.c_[X,N].astype('<f4').tobytes())
print("wrote points_normals.ply (%d points, normals oriented towards the cameras)"%len(X))
if a.no_mesh: raise SystemExit
# signed-distance-like field: weighted mean of (q-p).n over nearby points
pad=a.radius+2*a.voxel; mn=X.min(0)-pad; mx=X.max(0)+pad
g=[np.arange(mn[i],mx[i],a.voxel) for i in range(3)]; shape=tuple(len(x) for x in g)
Q=np.stack(np.meshgrid(*g,indexing='ij'),-1).reshape(-1,3)
dist,idx=t.query(Q,k=12,distance_upper_bound=a.radius)
valid=np.isfinite(dist); idx=np.where(valid,idx,0)
w=np.exp(-(np.where(valid,dist,0)/(0.6*a.radius))**2)*valid
sd=((Q[:,None,:]-X[idx])*N[idx]).sum(-1)
F=(w*sd).sum(1)/np.maximum(w.sum(1),1e-9)
mask=(valid.sum(1)>=3).reshape(shape); F=F.reshape(shape)
from skimage.measure import marching_cubes   # only needed for the rough mesh, not for --no-mesh
V,Fc,_,_=marching_cubes(F,0.0,spacing=(a.voxel,)*3,mask=mask)
V=V+mn
# drop tiny floating pieces
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
E=np.r_[Fc[:,[0,1]],Fc[:,[1,2]]]; G=coo_matrix((np.ones(len(E)),(E[:,0],E[:,1])),shape=(len(V),)*2)
nc,lab=connected_components(G,directed=False); sz=np.bincount(lab); big=np.where(sz>=0.05*sz.max())[0]
vk=np.isin(lab,big); remap=-np.ones(len(V),int); remap[vk]=np.arange(vk.sum()); fk=vk[Fc].all(1)
V,Fc=V[vk],remap[Fc[fk]]
if a.smooth:
    # Taubin smoothing (shrink then inflate) so the surface is not flattened
    from scipy.sparse import csr_matrix
    E2=np.r_[Fc[:,[0,1]],Fc[:,[1,2]],Fc[:,[2,0]]]; A=csr_matrix((np.ones(len(E2)),(E2[:,0],E2[:,1])),shape=(len(V),)*2); A=((A+A.T)>0).astype(float)
    deg=np.asarray(A.sum(1)).ravel(); Dinv=1/np.maximum(deg,1)
    for _ in range(a.smooth):
        for lam in (0.5,-0.53):
            V=V+lam*((A@V)*Dinv[:,None]-V)
with open(os.path.join(a.out,"mesh.obj"),"w") as f:
    f.write("# LibreScanner3D mesh, mm\n"); [f.write("v %.3f %.3f %.3f\n"%tuple(v)) for v in V]; [f.write("f %d %d %d\n"%tuple(t+1)) for t in Fc]
print("cloud",name,"| mesh: %d vertices, %d triangles -> mesh.obj"%(len(V),len(Fc)))
