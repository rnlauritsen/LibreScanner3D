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
th,tf=T.track(P,ax,pv); print("total turn %.0f deg (max angle %.0f)"%(np.degrees(th[-1]),np.degrees(np.abs(th).max())))
X=np.vstack([tf(p,th[k]) for k,p in enumerate(P) if p is not None])
T.write_ply(os.path.join(a.out,"fused.ply"),X); np.savetxt(os.path.join(a.out,"angles_deg.csv"),np.degrees(th),fmt="%.2f")
print("wrote",os.path.join(a.out,"fused.ply"),len(X),"points")
