#!/usr/bin/env python3
"""LibreScanner3D pipeline: raw striped frames -> depth -> tracked, fused point cloud (PLY).

usage: python3 run.py FRAMES_DIR CALIB.txt OUT_DIR [--step 3] [--jobs 4]
FRAMES_DIR holds f_0001.png, f_0002.png ... (striped frames, gray, 1280x720).
"""
import argparse, glob, os, subprocess, sys
import numpy as np
from concurrent.futures import ThreadPoolExecutor
import track as T
here=os.path.dirname(os.path.abspath(__file__))
ap=argparse.ArgumentParser(); ap.add_argument("frames"); ap.add_argument("calib"); ap.add_argument("out")
ap.add_argument("--guided",action="store_true",help="second pass: model-guided decoding (denser, needs the fused model)")
ap.add_argument("--step",type=int,default=3,help="use every Nth frame"); ap.add_argument("--jobs",type=int,default=4)
a=ap.parse_args(); a.frames,a.calib,a.out=[os.path.abspath(x) for x in (a.frames,a.calib,a.out)]; os.makedirs(a.out,exist_ok=True); dec=os.path.join(a.out,"samples"); os.makedirs(dec,exist_ok=True)
frames=sorted(glob.glob(os.path.join(a.frames,"f_*.png")))[::a.step]
print(len(frames),"frames to decode")
def run(f):
    pre=os.path.join(dec,"d_"+os.path.basename(f)[2:6])
    if not os.path.exists(pre+"_samples.npy"):
        subprocess.run([sys.executable,"-I",os.path.join(here,"decode_frame.py"),f,a.calib,os.path.join(here,"ref30.csv"),pre],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,cwd=here)
with ThreadPoolExecutor(a.jobs) as ex: list(ex.map(run,frames))
T.load_camera(a.calib)
rows,xr=T.load_ref(os.path.join(here,"ref30.csv"))
fs=sorted(glob.glob(os.path.join(dec,"d_*_samples.npy"))); P=[T.sample_points(f,rows,xr) for f in fs]
print("object points per frame (median):",int(np.median([0 if p is None else len(p) for p in P])))
ax,pv=T.estimate_axis(P); print("turning axis",np.round(ax,3),"pivot",np.round(pv,1))
th,tf,q=T.track(P,ax,pv); print("total turn %.0f deg (max angle %.0f)"%(np.degrees(th[-1]),np.degrees(np.abs(th).max())))
np.savetxt(os.path.join(a.out,"quality.csv"),np.array([(k,o,r,int(ok)) for k,(o,r,ok) in enumerate(q)]),fmt=["%d","%.3f","%.3f","%d"],header="frame_index,overlap,rms_mm,tracking_ok",delimiter=",")
lost=[k for k,(o,r,ok) in enumerate(q) if not ok]
print("tracking quality: %d of %d frames flagged LOST (overlap<0.6 or rms>2.0 mm)"%(len(lost),len(q)),lost[:40])
X=np.vstack([tf(p,th[k]) for k,p in enumerate(P) if p is not None and q[k][2]])
T.write_ply(os.path.join(a.out,"fused.ply"),X); np.savetxt(os.path.join(a.out,"angles_deg.csv"),np.degrees(th),fmt="%.2f")
print("wrote",os.path.join(a.out,"fused.ply"),len(X),"points")

if a.guided:
    import guided as G
    from scipy.spatial import cKDTree
    M=G.plyload(os.path.join(a.out,"fused.ply")); ok_frames=[k for k,(o,r_,ok) in enumerate(q)]
    names=sorted(glob.glob(os.path.join(a.frames,"f_*.png")))[::a.step]
    def rot(t):
        K=np.array([[0,-ax[2],ax[1]],[ax[2],0,-ax[0]],[-ax[1],ax[0],0]]); return np.eye(3)+np.sin(t)*K+(1-np.cos(t))*K@K
    out=[]
    for k,f in enumerate(names[:len(q)]):
        if not q[k][2]: continue
        S=G.run(f,G.pred_depth(M,th[k],ax,pv),rows,xr)
        if len(S)<10: continue
        xu,yu=T.und(S[:,1],S[:,0]); Z=S[:,3]; X=np.c_[xu*Z,yu*Z,Z]
        out.append((X-pv)@rot(th[k]).T+pv)
    Fg=np.vstack(out)
    # drop isolated points (fewer than 3 neighbours within 2 mm)
    cnt=np.array([len(x) for x in cKDTree(Fg).query_ball_point(Fg,2.0)]); Fg=Fg[cnt>=4]
    T.write_ply(os.path.join(a.out,"fused_guided.ply"),Fg); print("guided: wrote fused_guided.ply",len(Fg),"points")
