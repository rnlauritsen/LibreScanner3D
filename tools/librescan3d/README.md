# librescan3d (prototype)

Raw striped frames from the Fox scanner -> depth -> tracked, fused point cloud (PLY).
Independent of JMStudio; uses your own `calib.txt`.

## Install (macOS, Apple Silicon)
    python3 -m pip install numpy scipy pillow

## Run
    python3 run.py FRAMES_DIR /path/to/calib.txt OUT_DIR [--step 3] [--jobs 4]

* FRAMES_DIR: `f_0001.png, f_0002.png ...` striped frames recorded with the capture script (exposure 25, gain 0).
* OUT_DIR gets `samples/` (per-frame depth), `fused.ply`, `angles_deg.csv`.
* About 8 minutes for 300 frames at --step 3 on the test machine. Decoding is the slow part and is cached in `samples/`.

## Assumptions (what it will NOT handle yet)
* Scanner fixed; object on a base turned by hand around ONE fixed axis. The object must turn 10-60 degrees in the first ~30 frames so the axis can be estimated.
* Object closer than 40 cm, background further than about 45 cm (it separates them by depth).
* Distances use a reference frame (`ref30.csv`) and a reference distance of 327.5 mm fitted for one scanner. Absolute depth may be off by a few mm elsewhere.
* Sparse: a few hundred points per frame on the object. Thin parts seen edge-on are mostly missing.
* Not a mesh. PLY points only.

## Status
Tested on one scene: fused model within 0.73 mm (median) of JMStudio's scan of the same figure; about two thirds of JMStudio's surface covered.

## Privacy
Do not commit your `calib.txt`, serial numbers or scan recordings to a public repo.
