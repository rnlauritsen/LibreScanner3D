#!/bin/bash
# macOS: double-click. First run creates a private Python environment next to the program and installs what it needs.
cd "$(dirname "$0")/../tools2/librescan3d" 2>/dev/null || cd "$(dirname "$0")/../librescan3d" || exit 1
V="$HOME/.librescan3d/venv"
if [ ! -x "$V/bin/python" ]; then
  echo "First start: setting up (a few minutes, needs internet once)..."
  PY=$(command -v python3.12 || command -v python3.11 || command -v python3.10 || command -v python3)
  "$PY" -m venv "$V" && "$V/bin/pip" install --quiet numpy scipy pillow scikit-image pywebview && "$V/bin/pip" install --quiet open3d || echo "(Open3D not installed: meshing with Poisson will not work on this Python)"
fi
exec "$V/bin/python" ui.py
