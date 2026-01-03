#!/usr/bin/env python3
"""Comic pipeline helper with improved CLI and dry-run support"""

import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
import shutil
import tempfile
from typing import List, Dict, Optional, Any
import requests
import json
import sys
import re
from PIL import Image as PILImage
import re
from darkseid.comic import Comic, MetadataFormat
from enum import Enum
import contextlib
import io

class FilenameFormat(Enum):
    """Enum for comic filename formats"""
    KAPOWARR = 1  # Series Name (Year) #001.cbz
    MYLAR = 2     # Series Name #001 (Year).cbz
    UNKNOWN = 3


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

# --- Color/Symbol helpers ---
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


class APIKeys:
    """Class to manage API keys"""
    comic_vine_api_key: Optional[str] = None
    kapowarr_api_key: Optional[str] = None
    
    @classmethod
    def set_api_keys(cls, comic_vine_api_key: Optional[str] = None, 
                     kapowarr_api_key: Optional[str] = None):
        """
        Sets the API keys for ComicVine and Kapowarr
        
        Args:
            comic_vine_api_key: API key for ComicVine
            kapowarr_api_key: API key for Kapowarr
        """
        if comic_vine_api_key:
            cls.comic_vine_api_key = comic_vine_api_key
        if kapowarr_api_key:
            cls.kapowarr_api_key = kapowarr_api_key


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

import re
from pathlib import Path

def has_valid_filename(comic_path: str) -> bool:
    """
    Strict filename check:
    'Series Vol.YYYY - #NNN.cbz'
    e.g. 'Iron Man Vol.2020 - #002.cbz'
    """
    filename = Path(comic_path).name  # include extension for debug
    stem = Path(comic_path).stem      # name without extension

    # Pattern on STEM only: "Series Vol.YYYY - #NNN"
    pattern = r'^.+? Vol\.\d{4} - #\d{3}$'
    m = re.match(pattern, stem)

    # TEMP DEBUG: show what we are checking
    print(f"[FNAME DEBUG] name='{filename}' stem='{stem}' match={bool(m)}")

    return bool(m)

def has_valid_filename(comic_path: str) -> bool:
    """
    Check if the filename follows a reasonable comic naming convention.
    
    Expected patterns (case-insensitive):
    - "Series Name Vol.YYYY - #NNN.cbz"
    - "Series Name (YYYY) - #NNN.cbz"
    - "Series Name #NNN (YYYY).cbz"
    - etc.
    
    Returns True if filename looks valid, False otherwise.
    """
    filename = Path(comic_path).stem  # Remove .cbz/.cbr extension
    
    # Pattern: should contain at least:
    # - Some text (series name)
    # - A 4-digit year OR "Vol." followed by year
    # - A number (issue number) with # or without
    
    # Check for year (4 digits)
    has_year = bool(re.search(r'\b(19|20)\d{2}\b', filename))
    
    # Check for issue number patterns:
    # - "#123" or "# 123"
    # - "123 (2023)" at end
    # - "- 123" or "Vol 123"
    has_issue_number = bool(re.search(r'(#\s*\d+|\b\d{1,4}\s*\(|\-\s*\d{3,4})', filename))
    
    # Filename should have both year and issue number
    # Also reject files with common "bad" patterns:
    bad_patterns = [
        r'\(\d{4}\)\s*\(\d{4}\)',  # Double years like (2023) (2024)
        r'^[A-Z]{2,}\s+\d+\s+\(',   # All-caps short names like "TF 001 (2023)"
        r'\(Digital\)',             # Raw digital tags without proper series name
    ]
    
    has_bad_pattern = any(re.search(pattern, filename, re.IGNORECASE) for pattern in bad_patterns)
    
    return has_year and has_issue_number and not has_bad_pattern

def get_comic_format(comic_path: str) -> ComicFormat:
    """
    Determines the format of images within a .cbz file.
    
    Args:
        comic_path: The path to the comic file (.cbz format)
        
    Returns:
        ComicFormat object containing format information
        
    Example:
        format_info = get_comic_format("/path/to/comic.cbz")
        if format_info.eed_conversion:
            print("Comic needs conversion")
    """
    try:
        with zipfile.ZipFile(comic_path, 'r') as zip_file:
            # Get all files except ComicInfo.xml
            images = [f for f in zip_file.namelist() if f != "ComicInfo.xml"]
            
            # Count different image formats
            webp_count = sum(1 for img in images if img.lower().endswith('.webp'))
            jpg_count = sum(1 for img in images if img.lower().endswith(('.jpg', '.jpeg')))
            png_count = sum(1 for img in images if img.lower().endswith('.png'))
            
            return ComicFormat(comic_path, webp_count, jpg_count, png_count)
            
    except Exception as e:
        print(f"Error analyzing comic format: {e}")
        return ComicFormat(comic_path, 0, 0, 0)


def convert_image_to_webp(input_path: str, output_path: str, quality: int = 75):
    """
    Converts an image to WebP format using Pillow.
    
    Args:
        input_path: Path to the input image
        output_path: Path to save the WebP image
        quality: Quality setting for WebP (0-100)
    """
    with PILImage.open(input_path) as img:
        # Convert to RGB if necessary (e.g. palette or CMYK images)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        img.save(output_path, format="WEBP", quality=quality)


def convert_to_webp(comics: List[str], verbose: bool = False, dry_run: bool = False):
    """
    Converts image files in .cbz comic archives to webp format.
    Expects a list of CBZ file paths (no directories).
    
    Args:
        comics: List of paths to comic files (.cbz format)
        verbose: Enable verbose output
        dry_run: If True, only preview changes without modifying files
    """
    if dry_run:
        print("[DRY RUN MODE] No files will be modified\n")
    
    for comic in comics:
        comic_path = Path(comic)
        
        if verbose:
            print(f"Processing: {comic_path}")
        
        if not comic_path.is_file() or comic_path.suffix.lower() != ".cbz":
            print(f"[SKIP] Not a CBZ file: {comic_path}")
            continue
        
        # Check if conversion is needed
        format_info = get_comic_format(str(comic_path))
        if not format_info.need_conversion:
            if verbose:
                print(f"The comic {comic_path.name} does not require conversion.")
            continue
        
        if dry_run:
            print(f"[DRY RUN] Would convert {comic_path.name}")
            print(f"  - JPG images: {format_info.jpg}")
            print(f"  - PNG images: {format_info.png}")
            print(f"  - Total to convert: {format_info.jpg + format_info.png}")
            continue
        
        temp_dir = Path(tempfile.gettempdir()) / comic_path.stem
        
        try:
            with zipfile.ZipFile(comic_path, 'r') as zip_file:
                zip_file.extractall(temp_dir)
            
            image_extensions = ['.jpg', '.jpeg', '.png']
            images = [f for f in temp_dir.rglob('*') if f.suffix.lower() in image_extensions]
            
            stat = shutil.disk_usage(comic_path.parent)
            free_space_gb = stat.free / (1024 ** 3)
            comic_size_gb = comic_path.stat().st_size / (1024 ** 3)
            
            if free_space_gb <= comic_size_gb:
                print(f"Not enough free space to convert images for {comic_path.name}")
                continue
            
            total_images = len(images)
            if total_images == 0:
                if verbose:
                    print(f"No JPG/PNG images found in {comic_path.name}")
                continue
            
            print(f"Processing {comic_path.name}")
            print(f"Converting {total_images} images to webp format...")
            
            for counter, image in enumerate(images, 1):
                percent_complete = (counter / total_images) * 100
                print(f"Progress: {counter}/{total_images} ({percent_complete:.1f}%)", end='\r')
                
                try:
                    output_path = image.parent / f"{image.stem}.webp"
                    convert_image_to_webp(str(image), str(output_path), quality=75)
                    image.unlink()
                except Exception as e:
                    print(f"\nError converting image {image}: {e}")
            
            print()  # newline after progress
            
            # Create new archive (ComicInfo.xml and everything else included)
            with zipfile.ZipFile(comic_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for file in temp_dir.rglob('*'):
                    if file.is_file():
                        zip_file.write(file, file.relative_to(temp_dir))
            
            print(f"Conversion complete for {comic_path.name}")
            
        finally:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)


