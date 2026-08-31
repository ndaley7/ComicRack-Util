#!/usr/bin/env python3
"""
ComicInfo.xml Generator for ExHentai/SadPanda Gallery Metadata
Parses an info.txt file and outputs a ComicInfo.xml file.
"""

import re
import sys
import argparse
import codecs
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from xml.etree.ElementTree import Element, ParseError, SubElement, parse, tostring
from xml.dom import minidom
from dataclasses import dataclass, field
from typing import List, Dict


TAG_BANK_FILENAME = 'UniversalTagBank.xml'


_CONTENT_RATING_TERMS_ENCODED = (
    'nany',
    'oybjwbo',
    'anxnqnfuv',
    'ohxxnxr',
    'tnat encr',
    'fpng',
    'fzrtzn',
    'shgnanev',
    'furznyr',
    'vzcertangvba',
    'k-enl',
    'nurtnb',
    'phzsyngvba',
    'snprfvggvat',
    'gragnpyrf',
    'nany vagrepbhefr',
    'qvpxtvey ba srznyr',
    'lhev',
    'obaqntr',
    'znfgheongvba',
    'ynpgngvba',
    'obql jevgvat',
    'onyy fhpxvat',
)

_GENRE_TRIGGER_TERMS_ENCODED = (
    'nany',
    'oybjwbo',
    'anxnqnfuv',
    'shgnanev',
    'furznyr',
    'nurtnb',
    'ohxxnxr',
    'tnat encr',
    'fpng',
    'fzrtzn',
)

_RESTRICTED_RATING_ENCODED = 'Nqhygf Bayl 18+'
_AUDIENCE_GENRE_ENCODED = 'Nqhyg'
_GENRE_LABELS_ENCODED = ('Uragnv', 'Cbeabtencul')


def configure_text_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding='utf-8', errors='backslashreplace')


def decode_text(value: str) -> str:
    return codecs.decode(value, 'rot_13')


def decode_terms(values) -> set:
    return {decode_text(value) for value in values}


@dataclass
class GalleryMetadata:
    title: str = ""
    url: str = ""
    category: str = ""
    uploader: str = ""
    posted: str = ""
    parent: str = ""
    visible: str = ""
    language: str = ""
    file_size: str = ""
    length: str = ""
    favorited: str = ""
    rating: str = ""
    tags: Dict[str, List[str]] = field(default_factory=dict)
    uploader_comment: str = ""
    social_links: List[str] = field(default_factory=list)


def parse_info_content(content: str) -> GalleryMetadata:
    """Parse info.txt content into GalleryMetadata."""
    meta = GalleryMetadata()
    lines = content.split('\n')
    
    # Title is the first non-empty line
    for line in lines:
        line = line.strip()
        if line:
            meta.title = line
            break
    
    # URL is the first line starting with http
    for line in lines:
        line = line.strip()
        if line.startswith('http'):
            meta.url = line
            break
    
    # Parse key-value pairs (Field: Value format)
    field_map = {
        'Category': 'category',
        'Uploader': 'uploader',
        'Posted': 'posted',
        'Parent': 'parent',
        'Visible': 'visible',
        'Language': 'language',
        'File Size': 'file_size',
        'Length': 'length',
        'Favorited': 'favorited',
        'Rating': 'rating',
    }
    
    in_tags_section = False
    in_uploader_comment = False
    current_tag_category = None
    
    for line in lines:
        stripped = line.strip()
        
        # Check for Tags section
        if stripped.lower() == 'tags:':
            in_tags_section = True
            in_uploader_comment = False
            continue
        
        # Check for Uploader Comment section
        if stripped.lower().startswith('uploader comment'):
            in_tags_section = False
            in_uploader_comment = True
            continue
        
        # Parse tags
        if in_tags_section:
            if stripped.startswith('>'):
                tag_line = stripped.lstrip('>').strip()
                if ':' in tag_line:
                    parts = tag_line.split(':', 1)
                    current_tag_category = parts[0].strip().lower()
                    tag_values = parts[1].strip()
                    if current_tag_category not in meta.tags:
                        meta.tags[current_tag_category] = []
                    for tag in tag_values.split(','):
                        tag = tag.strip()
                        if tag:
                            meta.tags[current_tag_category].append(tag)
                elif current_tag_category:
                    # Continuation of previous category's tags
                    for tag in tag_line.split(','):
                        tag = tag.strip()
                        if tag:
                            meta.tags[current_tag_category].append(tag)
            elif stripped == '' and current_tag_category is not None:
                # Empty line might end tags section or just be a gap
                pass
            elif not stripped.startswith('>'):
                # Non-tag line after tags, might be uploader comment or end
                pass
            continue
        
        # Parse uploader comment and social links
        if in_uploader_comment:
            if re.match(r'^(Page|Image)\s+\d+:', stripped):
                in_uploader_comment = False
                continue
            if stripped.startswith('Downloaded at ') or stripped.startswith('Generated by '):
                in_uploader_comment = False
                continue
            if stripped.startswith('http'):
                meta.social_links.append(stripped)
            elif stripped:
                meta.uploader_comment += (stripped + '\n')
            continue
        
        # Parse standard fields
        for field_name, attr_name in field_map.items():
            if stripped.startswith(field_name + ':'):
                value = stripped[len(field_name) + 1:].strip()
                setattr(meta, attr_name, value)
                break
    
    return meta


