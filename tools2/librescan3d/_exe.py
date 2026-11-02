"""How to start one of our scripts as a separate process, both from source and inside the packaged app."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
def pycmd(script, *args, flags=("-u",)):
    if getattr(sys, "frozen", False):  # packaged app: the program itself runs the script (see ui.py --script)
        return [sys.executable, "--script", script] + [str(a) for a in args]
    return [sys.executable] + list(flags) + [os.path.join(HERE, script)] + [str(a) for a in args]
