"""Compare a scan with a reference mesh/cloud (for example JMStudio's .obj or .ply of the same object).

usage: python3 compare.py SCAN.ply REFERENCE.(ply|obj)
The reference is moved onto the scan (global rotation search + point-to-plane refinement; both mirrored and plain
JMStudio coordinates are tried), cropped to the region the scan covers, and the distances are reported both ways:
  scan -> reference : how accurate the points of the scan are
  reference -> scan : how much of the reference surface the scan covers
Writes reference_aligned.ply next to the scan so both can be looked at together."""
import os, sys, numpy as np
from scipy.spatial import cKDTree
import merge as M, ui

def load(p):
    V, N, F = ui.read_obj(p) if p.lower().endswith(".obj") else ui.read_ply_full(p)
    return np.asarray(V, float), None if N is None else np.asarray(N, float)

def stats(name, d):
    print("RESULT %-18s median %.2f mm | within 1 mm %.0f%% | within 2 mm %.0f%% | within 4 mm %.0f%%" % (name, np.median(d), 100 * (d < 1).mean(), 100 * (d < 2).mean(), 100 * (d < 4).mean()), flush=True)

def main():
    if len(sys.argv) < 3: raise SystemExit(__doc__)
    A, NA = load(sys.argv[1]); B, NB = load(sys.argv[2])
    print("scan: %d points, reference: %d points" % (len(A), len(B)), flush=True)
    if NA is None:
        from scipy.spatial import cKDTree as KD
        NA = np.zeros_like(A); _, I = KD(A).query(A, k=8)
        for i, ix in enumerate(I):
            q = A[ix] - A[ix].mean(0); w, v = np.linalg.eigh(q.T @ q); NA[i] = v[:, 0]
    best = None
    for flip in (np.array([1., 1, 1]), np.array([-1., -1, 1])):
        R, t, s = M.register(A, B * flip, 120)
        d, _ = cKDTree(A).query((B * flip)[::10] @ R.T + t)
        print("  start %s: median %.2f mm" % ("mirrored (JMStudio)" if flip[0] < 0 else "plain", np.median(d)), flush=True)
        if best is None or np.median(d) < best[0]: best = (np.median(d), flip, R, t)
    _, flip, R, t = best
    Bf = B * flip
    R, t = M.icp_plane(Bf, A, NA, R, t, it=25); Bt = Bf @ R.T + t
    lo, hi = A.min(0) - 8, A.max(0) + 8; Bc = Bt[((Bt > lo) & (Bt < hi)).all(1)]
    print("reference cropped to the scanned region: %d of %d points" % (len(Bc), len(Bt)), flush=True)
    d1, _ = cKDTree(Bc).query(A); d2, _ = cKDTree(A).query(Bc)
    stats("scan -> reference", d1); stats("reference -> scan", d2)
    print("extent scan %s mm, reference %s mm" % (np.round(np.ptp(A, 0)), np.round(np.ptp(Bc, 0))))
    out = os.path.join(os.path.dirname(os.path.abspath(sys.argv[1])), "reference_aligned.ply")
    M.write_ply(out, Bc, np.tile([0., 0, -1], (len(Bc), 1))); print("wrote", out)

if __name__ == "__main__":
    main()
