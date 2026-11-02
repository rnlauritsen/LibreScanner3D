## Interface
- `ui.py` + `ui_web/`: browser-based interface (Scan, Viewer, Tracking, Tools, Settings), same on every OS.
- `compare.py`: compare a scan with a reference mesh (e.g. JMStudio) after automatic alignment.
- `run.py` writes `source.json` so the Tracking tab can show source frames; `speedtest.py`/`refine.py` find `ref30.csv` from any folder.
- uvc.py: built-in UVC camera controls (exposure/gain/...) over libusb, replaces uvc-util/v4l2-ctl; used by record.py.
