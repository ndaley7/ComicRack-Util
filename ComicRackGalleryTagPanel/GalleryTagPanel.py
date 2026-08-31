#@Name GalleryTagPanel
#@Key GalleryTagPanel
#@Hook Books
#@Enabled true
#@Description E-H style tag browser panel for the selected comic.

import clr
clr.AddReference("System")
clr.AddReference("System.Drawing")
clr.AddReference("System.Windows.Forms")

from System.Diagnostics import Process
from System.Drawing import Color, Font, FontStyle, Size
from System.Windows.Forms import (
    AutoSizeMode,
    BorderStyle,
    Button,
    DataGridView,
    DataGridViewAutoSizeColumnsMode,
    DataGridViewSelectionMode,
    DockStyle,
    FlatStyle,
    FlowLayoutPanel,
    Form,
    FormStartPosition,
    Label,
    MessageBox,
    Orientation,
    Padding,
    PictureBox,
    PictureBoxSizeMode,
    RowStyle,
    ScrollBars,
    SizeType,
    SplitContainer,
    TableLayoutPanel,
    TextBox,
)

from gallery_tag_core import (
    book_matches_filters,
    get_book_tags,
    get_field,
    metadata_rows,
    normalize,
    ordered_categories,
    safe_text,
    title_for_book,
)


TAG_COLORS = {
    "artist": Color.FromArgb(255, 244, 198),
    "group": Color.FromArgb(220, 237, 255),
    "parody": Color.FromArgb(225, 245, 219),
    "character": Color.FromArgb(246, 224, 255),
    "female": Color.FromArgb(255, 229, 239),
    "male": Color.FromArgb(224, 234, 255),
    "mixed": Color.FromArgb(235, 235, 235),
    "genre": Color.FromArgb(234, 245, 255),
    "format": Color.FromArgb(239, 239, 215),
    "publisher": Color.FromArgb(230, 245, 230),
    "story arc": Color.FromArgb(255, 236, 214),
    "series group": Color.FromArgb(235, 230, 255),
    "team": Color.FromArgb(225, 245, 245),
    "location": Color.FromArgb(239, 232, 219),
    "language": Color.FromArgb(232, 242, 232),
}


def get_library_books(seed_books):
    try:
        return list(ComicRack.App.GetLibraryBooks())
    except Exception:
        return list(seed_books or [])


def show_book_info(book):
    try:
        ComicRack.App.ShowComicInfo([book])
        return True
    except Exception:
        return False


def open_book(book):
    for target_name in ["ComicDisplay", "MainWindow"]:
        try:
            target = getattr(ComicRack, target_name)
        except Exception:
            target = None
        if target is None:
            continue

        for method_name in ["OpenBook", "ShowBook", "DisplayBook", "ReadBook"]:
            try:
                method = getattr(target, method_name)
                method(book)
                return
            except Exception:
                pass

    path = safe_text(get_field(book, "FilePath"))
    if path:
        try:
            Process.Start(path)
            return
        except Exception:
            pass

    show_book_info(book)


