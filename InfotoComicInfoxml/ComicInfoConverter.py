#!/usr/bin/env python3
"""
ComicInfo.xml Generator for ExHentai/SadPanda Gallery Metadata
Parses an info.txt file and outputs a ComicInfo.xml file.
"""

import re
import sys
import os
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom
from dataclasses import dataclass, field
from typing import List, Dict, Optional


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


def parse_info_txt(filepath: str) -> GalleryMetadata:
    """Parse the info.txt file into GalleryMetadata."""
    meta = GalleryMetadata()
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
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
    
    explicit_tags = {
        'anal', 'blowjob', 'nakadashi', 'bukkake', 'gang rape', 'shotacon',
        'lolicon', 'scat', 'smegma', 'futanari', 'shemale', 'impregnation',
        'x-ray', 'ahegao', 'cumflation', 'facesitting', 'tentacles',
        'anal intercourse', 'dickgirl on female', 'yuri', 'bondage',
        'masturbation', 'lactation', 'body writing', 'ball sucking',
    }
    
    for tag in all_tags_lower:
        if tag in explicit_tags:
            return 'Adults Only 18+'
    
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
    
    if 'western imageset' in all_tags_lower