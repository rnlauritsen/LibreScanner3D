"""Robustness test of the tracker: re-track a finished run (its samples/, tracking.npz, angles_deg.csv) using only every Nth frame, i.e. a faster turn.
usage: python3 speedtest.py OUT_DIR CALIB.txt"""
import os, numpy as np, glob, sys
sys.path.insert(0,'.')
import track as T
T.load_camera(sys.argv[2]); rows,xr=T.load_ref(os.path.join(os.path.dirname(os.path.abspath(__file__)),'ref30.csv'))
run=sys.argv[1]
fs=sorted(glob.glob('%s/samples/d_*_samples.npy'%run)); P=[T.sample_points(f,rows,xr) for f in fs]
tk=np.load('%s/tracking.npz'%run); ang=(np.loadtxt('%s/angles_deg.csv'%run))
print("full rate: %.1f deg/frame mean, total %.0f"%(np.diff(ang).mean(),ang[-1]))
for s in (1,2,3,4,5,6):
    Ps=P[::s]; th,tf,q=T.track(Ps,tk['axis'],tk['pivot']); a=np.degrees(th); ref=ang[::s][:len(a)]
    err=np.abs(a-ref); lost=sum(1 for o,r,ok in q if not ok)
    print("every %d: %.1f deg/frame, lost %d/%d, final angle %.0f (true %.0f), max angle error %.1f deg, median %.2f"%(s,np.diff(ref).mean(),lost,len(q),a[-1],ref[-1],err.max(),np.median(err)),flush=True)