def get_comic_vine_info(id: str, type: str) -> Optional[Dict[str, Any]]:
    """
    Fetches information about a comic entity from the ComicVine API.
    
    Args:
        id: The ID of the comic entity
        type: The type of entity (volume, issue, person, character, concept, 
              location, object, origin, publisher, story_arc, team)
              
    Returns:
        Dictionary containing the comic entity information
        
    Example:
        info = get_comic_vine_info("12345", "volume")
    """
    valid_types = ["volume", "issue", "person", "character", "concept", 
                   "location", "object", "origin", "publisher", "story_arc", "team"]
    
    if type not in valid_types:
        raise ValueError(f"Invalid type: {type}. Must be one of {valid_types}")
    
    # Check if API key is set
    if not APIKeys.comic_vine_api_key:
        raise ValueError("ComicVine API key not set. Please run APIKeys.set_api_keys()")
    
    # Determine type code
    type_codes = {
        "volume": "4050",
        "issue": "4000"
    }
    
    type_code = type_codes.get(type)
    if not type_code:
        raise ValueError(f"Unsupported type: {type}")
    
    # Prepare request
    params = {
        'api_key': APIKeys.comic_vine_api_key,
        'format': 'json'
    }
    
    url = f"https://comicvine.gamespot.com/api/{type}/{type_code}-{id}"
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        return data.get('results')
        
    except requests.exceptions.RequestException as e:
        try:
            error_data = response.json()
            error_message = error_data.get('error', str(e))
            if error_message == "CVRateLimitReached":
                print("ComicVine API rate limit reached, please try again later.")
            else:
                print(f"ComicVineAPI: {error_message}")
        except:
            print(f"Error fetching ComicVine info: {e}")
        return None

def needs_scraping(
    path: str,
    strict: bool = False,
    check_filenames: bool = False,
    verbose: bool = False,
) -> list[str]:
    """
    Check if a comic file needs scraping.
    Returns a list of reasons (empty if no scraping needed).
    """
    reasons: list[str] = []

    def status_line(check: str, status: str, passed: bool) -> str:
        symbol = Colors.GREEN + "✓" if passed else Colors.RED + "✗"
        return f"  {symbol} {check}: {status}{Colors.RESET}"

    if verbose:
        print(
            f"\n{Colors.BLUE}[CHECKING]{Colors.RESET} {os.path.basename(path)}",
            file=sys.stderr,
        )

    # ---------- (A) Optional: filename check ----------
    if check_filenames:
        base = os.path.basename(path)
        is_standard = bool(
            re.search(r"\(\d{4}\)", base) and re.search(r"#\d+", base)
        )

        if verbose:
            print(
                status_line(
                    "Filename format",
                    "standard" if is_standard else "non-standard",
                    is_standard,
                ),
                file=sys.stderr,
            )

        if strict and not is_standard:
            reasons.append("non-standard filename")

    # ---------- (B) Open comic ----------
    try:
        comic = Comic(path)
    except Exception as e:
        reasons.append(f"cannot open archive: {e}")
        if verbose:
            print(
                f"  {Colors.RED}✗ ERROR opening archive: {e}{Colors.RESET}",
                file=sys.stderr,
            )
            print(
                f"  {Colors.RED}✗ NEEDS SCRAPING{Colors.RESET}: {', '.join(reasons)}",
                file=sys.stderr,
            )
        return reasons

    # ---------- (C) Check presence of ComicInfo ----------
    has_comicinfo = comic.has_metadata(MetadataFormat.COMIC_INFO)
    if verbose:
        print(
            status_line(
                "ComicInfo.xml",
                "present" if has_comicinfo else "MISSING",
                has_comicinfo,
            ),
            file=sys.stderr,
        )

    if not has_comicinfo:
        reasons.append("no ComicInfo.xml")
        if verbose:
            print(
                f"  {Colors.RED}✗ NEEDS SCRAPING{Colors.RESET}: {', '.join(reasons)}",
                file=sys.stderr,
            )
        return reasons

    # ---------- (D) Read ComicInfo (may return empty object on error) ----------
    # Suppress Darkseid's verbose error output
    metadata = comic.read_metadata(MetadataFormat.COMIC_INFO)


    # ---------- (E) Check required fields ----------
    try:
        # Extract values from Darkseid objects properly
        series_obj = getattr(metadata, "series", None)
        series = series_obj.name if series_obj and hasattr(series_obj, "name") else ""
        
        # Darkseid uses 'issue' not 'number'
        issue = getattr(metadata, "issue", None)
        number = str(issue) if issue is not None else ""
        
        # Year comes from cover_date
        cover_date = getattr(metadata, "cover_date", None)
        if cover_date and hasattr(cover_date, "year"):
            year = str(cover_date.year)
        else:
            year = ""
        
        publisher_obj = getattr(metadata, "publisher", None)
        publisher = publisher_obj.name if publisher_obj and hasattr(publisher_obj, "name") else ""
        
        # Title might be in 'stories' list
        stories = getattr(metadata, "stories", [])
        title = stories[0] if stories else ""

        # If ALL critical fields are empty, metadata is broken/unreadable
        if not any([series, number, year]):
            reasons.append("ComicInfo.xml unreadable or all fields empty")
            if verbose:
                print(
                    status_line(
                        "ComicInfo.xml",
                        "BROKEN / all fields empty",
                        False,
                    ),
                    file=sys.stderr,
                )
                print(
                    f"  {Colors.RED}✗ NEEDS SCRAPING{Colors.RESET}: {', '.join(reasons)}",
                    file=sys.stderr,
                )
            return reasons

        checks = [
            ("Series", series),
            ("Number", number),
            ("Year", year),
            ("Publisher", publisher),
            ("Title", title),
        ]

        for field_name, value in checks:
            has_value = bool(value)
            if verbose:
                print(
                    status_line(
                        field_name,
                        f"'{value}'" if has_value else "EMPTY",
                        has_value,
                    ),
                    file=sys.stderr,
                )
            if not has_value:
                reasons.append(f"missing {field_name.lower()}")

    except Exception as e:
        reasons.append(f"metadata error: {e}")
        if verbose:
            print(
                f"  {Colors.RED}✗ ERROR: {e}{Colors.RESET}",
                file=sys.stderr,
                )

    # ---------- (F) Final verdict ----------
    if verbose:
        if reasons:
            print(
                f"  {Colors.RED}✗ NEEDS SCRAPING{Colors.RESET}: {', '.join(reasons)}",
                file=sys.stderr,
            )
        else:
            print(
                f"  {Colors.GREEN}✓ OK{Colors.RESET} - no scraping needed",
                file=sys.stderr,
            )

    return reasons

