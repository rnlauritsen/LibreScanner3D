"""Model-guided decoding: predict each stripe's depth from the fused model, pick the table row that fits.
Only fills in surfaces the model already has from other views; it cannot discover new geometry."""
import numpy as np
from PIL import Image
from scipy import ndimage
import track as T
def plyload(p):
    L=open(p,'rb').read(); i=L.index(b'end_header')+len(b'end_header\n'); return np.frombuffer(L[i:],'<f4').reshape(-1,3).astype(float)
def fwd_distort(xu,yu):
    r2=xu*xu+yu*yu; rad=1+T.k1*r2+T.k2*r2**2+T.k3*r2**3
    xd=xu*rad+2*T.p1*xu*yu+T.p2*(r2+2*xu*xu); yd=yu*rad+T.p1*(r2+2*yu*yu)+2*T.p2*xu*yu
    return T.fx*xd+T.cx,T.fy*yd+T.cy
def pred_depth(M,theta,a,p,W=1280,H=720):
    K=np.array([[0,-a[2],a[1]],[a[2],0,-a[0]],[-a[1],a[0],0]]); R=np.eye(3)+np.sin(theta)*K+(1-np.cos(theta))*K@K
    X=(M-p)@R+p            # frame0 -> frame k (inverse of tf)
    u,v=fwd_distort(X[:,0]/X[:,2],X[:,1]/X[:,2]); D=np.full((H,W),np.inf)
    iu=np.round(u).astype(int); iv=np.round(v).astype(int); ok=(iu>=0)&(iu<W)&(iv>=0)&(iv<H)
    np.minimum.at(D,(iv[ok],iu[ok]),X[ok,2]); D[np.isinf(D)]=np.nan
    m=~np.isnan(D); idx=ndimage.distance_transform_edt(~m,return_distances=True,return_indices=True)
    dist,(ii,jj)=idx; Df=D[ii,jj]; Df[dist>7]=np.nan; return Df
def run(img_path,Dp,rows,xr,band=64,step=4,tol=1.5,ampmin=6.0):
    img=np.asarray(Image.open(img_path).convert('L'),dtype=np.float32); H,W=img.shape
    xru=np.array([T.und(np.array([x]),np.array([360.0]))[0][0]*T.fx+T.cx for x in xr]).ravel()
    def hp(v,n): return v-np.convolve(v,np.ones(n)/n,'same')
    out=[]
    for y0 in range(0,H-band+1,step):
        prof=img[y0:y0+band].mean(0); r=hp(prof,41); xs=np.arange(W,dtype=float); w=2*np.pi/12.9
        z=np.convolve(r*np.exp(-1j*w*xs),np.hanning(41)/np.hanning(41).sum(),'same')
        tot=w*xs+np.unwrap(np.angle(z)); n0=int(np.ceil(tot[20]/(2*np.pi))); n1=int(np.floor(tot[-20]/(2*np.pi)))
        for n in range(n0,n1+1):
            c=float(np.interp(2*np.pi*n,tot,xs)); amp=2*abs(z[int(round(c))])
            if amp<ampmin: continue
            yc=y0+band//2; pr=Dp[yc,int(round(c))]
            if np.isnan(pr): continue
            xu,_=T.und(np.array([c]),np.array([float(yc)])); xuu=xu[0]*T.fx+T.cx
            inv=1/T.ZREF+(xuu-xru)/T.C; Zc=np.where(inv>0,1/np.where(inv>0,inv,1),np.inf)
            j=int(np.argmin(abs(Zc-pr)))
            if abs(Zc[j]-pr)<=tol: out.append((yc,c,rows[j],Zc[j]))
    return np.array(out)
