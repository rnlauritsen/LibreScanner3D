"""Whole-frame structured-light decode (experimental).
usage: decode_frame.py striped.png calib.txt ref30.csv out_prefix
Per band of rows: find stripe peaks, read bead phase per stripe, decode windows of stripes against the
code table with a depth prior (scene between ZMIN and ZMAX), vote per stripe, convert to depth."""
import sys, numpy as np
sys.path.insert(0,'.')
import stripe_decode as sd
from PIL import Image
img_p,cal_p,ref_p,outp=sys.argv[1:5]
T,fx,bproj=sd.load_calib(cal_p); C=fx*bproj
ref={int(l.split(",")[0]):float(l.split(",")[1]) for l in open(ref_p).read().split("\n")[1:] if l}
ZREF=330.0; ZMIN,ZMAX=240.0,480.0
img=np.asarray(Image.open(img_p).convert("L"),dtype=np.float32); H,W=img.shape
f=(-np.arange(6))%3; TS=np.diff(f[T])%3
BAND=64; STEP=4; AMPMIN=6.0; WIN=8; GW=4; ZTOL=12.0
def hp(v,n): return v-np.convolve(v,np.ones(n)/n,'same')
AMP={}
def band_peaks(y0,y1,pitch=12.9):
    prof=img[y0:y1].mean(0); r=hp(prof,41); xs=np.arange(W,dtype=float); w=2*np.pi/pitch
    z=np.convolve(r*np.exp(-1j*w*xs),np.hanning(41)/np.hanning(41).sum(),'same')
    tot=w*xs+np.unwrap(np.angle(z)); n0=int(np.ceil(tot[20]/(2*np.pi))); n1=int(np.floor(tot[-20]/(2*np.pi)))
    cs=[float(np.interp(2*np.pi*n,tot,xs)) for n in range(n0,n1+1)]
    AMP.clear()
    for c in cs: AMP[c]=2*abs(z[int(round(c))])
    return cs
def phases(xs,y0,y1,P):
    ya=max(0,y0-16); yb=min(H,y1+16); ys=np.arange(ya,yb,dtype=float); out=[]
    for c in xs:
        xi=np.arange(int(np.floor(c-4.5)),int(np.ceil(c+4.5))+1); xi=np.clip(xi,0,W-1)
        wg=np.clip(5.0-np.abs(xi-c),0,1)
        s=hp((img[ya:yb][:,xi]*wg).sum(1)/wg.sum(),31)
        m=(ys>=y0)&(ys<y1); e=np.exp(-2j*np.pi*ys[m]/P); z=np.sum(s[m]*e)
        out.append((np.angle(z),abs(z)))
    return out
def best_P(xs,y0,y1):
    best=None
    for P in np.arange(15.8,17.2,0.05):
        a=sum(p[1] for p in phases(xs[::5],y0,y1,P))
        if best is None or a>best[0]: best=(a,P)
    return best[1]
samples=[]  # y, x, row, z, votes
for y0 in range(0,H-BAND+1,STEP):
    y1=y0+BAND; xs=band_peaks(y0,y1)
    if len(xs)<WIN: continue
    P=best_P(xs,y0,y1); ph=phases(xs,y0,y1,P)
    votes={}
    n=len(xs)
    for s in range(0,n-WIN+1):
        idx=list(range(s,s+WIN)); xx=[xs[k] for k in idx]
        if np.any(np.diff(xx)>17.5) or np.any(np.diff(xx)<8.5) or min(AMP[x] for x in xx)<AMPMIN: continue
        pp=np.array([ph[k][0] for k in idx]); amp=np.array([ph[k][1] for k in idx])
        d=(np.diff(pp)+np.pi)%(2*np.pi)-np.pi; six=np.round(d/(np.pi/3)).astype(int)%6
        obs=np.where(six%2==0,six//2,-1); o=np.where(obs[::-1]>=0,(-obs[::-1])%3,-1); mask=o>=0
        if mask.sum()<5: continue
        xr=xx[-1]
        best=[]
        for c in range(0,len(TS)-len(o)+1):
            if c not in ref: continue
            dx=xr-ref[c]                       # shift of the rightmost stripe vs wall reference
            Z=1/(1/ZREF+dx/C) if (1/ZREF+dx/C)>0 else 1e9
            if not (ZMIN<=Z<=ZMAX): continue
            best.append(((TS[c:c+len(o)]==o)[mask].sum(),c))
        if len(best)<2: continue
        best.sort(reverse=True)
        sc,c=best[0]
        if sc==mask.sum() and best[1][0]<=sc-2:
            for pos,k in enumerate(idx):
                j=c+(WIN-1-pos); votes.setdefault((k,j),0); votes[(k,j)]+=1
    # per stripe: keep consistent vote
    per={}
    for (k,j),v in votes.items(): per.setdefault(k,[]).append((v,j))
    assign={}
    for k,lst in per.items():
        lst.sort(reverse=True); v,j=lst[0]
        if len(lst)>1 and lst[1][0]==v: continue
        if j in ref:
            inv=1/ZREF+(xs[k]-ref[j])/C
            if inv>0: assign[k]=(j,1/inv,v,1)
    # guided passes: short windows, candidate depth within +-ZTOL of nearest decoded neighbour
    for it in range(3):
        new={}
        for s0 in range(0,n-GW+1):
            idx=list(range(s0,s0+GW))
            if all(k in assign for k in idx): continue
            xx=[xs[k] for k in idx]
            if np.any(np.diff(xx)>17.5) or np.any(np.diff(xx)<8.5) or min(AMP[x] for x in xx)<AMPMIN: continue
            # prior: nearest decoded stripe within 6 stripes
            near=[(abs(k-s0),k) for k in assign if abs(k-s0)<=6+GW]
            if not near: continue
            kn=min(near)[1]; Zp=assign[kn][1]
            pp=np.array([ph[k][0] for k in idx])
            d=(np.diff(pp)+np.pi)%(2*np.pi)-np.pi; six=np.round(d/(np.pi/3)).astype(int)%6
            obs=np.where(six%2==0,six//2,-1); o=np.where(obs[::-1]>=0,(-obs[::-1])%3,-1); mask=o>=0
            if mask.sum()<GW-1: continue
            xr=xx[-1]; cands=[]
            for c in range(0,len(TS)-len(o)+1):
                if c not in ref: continue
                den=1/ZREF+(xr-ref[c])/C
                if den<=0: continue
                Z=1/den
                if abs(Z-Zp)>ZTOL: continue
                cands.append(((TS[c:c+len(o)]==o)[mask].sum(),c,Z))
            if len(cands)<1: continue
            cands.sort(reverse=True)
            if cands[0][0]==mask.sum() and (len(cands)==1 or cands[1][0]<mask.sum()):
                sc,c,Z=cands[0]
                for pos,k in enumerate(idx):
                    j=c+(GW-1-pos)
                    if k in assign or j not in ref: continue
                    inv=1/ZREF+(xs[k]-ref[j])/C
                    if inv>0: new.setdefault(k,[]).append((j,1/inv))
        added=0
        for k,lst in new.items():
            js=set(j for j,_ in lst)
            if len(js)==1 and k not in assign: assign[k]=(lst[0][0],lst[0][1],1,2+it); added+=1
        if not added: break
    for k,(j,Z,v,ps) in assign.items(): samples.append((y0+BAND/2,xs[k],j,Z,ps))
S=np.array(samples); np.save(outp+"_samples.npy",S)
print("decoded stripe samples:",len(S)); 
if len(S):
    print("Z percentiles 5/50/95: %.0f %.0f %.0f"%tuple(np.percentile(S[:,3],[5,50,95])))
