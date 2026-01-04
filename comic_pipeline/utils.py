"""Utility functions and classes"""
import sys
import os
from pathlib import Path
from typing import List, Optional
import xml.etree.ElementTree as ET


class ComicInfo:
    """Represents ComicInfo.xml metadata"""
    def __init__(self, xml_root: ET.Element):
        self.xml = xml_root
    
    def get(self, tag: str, default: str = "") -> str:
        """Get tag value, case-insensitive"""
        for elem in self.xml:
            if elem.tag.lower() == tag.lower():
                return elem.text or default
        return default
    
    def set(self, tag: str, value: str):
        """Set tag value, case-insensitive"""
        for elem in self.xml:
            if elem.tag.lower() == tag.lower():
                elem.text = value
                return
        # Tag doesn't exist, create it
        ET.SubElement(self.xml, tag).text = value
    
    def has(self, tag: str) -> bool:
        """Check if tag exists"""
        for elem in self.xml:
            if elem.tag.lower() == tag.lower():
                return True
        return False


class APIKeys:
    """Global API key storage"""
    comic_vine_api_key: Optional[str] = None
    kapowarr_api_key: Optional[str] = None
    
    @classmethod
    def set_api_keys(cls, comic_vine_api_key: Optional[str] = None, 
                     kapowarr_api_key: Optional[str] = None):
        """Set API keys"""
        if comic_vine_api_key:
            cls.comic_vine_api_key = comic_vine_api_key
        if kapowarr_api_key:
            cls.kapowarr_api_key = kapowarr_api_key


class Colors:
    """ANSI color codes for terminal output"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'
    CYAN = "\033[36m"


def check_mark(passed: bool) -> str:
    """Returns colored checkmark or X"""
    if passed:
        return f"{Colors.GREEN}✓{Colors.RESET}"
    else:
        return f"{Colors.RED}✗{Colors.RESET}"


def status_line(label: str, value: str, passed: bool = True) -> str:
    """Format a status line with checkmark/X"""
    symbol = check_mark(passed)
    return f"  {symbol} {label}: {value}"


def get_tag_element(xml, tag_name):
    """
    Find a tag case-insensitively, or create it if missing.
    Returns the element.
    """
    for elem in xml:
        if elem.tag.lower() == tag_name.lower():
            return elem
    # Not found, create it
    return ET.SubElement(xml, tag_name)


def collect_cbz_from_paths(paths: List[str], include_cbr: bool = False) -> List[str]:
    """
    Collect all CBZ files from given paths (files or directories).
    
    Args:
        paths: List of file or directory paths
        include_cbr: If True, also collect CBR and CB7 files
        
    Returns:
        List of CBZ file paths (and CBR/CB7 if include_cbr=True)
    """
    cbz_files = []
    extensions = ['.cbz']
    if include_cbr:
        extensions.extend(['.cbr', '.cb7'])
    
    for path_str in paths:
        path = Path(path_str)
        if path.is_file():
            if path.suffix.lower() in extensions:
                cbz_files.append(str(path))
        elif path.is_dir():
            for ext in extensions:
                cbz_files.extend([str(f) for f in path.rglob(f'*{ext}')])
    
    return sorted(cbz_files)