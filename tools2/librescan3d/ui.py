#!/usr/bin/env python3
"""LibreScanner3D local web interface.

usage:  python3 ui.py [--port 8765] [--work ~/LibreScan] [--no-browser]

Starts a small web server on this computer only (127.0.0.1) and opens it in your browser. From the page you can
record, run the pipeline (decode, track, crop, merge, mesh), watch the log, look at clouds and meshes in 3D,
see the tracking quality, and compare a result with a reference mesh (for example JMStudio's).
Needs nothing beyond what the pipeline already needs (numpy, scipy, pillow; open3d for the mesh step).
The page talks to this server with a random token that changes at every start; nothing is sent over the internet.
"""
import argparse, json, mimetypes, os, re, secrets, signal, struct, subprocess, sys, threading, time, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "ui_web")
HOME = os.path.expanduser("~")
CONF_DIR = os.path.join(HOME, ".librescan3d")
CONF_FILE = os.path.join(CONF_DIR, "config.json")
TOKEN = secrets.token_urlsafe(16)
FILE_EXT = {".png", ".ply", ".obj", ".csv", ".txt", ".npy", ".npz", ".json", ".log", ".jpg"}

# ---------------------------------------------------------------- config
def load_conf():
    c = {"calib": "", "work": os.path.join(HOME, "LibreScan"), "record_sh": "", "recent": []}
    try: c.update(json.load(open(CONF_FILE)))
    except Exception: pass
    return c

def save_conf(c):
    os.makedirs(CONF_DIR, exist_ok=True)
    json.dump(c, open(CONF_FILE, "w"), indent=1)

CONF = load_conf()

# ---------------------------------------------------------------- files
PROTECTED = {".ssh", ".gnupg", ".aws", "library", "appdata", ".config", ".claude", ".kube", ".docker"}

def safe_path(p):
    """only files below the user's home folder; no credential or system-settings folders (same rule on macOS, Linux and Windows)"""
    p = os.path.realpath(os.path.expanduser(p)); h = os.path.realpath(HOME)
    nc = os.path.normcase
    if not (nc(p) == nc(h) or nc(p).startswith(nc(h) + os.sep)): raise PermissionError("outside the home folder")
    rel = os.path.relpath(p, h).split(os.sep)
    if rel[0].lower() in PROTECTED: raise PermissionError("protected folder")
    return p

def count_frames(d):
    try: return sum(1 for n in os.listdir(d) if re.match(r"f_\d+\.png$", n))
    except Exception: return 0

def browse(path):
    p = safe_path(path or HOME)
    if os.path.isfile(p): p = os.path.dirname(p)
    dirs, files = [], []
    try: names = sorted(os.listdir(p), key=str.lower)
    except Exception as e: raise PermissionError(str(e))
    for n in names:
        if n.startswith("."): continue
        f = os.path.join(p, n)
        if os.path.isdir(f):
            dirs.append({"name": n, "frames": count_frames(f),
                         "result": any(os.path.exists(os.path.join(f, x)) for x in ("points_normals.ply", "poisson_mesh.ply", "fused.ply"))})
        elif os.path.splitext(n)[1].lower() in (".ply", ".obj", ".txt", ".csv"):
            files.append({"name": n, "size": os.path.getsize(f)})
    return {"path": p, "parent": os.path.dirname(p) if os.path.normcase(p) != os.path.normcase(os.path.realpath(HOME)) else None, "dirs": dirs, "files": files, "frames": count_frames(p), "home": HOME}

RESULT_FILES = ["poisson_mesh.ply", "points_normals.ply", "fused_dense.ply", "fused.ply", "fused_guided.ply", "mesh.obj"]