def parse_info_txt(filepath: str) -> GalleryMetadata:
    """Parse the info.txt file into GalleryMetadata."""
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        return parse_info_content(f.read())


def normalize_tag_bank_category(category: str) -> str:
    return re.sub(r'\s+', ' ', category.strip().lower())


def normalize_tag_bank_tag(tag: str) -> str:
    return re.sub(r'\s+', ' ', tag.strip())


def load_tag_bank(tag_bank_path: Path) -> Dict[str, List[str]]:
    """Load an existing universal tag bank XML file."""
    tag_bank: Dict[str, List[str]] = {}
    if not tag_bank_path.exists():
        return tag_bank

    try:
        root = parse(tag_bank_path).getroot()
    except ParseError as exc:
        raise ValueError(f'Could not parse tag bank XML: {tag_bank_path}: {exc}') from exc

    for category_element in root.findall('Category'):
        category = normalize_tag_bank_category(category_element.get('name', ''))
        if not category:
            continue

        category_tags = tag_bank.setdefault(category, [])
        seen = {tag.casefold() for tag in category_tags}
        for tag_element in category_element.findall('Tag'):
            tag = normalize_tag_bank_tag(tag_element.text or '')
            key = tag.casefold()
            if tag and key not in seen:
                category_tags.append(tag)
                seen.add(key)

    return tag_bank


def merge_tags_into_bank(tag_bank: Dict[str, List[str]], tags: Dict[str, List[str]]) -> int:
    """Add unseen tags to an in-memory tag bank."""
    added = 0
    for category, tag_list in tags.items():
        clean_category = normalize_tag_bank_category(category)
        if not clean_category:
            continue

        bank_tags = tag_bank.setdefault(clean_category, [])
        seen = {tag.casefold() for tag in bank_tags}
        for tag in tag_list:
            clean_tag = normalize_tag_bank_tag(tag)
            key = clean_tag.casefold()
            if clean_tag and key not in seen:
                bank_tags.append(clean_tag)
                seen.add(key)
                added += 1
    return added


def build_tag_bank_xml(tag_bank: Dict[str, List[str]]) -> str:
    """Build a sorted universal tag bank XML document."""
    root = Element('UniversalTagBank')

    for category in sorted(tag_bank.keys(), key=lambda value: (value.casefold(), value)):
        tags = tag_bank[category]
        if not tags:
            continue
        category_element = SubElement(root, 'Category', {'name': category})
        unique_tags = unique_preserve_order(tags)
        for tag in sorted(unique_tags, key=lambda value: (value.casefold(), value)):
            SubElement(category_element, 'Tag').text = tag

    rough_string = tostring(root, encoding='utf-8')
    pretty = minidom.parseString(rough_string).toprettyxml(indent='  ', encoding='utf-8')
    return pretty.decode('utf-8')


