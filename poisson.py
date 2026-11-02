#!/usr/bin/env python3
"""Poisson surface from points_normals.ply using Open3D, trimming surface invented over gaps.
usage: python3 poisson.py [OUT_DIR] [--depth 8] [--trim 0.08]
Without OUT_DIR it uses the folder this script is in (put points_normals.ply next to it); the result is written there too.
Needs: python3 -m pip install open3d   (Open3D may not support the newest Python versions; use 3.9-3.12)
Writes OUT_DIR/poisson_mesh.ply.  NOTE: written without being able to run it on the author's machine - report problems."""
import argparse, os, subprocess, sys, time, numpy as np
ap=argparse.ArgumentParser(); ap.add_argument("out",nargs="?",default=os.path.dirname(os.path.abspath(__file__))); ap.add_argument("--depth",type=int,default=8)
ap.add_argument("--min-piece",type=float,default=0.05,help="drop connected pieces smaller than this fraction of the largest piece (0 = keep all)")
ap.add_argument("--min-neighbors",type=int,default=15,help="drop points with fewer than this many neighbours within 2 mm (removes streaks and strays; 0 = off)")
ap.add_argument("--smooth",type=int,default=10,help="Taubin smoothing iterations on the finished mesh (removes the stripe ripple without shrinking; 0 = off)")
ap.add_argument("--child",action="store_true",help=argparse.SUPPRESS)
ap.add_argument("--voxel",type=float,default=0.7,help="thin the points to one per voxel (mm) before Poisson; 0 = off")
ap.add_argument("--trim",type=float,default=0.08,help="remove the least-supported fraction of the surface (0 = keep all)")
a=ap.parse_args()
if not os.path.exists(os.path.join(a.out,"points_normals.ply")): raise SystemExit("points_normals.ply not found in "+a.out)

def components(Tr,nv):
    """connected-component label per triangle (numpy/scipy only; no Open3D mesh editing)"""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    E=np.r_[Tr[:,[0,1]],Tr[:,[1,2]]]; G=coo_matrix((np.ones(len(E)),(E[:,0],E[:,1])),shape=(nv,nv))
    _,lab=connected_components(G,directed=False); return lab[Tr[:,0]]
def finish(V,Tr,dens,trim,min_piece):
    if trim>0:                                    # drop the least-supported part of the surface (invented over gaps)
        keep=dens>=np.quantile(dens,trim); Tr=Tr[keep[Tr].all(1)]
    if min_piece>0 and len(Tr):                   # drop small floating pieces
        lab=components(Tr,len(V)); sz=np.bincount(lab); big=sz>=min_piece*sz.max()
        print("pieces: %d, dropped %d small ones"%(int((sz>0).sum()),int(((~big)&(sz>0)).sum())),flush=True); Tr=Tr[big[lab]]
    A=np.cross(V[Tr[:,1]]-V[Tr[:,0]],V[Tr[:,2]]-V[Tr[:,0]]); Tr=Tr[np.linalg.norm(A,axis=1)>1e-9]   # degenerate triangles
    used=np.unique(Tr); remap=-np.ones(len(V),int); remap[used]=np.arange(len(used)); return V[used],remap[Tr]
def taubin(V,Tr,it,lam=0.5,mu=-0.53):
    """shrink-free Laplacian smoothing (numpy/scipy only); vertices on open borders are kept fixed so edges do not creep"""
    from scipy.sparse import coo_matrix
    n=len(V); E=np.r_[Tr[:,[0,1]],Tr[:,[1,2]],Tr[:,[2,0]]]; E=np.r_[E,E[:,::-1]]
    W=coo_matrix((np.ones(len(E)),(E[:,0],E[:,1])),shape=(n,n)).tocsr(); W.data[:]=1.0
    deg=np.asarray(W.sum(1)).ravel(); deg[deg==0]=1
    Eb=np.sort(np.r_[Tr[:,[0,1]],Tr[:,[1,2]],Tr[:,[2,0]]],axis=1); u,c=np.unique(Eb,axis=0,return_counts=True); bd=np.zeros(n,bool); bd[u[c==1].ravel()]=True
    V=V.copy()
    for _ in range(it):
        for f in (lam,mu):
            L=(W@V)/deg[:,None]-V; L[bd]=0; V=V+f*L
    return V
