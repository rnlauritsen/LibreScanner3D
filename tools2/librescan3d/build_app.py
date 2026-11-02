"""Build the stand-alone app for the system you are on (macOS .app, Windows folder with .exe, Linux folder).

  pip install pyinstaller numpy scipy pillow scikit-image pywebview imageio-ffmpeg pyusb libusb-package open3d
  python3 build_app.py           ->  dist/LibreScanner3D(.app)

The result contains Python and every library, so the user installs nothing. It can only be built on the system it is
meant for (no cross-building); the GitHub workflow in .github/workflows/build-app.yml builds all three automatically.
"""
import os, sys, subprocess, importlib.util
here = os.path.dirname(os.path.abspath(__file__)); sep = os.pathsep
mods = [f[:-3] for f in os.listdir(here) if f.endswith(".py") and f not in ("build_app.py", "mergetest.py")]
cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--name", "LibreScanner3D", "--paths", here,
       "--add-data", os.path.join(here, "ui_web") + sep + "ui_web", "--collect-all", "webview", "--collect-all", "imageio_ffmpeg", "--collect-all", "libusb_package", "--hidden-import", "usb.backend.libusb1"]
if os.path.exists(os.path.join(here, "ref30.csv")): cmd += ["--add-data", os.path.join(here, "ref30.csv") + sep + "."]
for m in mods: cmd += ["--hidden-import", m]
for lib in ("skimage", "scipy"): cmd += ["--collect-submodules", lib]
if importlib.util.find_spec("open3d"): cmd += ["--collect-all", "open3d"]
else: print("NOTE: open3d is not installed here: the app will not be able to build Poisson meshes")
cmd.append(os.path.join(here, "ui.py"))
print(" ".join(cmd)); sys.exit(subprocess.call(cmd, cwd=here))