def projects(root):
    out = []; root = safe_path(root)
    if not os.path.isdir(root): return out
    def scan(d, depth):
        try: names = os.listdir(d)
        except Exception: return
        have = [f for f in RESULT_FILES if f in names]
        if have or "quality.csv" in names:
            m = max((os.path.getmtime(os.path.join(d, f)) for f in have + (["quality.csv"] if "quality.csv" in names else [])), default=0)
            out.append({"path": d, "name": os.path.relpath(d, root) if d != root else ".", "files": have, "tracking": "quality.csv" in names, "mtime": m})
        if depth < 2:
            for n in sorted(names):
                f = os.path.join(d, n)
                if os.path.isdir(f) and not n.startswith(".") and n != "samples": scan(f, depth + 1)
    scan(root, 0); out.sort(key=lambda x: -x["mtime"]); return out

# ---------------------------------------------------------------- mesh / cloud reading for the viewer
PLY_T = {"float": "<f4", "float32": "<f4", "double": "<f8", "float64": "<f8", "uchar": "u1", "uint8": "u1", "char": "i1", "int8": "i1",
         "short": "<i2", "int16": "<i2", "ushort": "<u2", "uint16": "<u2", "int": "<i4", "int32": "<i4", "uint": "<u4", "uint32": "<u4"}

def read_ply_full(path):
    raw = open(path, "rb").read(); e = raw.index(b"end_header"); e = raw.index(b"\n", e) + 1
    hdr = raw[:e].decode(errors="ignore").split("\n"); fmt = [l for l in hdr if l.startswith("format")][0].split()[1]
    els = []; cur = None
    for l in hdr:
        w = l.split()
        if not w: continue
        if w[0] == "element": cur = {"name": w[1], "n": int(w[2]), "props": []}; els.append(cur)
        elif w[0] == "property" and cur is not None:
            if w[1] == "list": cur["props"].append(("list", w[2], w[3], w[4]))
            else: cur["props"].append(("s", w[1], w[2]))
    V = N = F = None; off = e
    if fmt == "ascii":
        lines = raw[e:].decode(errors="ignore").split("\n"); li = 0
        for el in els:
            rows = lines[li:li + el["n"]]; li += el["n"]
            if el["name"] == "vertex":
                names = [p[2] for p in el["props"]]; a = np.array([r.split() for r in rows], float)
                V = a[:, [names.index("x"), names.index("y"), names.index("z")]]
                if "nx" in names: N = a[:, [names.index("nx"), names.index("ny"), names.index("nz")]]
            elif el["name"] == "face": F = np.array([[int(x) for x in r.split()[1:4]] for r in rows if r.split() and int(r.split()[0]) == 3])
        return V, N, F
    endian = ">" if "big" in fmt else "<"
    for el in els:
        if all(p[0] == "s" for p in el["props"]):
            dt = np.dtype([(p[2], endian + PLY_T[p[1]][1:]) for p in el["props"]]); b = np.frombuffer(raw, dt, el["n"], off); off += dt.itemsize * el["n"]
            if el["name"] == "vertex":
                V = np.c_[b["x"], b["y"], b["z"]].astype(np.float32)
                if "nx" in b.dtype.names: N = np.c_[b["nx"], b["ny"], b["nz"]].astype(np.float32)
        else:    # list property, e.g. faces: only the common "uchar count + ints" layout of triangles/quads
            p = el["props"][0]; ct = np.dtype(PLY_T[p[1]]); it = np.dtype(endian + PLY_T[p[2]][1:]); faces = []
            if len(el["props"]) == 1:
                for _ in range(el["n"]):
                    c = int(np.frombuffer(raw, ct, 1, off)[0]); off += ct.itemsize
                    idx = np.frombuffer(raw, it, c, off); off += it.itemsize * c
                    for k in range(1, c - 1): faces.append((idx[0], idx[k], idx[k + 1]))
                if el["name"] == "face": F = np.array(faces, np.uint32).reshape(-1, 3)
    return V, N, F

def read_obj(path):
    V = []; F = []
    for l in open(path, errors="ignore"):
        if l.startswith("v "): V.append(l.split()[1:4])
        elif l.startswith("f "):
            idx = [int(w.split("/")[0]) - 1 for w in l.split()[1:]]
            for k in range(1, len(idx) - 1): F.append((idx[0], idx[k], idx[k + 1]))
    return np.array(V, np.float32), None, (np.array(F, np.uint32).reshape(-1, 3) if F else None)

