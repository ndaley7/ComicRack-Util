from System import Environment
from System.IO import Directory, File, Path


def script_log(message):
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


#@Name Show Gallery Tag Panel
#@Key GalleryTagShowLauncher
#@Hook Books
#@Enabled true
#@Description Opens the Gallery Tag Panel for the selected comic.
def GalleryTagShowLauncher(books):
    script_log("Manual Gallery Tag Panel hook called")
    try:
        import GalleryTagPanel as gallery_panel

        gallery_panel.set_comicrack(ComicRack)
        gallery_panel.show_gallery_tag_panel(
            list(books or []),
            modal=False,
            replace_existing=True,
        )
    except Exception as error:
        script_log("GalleryTagShowLauncher failed\n" + unicode(error))
