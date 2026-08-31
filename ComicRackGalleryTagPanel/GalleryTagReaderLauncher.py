#@Name GalleryTagReaderLauncher
#@Key GalleryTagReaderLauncher
#@Hook BookOpened
#@Enabled true
#@Description Shows a small floating Tags launcher while reading.

import clr
import os
import sys
import traceback
clr.AddReference("System.Drawing")
clr.AddReference("System.Windows.Forms")

from System.Drawing import Font, FontStyle, Size
from System.Windows.Forms import (
    Button,
    DockStyle,
    FlowLayoutPanel,
    Form,
    FormBorderStyle,
    FormStartPosition,
    Label,
    Padding,
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else ""
if SCRIPT_DIR and SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from GalleryTagPanel import show_gallery_tag_panel
from gallery_tag_core import title_for_book


LAUNCHER = None


def debug_log(message):
    try:
        root = os.path.join(
            os.environ.get("APPDATA", os.path.expanduser("~")),
            "cYo",
            "ComicRack Community Edition",
        )
        if not os.path.isdir(root):
            root = SCRIPT_DIR or os.getcwd()
        path = os.path.join(root, "GalleryTagPanel.log")
        with open(path, "a") as handle:
            handle.write(message + "\n")
    except Exception:
        pass


def debug_exception(context):
    debug_log(context + "\n" + traceback.format_exc())


class ReaderTagLauncher(Form):
    def __init__(self):
        Form.__init__(self)
        self.current_book = None
        self.Text = "Tags"
        self.ShowInTaskbar = False
        self.TopMost = True
        self.FormBorderStyle = FormBorderStyle.FixedToolWindow
        self.StartPosition = FormStartPosition.Manual
        self.Size = Size(280, 86)
        self.MinimumSize = Size(220, 80)

        layout = FlowLayoutPanel()
        layout.Dock = DockStyle.Fill
        layout.Padding = Padding(8)
        layout.WrapContents = False
        self.Controls.Add(layout)

        self.title_label = Label()
        self.title_label.AutoSize = False
        self.title_label.Width = 165
        self.title_label.Height = 42
        self.title_label.Font = Font("Segoe UI", 8, FontStyle.Regular)
        layout.Controls.Add(self.title_label)

        self.tags_button = Button()
        self.tags_button.Text = "Tags"
        self.tags_button.Width = 72
        self.tags_button.Height = 34
        self.tags_button.Enabled = False
        self.tags_button.Click += self._show_tags
        layout.Controls.Add(self.tags_button)

    def wait_for_book(self):
        self.current_book = None
        self.title_label.Text = "Open a comic to browse tags."
        self.tags_button.Enabled = False

    def set_book(self, book):
        self.current_book = book
        self.title_label.Text = title_for_book(book)
        self.tags_button.Enabled = True

    def _show_tags(self, sender, event):
        if self.current_book is not None:
            show_gallery_tag_panel([self.current_book], modal=False)


def place_launcher(form):
    try:
        owner = ComicRack.MainWindow
        bounds = owner.Bounds
        form.Left = bounds.Left + 24
        form.Top = bounds.Top + 86
    except Exception:
        form.Left = 80
        form.Top = 80


def ensure_launcher():
    global LAUNCHER

    if LAUNCHER is None or LAUNCHER.IsDisposed:
        debug_log("Creating Gallery Tag launcher")
        LAUNCHER = ReaderTagLauncher()
        place_launcher(LAUNCHER)
        try:
            LAUNCHER.Show(ComicRack.MainWindow)
        except Exception:
            try:
                LAUNCHER.Show()
            except Exception:
                debug_exception("Could not show Gallery Tag launcher")
                raise

    return LAUNCHER


def GalleryTagReaderLauncher(book):
    debug_log("BookOpened hook called")
    if book is None:
        debug_log("BookOpened hook received no book")
        return

    try:
        launcher = ensure_launcher()
        launcher.set_book(book)
        try:
            launcher.Activate()
        except Exception:
            pass
    except Exception:
        debug_exception("GalleryTagReaderLauncher failed")


def BookHasBeenOpened(book):
    debug_log("BookHasBeenOpened callback called")
    GalleryTagReaderLauncher(book)
