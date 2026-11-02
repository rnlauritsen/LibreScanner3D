@echo off
rem Windows: double-click. First run creates a private Python environment and installs what it needs (Python 3.10-3.12 must be installed).
cd /d "%~dp0..\tools2\librescan3d" 2>nul || cd /d "%~dp0..\librescan3d"
set V=%USERPROFILE%\.librescan3d\venv
if not exist "%V%\Scripts\python.exe" (
  echo First start: setting up, needs internet once...
  py -3 -m venv "%V%" && "%V%\Scripts\pip" install --quiet numpy scipy pillow scikit-image pywebview && "%V%\Scripts\pip" install --quiet open3d
)
"%V%\Scripts\python" ui.py