def repair_archive(path: str, dry_run: bool = False, verbose: bool = False) -> bool:
    """
    Repair non-standard CBZ archive structure by flattening all files to root level.
    Returns True if repairs were made, False otherwise.
    """
    import zipfile
    import tempfile
    import shutil
    
    if verbose:
        print(f"\n{Colors.BLUE}[REPAIRING]{Colors.RESET} {os.path.basename(path)}", file=sys.stderr)
    
    try:
        with zipfile.ZipFile(path, 'r') as zf:
            file_list = zf.namelist()
            
            # Check if any files are in subfolders
            files_in_subfolders = [f for f in file_list if '/' in f and not f.endswith('/')]
            
            if not files_in_subfolders:
                if verbose:
                    print(f"  {Colors.GREEN}✓{Colors.RESET} Archive structure is already correct", file=sys.stderr)
                return False
            
            if verbose:
                print(f"  {Colors.YELLOW}⚠{Colors.RESET} Found {len(files_in_subfolders)} files in subfolders", file=sys.stderr)
            
            if dry_run:
                print(f"  {Colors.BLUE}[DRY RUN]{Colors.RESET} Would flatten {len(files_in_subfolders)} files to root", file=sys.stderr)
                for f in files_in_subfolders[:5]:  # Show first 5
                    new_name = os.path.basename(f)
                    print(f"    {f} → {new_name}", file=sys.stderr)
                if len(files_in_subfolders) > 5:
                    print(f"    ... and {len(files_in_subfolders) - 5} more", file=sys.stderr)
                return True
            
            # Create temporary file
            temp_fd, temp_path = tempfile.mkstemp(suffix='.cbz')
            os.close(temp_fd)
            
            try:
                with zipfile.ZipFile(temp_path, 'w', zipfile.ZIP_DEFLATED) as new_zf:
                    for file_name in file_list:
                        # Skip directories
                        if file_name.endswith('/'):
                            continue
                        
                        # Get just the filename (no path)
                        new_name = os.path.basename(file_name)
                        
                        # Read from old archive and write to new with flattened name
                        data = zf.read(file_name)
                        new_zf.writestr(new_name, data)
                        
                        if verbose and '/' in file_name:
                            print(f"    {file_name} → {new_name}", file=sys.stderr)
                
                # Replace original with repaired version
                shutil.move(temp_path, path)
                
                if verbose:
                    print(f"  {Colors.GREEN}✓{Colors.RESET} Archive repaired successfully", file=sys.stderr)
                
                return True
                
            except Exception as e:
                # Clean up temp file on error
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                raise
                
    except Exception as e:
        if verbose:
            print(f"  {Colors.RED}✗ ERROR:{Colors.RESET} {e}", file=sys.stderr)
        return False

def needs_normalize(comic_path: str, start_years: Optional[Dict[tuple, int]] = None) -> List[str]:
    """
    Determine if a CBZ needs normalization using Darkseid.
    """
    reasons: List[str] = []
    path = Path(comic_path)

    if not path.is_file() or path.suffix.lower() != ".cbz":
        reasons.append("not a CBZ file")
        return reasons

    try:
        comic = Comic(str(path))
        
        if not comic.has_cix():
            reasons.append("no ComicInfo.xml")
            return reasons
        
        metadata = comic.read_cix()
        
        series = (metadata.series or "").strip()
        publisher = (metadata.publisher or "").strip()
        year = str(metadata.year or "").strip()
        volume = str(metadata.volume or "").strip() if metadata.volume else ""
        story_arc = (metadata.story_arc or "").strip()
        alt_series = (metadata.alternate_series or "").strip()
        
        # Check 1: Volume missing
        if not volume:
            reasons.append("missing Volume")
        
        # Check 2: Volume incorrect (if we have start_years data)
        elif start_years and series and year:
            key = (series, publisher)
            if key in start_years:
                expected_vol = str(start_years[key])
                if volume != expected_vol:
                    reasons.append(f"Volume is '{volume}', should be '{expected_vol}'")
        
        # Check 3: StoryArc exists but AlternateSeries doesn't
        if story_arc and not alt_series:
            reasons.append("has StoryArc but missing AlternateSeries")
                    
    except Exception as e:
        reasons.append(f"error reading comic: {e}")

    return reasons

def find_files_needing_normalize(paths: List[str],
                                  output_format: str = "console",
                                  output_file: Optional[str] = None) -> List[Path]:
    """
    Walk given files/dirs and return CBZ files that need normalization.
    
    Args:
        paths: List of file or directory paths to scan
        output_format: Output format - "console", "json", or "list"
        output_file: Optional file path to write results to
        
    Returns:
        List of Path objects for files needing normalization
    """
    # First pass: build start_years map
    all_cbz = []
    for p in paths:
        pth = Path(p)
        if pth.is_dir():
            for cbz in pth.rglob("*.cbz"):
                if "#recycle" not in str(cbz):
                    all_cbz.append(cbz)
        elif pth.is_file() and pth.suffix.lower() == ".cbz":
            all_cbz.append(pth)
    
    # Build start_years (same logic as normalize_comic_metadata Pass 1)
    runs: Dict[tuple, List[int]] = {}
    for cbz in all_cbz:
        try:
            with zipfile.ZipFile(cbz, "r") as z:
                ci_name = next((n for n in z.namelist() if n.lower().endswith("comicinfo.xml")), None)
                if not ci_name:
                    continue
                root = ET.fromstring(z.read(ci_name))
                
                def get_text(tag):
                    for child in root:
                        if child.tag.lower() == tag.lower():
                            return (child.text or "").strip()
                    return ""
                
                series = get_text("Series")
                publisher = get_text("Publisher")
                year_text = get_text("Year")
                
                if series and year_text:
                    m = re.search(r"(\d{4})", year_text)
                    if m:
                        year = int(m.group(1))
                        key = (series, publisher)
                        runs.setdefault(key, []).append(year)
        except Exception:
            continue
    
    start_years = {k: min(v) for k, v in runs.items()}
    
    # Second pass: check each file
    results: List[Path] = []
    results_with_reasons: List[Dict[str, Any]] = []
    
    for cbz in all_cbz:
        reasons = needs_normalize(str(cbz), start_years=start_years)
        if reasons:
            results.append(cbz)
            results_with_reasons.append({
                "path": str(cbz),
                "reasons": reasons
            })
            if output_format == "console":
                print(f"[NEEDS NORMALIZE] {cbz} -> {', '.join(reasons)}")
    
    # Handle output formats
    if output_format == "json":
        output_data = {
            "total": len(results),
            "files": results_with_reasons
        }
        json_output = json.dumps(output_data, indent=2)
        
        if output_file:
            with open(output_file, 'w') as f:
                f.write(json_output)
            print(f"JSON output written to: {output_file}")
        else:
            print(json_output)
    
    elif output_format == "list":
        list_output = "\n".join(str(p) for p in results)
        
        if output_file:
            with open(output_file, 'w') as f:
                f.write(list_output)
            print(f"File list written to: {output_file}")
        else:
            print(list_output)
    
    return results


