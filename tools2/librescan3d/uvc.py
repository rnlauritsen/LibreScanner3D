"""Camera controls (exposure, gain, ...) over USB, built into the package: replaces uvc-util (macOS) and v4l2-ctl (Linux).
Talks the standard USB Video Class control protocol through libusb, so it works for any UVC camera without drivers or root on macOS.

  python3 uvc.py --list                       list UVC cameras (index, name, ids)
  python3 uvc.py -I 0 --controls              show the controls camera 0 offers, with current value and range
  python3 uvc.py -I 0 -s exposure-time-abs=25 -s gain=0
  python3 uvc.py -I 0 -g exposure-time-abs

Needs: pip install pyusb libusb-package   (both are bundled in the stand-alone app)
STATUS: written from the UVC 1.5 specification and checked only against synthetic descriptors; NOT yet run on a real camera.
Windows cannot use this (the camera driver blocks libusb): set exposure in the camera's own settings there.
"""
import sys, struct, argparse

# name: (unit kind, selector, size in bytes, signed, description). CT = camera terminal, PU = processing unit.
CONTROLS = {
    "auto-exposure-mode":     ("CT", 0x02, 1, False, "1 manual, 2 auto, 4 shutter priority, 8 aperture priority"),
    "exposure-time-abs":      ("CT", 0x04, 4, False, "exposure in units of 100 microseconds"),
    "focus-abs":              ("CT", 0x06, 2, False, "focus"),
    "auto-focus":             ("CT", 0x08, 1, False, "0 off, 1 on"),
    "zoom-abs":               ("CT", 0x0B, 2, False, "zoom"),
    "backlight-compensation": ("PU", 0x01, 2, False, "backlight compensation"),
    "brightness":             ("PU", 0x02, 2, True,  "brightness"),
    "contrast":               ("PU", 0x03, 2, False, "contrast"),
    "gain":                   ("PU", 0x04, 2, False, "gain"),
    "power-line-frequency":   ("PU", 0x05, 1, False, "0 off, 1 50 Hz, 2 60 Hz"),
    "hue":                    ("PU", 0x06, 2, True,  "hue"),
    "saturation":             ("PU", 0x07, 2, False, "saturation"),
    "sharpness":              ("PU", 0x08, 2, False, "sharpness"),
    "gamma":                  ("PU", 0x09, 2, False, "gamma"),
    "white-balance-temp":     ("PU", 0x0A, 2, False, "white balance temperature"),
    "auto-white-balance-temp":("PU", 0x0B, 1, False, "0 off, 1 on"),
}
SET_CUR, GET_CUR, GET_MIN, GET_MAX, GET_RES, GET_INFO, GET_DEF = 0x01, 0x81, 0x82, 0x83, 0x84, 0x86, 0x87

def parse_config(cfg):
    """Raw configuration descriptor -> {'vc': interface number, 'ct': camera terminal id, 'pu': processing unit id} or None if not a UVC camera."""
    i = 0; cur = None; res = {}
    while i + 2 <= len(cfg):
        n, t = cfg[i], cfg[i + 1]
        if n < 2: break
        d = cfg[i:i + n]
        if t == 4 and n >= 9:                                  # interface descriptor
            cur = (d[2], d[5], d[6])                            # number, class, subclass
            if d[5] == 0x0E and d[6] == 0x01 and "vc" not in res: res["vc"] = d[2]
        elif t == 0x24 and cur and cur[1] == 0x0E and cur[2] == 0x01 and cur[0] == res.get("vc") and n >= 4:
            sub = d[2]
            if sub == 0x02 and n >= 8 and struct.unpack("<H", bytes(d[4:6]))[0] == 0x0201: res["ct"] = d[3]    # input terminal, ITT_CAMERA
            elif sub == 0x05: res["pu"] = d[3]                                                                   # processing unit
        i += n
    return res if "vc" in res else None

def request_args(kind, req, name, ids):
    """(bmRequestType, bRequest, wValue, wIndex, size) for one control request."""
    k, sel, size, signed, _ = CONTROLS[name]
    unit = ids.get("ct" if k == "CT" else "pu")
    if unit is None: raise KeyError("this camera has no %s unit" % ("camera terminal" if k == "CT" else "processing unit"))
    rt = 0x21 if req == SET_CUR else 0xA1
    return rt, req, sel << 8, (unit << 8) | ids["vc"], size

