#@Name Gallery Tags Startup Launcher
#@Key GalleryTagStartupLauncher
#@Hook Startup
#@Enabled true
#@Description Shows the floating Tags launcher when ComicRack starts.

import os
import sys

import clr
clr.AddReference("System.Windows.Forms")
from System.Windows.Forms import Timer

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else ""
if SCRIPT_DIR and SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from GalleryTagReaderLauncher import debug_exception, debug_log, ensure_launcher


STARTUP_TIMER = None


def show_startup_launcher():
    try:
        launcher = ensure_launcher()
        launcher.wait_for_book()
        try:
            launcher.Activate()
        except Exception:
            pass
        debug_log("Startup launcher shown")
    except Exception:
        debug_exception("GalleryTagStartupLauncher failed")


def GalleryTagStartupLauncher():
    global STARTUP_TIMER

    debug_log("Startup hook called")
    STARTUP_TIMER = Timer()
    STARTUP_TIMER.Interval = 1500

    def timer_tick(sender, event):
        global STARTUP_TIMER
        try:
            sender.Stop()
            show_startup_launcher()
        finally:
            try:
                sender.Dispose()
            except Exception:
                pass
            STARTUP_TIMER = None

    STARTUP_TIMER.Tick += timer_tick
    STARTUP_TIMER.Start()


#@Name Show Gallery Tags Launcher
#@Key GalleryTagShowLauncher
#@Hook Books
#@Enabled true
#@Description Shows the floating Tags launcher for the selected comic.
def GalleryTagShowLauncher(books):
    debug_log("Manual launcher hook called")
    try:
        selected = list(books or [])
        launcher = ensure_launcher()
        if selected:
            launcher.set_book(selected[0])
        else:
            launcher.wait_for_book()
        try:
            launcher.Activate()
        except Exception:
            pass
    except Exception:
        debug_exception("GalleryTagShowLauncher failed")