class GalleryTagPanelForm(Form):
    def __init__(self, selected_books, library_books):
        Form.__init__(self)
        self.selected_books = list(selected_books or [])
        self.library_books = list(library_books or self.selected_books)
        self.current_book = self.selected_books[0] if self.selected_books else None
        self.filters = []
        self.result_books = []

        self.Text = "Gallery Tag Panel"
        self.StartPosition = FormStartPosition.CenterScreen
        self.Size = Size(1180, 720)
        self.MinimumSize = Size(900, 560)

        self._build_ui()
        self._load_current_book()

    def _build_ui(self):
        self.split = SplitContainer()
        self.split.Dock = DockStyle.Fill
        self.split.Orientation = Orientation.Vertical
        self.split.SplitterDistance = 430
        self.Controls.Add(self.split)

        left = TableLayoutPanel()
        left.Dock = DockStyle.Fill
        left.RowCount = 3
        left.ColumnCount = 1
        left.Padding = Padding(10)
        left.RowStyles.Add(RowStyle(SizeType.Absolute, 310))
        left.RowStyles.Add(RowStyle(SizeType.Absolute, 62))
        left.RowStyles.Add(RowStyle(SizeType.Percent, 100))
        self.split.Panel1.Controls.Add(left)

        self.cover = PictureBox()
        self.cover.Dock = DockStyle.Top
        self.cover.Height = 300
        self.cover.BorderStyle = BorderStyle.FixedSingle
        self.cover.SizeMode = PictureBoxSizeMode.Zoom
        left.Controls.Add(self.cover, 0, 0)

        self.title_label = Label()
        self.title_label.AutoSize = False
        self.title_label.Dock = DockStyle.Top
        self.title_label.Height = 54
        self.title_label.Font = Font("Segoe UI", 12, FontStyle.Bold)
        left.Controls.Add(self.title_label, 0, 1)

        self.meta_box = TextBox()
        self.meta_box.Dock = DockStyle.Fill
        self.meta_box.Multiline = True
        self.meta_box.ReadOnly = True
        self.meta_box.ScrollBars = ScrollBars.Vertical
        left.Controls.Add(self.meta_box, 0, 2)

        right = TableLayoutPanel()
        right.Dock = DockStyle.Fill
        right.RowCount = 3
        right.ColumnCount = 1
        right.Padding = Padding(10)
        right.RowStyles.Add(RowStyle(SizeType.Absolute, 38))
        right.RowStyles.Add(RowStyle(SizeType.Percent, 100))
        right.RowStyles.Add(RowStyle(SizeType.Absolute, 255))
        self.split.Panel2.Controls.Add(right)

        self.filter_label = Label()
        self.filter_label.AutoSize = False
        self.filter_label.Dock = DockStyle.Top
        self.filter_label.Height = 32
        self.filter_label.Font = Font("Segoe UI", 9, FontStyle.Bold)
        right.Controls.Add(self.filter_label, 0, 0)

        self.tags_panel = FlowLayoutPanel()
        self.tags_panel.Dock = DockStyle.Fill
        self.tags_panel.AutoScroll = True
        self.tags_panel.WrapContents = True
        right.Controls.Add(self.tags_panel, 0, 1)

        results_area = TableLayoutPanel()
        results_area.Dock = DockStyle.Bottom
        results_area.Height = 245
        results_area.RowCount = 2
        results_area.ColumnCount = 1
        results_area.RowStyles.Add(RowStyle(SizeType.Absolute, 40))
        results_area.RowStyles.Add(RowStyle(SizeType.Percent, 100))
        right.Controls.Add(results_area, 0, 2)

        result_actions = FlowLayoutPanel()
        result_actions.Dock = DockStyle.Top
        result_actions.Height = 36
        results_area.Controls.Add(result_actions, 0, 0)

        clear_button = Button()
        clear_button.Text = "Clear filters"
        clear_button.AutoSize = True
        clear_button.Click += self._clear_filters
        result_actions.Controls.Add(clear_button)

        info_button = Button()
        info_button.Text = "Info"
        info_button.AutoSize = True
        info_button.Click += self._show_selected_result_info
        result_actions.Controls.Add(info_button)

        open_button = Button()
        open_button.Text = "Open"
        open_button.AutoSize = True
        open_button.Click += self._open_selected_result
        result_actions.Controls.Add(open_button)

        self.results = DataGridView()
        self.results.Dock = DockStyle.Fill
        self.results.AllowUserToAddRows = False
        self.results.AllowUserToDeleteRows = False
        self.results.ReadOnly = True
        self.results.SelectionMode = DataGridViewSelectionMode.FullRowSelect
        self.results.MultiSelect = False
        self.results.AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.Fill
        self.results.RowHeadersVisible = False
        self.results.Columns.Add("Title", "Title")
        self.results.Columns.Add("Series", "Series")
        self.results.Columns.Add("Issue", "#")
        self.results.Columns.Add("Publisher", "Publisher")
        self.results.Columns.Add("Format", "Format")
        self.results.CellDoubleClick += self._result_double_click
        results_area.Controls.Add(self.results, 0, 1)

    def _load_current_book(self):
        if self.current_book is None:
            self.title_label.Text = "Select one or more comics, then run Automation > GalleryTagPanel."
            self.meta_box.Text = ""
            return

        self.title_label.Text = title_for_book(self.current_book)
        self.meta_box.Text = "\r\n".join(["%s: %s" % row for row in metadata_rows(self.current_book)])
        self._load_cover()
        self._render_tags()
        self._refresh_results()

    def _load_cover(self):
        try:
            image = ComicRack.App.GetComicThumbnail(self.current_book, 0)
            if image is None:
                image = ComicRack.App.GetComicPage(self.current_book, 0)
            self.cover.Image = image
        except Exception:
            self.cover.Image = None

    def _render_tags(self):
        self.tags_panel.Controls.Clear()
        tag_map = get_book_tags(self.current_book)

        for category in ordered_categories(tag_map):
            group_label = Label()
            group_label.Text = category + ":"
            group_label.AutoSize = False
            group_label.Width = 92
            group_label.Height = 26
            group_label.Font = Font("Segoe UI", 9, FontStyle.Bold)
            group_label.Margin = Padding(0, 4, 4, 2)
            self.tags_panel.Controls.Add(group_label)

            for value in tag_map.get(category, []):
                button = Button()
                button.Text = value
                button.AutoSize = True
                button.AutoSizeMode = AutoSizeMode.GrowAndShrink
                button.BackColor = TAG_COLORS.get(category, Color.FromArgb(245, 245, 245))
                button.FlatStyle = FlatStyle.Popup
                button.Margin = Padding(2, 2, 4, 2)
                button.Tag = (category, value)
                button.Click += self._tag_clicked
                self.tags_panel.Controls.Add(button)

    def _tag_clicked(self, sender, event):
        category, value = sender.Tag
        key = (normalize(category), normalize(value))
        existing = [(normalize(c), normalize(v)) for c, v in self.filters]
        if key in existing:
            self.filters = [(c, v) for c, v in self.filters if (normalize(c), normalize(v)) != key]
        else:
            self.filters.append((category, value))
        self._refresh_results()

    def _clear_filters(self, sender, event):
        self.filters = []
        self._refresh_results()

    def _refresh_results(self):
        self.results.Rows.Clear()
        if not self.filters:
            self.filter_label.Text = "Click a tag to find matching comics. Multiple tags use AND."
            self.result_books = []
            return

        self.filter_label.Text = "Filters: " + " + ".join(["%s:%s" % (c, v) for c, v in self.filters])
        matches = []
        for book in self.library_books:
            if book_matches_filters(book, self.filters):
                matches.append(book)

        self.result_books = matches
        for book in matches[:500]:
            row_index = self.results.Rows.Add(
                title_for_book(book),
                safe_text(get_field(book, "Series")),
                safe_text(get_field(book, "Number")),
                safe_text(get_field(book, "Publisher")),
                safe_text(get_field(book, "Format")),
            )
            self.results.Rows[row_index].Tag = book

    def _selected_result_book(self):
        if self.results.SelectedRows.Count == 0:
            return None
        return self.results.SelectedRows[0].Tag

    def _show_selected_result_info(self, sender, event):
        book = self._selected_result_book()
        if book is not None:
            show_book_info(book)

    def _open_selected_result(self, sender, event):
        book = self._selected_result_book()
        if book is not None:
            open_book(book)

    def _result_double_click(self, sender, event):
        if event.RowIndex >= 0:
            book = self.results.Rows[event.RowIndex].Tag
            if book is not None:
                open_book(book)


def GalleryTagPanel(books):
    selected = list(books or [])
    if not selected:
        MessageBox.Show("Select at least one comic first.", "Gallery Tag Panel")
        return

    library = get_library_books(selected)
    form = GalleryTagPanelForm(selected, library)
    try:
        form.ShowDialog(ComicRack.MainWindow)
    except Exception:
        form.ShowDialog()