def cloud_bytes(path, maxpts):
    path = safe_path(path); V, N, F = read_obj(path) if path.lower().endswith(".obj") else read_ply_full(path)
    nf = 0 if F is None else len(F)
    if nf == 0 and len(V) > maxpts:
        sel = np.sort(np.random.default_rng(0).choice(len(V), maxpts, replace=False)); V = V[sel]; N = None if N is None else N[sel]
    flags = 1 if N is not None else 0
    out = b"LS3D" + struct.pack("<III", len(V), nf, flags) + V.astype("<f4").tobytes()
    if N is not None: out += N.astype("<f4").tobytes()
    if nf: out += F.astype("<u4").tobytes()
    return out

# ---------------------------------------------------------------- jobs
JOBS = {}; JOB_LOCK = threading.Lock(); JOB_N = [0]

def need(p, kind="path"):
    p = safe_path(p)
    if not os.path.exists(p): raise ValueError("not found: " + p)
    return p

def build_job(kind, a):
    py = [sys.executable, "-u"]
    if kind == "scan":
        recs = [need(r) for r in a["recs"]]
        if not recs: raise ValueError("choose at least one recording folder")
        calib = need(a.get("calib") or CONF.get("calib") or ""); out = safe_path(a["out"])
        cmd = py + [os.path.join(HERE, "scan.py")] + recs + ["--calib", calib, "--out", out, "--step", str(int(a.get("step", 3))),
                                                            "--depth", str(int(a.get("depth", 8))), "--voxel", str(float(a.get("voxel", 0.4))), "--jobs", str(int(a.get("jobs", 4)))]
        if a.get("no_poisson"): cmd.append("--no-poisson")
        return cmd, "Scan " + os.path.basename(recs[0]) + (" + %d more" % (len(recs) - 1) if len(recs) > 1 else "")
    if kind == "merge":
        cmd = py + [os.path.join(HERE, "merge.py"), need(a["a"]), need(a["b"]), safe_path(a["out"])]
        if a.get("fpfh"): cmd.append("--fpfh")
        if a.get("partial"): cmd.append("--partial")
        return cmd, "Merge"
    if kind == "poisson":
        return py + [os.path.join(HERE, "poisson.py"), need(a["dir"]), "--depth", str(int(a.get("depth", 8))), "--voxel", str(float(a.get("voxel", 0.4))),
                     "--trim", str(float(a.get("trim", 0.05))), "--smooth", str(int(a.get("smooth", 10)))], "Mesh (Poisson)"
    if kind == "compare":
        return py + [os.path.join(HERE, "compare.py"), need(a["a"]), need(a["b"])], "Compare"
    if kind == "speedtest":
        return py + [os.path.join(HERE, "speedtest.py"), need(a["dir"]), need(a.get("calib") or CONF.get("calib") or "")], "Speed test"
    if kind == "record":
        sh = a.get("record_sh") or CONF.get("record_sh") or os.path.join(HERE, "record.py")
        if sh.lower().endswith(".py"): return py + [need(sh), safe_path(a["out"])], "Record"
        if os.name == "nt": raise ValueError("record.sh needs bash (macOS/Linux); a cross-platform recorder is planned")
        return ["bash", need(sh), safe_path(a["out"])], "Record"
    raise ValueError("unknown job kind")

def start_job(kind, a):
    cmd, title = build_job(kind, a)
    env = dict(os.environ, PYTHONUNBUFFERED="1")
    with JOB_LOCK:
        JOB_N[0] += 1; jid = str(JOB_N[0])
        j = {"id": jid, "kind": kind, "title": title, "cmd": cmd, "lines": [], "status": "running", "t0": time.time(), "t1": None, "rc": None, "out": a.get("out") or a.get("dir")}
        JOBS[jid] = j
    try:
        extra = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
        j["proc"] = subprocess.Popen(cmd, cwd=HERE, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, encoding="utf-8", errors="replace", **extra)
    except Exception as e:
        j["status"] = "failed"; j["lines"].append("could not start: %s" % e); j["t1"] = time.time(); return j
    def reader():
        for line in j["proc"].stdout:
            j["lines"].append(line.rstrip("\n"))
        j["rc"] = j["proc"].wait(); j["t1"] = time.time()
        if j["status"] != "stopped": j["status"] = "done" if j["rc"] == 0 else "failed"
    threading.Thread(target=reader, daemon=True).start(); return j

