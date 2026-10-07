from System import Environment
from System.IO import Directory, File, Path

import GalleryTagPanel as gallery_panel


def debug_log(message):
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


def debug_exception(context, error):
    debug_log(context + "\n" + unicode(error))


#@Name Gallery Tag Panel (Auto Open)
#@Key GalleryTagReaderLauncher
#@Hook BookOpened
#@Enabled true
#@Description Opens the Gallery Tag Panel when a comic is opened.
def GalleryTagReaderLauncher(book):
    debug_log("BookOpened hook called")
    if book is None:
        debug_log("BookOpened hook received no book")
        return

    try:
        gallery_panel.set_comicrack(ComicRack)
        gallery_panel.show_gallery_tag_panel(
            [book],
            modal=False,
            replace_existing=True,
            close_when_book_closes=True,
        )
    except Exception as error:
        debug_exception("GalleryTagReaderLauncher failed", error)


def BookHasBeenOpened(book):
    debug_log("BookHasBeenOpened callback called")
    GalleryTagReaderLauncher(book)
