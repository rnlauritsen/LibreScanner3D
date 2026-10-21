# LibreScanner3D

An open-source, Mac-first (Apple Silicon) alternative to the vendor software for the 3DMakerpro Fox
structured-light 3D scanner. Goal: scan like the vendor software, with better tracking and fewer alignment errors.

**Status: early prototype.** A working pipeline exists for *turntable-style* scans (scanner fixed, object on a
base turned by hand). It is not a finished app. See `docs/findings.md` for what is known about the scanner and where the work stands.

## What works today
`tools/librescan3d/` turns raw striped camera frames plus the device's own `calib.txt` into a tracked, fused
point cloud (PLY), without any vendor software in the loop. On one test scene the result was within 0.73 mm
(median) of the vendor software's scan of the same object, covering about two thirds of its surface.

Run it: see `tools/librescan3d/README.md`.

## What does not work yet
* Hand-held scanning (moving scanner), thin or edge-on parts, dark/shiny surfaces.
* No mesh output, no GUI, no live capture app. Frames are recorded with `ffmpeg` and a small script (to be added to `tools/capture/`).
* Absolute depth is calibrated on one device only.

## Contributing
Useful help: more recordings of different objects (with your own device's calibration, never shared), capture tooling, a mesher, a GUI.
**Never commit** `calib.txt`, serial numbers or scan recordings (the `.gitignore` blocks the usual ones).

## Legal
Independent project, not affiliated with 3DMakerpro. Interoperability analysis of one's own device (EU Directive 2009/24/EC Art. 6, US 17 U.S.C. 1201(f)) is the basis; this is not legal advice. No vendor code or binaries are included.
