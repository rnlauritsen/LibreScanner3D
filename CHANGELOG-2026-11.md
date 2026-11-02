# Update, November 2026

Files go in `tools2/librescan3d/` (pipeline) and `tools/capture/` (recording script, unchanged).

* `scan.py` (new): one command from recorded frames to a Poisson mesh, for one or several recordings.
* `merge.py` (new): aligns recordings of the same object in different poses (global rotation search + point-to-plane ICP; experimental `--fpfh`/`--partial`). Needs about half of the surface shared between poses.
* `mesh.py`: crops to the figure around the turning axis and drops thin streaks; `--no-mesh` writes only `points_normals.ply`.
* `poisson.py`: sturdier retry ladder when Open3D fails with "Failed to close loop", mesh cleaning, Taubin smoothing.
* `run.py`/`track.py`: saves the turning axis (`tracking.npz`), robust axis estimate for small objects (`--axis-step`), `--dense`, depth smoothing/row fill options.
* `mergetest.py`: synthetic known-motion test of the merge (needs a `points_normals.ply` to cut up).
* Do not commit `calib.txt`, serial numbers or recordings.
* `track.py`: tracks turns about four times faster than before (up to ~13 degrees per processed frame, was ~3-6): the model is now re-indexed after every accepted frame and the angle search follows the turning speed. `speedtest.py` re-runs a finished recording at a faster effective speed to test this. `refine.py` (experimental): six-degree-of-freedom pose refinement; gave only ~10% better frame agreement, so it is not used by default.
