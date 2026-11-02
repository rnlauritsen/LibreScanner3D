# librescan3d (prototype)

Raw striped frames from the Fox scanner -> depth -> tracked, fused point cloud (PLY).
Independent of JMStudio; uses your own `calib.txt`.

## Quick start: one command from frames to mesh
    python3 scan.py REC1 [REC2 ...] --calib calib.txt --out OUT [--depth 8] [--voxel 0.4]
Each REC is a folder of `f_0001.png ...` (one turntable recording). `scan.py` runs `run.py` (decode + track + `--dense`), `mesh.py --no-mesh` (crop to the figure, normals), `merge.py` (when you give several recordings) and `poisson.py` (Poisson + trim + smoothing), and writes `OUT/poisson_mesh.ply`. Finished steps are skipped on a re-run. Needs `numpy scipy pillow` and, for the last step, `open3d` (Python 3.9-3.12).

### Several recordings of one object
One turntable pass cannot see the top or underside. Record the object in two or three different poses and give all folders to `scan.py`; `merge.py` aligns them without markers. Tested: two passes of a larger figure fell onto each other within 0.4 mm (median).
* **The poses must share at least about half of their surface.** On synthetic tests (a real scan cut into two overlapping parts and moved by a known motion) the alignment was correct at 70% and 50% shared surface (0.3 mm error) and failed at 35% and below. So tilt the object 40-60 degrees between recordings rather than laying it completely on another side.
* A recording in almost the same pose adds points but no new surface (the merge then reports a rotation of only a few degrees).
* `merge.py` prints how much of the second scan lies within 2 mm of the first and warns below 50%. `--fpfh` (Open3D feature matching) and `--partial` are experimental options for small overlaps; neither was verified to fix the 35% case.
* Ideas taken from FoxStudio's registration (point-to-plane ICP) improved the fit from 83% to 88% of points within 2 mm.

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

## Optional: --dense
`--dense` fills in depth between neighbouring decoded stripes (only where the surface is smooth, within 1.5 mm) and writes `fused_dense.ply/.npz`: about 4x the points. Against the vendor scan its accuracy was the same as the normal cloud (median 0.93 mm); it does not add coverage, it removes the stripe-pattern ridges that otherwise show up in a mesh.

## Meshing (experimental)
`python3 mesh.py OUT_DIR --no-mesh` writes `points_normals.ply`: the fused points with normals oriented towards the cameras that saw them. Open it in MeshLab (Filters > Remeshing > Screened Poisson) or Open3D to get a surface.
Without `--no-mesh` it also writes a rough `mesh.obj` (needs scikit-image). That mesh is **not good yet**: on the test scene the vertices were a median 3 mm from the vendor scan (the cloud itself is 0.9 mm), so it adds surface where there are no points. Use the Poisson route for now.

`poisson.py OUT_DIR` does the Poisson step with Open3D (`pip install open3d`) and trims surface invented over gaps. Untested by the author so far.


## How fast may the object turn?
Tracking was tested by re-running a finished recording with only every 2nd, 3rd, 4th ... frame (`python3 speedtest.py OUT_DIR calib.txt`). At the default `--step 3` on a 10 fps recording, the tracker follows turns of up to about 13 degrees per processed frame (about 40 degrees per second) without losing a frame; at 16 degrees per frame and above it loses the object. If you turn faster, use `--step 1` or `--step 2`. The frame-to-frame agreement of the fused scan is about 0.25 mm, and the scale agrees with JMStudio's mesh of the same figure to within 0.5%.

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

## Graphical interface (all platforms)

```
python3 ui.py
```

Opens LibreScanner3D in your web browser (a small local server on 127.0.0.1; nothing leaves your computer, no internet needed).
The page looks and works the same on macOS, Linux and Windows; use the **Quit** button in the page to stop the program.

- **Scan**: add one recording folder per pose, choose calibration and output folder, press *Start scan*. Live log with stage indicator.
- **Viewer**: own 3D viewer for clouds and meshes (drag = rotate, right-drag = pan, wheel = zoom).
- **Tracking**: angle / overlap / RMS plots with lost frames marked, and a slider through the source frames.
- **Tools**: merge, mesh only, compare with a reference mesh (`compare.py`), speed test, record.
- **Settings**: default calibration, work folder, recorder script (saved in `~/.librescan3d/config.json`).

Needs `numpy scipy pillow` (as the command line tools). The server only serves files inside your home folder, requires a random token and refuses other host names.
Status: tested on Linux in a headless browser; **not yet tested on macOS or Windows**. The Record button runs `record.py` (ffmpeg; exposure via uvc-util on macOS, v4l2-ctl on Linux; on Windows set exposure low in the camera settings yourself). `python3 record.py --list` shows the camera numbers/names. Only the macOS path is based on a verified script; Linux and Windows are untested.

### Own window instead of the browser

`ui.py` opens its own window when `pywebview` is installed (`pip install pywebview`), otherwise it falls back to the browser (`--browser` forces the browser). The window is the normal OS window, so closing works like any app (X on Windows, red dot on macOS); the Quit button does the same.
Double-click launchers that set everything up on first start are in `launchers/` (`LibreScanner3D.command` macOS, `LibreScanner3D.bat` Windows, `librescanner3d-linux.sh` Linux). **Untested**: pywebview and the launchers could not be run where this was written. A frozen single-file app (PyInstaller) is not done yet: the scan jobs run as separate Python processes, which a frozen app has to be reworked for.
