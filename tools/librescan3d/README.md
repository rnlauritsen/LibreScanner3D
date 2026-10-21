# librescan3d (prototype)

Raw striped frames from the Fox scanner -> depth -> tracked, fused point cloud (PLY).
Independent of JMStudio; uses your own `calib.txt`.

## Install (macOS, Apple Silicon)
    python3 -m pip install numpy scipy pillow

## Run
    python3 run.py FRAMES_DIR /path/to/calib.txt OUT_DIR [--step 3] [--jobs 4]

* FRAMES_DIR: `f_0001.png, f_0002.png ...` striped frames recorded with the capture script (exposure 25, gain 0).
* OUT_DIR gets `samples/` (per-frame depth), `fused.ply`, `angles_deg.csv` and `quality.csv`.
* `quality.csv` has one row per frame: overlap with the model so far, leftover error (mm) and `tracking_ok`. Frames flagged lost (overlap < 0.6 or error > 2 mm) are not added to the model; the run prints which ones. If the turning axis cannot be estimated reliably, the run stops with an error instead of producing a bad model.
* About 8 minutes for 300 frames at --step 3 on the test machine. Decoding is the slow part and is cached in `samples/`.

## Optional: --guided
`--guided` adds a second pass that predicts each stripe's depth from the fused model and decodes with that hint, writing `fused_guided.ply`. On the test scene it gave about 3x the points and raised the share of the vendor scan's surface covered to within 2 mm from 57% to 70%, but its points are a little less accurate (median distance to the vendor scan 1.2 mm instead of 0.9 mm). It only fills in surfaces the model already has; it cannot find new geometry.

## Meshing (experimental)
`python3 mesh.py OUT_DIR --no-mesh` writes `points_normals.ply`: the fused points with normals oriented towards the cameras that saw them. Open it in MeshLab (Filters > Remeshing > Screened Poisson) or Open3D to get a surface.
Without `--no-mesh` it also writes a rough `mesh.obj` (needs scikit-image). That mesh is **not good yet**: on the test scene the vertices were a median 3 mm from the vendor scan (the cloud itself is 0.9 mm), so it adds surface where there are no points. Use the Poisson route for now.

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
