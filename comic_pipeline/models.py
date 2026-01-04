"""Data models and enums"""

import os
import re
from enum import Enum


class FilenameFormat(Enum):
    """Enum for comic filename formats"""
    KAPOWARR = 1  # Series Name (Year) #001.cbz
    MYLAR = 2     # Series Name #001 (Year).cbz
    UNKNOWN = 3


class ComicFormat:
    """Class to represent comic format information"""
    
    def __init__(self, path: str, webp: int, jpg: int, png: int):
        self.path = path
        self.webp = webp
        self.jpg = jpg
        self.png = png
    
    @property
    def need_conversion(self) -> bool:
        """Returns True if the comic needs conversion (has jpg or png images)"""
        return self.jpg > 0 or self.png > 0
    
    def __repr__(self):
        return f"ComicFormat(path={self.path}, webp={self.webp}, jpg={self.jpg}, png={self.png})"


def get_filename_format(filename: str) -> FilenameFormat:
    """Detect comic filename format."""
    base = os.path.basename(filename)

    # Kapowarr: Series Name (Year) #001.cbz
    if re.match(r".+\s\(\d{4}\)\s#\d+.*\.cb[zr]$", base):
        return FilenameFormat.KAPOWARR

    # Mylar: Series Name #001 (Year).cbz
    if re.match(r".+\s#\d+\s\(\d{4}\).*\.cb[zr]$", base):
        return FilenameFormat.MYLAR

    return FilenameFormat.UNKNOWN