def update_universal_tag_bank(source_dir: Path, tags: Dict[str, List[str]]) -> int:
    """Add new tags to the universal tag bank in the source directory."""
    if not any(tags.values()):
        return 0

    tag_bank_path = source_dir / TAG_BANK_FILENAME
    tag_bank = load_tag_bank(tag_bank_path)
    added = merge_tags_into_bank(tag_bank, tags)
    if added:
        tag_bank_path.write_text(build_tag_bank_xml(tag_bank), encoding='utf-8', newline='\n')
    return added


def build_prefixed_tags(tags: Dict[str, List[str]]) -> List[str]:
    """Build a list of tags with category prefixes."""
    prefixed_tags = []
    
    # Category mapping for prefixes
    prefix_map = {
        'parody': 'Parody-',
        'character': 'Character-',
        'artist': 'Artist-',
        'female': 'Female-',
        'male': 'Male-',
        'mixed': 'Mixed-',
        'other': 'Other-',
        'language': 'Language-',
        'group': 'Group-',
        'cosplayer': 'Cosplayer-',
        'reclass': 'Reclass-',
        'temp': 'Temp-',
    }
    
    for category, tag_list in tags.items():
        prefix = prefix_map.get(category, f'{category.capitalize()}-')
        for tag in tag_list:
            # Clean up the tag: remove pipe-separated alternate names
            # Keep the first option before the pipe
            clean_tag = tag.split('|')[0].strip()
            prefixed_tags.append(f'{prefix}{clean_tag}')
    
    return prefixed_tags


def extract_characters(tags: Dict[str, List[str]]) -> List[str]:
    """Extract and clean character names from tags."""
    characters = []
    if 'character' in tags:
        for char in tags['character']:
            # Keep both names if pipe-separated, but clean them up
            names = char.split('|')
            for name in names:
                name = name.strip()
                if name:
                    # Title-case the character name
                    characters.append(name.title())
    return characters


def extract_parodies(tags: Dict[str, List[str]]) -> List[str]:
    """Extract parody/series names from tags."""
    parodies = []
    if 'parody' in tags:
        for parody in tags['parody']:
            clean = parody.split('|')[0].strip()
            parodies.append(clean.title())
    return parodies


def extract_artist(tags: Dict[str, List[str]]) -> str:
    """Extract artist name from tags."""
    if 'artist' in tags and tags['artist']:
        return tags['artist'][0].strip()
    return ""


def determine_age_rating(tags: Dict[str, List[str]]) -> str:
    """Determine age rating based on content tags."""
    all_tags_lower = []
    for cat_tags in tags.values():
        all_tags_lower.extend([t.lower() for t in cat_tags])
    
    rating_terms = decode_terms(_CONTENT_RATING_TERMS_ENCODED)
    
    for tag in all_tags_lower:
        if tag in rating_terms:
            return decode_text(_RESTRICTED_RATING_ENCODED)
    
    return 'Unknown'


def determine_genre(category: str, tags: Dict[str, List[str]]) -> str:
    """Determine genre string from category and tags."""
    genres = []
    
    if category:
        genres.append(category)
    
    # Check for imageset
    all_tags_lower = []
    for cat_tags in tags.values():
        all_tags_lower.extend([t.lower() for t in cat_tags])
    
    if 'western imageset' in all_tags_lower or 'imageset' in all_tags_lower:
        genres.append('Imageset')
    
    
    genre_trigger_terms = decode_terms(_GENRE_TRIGGER_TERMS_ENCODED)
    if any(tag in all_tags_lower for tag in genre_trigger_terms):
        genres.append(decode_text(_AUDIENCE_GENRE_ENCODED))
        genres.extend(decode_text(label) for label in _GENRE_LABELS_ENCODED)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_genres = []
    for g in genres:
        if g not in seen:
            seen.add(g)
            unique_genres.append(g)
    
    return ', '.join(unique_genres) if unique_genres else 'Adult'


def parse_page_count(length: str) -> int:
    """Extract page count from the Length field."""
    match = re.search(r'(\d+)', length)
    if match:
        return int(match.group(1))
    return 0


