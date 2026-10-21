# Capture (macOS)

`record.sh OUT_DIR` records 30 s of striped frames (`f_0001.png ...`) from camera A.

* Needs `ffmpeg`, [`uvc-util`](https://github.com/jtfrey/uvc-util) and python3 with numpy + pillow.
* Camera indices are device-specific: `AVF_INDEX` (ffmpeg's avfoundation index of camera A) and `CAM_A`/`CAM_B` (uvc-util indices). Check with `ffmpeg -f avfoundation -list_devices true -i ""` and `uvc-util -d`.
* The script sets exposure and gain, so it changes camera settings; at the end it restores the values observed on the author's device (exposure 78, auto exposure mode 8). Check these on yours.
* Exposure 25 / gain 0 worked for a pale figure at 30 cm. Brighter or closer objects saturate and break the stripe code; check the printed saturation (should stay under a few percent).
* The frames then go to `tools/librescan3d/run.py`.
