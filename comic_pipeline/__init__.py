"""Comic Pipeline - A tool for managing and processing comic book archives"""

__version__ = "1.0.0"

from .scanner import find_files_needing_scraping
from .normalizer import normalize_comic_metadata, find_files_needing_normalize
from .image_converter import convert_to_webp
from .archive_converter import convert_cbr_to_cbz, convert_cb7_to_cbz, batch_convert_to_cbz
from .repair import repair_archive
from .kapowarr import update_kapowarr_volumes
from .scraper import metron_scrape
from .pipeline import run_pipeline
from .utils import (
    ComicInfo,
    APIKeys,
    collect_cbz_from_paths,
    Colors
)

__all__ = [
    'find_files_needing_scraping',
    'find_files_needing_normalize',
    'normalize_comic_metadata',
    'convert_to_webp',
    'convert_cbr_to_cbz',
    'convert_cb7_to_cbz',
    'batch_convert_to_cbz',
    'repair_archive',
    'update_kapowarr_volumes',
    'metron_scrape',
    'run_pipeline',
    'ComicInfo',
    'APIKeys',
    'collect_cbz_from_paths',
    'Colors',
]