def find_files_needing_scraping(
    paths: List[str],
    strict: bool = True,
    check_filenames: bool = False,
    output_format: str = "console",
    output_file: Optional[str] = None
) -> int:
    """
    Walk given files/dirs and return CBZ/CBR files that need scraping.
    
    Returns:
        Exit code: 0 if no files need scraping, 1 if files need scraping
    """
    results: List[Path] = []
    results_with_reasons: List[Dict[str, Any]] = []
    total_checked = 0
    
    # ALWAYS show per-file checks (to stderr)
    verbose = True

    for p in paths:
        pth = Path(p)
        if pth.is_dir():
            for f in pth.rglob("*"):
                if f.is_file() and f.suffix.lower() in (".cbz", ".cbr"):
                    if "#recycle" in str(f):
                        continue
                    total_checked += 1
                    reasons = needs_scraping(str(f), strict=strict, check_filenames=check_filenames, verbose=verbose)
                    if reasons:
                        results.append(f)
                        results_with_reasons.append({
                            "path": str(f),
                            "reasons": reasons
                        })
        elif pth.is_file() and pth.suffix.lower() in (".cbz", ".cbr"):
            total_checked += 1
            reasons = needs_scraping(str(pth), strict=strict, check_filenames=check_filenames, verbose=verbose)
            if reasons:
                results.append(pth)
                results_with_reasons.append({
                    "path": str(pth),
                    "reasons": reasons
                })

    # Handle output formats
    if output_format == "json":
        output_data = {
            "total": len(results),
            "files": results_with_reasons
        }
        json_output = json.dumps(output_data, indent=2)
        
        if output_file:
            with open(output_file, 'w') as f:
                f.write(json_output)
            print(f"{Colors.BLUE}ℹ{Colors.RESET} JSON output written to: {output_file}", file=sys.stderr)
        else:
            print(json_output)
    
    elif output_format == "list":
        # Use absolute paths
        list_output = "\n".join(str(p.resolve()) for p in results)
        
        if output_file:
            with open(output_file, 'w') as f:
                f.write(list_output)
            print(f"{Colors.BLUE}ℹ{Colors.RESET} File list written to: {output_file}", file=sys.stderr)
        else:
            # Print to stdout (for piping)
            print(list_output)
    
    elif output_format == "console":
        # Summary
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"{Colors.BOLD}SCAN SUMMARY{Colors.RESET}", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)
        print(f"Total files checked: {total_checked}", file=sys.stderr)
        
        if results:
            print(f"{Colors.RED}✗ {len(results)} file(s) need scraping{Colors.RESET}", file=sys.stderr)
        else:
            print(f"{Colors.GREEN}✓ All files OK - no scraping needed{Colors.RESET}", file=sys.stderr)
        print(f"{'='*60}\n", file=sys.stderr)

    return 1 if results else 0


def normalize_comic_metadata(comics: List[str], dry_run: bool = False, verbose: bool = False):
    """
    Normalizes ComicInfo metadata using Darkseid.
    - Always ensures Volume exists and is set to the start year.
    - Sets AlternateSeries from StoryArc if present and AlternateSeries is empty.
    """
    if dry_run:
        print("[DRY RUN MODE] No files will be modified\n")

    runs: Dict[tuple, List[int]] = {}

    # ---------- PASS 1: collect years ----------
    if verbose:
        print("=== PASS 1: Collecting Series/Year data ===\n")

    for c in comics:
        path = Path(c)
        if not path.is_file() or path.suffix.lower() != ".cbz":
            continue

        if verbose:
            print(f"[PASS1] {path.name}")

        try:
            comic = Comic(str(path))
            if not comic.has_cix():
                if verbose:
                    print("  No ComicInfo.xml found\n")
                continue

            metadata = comic.read_cix()
            series = (metadata.series or "").strip()
            publisher = (metadata.publisher or "").strip()
            year_text = str(metadata.year or "").strip()

            if verbose:
                print(f"  Series='{series}', Publisher='{publisher}', Year='{year_text}'")

            if not series or not year_text:
                if verbose:
                    print("  Missing Series or Year, skipping\n")
                continue

            m = re.search(r"(\d{4})", year_text)
            if not m:
                if verbose:
                    print("  No 4-digit year found, skipping\n")
                continue

            year = int(m.group(1))
            key = (series, publisher)
            runs.setdefault(key, []).append(year)

            if verbose:
                print(f"  Added: {key} -> {year}\n")

        except Exception as e:
            print(f"[WARN] {path.name}: {e}")

    if not runs:
        print("No valid Series/Year data found.")
        return

    start_years = {k: min(v) for k, v in runs.items()}

    print("\nDetected runs:")
    for (series, publisher), y in sorted(start_years.items()):
        print(f"- {publisher or 'Unknown'} | {series} -> start year {y}")

    print(f"\n{'[DRY RUN] Checking' if dry_run else 'Updating'} metadata...\n")

    # ---------- PASS 2: Apply ----------
    changes = 0

    for c in comics:
        path = Path(c)
        if not path.is_file() or path.suffix.lower() != ".cbz":
            continue

        if verbose:
            print(f"[PASS2] {path.name}")

        try:
            comic = Comic(str(path))
            if not comic.has_cix():
                if verbose:
                    print("  No ComicInfo.xml\n")
                continue

            metadata = comic.read_cix()
            
            series = (metadata.series or "").strip()
            publisher = (metadata.publisher or "").strip()
            key = (series, publisher)

            if verbose:
                print(f"  Key: {key}")

            if key not in start_years:
                if verbose:
                    print(f"  Key {key} not in start_years, skipping\n")
                continue

            target_year = str(start_years[key])

            # Track old values
            old_volume = str(metadata.volume or "").strip() if metadata.volume else None
            old_alt = (metadata.alternate_series or "").strip() if metadata.alternate_series else None

            # Set Volume
            metadata.volume = target_year

            # Set AlternateSeries from StoryArc if needed
            story_arc = (metadata.story_arc or "").strip()
            if story_arc and not (metadata.alternate_series or "").strip():
                metadata.alternate_series = story_arc

            # Check what changed
            new_volume = str(metadata.volume or "").strip()
            new_alt = (metadata.alternate_series or "").strip() if metadata.alternate_series else None

            volume_changed = (old_volume != new_volume)
            alt_changed = (old_alt != new_alt)

            if not volume_changed and not alt_changed:
                if verbose:
                    print(f"  No changes needed for {path.name}\n")
                continue

            # Print summary
            print(f"[NORMALIZE] {path.name}")
            if volume_changed:
                print(f"  Volume: {old_volume or '<none>'} -> {new_volume}")
            if alt_changed:
                print(f"  AlternateSeries: {old_alt or '<none>'} -> {new_alt}")

            changes += 1

            if dry_run:
                print(f"[DRY RUN] Would update {path.name}\n")
                continue

            # Write back (Darkseid handles the archive rewrite!)
            comic.write_cix(metadata)

            if verbose:
                print(f"  ✓ Updated {path.name}\n")

        except Exception as e:
            print(f"[WARN] {path.name}: {e}")
            if verbose:
                import traceback
                traceback.print_exc()

    print(f"\n{'[DRY RUN] Would change' if dry_run else 'Changed'} {changes} files")
    print("Done ✔")

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


