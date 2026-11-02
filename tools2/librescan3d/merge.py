"""Merge two scans of the same object in different poses (e.g. upright + lying down) into one cloud.

usage: python3 merge.py scanA_folder scanB_folder out_folder
Each folder needs points_normals.ply (from mesh.py --no-mesh). B is moved onto A with a global search over
rotations followed by trimmed ICP; the merged points_normals.ply goes to out_folder (mesh it with poisson.py).
"""
import sys, os, argparse, numpy as np
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation as Rot

def read_ply(p):
    L = open(p, 'rb').read(); i = L.index(b'end_header') + len(b'end_header\n'); h = L[:i].decode(errors='ignore')
    n = int([l for l in h.split('\n') if l.startswith('element vertex')][0].split()[-1])
    pr = [l.split() for l in h.split('\n') if l.startswith('property')]
    m = {'float': '<f4', 'double': '<f8', 'uchar': 'u1', 'int': '<i4', 'float32': '<f4'}
    b = np.frombuffer(L[i:], np.dtype([(q[2], m[q[1]]) for q in pr]), n)
    X = np.c_[b['x'], b['y'], b['z']].astype(float)
    N = np.c_[b['nx'], b['ny'], b['nz']].astype(float) if 'nx' in b.dtype.names else None
    return X, N

def write_ply(p, X, N):
    X = X.astype('<f4'); N = N.astype('<f4')
    h = "ply\nformat binary_little_endian 1.0\nelement vertex %d\nproperty float x\nproperty float y\nproperty float z\nproperty float nx\nproperty float ny\nproperty float nz\nend_header\n" % len(X)
    with open(p, 'wb') as f:
        f.write(h.encode()); f.write(np.hstack([X, N]).astype('<f4').tobytes())

def rigid(A, B, w=None):
    ca, cb = A.mean(0), B.mean(0); U, S, Vt = np.linalg.svd((A - ca).T @ (B - cb))
    D = np.diag([1, 1, np.sign(np.linalg.det(Vt.T @ U.T))]); R = Vt.T @ D @ U.T; return R, cb - R @ ca

def icp(A, tB, B, R, t, it, keep=0.6):
    for _ in range(it):
        d, i = tB.query(A @ R.T + t); m = d <= np.quantile(d, keep)
        R, t = rigid(A[m], B[i[m]])
    d, _ = tB.query(A @ R.T + t); return R, t, np.mean(np.minimum(d, 10) ** 2) if keep >= 1 else np.median(d)

def icp_plane(B, A, NA, R, t, it=20, keep=0.8):
    """point-to-plane refinement (as in FoxStudio/ScanRuler): minimise the distance along the target normals; better on smooth surfaces"""
    tA = cKDTree(A)
    for _ in range(it):
        Bp = B @ R.T + t; d, i = tA.query(Bp); m = d <= np.quantile(d, keep)
        a = Bp[m]; b = A[i[m]]; n = NA[i[m]]
        J = np.c_[np.cross(a, n), n]; r = ((b - a) * n).sum(1)
        x = np.linalg.lstsq(J.T @ J + 1e-6 * np.eye(6), J.T @ r, rcond=None)[0]
        w = x[:3]; th = np.linalg.norm(w)
        if th > 1e-12:
            k = w / th; K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]]); dR = np.eye(3) + np.sin(th) * K + (1 - np.cos(th)) * K @ K
        else: dR = np.eye(3)
        R = dR @ R; t = dR @ t + x[3:]
    return R, t

def register(A, B, nstart=400, seed=0, partial=False):
    """Move B onto A. Global search over random rotations, coarse -> fine."""
    rng = np.random.default_rng(seed)
    As = A[rng.choice(len(A), min(len(A), 4000), replace=False)]; Bs = B[rng.choice(len(B), min(len(B), 4000), replace=False)]
    tA = cKDTree(As); cands = []
    # start translations: the two centroids, and (for scans that share only part of their surface) each of a few
    # regions of A paired with the centroid of B, so the first guess does not need the whole objects to overlap
    from scipy.cluster.vq import kmeans2
    centres = [As.mean(0)]
    if partial:
        _, lab = kmeans2(As[:3000], 6, minit='++', seed=seed); centres += [As[:3000][lab == k].mean(0) for k in range(6) if (lab == k).any()]
    Bq = Bs[:1500]; Aq = As[:1500]; tAq = cKDTree(Aq)
    for r in Rot.random(nstart, random_state=seed):
        R0 = r.as_matrix()
        for c in centres:
            t0 = c - R0 @ Bs.mean(0)
            R, t, s = icp(Bq, tAq, Aq, R0, t0, 10, keep=0.5); cands.append((s, R, t))
    cands.sort(key=lambda c: c[0]); best = None
    A2 = A[rng.choice(len(A), min(len(A), 30000), replace=False)]; B2 = B[rng.choice(len(B), min(len(B), 30000), replace=False)]; tA2 = cKDTree(A2)
    for s0, R, t in cands[:12]:
        R, t, s = icp(B2, tA2, A2, R, t, 40, keep=0.6)
        if best is None or s < best[0]: best = (s, R, t)
    s, R, t = best
    R, t, s = icp(B, cKDTree(A), A, R, t, 25, keep=0.7)
    return R, t, s

