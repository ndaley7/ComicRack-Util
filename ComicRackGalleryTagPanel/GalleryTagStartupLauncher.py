import os
import sys
import traceback


SCRIPT_DIR = globals().get("ScriptPath", "")
if not SCRIPT_DIR and "__file__" in globals():
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR and SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)


def startup_log(message):
    try:
        root = os.path.join(
            os.environ.get("APPDATA", SCRIPT_DIR or os.getcwd()),
            "cYo",
            "ComicRack Community Edition",
        )
        if not os.path.isdir(root):
            root = SCRIPT_DIR or os.getcwd()
        path = os.path.join(root, "GalleryTagPanel.log")
        with open(path, "a") as handle:
            handle.write(str(message) + "\n")
    except Exception:
        pass


startup_log("GalleryTagStartupLauncher module loading")


#@Name Gallery Tags Startup Launcher
#@Key GalleryTagStartupLauncher
#@Hook Startup
#@Enabled true
#@Description Shows the floating Tags launcher when ComicRack starts.
def GalleryTagStartupLauncher():
    startup_log("Startup hook called")
    try:
        from GalleryTagReaderLauncher import ensure_launcher

        launcher = ensure_launcher()
        launcher.wait_for_book()
        try:
            launcher.Activate()
        except Exception:
            pass
        startup_log("Startup launcher shown")
    except Exception:
        startup_log("GalleryTagStartupLauncher failed\n" + traceback.format_exc())


#@Name Show Gallery Tags Launcher
#@Key GalleryTagShowLauncher
#@Hook Books
#@Enabled true
#@Description Shows the floating Tags launcher for the selected comic.
def GalleryTagShowLauncher(books):
    startup_log("Manual launcher hook called")
    try:
        from GalleryTagReaderLauncher import ensure_launcher

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
        startup_log("GalleryTagShowLauncher failed\n" + traceback.format_exc())
