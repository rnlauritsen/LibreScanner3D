# Findings (reverse engineering notes)

All derived from the author's own device by observation of its USB video streams and files. No vendor code is included.

## Hardware (front, left to right as seen from the front, scanner upright)
* Left outer window: infrared camera that sees the stripes.
* Centre window: ordinary grey camera with four white LEDs around it; off-centre.
* Right outer window: pattern projector (reflects strongly from a phone screen held in front).
* Calibration geometry (from `calib.txt`): camera-to-camera baseline about 32 mm, camera-to-projector baseline about 57 mm, same direction.
* macOS exposes two UVC cameras ("...A" and "...B"). Only one stream at a time seems usable (switching in one app switches it in another).
* Stream A alternates between a striped frame and a plain frame each time the stream is opened (not per frame). Raw frames are rotated 180 degrees relative to the vendor software's output.

## Stripe code
* Vertical stripes, pitch about 12.6-13.1 px, with a bead modulation along each stripe (period about 16-17 px) in three phase levels.
* `calib.txt` contains a 246-row table: a de Bruijn-style sequence of six rotations of (1 3 2 4 1 2). Decoding takes about 8 consecutive stripes; steps are read in Z3.
* Image left to right = decreasing table row.

## Depth model
Rectified reference frame (flat wall at known distance) gives x_ref per table row. Then
`1/Z = 1/Z_ref + (x - x_ref[row]) / (f * b)`, with `f` = camera focal length (px), `b` = camera-projector baseline (mm), after lens undistortion.
Validated against the vendor scan of the same object: wall about 2 mm mean absolute difference; the reference distance needed a one-time fit.

## `calib.txt` layout
Line 1: image size. Lines 5-7: three blocks of `fx fy cx cy k1 k2 p1 p2 k3` followed by a rotation vector and a translation (camera 1, camera 2, projector). A 246-row code table follows a line containing `246`.

## Vendor `.rscan` files (for comparison only)
Protobuf-like: per frame a name, pose (R,t), a point cloud (points, normals, small ints) and, for about every fifth frame, a plain grey image. Per-frame clouds are already in a common frame. Poses are cumulative camera-to-first-frame motion and match an independent fit (total turn 179 vs 191 degrees on one scan; different takes).

## Open questions
* How the vendor software gets pattern and plain frames; any extension-unit controls.
* Handling hand-held motion; thin parts; model-guided decoding of edge-on views.
