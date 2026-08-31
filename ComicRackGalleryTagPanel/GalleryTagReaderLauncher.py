#@Name GalleryTagReaderLauncher
#@Key GalleryTagReaderLauncher
#@Hook BookOpened
#@Enabled true
#@Description Shows a small floating Tags launcher while reading.

import clr
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

from GalleryTagPanel import show_gallery_tag_panel
from gallery_tag_core import title_for_book


LAUNCHER = None


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
        self.tags_button.Click += self._show_tags
        layout.Controls.Add(self.tags_button)

    def set_book(self, book):
        self.current_book = book
        self.title_label.Text = title_for_book(book)

    def _show_tags(self, sender, event):
        if self.current_book is not None:
            show_gallery_tag_panel([self.current_book], modal=False)


def place_launcher(form):
    try:
        owner = ComicRack.MainWindow
        bounds = owner.Bounds
        form.Left = bounds.Right - form.Width - 32
        form.Top = bounds.Top + 96
    except Exception:
        form.Left = 80
        form.Top = 80


def GalleryTagReaderLauncher(book):
    global LAUNCHER

    if book is None:
        return

    if LAUNCHER is None or LAUNCHER.IsDisposed:
        LAUNCHER = ReaderTagLauncher()
        place_launcher(LAUNCHER)
        try:
            LAUNCHER.Show(ComicRack.MainWindow)
        except Exception:
            LAUNCHER.Show()

    LAUNCHER.set_book(book)
    try:
        LAUNCHER.Activate()
    except Exception:
        pass
