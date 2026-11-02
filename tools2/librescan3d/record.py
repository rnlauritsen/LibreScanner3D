"""Cross-platform recorder for the Fox scanner (camera A with the stripe pattern). Replaces record.sh.

usage: python3 record.py OUT_DIR [--seconds 30] [--device N|NAME] [--exp 25] [--list] [--dry-run]
Needs ffmpeg on the PATH. Exposure control (keeps pale objects from saturating the stripes):
  macOS : uvc-util (github.com/jtfrey/uvc-util), set UVC=/path/to/uvc-util if not in ~/uvc-util/src
  Linux : v4l2-ctl (package v4l-utils)
  Windows: not automated; set exposure low in the camera's own settings before recording (see README).
STATUS: only the macOS path is derived from a verified script (record.sh); Linux and Windows are UNTESTED.
"""
import sys, os, argparse, subprocess, shutil, time, platform

def ff_input(dev):
    s = sys.platform
    if s == "darwin": return ["-f", "avfoundation", "-pixel_format", "uyvy422", "-framerate", "10", "-video_size", "1280x720", "-i", str(dev)]
    if s.startswith("linux"): return ["-f", "v4l2", "-framerate", "10", "-video_size", "1280x720", "-i", dev if str(dev).startswith("/dev") else "/dev/video" + str(dev)]
    return ["-f", "dshow", "-framerate", "10", "-video_size", "1280x720", "-i", "video=" + str(dev)]

def list_devices():
    s = sys.platform
    if s == "darwin": cmd = ["ffmpeg", "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""]
    elif s.startswith("linux"): cmd = ["v4l2-ctl", "--list-devices"]
    else: cmd = ["ffmpeg", "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"]
    try: r = subprocess.run(cmd, capture_output=True, text=True); print(r.stdout + r.stderr)
    except FileNotFoundError: print("%s not found; install it first" % cmd[0])

def set_exposure(exp, dry):
    """Best effort; returns a note for the log."""
    def run(c):
        print("$", " ".join(c))
        if not dry: subprocess.run(c, capture_output=True)
    if sys.platform == "darwin":
        uvc = os.environ.get("UVC", os.path.expanduser("~/uvc-util/src/uvc-util"))
        if not os.path.exists(uvc) and not dry: return "uvc-util not found: exposure left as is"
        for i, e in ((0, exp), (1, 5)):
            run([uvc, "-I", str(i), "-s", "auto-exposure-mode=1"]); run([uvc, "-I", str(i), "-s", "exposure-time-abs=%d" % e]); run([uvc, "-I", str(i), "-s", "gain=0"])
        return "exposure set with uvc-util"
    if sys.platform.startswith("linux"):
        if not shutil.which("v4l2-ctl") and not dry: return "v4l2-ctl not found: exposure left as is"
        dev = os.environ.get("V4L2_DEV", "/dev/video0")
        run(["v4l2-ctl", "-d", dev, "-c", "auto_exposure=1,exposure_time_absolute=%d,gain=0" % exp]); return "exposure set with v4l2-ctl (values may need adjusting, Linux is untested)"
    return "exposure not automated on this system: set it low in the camera settings"

def is_striped(png):
    from chk_stripes import check
    return check(png)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("out", nargs="?"); ap.add_argument("--seconds", type=int, default=30); ap.add_argument("--device", default=os.environ.get("AVF_INDEX", "1" if sys.platform == "darwin" else "0"))
    ap.add_argument("--exp", type=int, default=int(os.environ.get("EXP", 25))); ap.add_argument("--list", action="store_true"); ap.add_argument("--dry-run", action="store_true"); a = ap.parse_args()
    if a.list: return list_devices()
    if not a.out: ap.error("OUT_DIR required")
    ff = os.environ.get("FFMPEG", "ffmpeg")
    if not shutil.which(ff) and not a.dry_run: raise SystemExit("ffmpeg not found; install it first")
    os.makedirs(a.out, exist_ok=True); print(set_exposure(a.exp, a.dry_run))
    def cap(extra, name): 
        c = [ff, "-loglevel", "error", "-y"] + ff_input(a.device) + extra + ["-pix_fmt", "gray", name]; print("$", " ".join(c))
        if not a.dry_run: subprocess.run(c, cwd=a.out)
    probe = os.path.join(a.out, "probe.png")
    # opening the stream alternates striped / plain frames on the Mac: probe once, throw away one open if it was striped
    time.sleep(0 if a.dry_run else 2); cap(["-frames:v", "3", "-update", "1"], "probe.png")
    if not a.dry_run and os.path.exists(probe) and is_striped(probe): print("probe was striped, so the next open will be plain: doing one throwaway open"); time.sleep(1); cap(["-frames:v", "3", "-update", "1"], "probe.png")
    time.sleep(0 if a.dry_run else 1); print("Start turning the base slowly NOW. Recording %d s..." % a.seconds)
    cap(["-t", str(a.seconds)], "f_%04d.png")
    if not a.dry_run:
        n = len([f for f in os.listdir(a.out) if f.startswith("f_")]); print("frames:", n)
        mid = os.path.join(a.out, "f_%04d.png" % max(1, n // 2))
        if os.path.exists(mid): print("middle frame looks", "striped (good)" if is_striped(mid) else "PLAIN (no stripes): record again")

if __name__ == "__main__": main()