def update_kapowarr_volumes(kapowarr_url: str = "http://localhost:5656",
                            comics_path: str = "/mnt/comics",
                            verbose: bool = False,
                            dry_run: bool = False):
    """
    Updates and synchronizes comic volumes with the Kapowarr system.
    
    Args:
        kapowarr_url: The URL of the Kapowarr instance
        comics_path: The root directory path where comic volumes are stored
        verbose: Enable verbose output
        dry_run: If True, only preview changes without making modifications
        
    Example:
        update_kapowarr_volumes("http://localhost:5656", "/mnt/comics")
    """
    if dry_run:
        print("[DRY RUN MODE] No changes will be made to Kapowarr\n")
    
    # Check if API keys are set
    if not APIKeys.kapowarr_api_key:
        raise ValueError("Kapowarr API key not set. Please run APIKeys.set_api_keys()")
    
    if not APIKeys.comic_vine_api_key:
        raise ValueError("ComicVine API key not set. Please run APIKeys.set_api_keys()")
    
    params = {'api_key': APIKeys.kapowarr_api_key}
    
    try:
        # Fetch all volumes from Kapowarr
        response = requests.get(f"{kapowarr_url}/api/volumes", params=params)
        response.raise_for_status()
        kapowarr_volumes = response.json()['result']
        
        # Fetch details for each volume
        kapowarr_volumes_details = []
        for volume in kapowarr_volumes:
            response = requests.get(f"{kapowarr_url}/api/volumes/{volume['id']}", params=params)
            response.raise_for_status()
            kapowarr_volumes_details.append(response.json()['result'])
        
        # Get volumes with incorrect paths
        wrong_volumes = [v for v in kapowarr_volumes_details 
                        if 'Volume' in v.get('volume_folder', '')]
        
        if wrong_volumes and verbose:
            print(f"Found {len(wrong_volumes)} volumes with incorrect paths")
        
        for wrong_volume in wrong_volumes:
            volume_path = f"{comics_path}/{wrong_volume['publisher']}/{wrong_volume['title']} ({wrong_volume['year']})"
            if verbose:
                print(f"{'[DRY RUN] Would fix' if dry_run else 'Fixing'} path: {volume_path}")
                print(f"  Path exists: {Path(volume_path).exists()}")
        
        # Get comic folders
        comics_path_obj = Path(comics_path)
        comic_folders = [f for f in comics_path_obj.iterdir() 
                        if f.is_dir() and '#recycle' not in f.name 
                        and '(' not in f.name and ')' not in f.name]
        
        volumes_to_add = 0
        volumes_to_update = 0
        
        # Process each comic folder
        for comic in comic_folders:
            volumes = list(comic.iterdir())
            
            for volume in volumes:
                if not volume.is_dir():
                    continue
                
                if verbose:
                    print(f"Processing volume: {volume}")
                
                # Construct volume path
                volume_path = str(volume).split('/comics/')[-1]
                
                # Check if volume already exists
                existing_folders = [v.get('volume_folder') for v in kapowarr_volumes_details]
                
                if volume_path in existing_folders:
                    if verbose:
                        print(f"Volume already exists in Kapowarr: {volume_path}")
                    continue
                
                # Get issues in the volume
                issues = list(volume.glob("*.cbz"))
                if not issues:
                    print(f"Empty folder: {volume}, skipping...")
                    continue
                
                try:
                    # Extract ComicInfo from first issue
                    comic_info = ComicInfo.get_comic_info(str(issues[0]))
                    if comic_info is None:
                        print(f"Error reading ComicInfo.xml file in {issues[0]}")
                        continue
                    
                    # Extract Issue ID
                    notes = comic_info.find('Notes')
                    if notes is None or not notes.text:
                        print(f"Issue ID not found in ComicInfo.xml for {issues[0]}")
                        continue
                    
                    match = re.search(r'CVDB(\d+)', notes.text)
                    if not match:
                        print(f"Issue ID not found in ComicInfo.xml for {issues[0]}")
                        continue
                    
                    issue_id = match.group(1)
                    
                    if verbose:
                        print(f"Issue ID: {issue_id}")
                    
                    # Check for series.json
                    series_json_path = volume / "series.json"
                    
                    if series_json_path.exists():
                        with open(series_json_path, 'r') as f:
                            volume_cv_info = json.load(f)
                        volume_id = volume_cv_info['id']
                    else:
                        if dry_run:
                            print(f"[DRY RUN] Would fetch ComicVine info for issue {issue_id}")
                            continue
                        
                        # Fetch from ComicVine
                        issue_cv_info = get_comic_vine_info(issue_id, "issue")
                        if not issue_cv_info:
                            continue
                        
                        volume_cv_info = get_comic_vine_info(str(issue_cv_info['volume']['id']), "volume")
                        if not volume_cv_info:
                            continue
                        
                        volume_id = volume_cv_info['id']
                        
                        # Save series.json
                        with open(series_json_path, 'w') as f:
                            json.dump(volume_cv_info, f, indent=2)
                    
                    # Add volume to Kapowarr
                    body = {
                        'comicvine_id': str(volume_id),
                        'root_folder_id': 1,
                        'monitor': True,
                        'volume_folder': volume_path,
                        'auto_search': False
                    }
                    
                    if dry_run:
                        print(f"[DRY RUN] Would add volume to Kapowarr: {volume_path}")
                        volumes_to_add += 1
                        continue
                    
                    try:
                        response = requests.post(
                            f"{kapowarr_url}/api/volumes",
                            params=params,
                            json=body
                        )
                        response.raise_for_status()
                        print(f"Added Volume to Kapowarr: {volume_path}")
                        volumes_to_add += 1
                        
                    except requests.exceptions.RequestException as e:
                        try:
                            error_data = response.json()
                            error_message = error_data.get('error', str(e))
                            
                            if error_message == "CVRateLimitReached":
                                print("ComicVine API rate limit reached, please try again later.")
                                continue
                            elif error_message == "VolumeAlreadyAdded":
                                print(f"Volume already added, updating path in Kapowarr for: {volume_path}")
                                
                                # Find Kapowarr volume
                                kapowarr_volume = next(
                                    (v for v in kapowarr_volumes_details 
                                     if v.get('comicvine_id') == volume_id),
                                    None
                                )
                                
                                if kapowarr_volume:
                                    update_body = {
                                        'root_folder': 1,
                                        'monitored': True,
                                        'volume_folder': volume_path,
                                        'special_version_locked': False
                                    }
                                    
                                    response = requests.put(
                                        f"{kapowarr_url}/api/volumes/{kapowarr_volume['id']}",
                                        params=params,
                                        json=update_body
                                    )
                                    response.raise_for_status()
                                    volumes_to_update += 1
                            else:
                                print(f"Kapowarr: {error_message}")
                                continue
                        except:
                            print(f"Error adding volume: {e}")
                            
                except Exception as e:
                    print(f"Error processing volume {volume}: {e}")
                    continue
        
        # Update all volumes in Kapowarr
        if not dry_run and (volumes_to_add > 0 or volumes_to_update > 0):
            update_body = {'cmd': 'update_all'}
            requests.post(
    f"{kapowarr_url}/api/system/tasks",
                params=params,
                json=update_body
            )
            print(f"\nTriggered Kapowarr update for all volumes")
        
        print(f"\n{'[DRY RUN] Would add' if dry_run else 'Added'} {volumes_to_add} volumes")
        print(f"{'[DRY RUN] Would update' if dry_run else 'Updated'} {volumes_to_update} volumes")
        
    except requests.exceptions.RequestException as e:
        print(f"Error communicating with Kapowarr: {e}", file=sys.stderr)
        sys.exit(1)