def stop_job(jid):
    j = JOBS.get(jid)
    if j and j["status"] == "running":
        j["status"] = "stopped"
        try:
            if os.name == "nt": subprocess.run(["taskkill", "/T", "/F", "/PID", str(j["proc"].pid)], capture_output=True)
            else: os.killpg(os.getpgid(j["proc"].pid), signal.SIGTERM)
        except Exception: pass
    return j

def job_view(j, frm=0):
    return {"id": j["id"], "kind": j["kind"], "title": j["title"], "status": j["status"], "rc": j["rc"], "n": len(j["lines"]), "lines": j["lines"][frm:],
            "t0": j["t0"], "t1": j["t1"], "out": j["out"], "cmd": " ".join(j["cmd"])}

# ---------------------------------------------------------------- tracking / frames
def tracking(d):
    d = safe_path(d); res = {}
    q = os.path.join(d, "quality.csv")
    if os.path.exists(q):
        a = np.loadtxt(q, delimiter=",", skiprows=1, ndmin=2); res.update(overlap=a[:, 1].tolist(), rms=np.nan_to_num(a[:, 2], nan=-1).tolist(), ok=a[:, 3].astype(int).tolist())
    p = os.path.join(d, "angles_deg.csv")
    if os.path.exists(p): res["angles"] = np.atleast_1d(np.loadtxt(p)).tolist()
    tk = os.path.join(d, "tracking.npz")
    if os.path.exists(tk):
        z = np.load(tk); res["axis"] = np.round(z["axis"], 4).tolist(); res["pivot"] = np.round(z["pivot"], 1).tolist()
    return res

def frame_png(d, i, w):
    from PIL import Image
    import io
    d = safe_path(d); names = sorted(n for n in os.listdir(d) if re.match(r"f_\d+\.png$", n))
    if not names: raise FileNotFoundError("no frames")
    im = Image.open(os.path.join(d, names[max(0, min(i, len(names) - 1))])).convert("L")
    if w and w < im.width: im = im.resize((w, int(im.height * w / im.width)))
    b = io.BytesIO(); im.save(b, "PNG"); return b.getvalue()