def write_mesh(path,V,Tr):
    A=np.cross(V[Tr[:,1]]-V[Tr[:,0]],V[Tr[:,2]]-V[Tr[:,0]]); N=np.zeros_like(V)
    for k in range(3): np.add.at(N,Tr[:,k],A)
    N/=np.maximum(np.linalg.norm(N,axis=1,keepdims=True),1e-12)
    vd=np.dtype([("p","<f4",3),("n","<f4",3)]); v=np.empty(len(V),vd); v["p"]=V; v["n"]=N
    fd=np.dtype([("c","u1"),("i","<i4",3)]); f=np.empty(len(Tr),fd); f["c"]=3; f["i"]=Tr
    with open(path,"wb") as fh:
        fh.write(("ply\nformat binary_little_endian 1.0\nelement vertex %d\nproperty float x\nproperty float y\nproperty float z\nproperty float nx\nproperty float ny\nproperty float nz\nelement face %d\nproperty list uchar int vertex_indices\nend_header\n"%(len(V),len(Tr))).encode())
        fh.write(v.tobytes()); fh.write(f.tobytes())
if not a.child:
    # Open3D's Poisson can abort the whole process ("Failed to close loop"), so run it in a child process and retry coarser
    t0=time.time(); outf=os.path.join(a.out,"poisson_mesh.ply")
    for d,vx in ((a.depth,a.voxel),(a.depth,a.voxel*1.5),(a.depth-1,a.voxel),(a.depth-1,a.voxel*1.5),(a.depth-2,a.voxel*1.5),(a.depth-2,a.voxel*2.2)):   # keep the detail level (depth) as long as possible
        cmd=[sys.executable,os.path.abspath(__file__),a.out,"--depth",str(d),"--trim",str(a.trim),"--min-piece",str(a.min_piece),"--voxel",str(round(vx,2)),"--min-neighbors",str(a.min_neighbors),"--smooth",str(a.smooth),"--child"]
        rc=subprocess.run(cmd).returncode
        if rc==0 and os.path.exists(outf) and os.path.getmtime(outf)>=t0: raise SystemExit(0)   # success only if a new file was written
        print("depth %d / thinning %.2f mm failed, trying coarser settings"%(d,vx),flush=True)
    raise SystemExit("Poisson failed at all depths tried")
import open3d as o3d
pcd=o3d.io.read_point_cloud(os.path.join(a.out,"points_normals.ply"))
print("points:",len(pcd.points),"has normals:",pcd.has_normals())
# sanitise: drop points/normals that are not finite or not unit length ("bad data" makes Poisson fail), renormalise
Pn=np.asarray(pcd.points); Nn=np.asarray(pcd.normals); ln=np.linalg.norm(Nn,axis=1)
good=np.isfinite(Pn).all(1)&np.isfinite(Nn).all(1)&(ln>0.5)
print("dropped %d points with bad coordinates/normals"%(~good).sum())
pcd=pcd.select_by_index(np.where(good)[0]); pcd.normals=o3d.utility.Vector3dVector(np.asarray(pcd.normals)/np.linalg.norm(np.asarray(pcd.normals),axis=1)[:,None])
# remove thin streaks and isolated bits: a real surface point has plenty of neighbours within 2 mm
if a.min_neighbors>0: pcd,_=pcd.remove_radius_outlier(nb_points=a.min_neighbors,radius=2.0)
print("after removing streaks/isolated points:",len(pcd.points))
pcd,_=pcd.remove_statistical_outlier(nb_neighbors=20,std_ratio=2.0)
print("after outlier removal:",len(pcd.points))
if a.voxel>0:
    pcd=pcd.voxel_down_sample(a.voxel); print("after thinning:",len(pcd.points))
print("running Poisson, depth",a.depth,flush=True)
mesh,dens=o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(pcd,depth=a.depth)
V=np.asarray(mesh.vertices).copy(); Tr=np.asarray(mesh.triangles).copy(); dens=np.asarray(dens).copy()
print("Poisson done: %d vertices"%len(V),flush=True)
print("trimming / cleaning",flush=True)
V,Tr=finish(V,Tr,dens,a.trim,a.min_piece)
if a.smooth>0: V=taubin(V,Tr,a.smooth); print("smoothed (%d Taubin iterations)"%a.smooth,flush=True)
outf=os.path.join(a.out,"poisson_mesh.ply"); write_mesh(outf,V,Tr)
print("wrote poisson_mesh.ply: %d vertices, %d triangles"%(len(V),len(Tr)))
