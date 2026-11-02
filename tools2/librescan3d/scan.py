#!/usr/bin/env python3
"""LibreScanner3D, whole pipeline in one command: striped frames -> tracked cloud -> crop -> (merge) -> Poisson mesh.

usage: python3 scan.py REC1 [REC2 [REC3 ...]] --calib CALIB.txt --out OUT_DIR [--depth 8] [--voxel 0.4]
Each REC is a folder of f_0001.png ... (one turntable recording). Give several recordings of the same object in
different poses (upright, tilted, on its side) and they are merged into one model before meshing.
Writes OUT_DIR/poisson_mesh.ply (plus OUT_DIR/scan_N/ with every intermediate result)."""
import argparse, os, subprocess, sys
here=os.path.dirname(os.path.abspath(__file__))
ap=argparse.ArgumentParser(); ap.add_argument("rec",nargs="+"); ap.add_argument("--calib",required=True); ap.add_argument("--out",required=True)
ap.add_argument("--step",type=int,default=3,help="use every Nth frame (3 for 10 fps recordings)"); ap.add_argument("--jobs",type=int,default=4)
ap.add_argument("--depth",type=int,default=8); ap.add_argument("--voxel",type=float,default=0.4,help="Poisson thinning (mm); with several scans 0.8 is safer")
ap.add_argument("--no-poisson",action="store_true",help="stop after the cloud (points_normals.ply)")
a=ap.parse_args(); os.makedirs(a.out,exist_ok=True)
py=sys.executable
def sh(*cmd):
    print("\n$"," ".join(cmd),flush=True)
    if subprocess.run(cmd,cwd=here).returncode: raise SystemExit("step failed: "+" ".join(cmd[:3]))
outs=[]
for i,r in enumerate(a.rec,1):
    o=os.path.abspath(os.path.join(a.out,"scan_%d"%i)); outs.append(o)
    if not os.path.exists(os.path.join(o,"points_normals.ply")):
        sh(py,"run.py",os.path.abspath(r),os.path.abspath(a.calib),o,"--step",str(a.step),"--axis-step","3" if a.step<=3 else "1","--jobs",str(a.jobs),"--dense")
        sh(py,"mesh.py",o,"--cloud","fused_dense","--voxel","0.4","--radius","3","--no-mesh")
final=outs[0]
if len(outs)>1:
    final=os.path.abspath(os.path.join(a.out,"merged")); cur=outs[0]
    for i,o in enumerate(outs[1:],1):
        dst=final if i==len(outs)-1 else os.path.abspath(os.path.join(a.out,"merged_%d"%i))
        sh(py,"merge.py",cur,o,dst); cur=dst
    final=cur
if not a.no_poisson: sh(py,"poisson.py",final,"--depth",str(a.depth),"--voxel",str(a.voxel if len(outs)==1 else max(a.voxel,0.8)),"--trim","0.05")
mesh=os.path.join(final,"poisson_mesh.ply")
if os.path.exists(mesh):
    import shutil; shutil.copy(mesh,os.path.join(a.out,"poisson_mesh.ply")); print("\nDone: "+os.path.join(a.out,"poisson_mesh.ply"))
else: print("\nDone: "+os.path.join(final,"points_normals.ply"))
