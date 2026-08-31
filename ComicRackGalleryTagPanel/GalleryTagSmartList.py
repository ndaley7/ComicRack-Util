#@Name GalleryTagSmartList
#@Key GalleryTagSmartList
#@Hook CreateBookList
#@PCount 2
#@Enabled false
#@Description Smart-list helper: parameter 1 is category, parameter 2 is tag value.

from gallery_tag_core import book_has_filter, normalize


def GalleryTagSmartList(books, category, value):
    clean_category = normalize(category)
    clean_value = normalize(value)
    if not clean_category or not clean_value:
        return []

    result = []
    for book in books:
        if book_has_filter(book, clean_category, clean_value):
            result.append(book)
    return result
