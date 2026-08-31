from System import Environment
from System.IO import Directory, File, Path


def startup_log(message):
    try:
        root = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
            "cYo",
            "ComicRack Community Edition",
        )
        Directory.CreateDirectory(root)
        path = Path.Combine(root, "GalleryTagPanel.log")
        File.AppendAllText(path, unicode(message) + Environment.NewLine)
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
    except Exception as error:
        startup_log("GalleryTagStartupLauncher failed\n" + unicode(error))


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
    except Exception as error:
        startup_log("GalleryTagShowLauncher failed\n" + unicode(error))