# ---------------------------------------------------------------- http
class H(BaseHTTPRequestHandler):
    server_version = "LS3D"
    def log_message(self, *a): pass
    def _send(self, code, body, ctype="application/json", extra=None):
        if isinstance(body, (dict, list)): body = json.dumps(body).encode()
        elif isinstance(body, str): body = body.encode()
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body))); self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(body)
    def _host_ok(self):
        h = (self.headers.get("Host") or "").split(":")[0]; return h in ("127.0.0.1", "localhost")
    def _handle(self, method):
        if not self._host_ok(): return self._send(403, {"error": "bad host"})
        u = urlparse(self.path); q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if method == "GET" and u.path in ("/", "/index.html"):
                html = open(os.path.join(WEB, "index.html"), encoding="utf-8").read().replace("__TOKEN__", TOKEN)
                return self._send(200, html, "text/html; charset=utf-8")
            if method == "GET" and u.path.startswith("/static/"):
                f = os.path.realpath(os.path.join(WEB, u.path[8:]))
                if not f.startswith(WEB + os.sep) or not os.path.isfile(f): return self._send(404, {"error": "not found"})
                return self._send(200, open(f, "rb").read(), mimetypes.guess_type(f)[0] or "application/octet-stream")
            if not u.path.startswith("/api/") or q.get("t") != TOKEN: return self._send(403, {"error": "forbidden"})
            body = {}
            if method == "POST":
                n = int(self.headers.get("Content-Length") or 0); body = json.loads(self.rfile.read(n) or b"{}")
            return self._api(u.path[5:], q, body)
        except PermissionError as e: return self._send(403, {"error": str(e)})
        except (ValueError, FileNotFoundError, KeyError) as e: return self._send(400, {"error": str(e) if not isinstance(e, KeyError) else "missing " + str(e)})
        except Exception as e:
            import traceback; traceback.print_exc(); return self._send(500, {"error": "%s: %s" % (type(e).__name__, e)})
    def do_GET(self): self._handle("GET")
    def do_POST(self): self._handle("POST")
    def _api(self, ep, q, body):
        global CONF
        if ep == "quit":
            self._send(200, {"ok": True}); threading.Thread(target=lambda: (time.sleep(0.3), os._exit(0)), daemon=True).start(); return
        if ep == "state": return self._send(200, {"conf": CONF, "home": HOME, "os": sys.platform, "python": sys.executable, "here": HERE})
        if ep == "config":
            for k in ("calib", "work", "record_sh"):
                if k in body: CONF[k] = os.path.expanduser(body[k])
            save_conf(CONF); return self._send(200, {"conf": CONF})
        if ep == "browse": return self._send(200, browse(q.get("path", "")))
        if ep == "mkdir":
            p = safe_path(body["path"]); os.makedirs(p, exist_ok=True); return self._send(200, {"path": p})
        if ep == "projects": return self._send(200, projects(q.get("root") or CONF["work"]))
        if ep == "cloud": return self._send(200, cloud_bytes(q["path"], int(q.get("max", 400000))), "application/octet-stream")
        if ep == "tracking": return self._send(200, tracking(q["dir"]))
        if ep == "frames": d = safe_path(q["dir"]); return self._send(200, {"n": count_frames(d)})
        if ep == "frame": return self._send(200, frame_png(q["dir"], int(q.get("i", 0)), int(q.get("w", 640))), "image/png")
        if ep == "file":
            p = safe_path(q["path"])
            if os.path.splitext(p)[1].lower() not in FILE_EXT: raise PermissionError("file type not served")
            return self._send(200, open(p, "rb").read(), mimetypes.guess_type(p)[0] or "application/octet-stream")
        if ep == "run": j = start_job(body["kind"], body); return self._send(200, job_view(j))
        if ep == "job":
            j = JOBS.get(q.get("id"));
            if not j: raise ValueError("no such job")
            return self._send(200, job_view(j, int(q.get("from", 0))))
        if ep == "jobs": return self._send(200, [{k: j[k] for k in ("id", "title", "status", "t0", "t1", "out")} for j in JOBS.values()][::-1])
        if ep == "stop": return self._send(200, job_view(stop_job(q["id"])))
        raise ValueError("unknown endpoint " + ep)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, default=8765); ap.add_argument("--work", default=None)
    ap.add_argument("--browser", action="store_true", help="open in the web browser instead of an own window")
    ap.add_argument("--no-browser", action="store_true", help="do not open anything (server only)"); a = ap.parse_args()
    if a.work: CONF["work"] = os.path.expanduser(a.work)
    srv = None
    for port in range(a.port, a.port + 20):
        try: srv = ThreadingHTTPServer(("127.0.0.1", port), H); break
        except OSError: continue
    if srv is None: raise SystemExit("no free port")
    url = "http://127.0.0.1:%d/" % srv.server_address[1]
    print("LibreScanner3D interface: " + url + "   (stop with Ctrl-C)", flush=True)
    def cleanup():
        for j in JOBS.values(): stop_job(j["id"])
    if not a.no_browser and not a.browser:
        try:
            import webview  # pywebview: native window (WKWebView on macOS, WebView2 on Windows, GTK/Qt WebKit on Linux)
        except Exception:
            webview = None; print("pywebview not installed: opening in the browser instead (pip install pywebview for an own window)")
        if webview:
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            webview.create_window("LibreScanner3D", url, width=1360, height=860, min_size=(900, 600))
            try: webview.start()
            finally: cleanup()
            return
    if not a.no_browser: threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try: srv.serve_forever()
    except KeyboardInterrupt: print("bye")
    finally: cleanup()

if __name__ == "__main__":
    main()