def metron_scrape(paths: List[str], ignore_existing: bool = True, dry_run: bool = False) -> int:
    """
    Run MetronTagger on the given files/directories.
    
    Returns:
        Exit code: 0 on success, 1 on error
    """
    import shutil
    
    # Check if metron-tagger is installed
    if not shutil.which("metron-tagger"):
        print(f"{Colors.RED}✗ ERROR{Colors.RESET}: metron-tagger not found in PATH", file=sys.stderr)
        print("Install it with: pip install metron-tagger", file=sys.stderr)
        return 1
    
    # Collect all CBZ/CBR files
    files = collect_cbz_from_paths(paths)
    
    if not files:
        print(f"{Colors.YELLOW}⚠{Colors.RESET} No CBZ/CBR files found")
        return 0
    
    print(f"\n{Colors.BOLD}MetronTagger Scraping{Colors.RESET}")
    print(f"{'='*60}")
    print(f"Files to process: {len(files)}")
    
    if dry_run:
        print(f"{Colors.CYAN}[DRY-RUN]{Colors.RESET} Would scrape these files:")
        for f in files:
            print(f"  - {f}")
        return 0
    
    print(f"{'='*60}\n")
    
    success_count = 0
    skip_count = 0
    error_count = 0
    
    for i, file_path in enumerate(files, 1):
        path = Path(file_path)
        print(f"[{i}/{len(files)}] {path.name}")
        
        # Check if already has MetronInfo.xml
        if ignore_existing:
            try:
                with zipfile.ZipFile(path, "r") as z:
                    if "MetronInfo.xml" in z.namelist():
                        print(f"  {Colors.YELLOW}⊘{Colors.RESET} Skipping (already has MetronInfo.xml)")
                        skip_count += 1
                        continue
            except Exception as e:
                print(f"  {Colors.RED}✗{Colors.RESET} Error checking file: {e}", file=sys.stderr)
                error_count += 1
                continue
        
        # Run metron-tagger
        cmd = ["metron-tagger", "--online", str(path)]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                print(f"  {Colors.GREEN}✓{Colors.RESET} Successfully scraped")
                success_count += 1
            else:
                print(f"  {Colors.RED}✗{Colors.RESET} Failed (exit code {result.returncode})")
                if result.stderr:
                    print(f"    Error: {result.stderr.strip()}", file=sys.stderr)
                error_count += 1
                
        except subprocess.TimeoutExpired:
            print(f"  {Colors.RED}✗{Colors.RESET} Timeout (>60s)", file=sys.stderr)
            error_count += 1
        except KeyboardInterrupt:
            print(f"\n{Colors.YELLOW}⚠{Colors.RESET} Interrupted by user")
            raise
        except Exception as e:
            print(f"  {Colors.RED}✗{Colors.RESET} Error: {e}", file=sys.stderr)
            error_count += 1
    
    # Summary
    print(f"\n{'='*60}")
    print(f"{Colors.BOLD}SCRAPING SUMMARY{Colors.RESET}")
    print(f"{'='*60}")
    print(f"{Colors.GREEN}✓{Colors.RESET} Success: {success_count}")
    print(f"{Colors.YELLOW}⊘{Colors.RESET} Skipped: {skip_count}")
    print(f"{Colors.RED}✗{Colors.RESET} Errors: {error_count}")
    print(f"{'='*60}\n")
    
    return 0 if error_count == 0 else 1

