import clr
clr.AddReferenceByPartialName("System")
clr.AddReferenceByPartialName("System.Drawing")
clr.AddReferenceByPartialName("System.Windows.Forms")

from System.Diagnostics import Process
from System.Drawing import Color, ContentAlignment, Font, FontStyle, Size
from System.Windows.Forms import (
    AutoSizeMode,
    BorderStyle,
    Button,
    DataGridView,
    DataGridViewAutoSizeColumnsMode,
    DataGridViewSelectionMode,
    DockStyle,
    FixedPanel,
    FlatStyle,
    FlowLayoutPanel,
    Form,
    FormStartPosition,
    Label,
    MessageBox,
    Orientation,
    Padding,
    Panel,
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


OPEN_PANELS = []
COMICRACK_HOST = None


def set_comicrack(host):
    global COMICRACK_HOST
    COMICRACK_HOST = host


def get_comicrack():
    if COMICRACK_HOST is not None:
        return COMICRACK_HOST
    try:
        return ComicRack
    except NameError:
        return None


def book_identity(book):
    for field_name in ["Id", "FilePath", "FileNameWithExtension", "FileName"]:
        value = safe_text(get_field(book, field_name))
        if value:
            return field_name + ":" + normalize(value)
    return "object:" + safe_text(book.GetHashCode())


def get_library_books(seed_books):
    selected = list(seed_books or [])
    host = get_comicrack()
    if host is None:
        return selected, "ComicRack library unavailable; searching the current comic only"

    try:
        library = list(host.App.GetLibraryBooks())
    except Exception as error:
        return selected, "Library query failed; searching the current comic only (%s)" % safe_text(error)

    merged = []
    seen = set()
    for book in library + selected:
        identity = book_identity(book)
        if identity in seen:
            continue
        seen.add(identity)
        merged.append(book)

    extra_count = len(merged) - len(library)
    note = "%d library comics loaded" % len(library)
    if extra_count:
        note += " + current file"
    return merged, note


def show_book_info(book):
    host = get_comicrack()
    if host is None:
        return False
    try:
        host.App.ShowComicInfo([book])
        return True
    except Exception:
        return False


def open_book(book):
    host = get_comicrack()
    if host is None:
        return

    try:
        if host.OpenBooks.Open(book, True, 0):
            return
    except Exception:
        pass

    for target_name in ["ComicDisplay", "MainWindow"]:
        try:
            target = getattr(host, target_name)
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


def remember_panel(form):
    OPEN_PANELS.append(form)

    def remove_panel(sender, event):
        try:
            OPEN_PANELS.remove(sender)
        except ValueError:
            pass

    form.FormClosed += remove_panel


def close_open_panels():
    for form in list(OPEN_PANELS):
        try:
            if not form.IsDisposed:
                form.Close()
        except Exception:
            pass
    OPEN_PANELS[:] = []


class GalleryTagPanelForm(Form):
    def __init__(self, selected_books, library_books, library_note):
        Form.__init__(self)
        self.selected_books = list(selected_books or [])
        self.library_books = list(library_books or self.selected_books)
        self.library_note = library_note
        self.current_book = self.selected_books[0] if self.selected_books else None
        self.preview_book = self.current_book
        self.filters = []
        self.result_books = []
        self.tag_buttons = []
        self.updating_results = False

        self.Text = "Gallery Tag Panel"
        self.StartPosition = FormStartPosition.CenterScreen
        self.Size = Size(1220, 760)
        self.MinimumSize = Size(940, 600)

        self._build_ui()
        self._load_current_book()
        self.Shown += self._apply_initial_layout

    def _build_ui(self):
        self.split = SplitContainer()
        self.split.Dock = DockStyle.Fill
        self.split.Orientation = Orientation.Vertical
        self.split.FixedPanel = FixedPanel.Panel1
        self.Controls.Add(self.split)
        self.split.Size = self.ClientSize
        self.split.SplitterDistance = 360
        self.split.Panel1MinSize = 300
        self.split.Panel2MinSize = 560

        left = TableLayoutPanel()
        left.Dock = DockStyle.Fill
        left.RowCount = 3
        left.ColumnCount = 1
        left.Padding = Padding(10)
        left.RowStyles.Add(RowStyle(SizeType.Absolute, 330))
        left.RowStyles.Add(RowStyle(SizeType.Absolute, 72))
        left.RowStyles.Add(RowStyle(SizeType.Percent, 100))
        self.split.Panel1.Controls.Add(left)

        cover_host = Panel()
        cover_host.Dock = DockStyle.Fill
        cover_host.BackColor = Color.FromArgb(245, 245, 245)
        left.Controls.Add(cover_host, 0, 0)

        self.cover = PictureBox()
        self.cover.Dock = DockStyle.Fill
        self.cover.BorderStyle = BorderStyle.FixedSingle
        self.cover.SizeMode = PictureBoxSizeMode.Zoom
        cover_host.Controls.Add(self.cover)

        self.cover_placeholder = Label()
        self.cover_placeholder.Dock = DockStyle.Fill
        self.cover_placeholder.Text = "Loading cover..."
        self.cover_placeholder.TextAlign = ContentAlignment.MiddleCenter
        self.cover_placeholder.ForeColor = Color.FromArgb(100, 100, 100)
        self.cover_placeholder.BackColor = Color.FromArgb(245, 245, 245)
        cover_host.Controls.Add(self.cover_placeholder)
        self.cover_placeholder.BringToFront()

        self.title_label = Label()
        self.title_label.AutoSize = False
        self.title_label.Dock = DockStyle.Top
        self.title_label.Height = 54
        self.title_label.Font = Font("Segoe UI", 12, FontStyle.Bold)
        self.title_label.Padding = Padding(0, 8, 0, 4)
        left.Controls.Add(self.title_label, 0, 1)

        self.meta_box = TextBox()
        self.meta_box.Dock = DockStyle.Fill
        self.meta_box.Multiline = True
        self.meta_box.ReadOnly = True
        self.meta_box.TabStop = False
        self.meta_box.ScrollBars = ScrollBars.Vertical
        left.Controls.Add(self.meta_box, 0, 2)

        right = TableLayoutPanel()
        right.Dock = DockStyle.Fill
        right.RowCount = 3
        right.ColumnCount = 1
        right.Padding = Padding(10)
        right.RowStyles.Add(RowStyle(SizeType.Absolute, 58))
        right.RowStyles.Add(RowStyle(SizeType.Percent, 52))
        right.RowStyles.Add(RowStyle(SizeType.Percent, 48))
        self.split.Panel2.Controls.Add(right)

        self.filter_label = Label()
        self.filter_label.AutoSize = False
        self.filter_label.Dock = DockStyle.Top
        self.filter_label.Height = 52
        self.filter_label.Font = Font("Segoe UI", 9, FontStyle.Bold)
        self.filter_label.AutoEllipsis = True
        right.Controls.Add(self.filter_label, 0, 0)

        self.tags_panel = FlowLayoutPanel()
        self.tags_panel.Dock = DockStyle.Fill
        self.tags_panel.AutoScroll = True
        self.tags_panel.WrapContents = True
        right.Controls.Add(self.tags_panel, 0, 1)

        results_area = TableLayoutPanel()
        results_area.Dock = DockStyle.Fill
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

        self.result_summary = Label()
        self.result_summary.AutoSize = True
        self.result_summary.Margin = Padding(14, 9, 0, 0)
        result_actions.Controls.Add(self.result_summary)

        self.results = DataGridView()
        self.results.Dock = DockStyle.Fill
        self.results.AllowUserToAddRows = False
        self.results.AllowUserToDeleteRows = False
        self.results.ReadOnly = True
        self.results.SelectionMode = DataGridViewSelectionMode.FullRowSelect
        self.results.MultiSelect = False
        self.results.AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.Fill
        self.results.RowHeadersVisible = False
        self.results.BackgroundColor = Color.White
        self.results.Columns.Add("Title", "Title")
        self.results.Columns.Add("Series", "Series")
        self.results.Columns.Add("Issue", "#")
        self.results.Columns.Add("Publisher", "Publisher")
        self.results.Columns.Add("Format", "Format")
        self.results.Columns[0].FillWeight = 44
        self.results.Columns[1].FillWeight = 24
        self.results.Columns[2].FillWeight = 8
        self.results.Columns[3].FillWeight = 14
        self.results.Columns[4].FillWeight = 10
        self.results.SelectionChanged += self._result_selection_changed
        self.results.CellDoubleClick += self._result_double_click
        results_area.Controls.Add(self.results, 0, 1)

    def _apply_initial_layout(self, sender, event):
        target = int(self.split.Width * 0.3)
        target = max(320, min(420, target))
        maximum = self.split.Width - self.split.Panel2MinSize - self.split.SplitterWidth
        if maximum >= self.split.Panel1MinSize:
            self.split.SplitterDistance = min(target, maximum)

    def _load_current_book(self):
        if self.current_book is None:
            self.title_label.Text = "Select one or more comics, then run Automation > GalleryTagPanel."
            self.meta_box.Text = ""
            return

        self._show_book_details(self.current_book)
        self._render_tags()
        self._refresh_results()

    def _show_book_details(self, book):
        if book is None:
            return

        self.preview_book = book
        self.title_label.Text = title_for_book(book)
        self.meta_box.Text = "\r\n".join(["%s: %s" % row for row in metadata_rows(book)])
        self.meta_box.SelectionLength = 0
        self._load_cover(book)

    def _load_cover(self, book):
        self.cover.Image = None
        self.cover_placeholder.Text = "Loading cover..."
        self.cover_placeholder.Visible = True
        self.cover_placeholder.BringToFront()

        host = get_comicrack()
        if host is None:
            self.cover_placeholder.Text = "Cover unavailable\r\nComicRack API was not connected"
            return

        image = None
        for method_name in ["GetComicThumbnail", "GetComicPage"]:
            try:
                image = getattr(host.App, method_name)(book, 0)
                if image is not None:
                    break
            except Exception:
                pass

        if image is None:
            self.cover_placeholder.Text = "Cover preview unavailable"
            return

        self.cover.Image = image
        self.cover_placeholder.Visible = False

    def _render_tags(self):
        self.tags_panel.Controls.Clear()
        self.tag_buttons = []
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
                button.FlatStyle = FlatStyle.Flat
                button.Margin = Padding(2, 2, 4, 2)
                button.Tag = (category, value)
                button.Click += self._tag_clicked
                self.tags_panel.Controls.Add(button)
                self.tag_buttons.append(button)

        self._update_tag_buttons()

    def _update_tag_buttons(self):
        active = [(normalize(c), normalize(v)) for c, v in self.filters]
        for button in self.tag_buttons:
            category, value = button.Tag
            selected = (normalize(category), normalize(value)) in active
            button.FlatAppearance.BorderSize = 2 if selected else 1
            button.FlatAppearance.BorderColor = Color.FromArgb(30, 30, 30) if selected else button.BackColor

    def _tag_clicked(self, sender, event):
        category, value = sender.Tag
        key = (normalize(category), normalize(value))
        existing = [(normalize(c), normalize(v)) for c, v in self.filters]
        if key in existing:
            self.filters = [(c, v) for c, v in self.filters if (normalize(c), normalize(v)) != key]
        else:
            self.filters.append((category, value))
        self._update_tag_buttons()
        self._refresh_results()

    def _clear_filters(self, sender, event):
        self.filters = []
        self._update_tag_buttons()
        self._refresh_results()

    def _refresh_results(self):
        self.updating_results = True
        self.results.Rows.Clear()
        if not self.filters:
            self.filter_label.Text = self.library_note + ". Click tags to find matching comics; multiple tags use AND."
            self.result_summary.Text = "No filters selected"
            self.result_books = []
            self.updating_results = False
            self._show_book_details(self.current_book)
            return

        filter_text = " + ".join(["%s:%s" % (c, v) for c, v in self.filters])
        matches = []
        for book in self.library_books:
            if book_matches_filters(book, self.filters):
                matches.append(book)

        matches = sorted(matches, key=lambda book: normalize(title_for_book(book)))
        self.result_books = matches
        self.filter_label.Text = "Filters: " + filter_text
        shown = min(len(matches), 500)
        self.result_summary.Text = "%d matches across %d searchable comics" % (
            len(matches),
            len(self.library_books),
        )
        if len(matches) > shown:
            self.result_summary.Text += " (%d shown)" % shown
        for book in matches[:500]:
            row_index = self.results.Rows.Add(
                title_for_book(book),
                safe_text(get_field(book, "Series")),
                safe_text(get_field(book, "Number")),
                safe_text(get_field(book, "Publisher")),
                safe_text(get_field(book, "Format")),
            )
            self.results.Rows[row_index].Tag = book

        self.updating_results = False
        if self.results.Rows.Count > 0:
            self.results.CurrentCell = self.results.Rows[0].Cells[0]
            self.results.Rows[0].Selected = True
            self._show_book_details(self.results.Rows[0].Tag)
        else:
            self._show_book_details(self.current_book)

    def _selected_result_book(self):
        if self.results.SelectedRows.Count == 0:
            return None
        return self.results.SelectedRows[0].Tag

    def _result_selection_changed(self, sender, event):
        if self.updating_results:
            return
        book = self._selected_result_book()
        if book is not None:
            self._show_book_details(book)

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


#@Name GalleryTagPanel
#@Key GalleryTagPanel
#@Hook Books
#@Enabled true
#@Description E-H style tag browser panel for the selected comic.
def GalleryTagPanel(books):
    try:
        set_comicrack(ComicRack)
    except NameError:
        pass
    show_gallery_tag_panel(books, modal=True)


def show_gallery_tag_panel(books, modal=True, replace_existing=False):
    selected = list(books or [])
    if not selected:
        MessageBox.Show("Select at least one comic first.", "Gallery Tag Panel")
        return

    if replace_existing:
        close_open_panels()

    library, library_note = get_library_books(selected)
    form = GalleryTagPanelForm(selected, library, library_note)
    host = get_comicrack()
    if modal:
        try:
            form.ShowDialog(host.MainWindow)
        except Exception:
            form.ShowDialog()
        return

    remember_panel(form)
    try:
        form.Show(host.MainWindow)
    except Exception:
        form.Show()
    try:
        form.Activate()
    except Exception:
        pass