def decode(b, signed): return int.from_bytes(bytes(b), "little", signed=signed)

class Camera:
    def __init__(self, dev, ids, name): self.dev, self.ids, self.name = dev, ids, name
    def get(self, name, req=GET_CUR):
        rt, r, v, idx, size = request_args("get", req, name, self.ids)
        return decode(self.dev.ctrl_transfer(rt, r, v, idx, size, timeout=2000), CONTROLS[name][3])
    def set(self, name, value):
        rt, r, v, idx, size = request_args("set", SET_CUR, name, self.ids)
        self.dev.ctrl_transfer(rt, r, v, idx, int(value).to_bytes(size, "little", signed=CONTROLS[name][3] and value < 0), timeout=2000)
    def supported(self):
        out = []
        for n, (k, sel, size, sg, desc) in CONTROLS.items():
            if self.ids.get("ct" if k == "CT" else "pu") is None: continue
            try:
                rt, r, v, idx, sz = request_args("get", GET_INFO, n, self.ids); info = self.dev.ctrl_transfer(rt, r, v, idx, 1, timeout=2000)[0]
                if info & 1: out.append(n)
            except Exception: pass
        return out

def find_cameras():
    try:
        import usb.core, usb.backend.libusb1 as lb
    except ImportError: raise SystemExit("pyusb is not installed (pip install pyusb libusb-package)")
    be = None
    try:
        import libusb_package; be = lb.get_backend(find_library=libusb_package.find_library)
    except Exception: pass
    cams = []
    for d in usb.core.find(find_all=True, backend=be):
        try:
            cfg = bytes(d.ctrl_transfer(0x80, 6, 0x0200, 0, 9, timeout=1000)); total = int.from_bytes(cfg[2:4], "little")
            cfg = bytes(d.ctrl_transfer(0x80, 6, 0x0200, 0, total, timeout=1000)); ids = parse_config(cfg)
        except Exception: continue
        if not ids: continue
        try: name = d.product or "UVC camera"
        except Exception: name = "UVC camera"
        cams.append(Camera(d, ids, "%s (%04x:%04x)" % (name, d.idVendor, d.idProduct)))
    cams.sort(key=lambda c: (c.dev.bus or 0, c.dev.address or 0))
    return cams

def set_scanner_exposure(exp_a, exp_b=5, cam_a=0, cam_b=1, log=print):
    """Same settings as record.sh: manual exposure, gain 0, backlight compensation 2 on both cameras of the scanner."""
    cams = find_cameras()
    for i, c in enumerate(cams): log("  camera %d: %s" % (i, c.name))
    for idx, e in ((cam_a, exp_a), (cam_b, exp_b)):
        if idx >= len(cams): log("  camera %d not found: exposure left as is" % idx); continue
        c = cams[idx]
        for n, v in (("auto-exposure-mode", 1), ("backlight-compensation", 2), ("exposure-time-abs", e), ("gain", 0)):
            try: c.set(n, v)
            except Exception as ex: log("  camera %d: could not set %s (%s)" % (idx, n, ex))
    return len(cams)

def main(argv=None):
    ap = argparse.ArgumentParser(description="UVC camera controls"); ap.add_argument("--list", action="store_true"); ap.add_argument("-I", "--index", type=int, default=0)
    ap.add_argument("--controls", action="store_true"); ap.add_argument("-s", "--set", action="append", default=[]); ap.add_argument("-g", "--get", action="append", default=[]); a = ap.parse_args(argv)
    cams = find_cameras()
    if a.list or not (a.controls or a.set or a.get):
        for i, c in enumerate(cams): print("%d: %s" % (i, c.name))
        if not cams: print("no UVC camera found")
        return 0 if cams else 1
    if a.index >= len(cams): print("no camera with index %d" % a.index); return 1
    c = cams[a.index]
    if a.controls:
        for n in c.supported():
            try: print("%-24s %6d  (min %d, max %d)  %s" % (n, c.get(n), c.get(n, GET_MIN), c.get(n, GET_MAX), CONTROLS[n][4]))
            except Exception as e: print("%-24s ?  %s" % (n, e))
    for s in a.set:
        n, _, v = s.partition("=")
        if n not in CONTROLS: print("unknown control", n); return 2
        c.set(n, int(v)); print("%s = %s" % (n, v))
    for n in a.get: print("%s = %d" % (n, c.get(n)))
    return 0

if __name__ == "__main__": sys.exit(main())
