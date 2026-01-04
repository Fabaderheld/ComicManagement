"""Comic Pipeline - A tool for managing and processing comic book archives"""

__version__ = "1.0.0"

from .api import APIKeys
from .models import ComicFormat, FilenameFormat
from .scanner import needs_scraping, find_files_needing_scraping
from .normalizer import normalize_comic_metadata, needs_normalize, find_files_needing_normalize
from .converter import convert_to_webp
from .repair import repair_archive
from .kapowarr import update_kapowarr_volumes
from .metron import metron_scrape
from .pipeline import run_pipeline
from .utils import Colors, check_mark, status_line, collect_cbz_from_paths

__all__ = [
    "APIKeys",
    "ComicFormat",
    "FilenameFormat",
    "needs_scraping",
    "find_files_needing_scraping",
    "normalize_comic_metadata",
    "needs_normalize",
    "find_files_needing_normalize",
    "convert_to_webp",
    "repair_archive",
    "update_kapowarr_volumes",
    "metron_scrape",
    "run_pipeline",
    "Colors",
    "check_mark",
    "status_line",
    "collect_cbz_from_paths",
]