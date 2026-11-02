"""Self-checks that need no scanner, no real data and no extra packages (numpy + scipy only).
Run:  python3 -m unittest discover -s tests -v      (from the repository's tools2 folder)"""
import os, sys, json, struct, tempfile, threading, unittest, urllib.request, urllib.error
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(os.path.dirname(HERE), "librescan3d")
sys.path.insert(0, PKG)

def bumpy_object(n=9000, seed=0):
    """Asymmetric closed surface (a bumpy cylinder) around the vertical axis, in millimetres."""
    r = np.random.default_rng(seed); th = r.uniform(0, 2 * np.pi, n); y = r.uniform(-30, 30, n)
    rad = 40 + 10 * np.sin(3 * th) + 8 * np.sin(y / 9 + 2 * th) + 5 * np.cos(5 * th + y / 7)
    return np.c_[rad * np.cos(th), y, rad * np.sin(th)]

class Ply(unittest.TestCase):
    def test_roundtrip(self):
        import merge as M
        X = np.random.default_rng(1).normal(size=(500, 3)) * 20; N = np.random.default_rng(2).normal(size=(500, 3)); N /= np.linalg.norm(N, axis=1, keepdims=True)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.ply"); M.write_ply(p, X, N); X2, N2 = M.read_ply(p)
        self.assertLess(np.abs(X - X2).max(), 1e-3); self.assertLess(np.abs(N - N2).max(), 1e-5)

class Merge(unittest.TestCase):
    def test_two_poses_with_half_overlap(self):
        import merge as M
        from scipy.spatial.transform import Rotation as Rot
        import track; X = bumpy_object(6000); N = track.normals(X)
        A = X[X[:, 1] <= 18]; NA = N[X[:, 1] <= 18]; mB = X[:, 1] >= -18; B0 = X[mB]   # the two poses share 60% of the surface
        Rt = Rot.from_euler("xyz", [70, 20, -35], degrees=True).as_matrix(); tt = np.array([5., -8, 12])
        B = B0 @ Rt.T + tt + np.random.default_rng(3).normal(0, 0.15, B0.shape)
        R, t, _ = M.register(A, B, 150); R, t = M.icp_plane(B, A, NA, R, t)
        err = np.linalg.norm(B @ R.T + t - B0, axis=1)
        self.assertLess(np.median(err), 1.0, "median error %.2f mm" % np.median(err))

class Tracker(unittest.TestCase):
    def test_recovers_turntable_angles(self):
        import track
        X = bumpy_object(5000); a = np.array([0., -1, 0]); p = np.array([0., 0, 0]); true = np.radians(np.arange(0, 180, 3.0))
        frames = []
        for ph in true:
            c, s = np.cos(ph), np.sin(ph); R = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]]); Y = X @ R.T
            Y = Y[Y[:, 2] < 5] + np.array([0, 0, 350.0]); frames.append(Y + np.random.default_rng(len(frames)).normal(0, 0.1, Y.shape))
        pivot = np.array([0., 0, 350.0]); th, tf, q = track.track(frames, a, pivot)
        sign = np.sign(np.median(th[1:] / true[1:])); err = np.degrees(np.abs(th - sign * true))
        self.assertLess(err.max(), 1.0, "worst angle error %.2f deg" % err.max()); self.assertTrue(all(x[2] for x in q), "a frame was reported lost")

class Uvc(unittest.TestCase):
    def test_descriptor_and_requests(self):
        import uvc
        def intf(n, cls, sub): return bytes([9, 4, n, 0, 1, cls, sub, 0, 0])
        cfg = bytes([9, 2, 0, 0, 2, 1, 0, 0x80, 50]) + intf(0, 0x0E, 1) + bytes([18, 0x24, 2, 1]) + struct.pack("<H", 0x0201) + bytes(2) + bytes(6) + bytes([3, 0, 0, 0])
        cfg += bytes([13, 0x24, 5, 3, 1, 0, 0, 2, 0, 0, 0, 0, 0]) + intf(1, 0x0E, 2) + bytes([13, 0x24, 5, 9, 1, 0, 0, 2, 0, 0, 0, 0, 0])
        ids = uvc.parse_config(cfg); self.assertEqual(ids, {"vc": 0, "ct": 1, "pu": 3})
        self.assertEqual(uvc.request_args("set", uvc.SET_CUR, "exposure-time-abs", ids), (0x21, 1, 0x0400, 0x0100, 4))
        self.assertEqual(uvc.request_args("get", uvc.GET_CUR, "gain", ids), (0xA1, 0x81, 0x0400, 0x0300, 2))
        self.assertIsNone(uvc.parse_config(bytes([9, 2, 0, 0, 1, 1, 0, 0x80, 50]) + intf(0, 3, 1)))

class Exe(unittest.TestCase):
    def test_pycmd(self):
        import _exe
        c = _exe.pycmd("merge.py", "a", 3); self.assertEqual(c[0], sys.executable); self.assertTrue(c[-3].endswith("merge.py")); self.assertEqual(c[-2:], ["a", "3"])

class UiSecurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp(); os.makedirs(os.path.join(cls.home, ".ssh")); os.environ["HOME"] = cls.home; os.environ["USERPROFILE"] = cls.home
        import importlib, ui; importlib.reload(ui); cls.ui = ui
        cls.srv = ui.ThreadingHTTPServer(("127.0.0.1", 0), ui.H); cls.port = cls.srv.server_address[1]; threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
    @classmethod
    def tearDownClass(cls): cls.srv.shutdown()
    def get(self, path, host=None):
        r = urllib.request.Request("http://127.0.0.1:%d%s" % (self.port, path), headers={"Host": host} if host else {})
        try: return urllib.request.urlopen(r).status
        except urllib.error.HTTPError as e: return e.code
    def test_safe_path(self):
        ui = self.ui
        with self.assertRaises(PermissionError): ui.safe_path("/etc/passwd")
        with self.assertRaises(PermissionError): ui.safe_path(os.path.join(self.home, ".ssh", "id_rsa"))
        with self.assertRaises(PermissionError): ui.safe_path(self.home + "_evil")
        self.assertTrue(ui.safe_path(os.path.join(self.home, "x")).startswith(os.path.realpath(self.home)))
    def test_token_and_host(self):
        self.assertEqual(self.get("/"), 200)
        self.assertEqual(self.get("/api/state"), 403)
        self.assertEqual(self.get("/api/state?t=wrong"), 403)
        self.assertEqual(self.get("/api/state?t=" + self.ui.TOKEN), 200)
        self.assertEqual(self.get("/", host="evil.example.com"), 403)
        self.assertEqual(self.get("/static/../ui.py"), 404)

if __name__ == "__main__": unittest.main()