def parse_language_iso(language: str, tags: Dict[str, List[str]]) -> str:
    """Determine ISO language code."""
    lang_lower = language.lower().strip()
    
    lang_map = {
        'english': 'en',
        'japanese': 'ja',
        'chinese': 'zh',
        'korean': 'ko',
        'french': 'fr',
        'german': 'de',
        'spanish': 'es',
        'italian': 'it',
        'portuguese': 'pt',
        'russian': 'ru',
        'dutch': 'nl',
        'polish': 'pl',
        'hungarian': 'hu',
        'czech': 'cs',
        'thai': 'th',
        'vietnamese': 'vi',
        'indonesian': 'id',
        'arabic': 'ar',
        'turkish': 'tr',
        'finnish': 'fi',
        'swedish': 'sv',
        'norwegian': 'no',
        'danish': 'da',
        'translation': 'en',
    }
    
    # Check the language field
    for lang_name, iso in lang_map.items():
        if lang_name in lang_lower:
            return iso
    
    # Check the language tags
    if 'language' in tags:
        for lang_tag in tags['language']:
            lang_tag_lower = lang_tag.lower().strip()
            for lang_name, iso in lang_map.items():
                if lang_name in lang_tag_lower:
                    return iso
    
    return 'en'  # Default to English


def is_manga(category: str) -> str:
    """Determine if this is manga or western content."""
    if category.lower() in ('western', 'imageset', 'artist cg', 'game cg'):
        return 'No'
    return 'Yes'


def is_black_and_white(tags: Dict[str, List[str]]) -> str:
    """Guess if content is black and white based on category."""
    # Western art is typically colored
    # Can't definitively determine this from tags alone
    return 'No'


def build_notes(meta: GalleryMetadata) -> str:
    """Build the Notes field from metadata."""
    parts = []
    
    if meta.url:
        parts.append(f'Source: {meta.url}')
    if meta.uploader:
        parts.append(f'Uploader: {meta.uploader}')
    if meta.posted:
        parts.append(f'Posted: {meta.posted}')
    if meta.parent:
        parts.append(f'Parent: {meta.parent}')
    if meta.favorited:
        parts.append(f'Favorited: {meta.favorited}')
    if meta.rating:
        parts.append(f'Rating: {meta.rating}')
    if meta.file_size:
        parts.append(f'File Size: {meta.file_size}')
    
    # Add social links
    if meta.social_links:
        link_parts = []
        for link in meta.social_links:
            # Try to identify the platform
            if 'twitter.com' in link or 'x.com' in link:
                handle = link.rstrip('/').split('/')[-1]
                link_parts.append(f'Twitter @{handle}')
            elif 'bsky.social' in link or 'bluesky' in link:
                handle = link.rstrip('/').split('/')[-1]
                link_parts.append(f'Bluesky {handle}')
            elif 'baraag.net' in link:
                handle = link.rstrip('/').split('/')[-1]
                link_parts.append(f'Baraag @{handle}')
            elif 'subscribestar' in link:
                link_parts.append(f'SubscribeStar {link}')
            elif 'fanbox' in link:
                link_parts.append(f'Fanbox {link}')
            elif 'patreon' in link:
                link_parts.append(f'Patreon {link}')
            else:
                link_parts.append(link)
        parts.append(f'Artist links: {", ".join(link_parts)}')
    
    return ' | '.join(parts)


def build_summary(meta: GalleryMetadata, tags: Dict[str, List[str]]) -> str:
    """Build a summary from available metadata."""
    parts = []
    
    # Add title context
    if meta.title:
        parts.append(meta.title)
    
    # Add page count
    if meta.length:
        parts.append(f'{parse_page_count(meta.length)} pages')
    
    # Add parody info if available
    parodies = extract_parodies(tags)
    if parodies:
        parts.append(f'Parodies: {", ".join(parodies)}')
    
    # Add character info if available
    characters = extract_characters(tags)
    if characters:
        parts.append(f'Characters: {", ".join(characters)}')
    
    return '. '.join(parts) + '.'


def parse_posted_date(posted: str) -> Dict[str, str]:
    """Extract ComicInfo date components from a posted timestamp."""
    match = re.match(r'(\d{4})-(\d{2})-(\d{2})', posted.strip())
    if not match:
        return {}
    year, month, day = match.groups()
    return {
        'Year': str(int(year)),
        'Month': str(int(month)),
        'Day': str(int(day)),
    }


