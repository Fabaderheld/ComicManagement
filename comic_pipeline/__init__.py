"""Comic Pipeline - A tool for managing and processing comic book archives"""

__version__ = "1.0.0"

from .scanner import find_files_needing_scraping
from .normalizer import normalize_comic_metadata
from .converter import convert_to_webp, convert_cbr_to_cbz, convert_cb7_to_cbz, batch_convert_to_cbz
from .repair import repair_cbz
from .kapowarr import update_kapowarr_volumes
from .metron import metron_scrape
from .utils import (
    ComicInfo,
    APIKeys,
    collect_cbz_from_paths,
    Colors
)

__all__ = [
    'find_files_needing_scraping',
    'normalize_comic_metadata',
    'convert_to_webp',
    'convert_cbr_to_cbz',
    'convert_cb7_to_cbz',
    'batch_convert_to_cbz',
    'repair_cbz',
    'update_kapowarr_volumes',
    'metron_scrape',
    'ComicInfo',
    'APIKeys',
    'collect_cbz_from_paths',
    'Colors',
]