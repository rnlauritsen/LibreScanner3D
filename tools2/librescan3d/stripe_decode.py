#!/usr/bin/env python3
"""
stripe_decode.py - identify the projected stripes in a 3DMakerpro Fox striped frame.

Reads ONLY your own files: a striped greyscale frame (PNG) and your own calib.txt.
It finds the ~95 vertical stripes, reads each stripe's bead phase (one of three levels),
and matches the sequence of phase steps against the 246-row code table in calib.txt
(a de Bruijn style sequence), which tells you which projector stripe each one is.

Usage:
  python3 stripe_decode.py frame.png calib.txt                       # identify stripes
  python3 stripe_decode.py frame.png calib.txt --csv out.csv         # also save row,x
  python3 stripe_decode.py frame.png calib.txt --ref ref.csv --ref-z 330   # depth vs a reference frame
Options: --rows R0 R1  (image rows to use, default 20 700; use rows with a flat surface, no edges)
Needs: numpy, pillow.   (pip install numpy pillow)
Status: experimental. Tested on 1280x720 frames of a flat wall at ~20-40 cm.
"""
import sys, argparse, itertools
import numpy as np
from PIL import Image

def load_calib(path):
    L = open(path).read().split("\n")
    i = L.index("246")
    rows = [tuple(map(int, l.split())) for l in L[i + 1:i + 247]]
    master = (1, 3, 2, 4, 1, 2)
    rot = [tuple(master[(s + j) % 6] for j in range(6)) for s in range(6)]
    T = np.array([rot.index(x) for x in rows])
    blk = [list(map(float, L[k].split())) for k in (4, 5, 6)]
    return T, blk[0][0], blk[2][12]          # code table, camera fx, projector offset (mm)

def hp(v, n):
    return v - np.convolve(v, np.ones(n) / n, 'same')

def find_stripes(img, r0, r1):
    reg = img[r0:r1, :]
    r = hp(reg.mean(0), 41)
    N = len(r) - 120
    sp = np.abs(np.fft.rfft(r[60:-60] * np.hanning(N)))
    k = int(np.argmax(sp[20:200])) + 20
    a, b, c = np.log(sp[k - 1]), np.log(sp[k]), np.log(sp[k + 1])
    pitch = N / (k + 0.5 * (a - c) / (a - 2 * b + c))
    xs = np.arange(len(r), dtype=np.float64)
    w = 2 * np.pi / pitch
    z = np.convolve(r * np.exp(-1j * w * xs), np.hanning(121) / np.hanning(121).sum(), 'same')
    tot = w * xs + np.unwrap(np.angle(z))
    n0 = int(np.ceil(tot[60] / (2 * np.pi))); n1 = int(np.floor(tot[-60] / (2 * np.pi)))
    cs = np.array([float(np.interp(2 * np.pi * n, tot, xs)) for n in range(n0, n1 + 1)])
    ys = np.arange(reg.shape[0], dtype=np.float64)
    def sig(c):
        xi = np.arange(int(np.floor(c - 4.5)), int(np.ceil(c + 4.5)) + 1)
        wg = np.clip(5.0 - np.abs(xi - c), 0, 1)
        return hp((reg[:, xi] * wg).sum(1) / wg.sum(), 31)[15:-15]
    y = ys[15:-15]
    best = None
    for P in np.arange(15.5, 17.5, 0.02):                       # bead period along the stripe
        e = np.exp(-2j * np.pi * y / P)
        amp = sum(abs(np.sum(sig(c) * e)) for c in cs[::4])
        if best is None or amp > best[0]: best = (amp, P)
    P = best[1]; e = np.exp(-2j * np.pi * y / P)
    ph = np.array([np.angle(np.sum(sig(c) * e)) for c in cs])
    return cs, ph, pitch, P

def identify(ph, T):
    d = (np.diff(ph) + np.pi) % (2 * np.pi) - np.pi
    six = np.round(d / (np.pi / 3)).astype(int) % 6
    obs = np.where(six % 2 == 0, six // 2, -1)                  # step in Z3, -1 = unreadable
    best = None
    for direction in ("reversed", "forward"):
        for sgn in (-1, 1):
            f = (sgn * np.arange(6)) % 3
            TS = np.diff(f[T]) % 3
            o = obs[::-1] if direction == "reversed" else obs
            if direction == "reversed": o = np.where(o >= 0, (-o) % 3, -1)
            mask = o >= 0
            sc = np.array([(TS[k:k + len(o)] == o)[mask].sum() for k in range(len(TS) - len(o) + 1)])
            idx = np.argsort(sc)[::-1]
            cand = (int(sc[idx[0]]), int(mask.sum()), int(idx[0]), int(sc[idx[1]]), direction)
            if best is None or cand[0] > best[0]: best = cand
    return best

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image"); ap.add_argument("calib")
    ap.add_argument("--rows", nargs=2, type=int, default=[20, 700])
    ap.add_argument("--csv"); ap.add_argument("--ref"); ap.add_argument("--ref-z", type=float)
    a = ap.parse_args()
    T, fx, b = load_calib(a.calib)
    img = np.asarray(Image.open(a.image).convert("L"), dtype=np.float32)
    cs, ph, pitch, P = find_stripes(img, *a.rows)
    score, known, off, second, direction = identify(ph, T)
    n = len(cs)
    print("stripes %d | pitch %.2f px | bead period %.2f px" % (n, pitch, P))
    print("match: %d of %d readable steps (runner-up offset scores %d) | order: %s | first table row %d"
          % (score, known, second, direction, off))
    if score < 0.8 * known or score - second < 0.25 * known:
        print("WARNING: weak match - frame may be plain (no stripes), too dark/saturated, or contain edges.")
    rowid = [off + (n - 1 - k) if direction == "reversed" else off + k for k in range(n)]
    if a.csv:
        with open(a.csv, "w") as fh:
            fh.write("table_row,x_px\n")
            for r_, x_ in zip(rowid, cs): fh.write("%d,%.2f\n" % (r_, x_))
        print("wrote", a.csv)
    if a.ref:
        ref = {int(l.split(",")[0]): float(l.split(",")[1]) for l in open(a.ref).read().split("\n")[1:] if l}
        c = fx * b                                              # px*mm  (camera focal x projector offset)
        zs = []
        for r_, x_ in zip(rowid, cs):
            if r_ in ref:
                inv = 1.0 / a.ref_z + (x_ - ref[r_]) / c
                if inv > 0: zs.append(1.0 / inv)
        zs = np.array(zs)
        print("depth vs reference plane at %.0f mm (camera optical-centre distance): %d stripes, median %.0f mm, spread %.0f mm"
              % (a.ref_z, len(zs), np.median(zs), zs.std()))
if __name__ == "__main__":
    main()
