"""Utility functions and classes"""

import sys
from pathlib import Path
from typing import List
import xml.etree.ElementTree as ET


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


def collect_cbz_from_paths(paths: List[str]) -> List[str]:
    """
    Collect all CBZ files from given paths (files or directories).
    """
    collected: List[str] = []
    
    for p in paths:
        path = Path(p)
        if path.is_dir():
            for cbz in path.rglob("*.cbz"):
                if "#recycle" in str(cbz):
                    continue
                collected.append(str(cbz))
        elif path.is_file() and path.suffix.lower() == ".cbz":
            collected.append(str(path))
    
    return collected