def run_pipeline(
    paths: list[str],
    do_repair: bool = False,
    do_scrape: bool = False,
    do_normalize: bool = False,
    do_webp: bool = False,
    do_kapowarr: bool = False,
    strict: bool = False,
    check_filenames: bool = False,
    dry_run: bool = False,
    verbose: bool = False,
) -> None:
    """
    Run a complete pipeline: scan → repair → scrape → normalize → webp → kapowarr
    """
    print(f"{Colors.BLUE}{'='*60}{Colors.RESET}")
    print(f"{Colors.BLUE}PIPELINE START{Colors.RESET}")
    print(f"{Colors.BLUE}{'='*60}{Colors.RESET}\n")
    
    # Step 1: Collect all CBZ files
    files = collect_cbz_from_paths(paths)
    if not files:
        print("No .cbz files found.", file=sys.stderr)
        return
    
    print(f"Found {len(files)} comic file(s)\n")
    
    # Step 2: Scan all files and categorize issues
    print(f"{Colors.BLUE}[STEP 1/6] SCANNING{Colors.RESET}")
    print(f"{Colors.BLUE}{'-'*60}{Colors.RESET}\n")

    needs_repair = []
    needs_scraping_list = []
    ok_files = []  # Files with good metadata

    for f in files:
        reasons = needs_scraping(f, strict=strict, check_filenames=check_filenames, verbose=verbose)
        
        if "non-standard archive structure" in ' '.join(reasons):
            needs_repair.append(f)
        elif reasons:  # Has other issues (missing metadata, etc.)
            needs_scraping_list.append(f)
        else:
            # File is OK
            ok_files.append(f)

    print(f"\n{Colors.BLUE}SCAN SUMMARY:{Colors.RESET}")
    print(f"  • {len(needs_repair)} file(s) need repair")
    print(f"  • {len(needs_scraping_list)} file(s) need scraping")
    print(f"  • {len(ok_files)} file(s) have complete metadata")
    print(f"  • {len(files)} total file(s) in pipeline\n")

    # Step 3: Repair
    if do_repair and needs_repair:
        print(f"\n{Colors.BLUE}[STEP 2/6] REPAIRING{Colors.RESET}")
        print(f"{Colors.BLUE}{'-'*60}{Colors.RESET}\n")
        
        repaired = 0
        for f in needs_repair:
            if repair_archive(f, dry_run=dry_run, verbose=verbose):
                repaired += 1
                # After repair, rescan to see if it needs scraping or is OK
                if not dry_run:
                    reasons = needs_scraping(f, strict=strict, check_filenames=check_filenames, verbose=False)
                    if reasons:
                        needs_scraping_list.append(f)
                    else:
                        ok_files.append(f)
        
        print(f"\n{'[DRY RUN] Would repair' if dry_run else 'Repaired'} {repaired}/{len(needs_repair)} file(s)")
    else:
        print(f"\n{Colors.BLUE}[STEP 2/6] REPAIR{Colors.RESET} - Skipped")

    # Step 4: Scrape
    if do_scrape and needs_scraping_list:
        print(f"\n{Colors.BLUE}[STEP 3/6] SCRAPING{Colors.RESET}")
        print(f"{Colors.BLUE}{'-'*60}{Colors.RESET}\n")
        
        if dry_run:
            print(f"[DRY RUN] Would scrape {len(needs_scraping_list)} file(s):")
            for f in needs_scraping_list[:10]:
                print(f"  • {os.path.basename(f)}")
            if len(needs_scraping_list) > 10:
                print(f"  ... and {len(needs_scraping_list) - 10} more")
        else:
            print(f"{Colors.YELLOW}⚠ Scraping requires external tool (perdoo){Colors.RESET}")
            print(f"Run this command manually:\n")
            print(f"  perdoo scrape \\")
            for i, f in enumerate(needs_scraping_list):
                end = " \\" if i < len(needs_scraping_list) - 1 else ""
                print(f"    '{f}'{end}")
            print()
    else:
        print(f"\n{Colors.BLUE}[STEP 3/6] SCRAPE{Colors.RESET} - Skipped")

    # Step 5: Normalize (only on files with complete metadata)
    if do_normalize and ok_files:
        print(f"\n{Colors.BLUE}[STEP 4/6] NORMALIZING{Colors.RESET}")
        print(f"{Colors.BLUE}{'-'*60}{Colors.RESET}\n")
        
        changed = normalize_comic_metadata(ok_files, dry_run=dry_run)
        print(f"\n{'[DRY RUN] Would modify' if dry_run else 'Modified'} {changed}/{len(ok_files)} file(s)")
    else:
        print(f"\n{Colors.BLUE}[STEP 4/6] NORMALIZE{Colors.RESET} - Skipped (no files with complete metadata)")

    # Step 6: WebP (all files)
    if do_webp:
        print(f"\n{Colors.BLUE}[STEP 5/6] WEBP CONVERSION{Colors.RESET}")
        print(f"{Colors.BLUE}{'-'*60}{Colors.RESET}\n")
        
        converted = convert_to_webp(files, dry_run=dry_run)
        print(f"\n{'[DRY RUN] Would convert' if dry_run else 'Converted'} {converted} file(s)")
    else:
        print(f"\n{Colors.BLUE}[STEP 5/6] WEBP{Colors.RESET} - Skipped")

    # Step 7: Kapowarr (all files)
    if do_kapowarr:
        print(f"\n{Colors.BLUE}[STEP 6/6] KAPOWARR SYNC{Colors.RESET}")
        print(f"{Colors.BLUE}{'-'*60}{Colors.RESET}\n")
        
        # This requires API keys, so check they exist
        try:
            api_keys = APIKeys()  # Will raise if keys missing
            update_kapowarr_volumes(files, api_keys, dry_run=dry_run)
        except ValueError as e:
            print(f"{Colors.RED}✗ ERROR:{Colors.RESET} {e}", file=sys.stderr)
    else:
        print(f"\n{Colors.BLUE}[STEP 6/6] KAPOWARR{Colors.RESET} - Skipped")