def add_text(parent: Element, name: str, value) -> None:
    """Add an XML child if the value is meaningful."""
    if value is None:
        return
    text = str(value).strip()
    if not text:
        return
    SubElement(parent, name).text = text


def unique_preserve_order(values: List[str]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        normalized = value.strip()
        key = normalized.lower()
        if normalized and key not in seen:
            seen.add(key)
            result.append(normalized)
    return result


def build_comicinfo_xml(meta: GalleryMetadata) -> str:
    """Build a ComicInfo.xml document from parsed gallery metadata."""
    root = Element('ComicInfo')

    page_count = parse_page_count(meta.length)
    tags = unique_preserve_order(build_prefixed_tags(meta.tags))
    characters = unique_preserve_order(extract_characters(meta.tags))
    parodies = unique_preserve_order(extract_parodies(meta.tags))
    artist = extract_artist(meta.tags)

    add_text(root, 'Title', meta.title)
    if parodies:
        add_text(root, 'Series', ', '.join(parodies))
    add_text(root, 'Writer', artist)
    add_text(root, 'Penciller', artist)
    add_text(root, 'Genre', determine_genre(meta.category, meta.tags))
    add_text(root, 'Summary', build_summary(meta, meta.tags))
    if meta.uploader_comment.strip():
        add_text(root, 'Notes', build_notes(meta) + ' | Comment: ' + meta.uploader_comment.strip())
    else:
        add_text(root, 'Notes', build_notes(meta))
    add_text(root, 'Web', meta.url)
    add_text(root, 'PageCount', page_count if page_count else None)
    add_text(root, 'LanguageISO', parse_language_iso(meta.language, meta.tags))
    add_text(root, 'Manga', is_manga(meta.category))
    add_text(root, 'BlackAndWhite', is_black_and_white(meta.tags))
    add_text(root, 'AgeRating', determine_age_rating(meta.tags))
    add_text(root, 'Characters', ', '.join(characters))
    add_text(root, 'Tags', ', '.join(tags))
    add_text(root, 'ScanInformation', 'Generated from info.txt')

    for field_name, value in parse_posted_date(meta.posted).items():
        add_text(root, field_name, value)

    rough_string = tostring(root, encoding='utf-8')
    pretty = minidom.parseString(rough_string).toprettyxml(indent='  ', encoding='utf-8')
    return pretty.decode('utf-8')


def convert_file(info_path: Path, output_path: Path = None, overwrite: bool = False) -> Path:
    """Convert one info.txt file to ComicInfo.xml."""
    if not info_path.is_file():
        raise FileNotFoundError(f'Input file does not exist: {info_path}')

    destination = output_path or info_path.with_name('ComicInfo.xml')
    if destination.exists() and not overwrite:
        raise FileExistsError(f'Output already exists: {destination}. Use --force to replace it.')

    meta = parse_info_txt(str(info_path))
    xml = build_comicinfo_xml(meta)
    destination.write_text(xml, encoding='utf-8', newline='\n')
    update_universal_tag_bank(info_path.parent, meta.tags)
    return destination


def normalized_archive_name(name: str) -> str:
    return name.replace('\\', '/').lstrip('/')


def is_root_archive_file(name: str, expected_name: str) -> bool:
    normalized = normalized_archive_name(name)
    return '/' not in normalized and normalized.lower() == expected_name.lower()


def find_root_archive_file(names: List[str], expected_name: str) -> str:
    for name in names:
        if is_root_archive_file(name, expected_name):
            return name
    return ''


def convert_cbz_file(cbz_path: Path, force: bool = False) -> str:
    """Add ComicInfo.xml to a CBZ when root info.txt is present."""
    if not cbz_path.is_file():
        raise FileNotFoundError(f'Input file does not exist: {cbz_path}')
    if cbz_path.suffix.lower() != '.cbz':
        raise ValueError(f'Input file is not a .cbz archive: {cbz_path}')

    with zipfile.ZipFile(cbz_path, 'r') as source:
        names = source.namelist()
        info_entry = find_root_archive_file(names, 'info.txt')
        comicinfo_entry = find_root_archive_file(names, 'ComicInfo.xml')

        if not info_entry:
            return f'Skipped {cbz_path}: root info.txt not found.'
        if comicinfo_entry and not force:
            return f'Skipped {cbz_path}: root ComicInfo.xml already exists. Use --force to replace it.'

        content = source.read(info_entry).decode('utf-8-sig')
        meta = parse_info_content(content)
        xml = build_comicinfo_xml(meta)

        temp_handle, temp_name = tempfile.mkstemp(
            dir=str(cbz_path.parent),
            prefix=f'.{cbz_path.stem}.',
            suffix='.tmp',
        )
        os.close(temp_handle)
        temp_path = Path(temp_name)

    try:
        with zipfile.ZipFile(cbz_path, 'r') as source:
            with zipfile.ZipFile(temp_path, 'w') as destination:
                for item in source.infolist():
                    if is_root_archive_file(item.filename, 'ComicInfo.xml'):
                        continue
                    destination.writestr(item, source.read(item.filename))
                destination.writestr('ComicInfo.xml', xml)

        shutil.move(str(temp_path), str(cbz_path))
        update_universal_tag_bank(cbz_path.parent, meta.tags)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise

    action = 'Replaced' if comicinfo_entry else 'Added'
    return f'{action} ComicInfo.xml in {cbz_path}'


def find_info_files(path: Path, recursive: bool) -> List[Path]:
    """Resolve a file or directory argument into info.txt files."""
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise FileNotFoundError(f'Input path does not exist: {path}')

    pattern = '**/info.txt' if recursive else 'info.txt'
    return sorted(path.glob(pattern))


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Convert ExHentai/E-Hentai Downloader info.txt metadata to ComicInfo.xml.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            'Examples:\n'
            '  python ComicInfoConverter.py info.txt\n'
            '  python ComicInfoConverter.py gallery.cbz\n'
            '  python ComicInfoConverter.py gallery.cbz --force\n'
            '  python ComicInfoConverter.py "D:\\Comics\\Incoming" --recursive --force\n\n'
            'CBZ behavior:\n'
            '  Only a root-level info.txt is used.\n'
            '  Archives without root info.txt are skipped.\n'
            '  Existing root ComicInfo.xml entries are skipped unless --force is passed.'
        ),
    )
    parser.add_argument(
        'input',
        help='Path to an info.txt file, a .cbz archive, or a directory containing info.txt files.',
    )
    parser.add_argument(
        '-o',
        '--output',
        help='Output XML path. Only valid when converting a single info.txt file, not a .cbz archive.',
    )
    parser.add_argument(
        '-r',
        '--recursive',
        action='store_true',
        help='When input is a directory, find info.txt files recursively.',
    )
    parser.add_argument(
        '-f',
        '--force',
        action='store_true',
        help='Replace existing ComicInfo.xml output. Required to replace ComicInfo.xml inside a .cbz.',
    )
    parser.add_argument(
        '--overwrite',
        action='store_true',
        help='Compatibility alias for --force.',
    )
    return parser.parse_args(argv)


def main(argv: List[str] = None) -> int:
    configure_text_output()
    args = parse_args(argv or sys.argv[1:])
    input_path = Path(args.input)
    force = args.force or args.overwrite

    if input_path.is_file() and input_path.suffix.lower() == '.cbz':
        if args.output:
            print('--output cannot be used when converting a .cbz archive.', file=sys.stderr)
            return 1
        try:
            print(convert_cbz_file(input_path, force))
        except Exception as exc:
            print(f'Failed to convert {input_path}: {exc}', file=sys.stderr)
            return 1
        return 0

    info_files = find_info_files(input_path, args.recursive)

    if not info_files:
        print(f'No info.txt files found in {input_path}', file=sys.stderr)
        return 1
    if args.output and len(info_files) > 1:
        print('--output can only be used with a single input file.', file=sys.stderr)
        return 1

    for info_file in info_files:
        output_path = Path(args.output) if args.output else None
        try:
            destination = convert_file(info_file, output_path, force)
            print(f'Wrote {destination}')
        except Exception as exc:
            print(f'Failed to convert {info_file}: {exc}', file=sys.stderr)
            return 1

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