def register_fpfh(A, NA, B, NB, voxel=1.5):
    """Global alignment from local surface features (FPFH + RANSAC, as in FoxStudio); needs Open3D. Works when the two scans share only part of their surface.
    UNTESTED by the author (Open3D is not available where this was written): if it fails, merge.py falls back to the normal search."""
    import open3d as o3d
    def prep(X, N):
        p = o3d.geometry.PointCloud(); p.points = o3d.utility.Vector3dVector(X); p.normals = o3d.utility.Vector3dVector(N)
        p = p.voxel_down_sample(voxel)
        f = o3d.pipelines.registration.compute_fpfh_feature(p, o3d.geometry.KDTreeSearchParamHybrid(radius=voxel * 5, max_nn=100)); return p, f
    pa, fa = prep(A, NA); pb, fb = prep(B, NB); dist = voxel * 1.5
    r = o3d.pipelines.registration.registration_ransac_based_on_feature_matching(
        pb, pa, fb, fa, True, dist, o3d.pipelines.registration.TransformationEstimationPointToPoint(False), 3,
        [o3d.pipelines.registration.CorrespondenceCheckerBasedOnEdgeLength(0.9), o3d.pipelines.registration.CorrespondenceCheckerBasedOnDistance(dist)],
        o3d.pipelines.registration.RANSACConvergenceCriteria(200000, 0.999))
    T = np.asarray(r.transformation); print("FPFH/RANSAC: fitness %.2f, inlier rmse %.2f mm" % (r.fitness, r.inlier_rmse))
    return T[:3, :3], T[:3, 3]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("a"); ap.add_argument("b"); ap.add_argument("out")
    ap.add_argument("--starts", type=int, default=400)
    ap.add_argument("--fpfh", action="store_true", help="use Open3D feature matching (FPFH+RANSAC) for the first alignment; for scans that share only a small part of their surface")
    ap.add_argument("--partial", action="store_true", help="the two scans share only a small part of their surface (below ~50%%): search more starting positions (slower)")
    a = ap.parse_args()
    A, NA = read_ply(os.path.join(a.a, "points_normals.ply")); B, NB = read_ply(os.path.join(a.b, "points_normals.ply"))
    print("scan A %d points, scan B %d points" % (len(A), len(B)))
    R = None
    if a.fpfh:
        try: R, t = register_fpfh(A, NA, B, NB); R, t, _ = icp(B, cKDTree(A), A, R, t, 30, keep=0.7)
        except Exception as e: print("FPFH alignment not available (%s); using the normal search" % e); R = None
    if R is None: R, t, s = register(A, B, a.starts, partial=a.partial)
    dA0, _ = cKDTree(A).query(B @ R.T + t)
    R, t = icp_plane(B, A, NA, R, t)
    print("point-to-plane refinement: median %.2f -> %.2f mm" % (np.median(dA0), np.median(cKDTree(A).query(B @ R.T + t)[0])))
    Bt = B @ R.T + t; NBt = NB @ R.T
    dA, _ = cKDTree(A).query(Bt); dB, _ = cKDTree(Bt).query(A)
    print("B -> A: median %.2f mm, within 1 mm %.0f%%, within 2 mm %.0f%%" % (np.median(dA), 100 * (dA < 1).mean(), 100 * (dA < 2).mean()))
    ov=(dA<2).mean()
    if ov<0.5: print("WARNING: only %.0f%% of scan B lies within 2 mm of scan A. The overlap between the two poses is probably too small or the alignment found a wrong match; the merged cloud will then show doubled surfaces. Use --starts 1500, or record the second pose so it shares more surface with the first." % (100*ov))
    print("rotation of B: %.0f deg" % np.degrees(np.arccos(np.clip((np.trace(R) - 1) / 2, -1, 1))))
    os.makedirs(a.out, exist_ok=True)
    X = np.vstack([A, Bt]); N = np.vstack([NA, NBt])
    write_ply(os.path.join(a.out, "points_normals.ply"), X, N); np.savez(os.path.join(a.out, "merge_pose.npz"), R=R, t=t)
    print("wrote %s (%d points)" % (os.path.join(a.out, "points_normals.ply"), len(X)))

if __name__ == "__main__":
    main()