if __name__ == "__main__":
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Comic pipeline helper CLI")
        
    # ---------- API keys (add BEFORE subparsers) ----------
    parser.add_argument(
        "--comicvine-key",
        help="ComicVine API key (overrides env/default)",
    )
    parser.add_argument(
        "--kapowarr-key",
        help="Kapowarr API key (overrides env/default)",
    )
    
    sub = parser.add_subparsers(dest="cmd", required=True)

    # ---------- scan ----------
    scan_parser = sub.add_parser(
        "scan",
        help="Scan for comics needing metadata scraping"
    )
    scan_parser.add_argument(
        "paths",
        nargs="+",
        help="Paths to scan (files or directories)"
    )
    scan_parser.add_argument(
        "--strict",
        action="store_true",
        help="Require Publisher and Title fields"
    )
    scan_parser.add_argument(
        "--check-filenames",
        action="store_true",
        help="Flag files with non-standard filenames for renaming"
    )
    scan_parser.add_argument(
        "--output",
        choices=["console", "json", "list"],
        default="console",
        help="Output format"
    )
    scan_parser.add_argument(
        "--output-file",
        help="Write output to file instead of stdout"
    )

    # ---------- normalize ----------
    normalize = sub.add_parser(
        "normalize",
        help="Normalize metadata: set Volume to start year, copy StoryArc to AlternateSeries",
    )
    normalize.add_argument("paths", nargs="+", help="Files or directories")
    normalize.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying files",
    )
    normalize.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed debug information",
    )

    # ---------- webp ----------
    webp = sub.add_parser(
        "webp",
        help="Convert JPG/PNG pages in CBZ files to WebP",
    )
    webp.add_argument("paths", nargs="+", help="Files or directories")
    webp.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output during conversion",
    )
    webp.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview conversion without modifying files",
    )

    # ---------- kapowarr-sync ----------
    ksync = sub.add_parser(
        "kapowarr-sync",
        help="Sync volumes with Kapowarr (adds/fixes volume folders)",
    )
    ksync.add_argument(
        "--url",
        default="http://localhost:5656",
        help="Kapowarr URL (default: http://localhost:5656)",
    )
    ksync.add_argument(
        "--comics-path",
        default="/mnt/comics",
        help="Root comics path (default: /mnt/comics)",
    )
    ksync.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output",
    )
    ksync.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview sync without making changes",
    )

    # ---------- check-normalize ----------
    check_norm = sub.add_parser(
        "check-normalize",
        help="Find comics that need normalization (missing/incorrect Volume, etc.)"
    )
    check_norm.add_argument("paths", nargs="+", help="Files or directories to scan")
    check_norm.add_argument(
        "--output",
        choices=["console", "json", "list"],
        default="console",
        help="Output format: console (default), json, or list",
    )
    check_norm.add_argument(
        "--output-file",
        help="Write output to file instead of stdout",
    )

    # ---------- metron scraper ----------    
    metron_parser = sub.add_parser(
        "metron-scrape",
        help="Scrape metadata using MetronTagger (non-interactive)"
    )
    metron_parser.add_argument(
        "paths",
        nargs="+",
        help="Comic files or directories to scrape"
    )
    metron_parser.add_argument(
        "--ignore-existing",
        action="store_true",
        help="Skip files that already have MetronInfo.xml"
    )
    metron_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be scraped without actually doing it"
    )

    # Repair command
    repair_parser = sub.add_parser(
        "repair",
        help="Repair non-standard CBZ archive structures (flatten subfolders)",
    )
    repair_parser.add_argument(
        "paths",
        nargs="+",
        help="Comic file(s) or folder(s) to repair",
    )
    repair_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be repaired without making changes",
    )

    # Pipeline command
    pipeline_parser = sub.add_parser(
        "pipeline",
        help="Run automated pipeline: scan → repair → scrape → normalize → webp → kapowarr",
    )
    pipeline_parser.add_argument(
        "paths",
        nargs="+",
        help="Comic file(s) or folder(s) to process",
    )
    pipeline_parser.add_argument(
        "--repair",
        action="store_true",
        help="Enable repair step (fix archive structure)",
    )
    pipeline_parser.add_argument(
        "--scrape",
        action="store_true",
        help="Enable scrape step (list files needing external scraping)",
    )
    pipeline_parser.add_argument(
        "--normalize",
        action="store_true",
        help="Enable normalize step (fix Volume/AlternateSeries)",
    )
    pipeline_parser.add_argument(
        "--webp",
        action="store_true",
        help="Enable WebP conversion step",
    )
    pipeline_parser.add_argument(
        "--kapowarr-sync",
        action="store_true",
        help="Enable Kapowarr sync step",
    )
    pipeline_parser.add_argument(
        "--all",
        action="store_true",
        help="Enable all pipeline steps",
    )
    pipeline_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )

    pipeline_parser.add_argument(
        "--strict",
        action="store_true",
        help="Use strict checking (require standard filenames)",
    )
    pipeline_parser.add_argument(
        "--check-filenames",
        action="store_true",
        help="Check filename format during scan",
    )

    pipeline_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed output for each file",
    )

    # Parse arguments
    args = parser.parse_args()

    # --- API key setup ---
    comicvine_key = args.comicvine_key or os.getenv("COMICVINE_API_KEY")
    kapowarr_key = args.kapowarr_key or os.getenv("KAPOWARR_API_KEY")

    # Only require keys for commands that actually use them
    if args.cmd == "kapowarr-sync":
        if not comicvine_key:
            parser.error(
                "ComicVine API key required for kapowarr-sync. "
                "Set COMICVINE_API_KEY env var or use --comicvine-key."
            )
        if not kapowarr_key:
            parser.error(
                "Kapowarr API key required for kapowarr-sync. "
                "Set KAPOWARR_API_KEY env var or use --kapowarr-key."
            )

    # Set whatever keys we have (some commands may not use them)
    try:
        APIKeys.set_api_keys(
            comic_vine_api_key=comicvine_key,
            kapowarr_api_key=kapowarr_key,
        )
    except Exception as e:
        print(f"Error setting API keys: {e}", file=sys.stderr)
        sys.exit(1)

    # ---------- RUN ----------
    exit_code = 0

    try:
        if args.cmd == "scan":
            sys.exit(find_files_needing_scraping(
                args.paths,
                strict=args.strict,
                check_filenames=args.check_filenames,
                output_format=args.output,
                output_file=args.output_file
            ))            
            if args.output == "console":
                print(f"\n{len(bad)} files need scraping")
            
            exit_code = 1 if bad else 0

        elif args.cmd == "normalize":
            files = collect_cbz_from_paths(args.paths)
            if not files:
                print("No CBZ files found in specified paths", file=sys.stderr)
                sys.exit(1)
            normalize_comic_metadata(files, dry_run=args.dry_run, verbose=args.verbose)

        elif args.cmd == "webp":
            files = collect_cbz_from_paths(args.paths)
            if not files:
                print("No CBZ files found in specified paths", file=sys.stderr)
                sys.exit(1)
            convert_to_webp(files, verbose=args.verbose, dry_run=args.dry_run)

        elif args.cmd == "kapowarr-sync":
            update_kapowarr_volumes(
                kapowarr_url=args.url,
                comics_path=args.comics_path,
                verbose=args.verbose,
                dry_run=args.dry_run,
            )

        elif args.cmd == "check-normalize":
            needs_norm = find_files_needing_normalize(
                args.paths,
                output_format=args.output,
                output_file=args.output_file
            )

        elif args.cmd == "metron-scrape":
            sys.exit(metron_scrape(
                args.paths,
                ignore_existing=args.ignore_existing,
                dry_run=args.dry_run
            ))


        elif args.cmd == "repair":
            files = collect_cbz_from_paths(args.paths)
            if not files:
                print("No .cbz files found.", file=sys.stderr)
                sys.exit(1)
            
            print(f"Repairing {len(files)} file(s)...\n")
            repaired = 0
            
            for f in files:
                if repair_archive(f, dry_run=args.dry_run, verbose=True):
                    repaired += 1
            
            print(f"\n{'[DRY RUN] Would repair' if args.dry_run else 'Repaired'} {repaired}/{len(files)} file(s)")

        elif args.cmd == "pipeline":
            # If --all is specified, enable everything
            if args.all:
                do_repair = do_scrape = do_normalize = do_webp = do_kapowarr = True
            else:
                do_repair = args.repair
                do_scrape = args.scrape
                do_normalize = args.normalize
                do_webp = args.webp
                do_kapowarr = args.kapowarr_sync
            
            # DEBUG
            print(f"DEBUG: do_repair={do_repair}, do_scrape={do_scrape}, do_normalize={do_normalize}, do_webp={do_webp}, do_kapowarr={do_kapowarr}", file=sys.stderr)
            
            run_pipeline(
                args.paths,
                do_repair=do_repair,
                do_scrape=do_scrape,
                do_normalize=do_normalize,
                do_webp=do_webp,
                do_kapowarr=do_kapowarr,
                strict=getattr(args, 'strict', False),
                check_filenames=getattr(args, 'check_filenames', False),
                dry_run=getattr(args, 'dry_run', False),
                verbose=getattr(args, 'verbose', False),
            )



    except FileNotFoundError as e:
        print(f"Error: File or directory not found - {e}", file=sys.stderr)
        exit_code = 1
    except PermissionError as e:
        print(f"Error: Permission denied - {e}", file=sys.stderr)
        exit_code = 1
    except KeyboardInterrupt:
        print("\nOperation cancelled by user", file=sys.stderr)
        exit_code = 130
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if getattr(args, 'verbose', False):
            import traceback
            traceback.print_exc()
        exit_code = 1

    sys.exit(exit_code)
