# Shared helpers for the GalleryTagPanel ComicRack script.
#
# This file is intentionally IronPython 2.7 friendly so it can run inside
# ComicRack / ComicRack Community Edition.

TAG_PREFIXES = {
    "parody": "Parody-",
    "character": "Character-",
    "artist": "Artist-",
    "female": "Female-",
    "male": "Male-",
    "mixed": "Mixed-",
    "other": "Other-",
    "language": "Language-",
    "group": "Group-",
    "cosplayer": "Cosplayer-",
    "reclass": "Reclass-",
    "temp": "Temp-",
}

TAG_PREFIX_TO_CATEGORY = {}
for _category, _prefix in TAG_PREFIXES.items():
    TAG_PREFIX_TO_CATEGORY[_prefix.lower()] = _category


DISPLAY_CATEGORY_ORDER = [
    "artist",
    "group",
    "parody",
    "character",
    "female",
    "male",
    "mixed",
    "genre",
    "format",
    "publisher",
    "story arc",
    "series group",
    "team",
    "location",
    "language",
    "other",
]


FIELD_CATEGORY_MAP = [
    ("artist", ["Writer", "Penciller", "Inker", "Colorist", "Letterer", "CoverArtist"]),
    ("parody", ["Series", "AlternateSeries"]),
    ("character", ["Characters"]),
    ("genre", ["Genre"]),
    ("format", ["Format"]),
    ("publisher", ["Publisher", "Imprint"]),
    ("story arc", ["StoryArc"]),
    ("series group", ["SeriesGroup", "MainCharacterOrTeam"]),
    ("team", ["Teams"]),
    ("location", ["Locations"]),
    ("language", ["LanguageISO", "Language"]),
]


def safe_text(value):
    if value is None:
        return ""
    try:
        return unicode(value).strip()
    except NameError:
        return str(value).strip()


def normalize(value):
    return " ".join(safe_text(value).split()).lower()


def split_values(value):
    text = safe_text(value)
    if not text:
        return []

    parts = text.replace(";", ",").replace("|", ",").split(",")
    result = []
    seen = set()
    for part in parts:
        cleaned = " ".join(part.split())
        key = normalize(cleaned)
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result


def get_field(book, field_name):
    try:
        value = getattr(book, field_name)
        if value is not None:
            return value
    except Exception:
        pass

    try:
        return book.GetCustomValue(field_name)
    except Exception:
        return ""


def clean_gallery_tag(raw_tag):
    text = safe_text(raw_tag)
    if "|" in text:
        text = text.split("|", 1)[0].strip()
    return " ".join(text.split())


def add_tag(tag_map, category, value):
    clean_category = normalize(category)
    clean_value = clean_gallery_tag(value)
    if not clean_category or not clean_value:
        return

    values = tag_map.setdefault(clean_category, [])
    if normalize(clean_value) not in [normalize(item) for item in values]:
        values.append(clean_value)


def parse_prefixed_tags(tags_value):
    tag_map = {}
    for raw_tag in split_values(tags_value):
        raw_key = raw_tag.lower()
        matched = False
        for prefix, category in TAG_PREFIX_TO_CATEGORY.items():
            if raw_key.startswith(prefix):
                add_tag(tag_map, category, raw_tag[len(prefix):])
                matched = True
                break
        if not matched:
            add_tag(tag_map, "tag", raw_tag)
    return tag_map


def get_book_tags(book):
    tag_map = parse_prefixed_tags(get_field(book, "Tags"))

    for category, field_names in FIELD_CATEGORY_MAP:
        for field_name in field_names:
            for value in split_values(get_field(book, field_name)):
                add_tag(tag_map, category, value)

    return tag_map


def ordered_categories(tag_map):
    ordered = []
    used = set()
    for category in DISPLAY_CATEGORY_ORDER:
        if category in tag_map:
            ordered.append(category)
            used.add(category)

    for category in sorted(tag_map.keys()):
        if category not in used:
            ordered.append(category)
    return ordered


def book_has_filter(book, category, value):
    wanted_category = normalize(category)
    wanted_value = normalize(value)
    tag_map = get_book_tags(book)
    for found in tag_map.get(wanted_category, []):
        if normalize(found) == wanted_value:
            return True
    return False


def book_matches_filters(book, filters):
    for category, value in filters:
        if not book_has_filter(book, category, value):
            return False
    return True


def title_for_book(book):
    title = safe_text(get_field(book, "Title"))
    series = safe_text(get_field(book, "Series"))
    number = safe_text(get_field(book, "Number"))

    if title:
        return title
    if series and number:
        return "%s #%s" % (series, number)
    if series:
        return series
    return safe_text(get_field(book, "FileNameWithExtension")) or safe_text(get_field(book, "FileName"))


def metadata_rows(book):
    rows = []
    field_pairs = [
        ("Series", "Series"),
        ("Issue", "Number"),
        ("Publisher", "Publisher"),
        ("Format", "Format"),
        ("Language", "LanguageISO"),
        ("Pages", "PageCount"),
        ("Rating", "Rating"),
        ("File", "FileNameWithExtension"),
    ]
    for label, field_name in field_pairs:
        value = safe_text(get_field(book, field_name))
        if value and value != "-1":
            rows.append((label, value))
    return rows
