"""Classify a frame as STRIPED (projector pattern visible) or plain. usage: python3 chk_stripes.py frame.png (exit 0 = striped)"""
import sys, numpy as np
from PIL import Image

def check(path, verbose=True):
    a=np.asarray(Image.open(path).convert("L"),dtype=np.float32)
    H,W=a.shape; best=0.0; nt=0
    for y in range(0,H-60,30):
        for x in range(0,W-200,100):
            t=a[y:y+60,x:x+200]
            if t.mean()<10: continue
            r=t.mean(0); r=r-np.convolve(r,np.ones(31)/31,'same'); r=r[20:-20]; r=r*np.hanning(len(r))
            sp=np.abs(np.fft.rfft(r,512))**2; fr=np.fft.rfftfreq(512,1.0)
            inb=(fr>1/13.4)&(fr<1/11.8); tot=sp[(fr>1/50)&(fr<1/4)].sum()+1e-9
            ratio=sp[inb].sum()/tot; best=max(best,ratio)
            if ratio>0.3: nt+=1
    ok=nt>=3
    if verbose: print("mean %.1f  saturated %.1f%%  stripe-tiles %d (best %.2f) -> %s"%(a.mean(),100*(a>=250).mean(),nt,best,"STRIPED" if ok else "plain"))
    return ok

if __name__=="__main__": sys.exit(0 if check(sys.argv[1]) else 1)
