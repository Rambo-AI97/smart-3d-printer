# usage: python3 tools/gcode_section.py FILE.gcode Zlo Zhi F_axial_N F_side_N z_grip  -> worst layers (stress = F/A + F_side*|z-z_grip|/Z)
# Layer-by-layer section of the real G-code: rasterize extrusions -> solid area, bending modulus.
import sys, re, numpy as np
def layers(path):
    z=None; x=y=0; e=0; w=0.45; rel=False; out={}
    for ln in open(path):
        if ln.startswith(';Z:'): z=round(float(ln[3:]),2); out.setdefault(z,[])
        elif ln.startswith(';WIDTH:'): w=float(ln[7:])
        elif ln.startswith('M83'): rel=True
        elif ln.startswith('M82'): rel=False
        elif ln.startswith('G92') and ' E' in ln: e=float(re.search(r'E(-?[\d.]+)',ln).group(1))
        elif ln.startswith(('G1 ','G0 ','G2 ','G3 ')):
            m=dict((k,float(v)) for k,v in re.findall(r'([XYE])(-?[\d.]+)',ln.split(';')[0]))
            nx=m.get('X',x); ny=m.get('Y',y)
            de=m.get('E',0) if rel else (m['E']-e if 'E' in m else 0)
            if 'E' in m and not rel: e=m['E']
            if de>0 and z is not None and (nx,ny)!=(x,y): out[z].append((x,y,nx,ny,w))
            x,y=nx,ny
    return out
def section(segs, h=0.1):
    a=np.array([s[:4] for s in segs]); W=np.array([s[4] for s in segs])
    x0,y0=a[:,[0,2]].min()-1,a[:,[1,3]].min()-1; x1,y1=a[:,[0,2]].max()+1,a[:,[1,3]].max()+1
    gx=np.arange(x0,x1,h); gy=np.arange(y0,y1,h); g=np.zeros((len(gy),len(gx)),bool)
    for (ax,ay,bx,by),w in zip(a,W):
        i0,i1=np.searchsorted(gx,[min(ax,bx)-w,max(ax,bx)+w]); j0,j1=np.searchsorted(gy,[min(ay,by)-w,max(ay,by)+w])
        X,Y=np.meshgrid(gx[i0:i1],gy[j0:j1]); dx,dy=bx-ax,by-ay; L=dx*dx+dy*dy
        t=np.clip(((X-ax)*dx+(Y-ay)*dy)/L,0,1); d2=(X-ax-t*dx)**2+(Y-ay-t*dy)**2
        g[j0:j1,i0:i1]|=d2<=(w/2)**2
    Y,X=np.nonzero(g); X=gx[X]; Y=gy[Y]; A=len(X)*h*h; cx,cy=X.mean(),Y.mean()
    Iy=((X-cx)**2).sum()*h*h; Ix=((Y-cy)**2).sum()*h*h
    Z=min(Ix/np.abs(Y-cy).max(), Iy/np.abs(X-cx).max())
    return A,Z,np.hypot(X-cx,Y-cy).max()
path=sys.argv[1]; zlo,zhi=float(sys.argv[2]),float(sys.argv[3]); Fax=float(sys.argv[4]); Fs=float(sys.argv[5]); zgrip=float(sys.argv[6]); sgn=float(sys.argv[7]) if len(sys.argv)>7 else 1
L=layers(path); res=[]
for z in sorted(L):
    if zlo<=z<=zhi and L[z]:
        A,Z,r=section(L[z]); M=Fs*abs(z-zgrip); s=Fax/A+M/Z; res.append((s,z,A,Z,r))
for s,z,A,Z,r in sorted(res,reverse=True)[:4]: print(f"z {z:5.1f}  r {r:4.1f}  area {A:6.0f} mm2  Z {Z:6.0f} mm3  stress {s:5.1f} MPa")
