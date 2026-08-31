#@Name Gallery Tags Startup Launcher
#@Key GalleryTagStartupLauncher
#@Hook Startup
#@Enabled true
#@Description Shows the floating Tags launcher when ComicRack starts.

import os
import sys


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else ""
if SCRIPT_DIR and SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from GalleryTagReaderLauncher import ensure_launcher


def GalleryTagStartupLauncher():
    launcher = ensure_launcher()
    launcher.wait_for_book()
    try:
        launcher.Activate()
    except Exception:
        pass
