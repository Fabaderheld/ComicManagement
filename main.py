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


class ComicInfo:
    """Class to handle ComicInfo extraction and manipulation"""
    
    @staticmethod
    def get_comic_info(comic_path: str) -> Optional[ET.Element]:
        """
        Extracts and returns ComicInfo from a .cbz file.
        
        Args:
            comic_path: The path to the comic file (.cbz format)
            
        Returns:
            XML Element containing ComicInfo data, or None if not found
            
        Example:
            comic_info = ComicInfo.get_comic_info("/path/to/comic.cbz")
        """
        try:
            with zipfile.ZipFile(comic_path, 'r') as zip_file:
                # Find ComicInfo.xml file
                comic_info_file = None
                for file_name in zip_file.namelist():
                    if 'ComicInfo.xml' in file_name:
                        comic_info_file = file_name
                        break
                
                if not comic_info_file:
                    return None
                
                # Read and parse the XML content
                with zip_file.open(comic_info_file) as file:
                    xml_content = file.read()
                    root = ET.fromstring(xml_content)
                    return root
                    
        except Exception as e:
            print(f"Error reading ComicInfo: {e}")
            return None


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


def get_comic_format(comic_path: str) -> ComicFormat:
    """
    Determines the format of images within a .cbz file.
    
    Args:
        comic_path: The path to the comic file (.cbz format)
        
    Returns:
        ComicFormat object containing format information
        
    Example:
        format_info = get_comic_format("/path/to/comic.cbz")
        if format_info.need_conversion:
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


def needs_scraping(comic_path: str, strict: bool = True) -> List[str]:
    """
    Determine if a CBZ 'needs scraping', i.e. has missing or weak ComicInfo.
    Returns a list of reasons. If list is empty, file looks OK.
    """
    reasons: List[str] = []
    path = Path(comic_path)
    
    if not path.is_file() or path.suffix.lower() != ".cbz":
        reasons.append("not a CBZ file")
        return reasons
    
    try:
        with zipfile.ZipFile(path, 'r') as z:
            if "ComicInfo.xml" not in z.namelist():
                reasons.append("no ComicInfo.xml")
                return reasons
            
            data = z.read("ComicInfo.xml")
            xml = ET.fromstring(data)
            
            series = (xml.findtext("Series") or "").strip()
            number = (xml.findtext("Number") or "").strip()
            year = (xml.findtext("Year") or "").strip()
            publisher = (xml.findtext("Publisher") or "").strip()
            title = (xml.findtext("Title") or "").strip()
            
            if not series:
                reasons.append("missing Series")
            if not number:
                reasons.append("missing Number")
            if not year:
                reasons.append("missing Year")
            
            if strict:
                if not publisher:
                    reasons.append("missing Publisher")
                if not title:
                    reasons.append("missing Title")
                    
    except Exception as e:
        reasons.append(f"error reading ComicInfo.xml: {e}")
    
    return reasons


def find_files_needing_scraping(paths: List[str], strict: bool = True, 
                                output_format: str = "console",
                                output_file: Optional[str] = None) -> List[Path]:
    """
    Walk given files/dirs and return CBZ files that need scraping.
    
    Args:
        paths: List of file or directory paths to scan
        strict: If True, also check for Publisher and Title
        output_format: Output format - "console", "json", or "list"
        output_file: Optional file path to write results to
        
    Returns:
        List of Path objects for files needing scraping
    """
    results: List[Path] = []
    results_with_reasons: List[Dict[str, Any]] = []
    
    for p in paths:
        pth = Path(p)
        if pth.is_dir():
            for cbz in pth.rglob("*.cbz"):
                if "#recycle" in str(cbz):
                    continue
                reasons = needs_scraping(str(cbz), strict=strict)
                if reasons:
                    results.append(cbz)
                    results_with_reasons.append({
                        "path": str(cbz),
                        "reasons": reasons
                    })
                    if output_format == "console":
                        print(f"[NEEDS SCRAPE] {cbz} -> {', '.join(reasons)}")
        elif pth.is_file() and pth.suffix.lower() == ".cbz":
            reasons = needs_scraping(str(pth), strict=strict)
            if reasons:
                results.append(pth)
                results_with_reasons.append({
                    "path": str(pth),
                    "reasons": reasons
                })
                if output_format == "console":
                    print(f"[NEEDS SCRAPE] {pth} -> {', '.join(reasons)}")
    
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
            print("\n--- FILE LIST ---")
            print(list_output)
    
    return results


def normalize_comic_metadata(comics: List[str], dry_run: bool = False):
    """
    Normalizes ComicInfo metadata for the supplied CBZ files:

    - Groups by (Series, Publisher)
    - Finds earliest Year in each group
    - Sets <Volume> to that starting Year
    - If <AlternateSeries> is empty/missing and <StoryArc> exists,
      copy StoryArc → AlternateSeries

    If dry_run=True, prints changes without modifying files.
    """
    if dry_run:
        print("[DRY RUN MODE] No files will be modified\n")
    
    runs: Dict[tuple, List[int]] = {}

    # PASS 1: collect years
    for c in comics:
        path = Path(c)
        if not path.is_file() or path.suffix.lower() != ".cbz":
            print(f"[SKIP] Not a CBZ: {path}")
            continue

        try:
            with zipfile.ZipFile(path, "r") as z:
                if "ComicInfo.xml" not in z.namelist():
                    print(f"[WARN] No ComicInfo.xml: {path}")
                    continue

                data = z.read("ComicInfo.xml")
                xml = ET.fromstring(data)

                series = (xml.findtext("Series") or "").strip()
                publisher = (xml.findtext("Publisher") or "").strip()
                year_text = (xml.findtext("Year") or "").strip()

                if not series or not year_text:
                    print(f"[WARN] Missing Series or Year in: {path}")
                    continue

                try:
                    year = int(year_text)
                except ValueError:
                    print(f"[WARN] Non-integer Year '{year_text}' in: {path}")
                    continue

                key = (series, publisher)
                runs.setdefault(key, []).append(year)
        except Exception as e:
            print(f"[WARN] Failed reading {path}: {e}")

    if not runs:
        print("No valid Series/Year data found. Nothing to do.")
        return

    # compute starting years
    start_years: Dict[tuple, int] = {k: min(v) for k, v in runs.items()}

    print("\nDetected runs (based on supplied files):")
    for (series, publisher), y in sorted(start_years.items()):
        pub = publisher or "Unknown"
        print(f"- {pub} | {series} -> start year {y}")

    # PASS 2: write Volume and AlternateSeries (from StoryArc)
    print(f"\n{'[DRY RUN] Would update' if dry_run else 'Updating'} Volume and AlternateSeries fields...\n")

    changes_count = 0
    for c in comics:
        path = Path(c)
        if not path.is_file() or path.suffix.lower() != ".cbz":
            continue

        try:
            with zipfile.ZipFile(path, "r") as z:
                if "ComicInfo.xml" not in z.namelist():
                    continue

                data = z.read("ComicInfo.xml")
                xml = ET.fromstring(data)

                series = (xml.findtext("Series") or "").strip()
                publisher = (xml.findtext("Publisher") or "").strip()
                key = (series, publisher)

                if key not in start_years:
                    continue

                # ----- Volume from starting year -----
                start_year = str(start_years[key])
                vol_elem = xml.find("Volume")
                if vol_elem is None:
                    vol_elem = ET.SubElement(xml, "Volume")

                old_vol_val = (vol_elem.text or "").strip()
                volume_changed = old_vol_val != start_year

                # ----- AlternateSeries from StoryArc if empty -----
                # Try both StoryArc and StoryArcTitle just in case
                story_arc = (
                    (xml.findtext("StoryArc") or "")
                    or (xml.findtext("StoryArcTitle") or "")
                ).strip()

                alt_series_elem = xml.find("AlternateSeries")
                if alt_series_elem is None:
                    alt_series_elem = ET.SubElement(xml, "AlternateSeries")

                old_alt_series = (alt_series_elem.text or "").strip()

                alt_series_changed = False
                if not old_alt_series and story_arc:
                    # Only copy if AlternateSeries is empty and StoryArc exists
                    alt_series_changed = True

                # If nothing changed, skip
                if not volume_changed and not alt_series_changed:
                    continue

                # Print what's changing
                if volume_changed:
                    print(f"{'[DRY RUN] Would update' if dry_run else 'Updating'} {path.name}: Volume {old_vol_val or '(empty)'} -> {start_year}")
                
                if alt_series_changed:
                    print(f"{'[DRY RUN] Would update' if dry_run else 'Updating'} {path.name}: AlternateSeries (empty) -> '{story_arc}'")

                changes_count += 1

                # Skip actual file modification in dry-run mode
                if dry_run:
                    continue

                # Apply changes
                if volume_changed:
                    vol_elem.text = start_year
                
                if alt_series_changed:
                    alt_series_elem.text = story_arc

                new_xml = ET.tostring(xml, encoding="utf-8", xml_declaration=True)

                # rewrite CBZ safely
                tmp = tempfile.NamedTemporaryFile(delete=False)
                tmp.close()

                with zipfile.ZipFile(path, "r") as zin, \
                     zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as zout:
                    for item in zin.infolist():
                        if item.filename == "ComicInfo.xml":
                            zout.writestr("ComicInfo.xml", new_xml)
                        else:
                            zout.writestr(item, zin.read(item.filename))

                shutil.move(tmp.name, path)

        except Exception as e:
            print(f"[WARN] Failed updating {path}: {e}")

    print(f"\n{'[DRY RUN] Would change' if dry_run else 'Changed'} {changes_count} files")
    print("\nDone normalizing metadata ✔")


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


if __name__ == "__main__":
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Comic pipeline helper CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # ---------- scan ----------
    scan = sub.add_parser("scan", help="Find comics needing scraping")
    scan.add_argument("paths", nargs="+", help="Files or directories to scan")
    scan.add_argument(
        "--strict",
        action="store_true",
        help="Also require Publisher + Title to be present",
    )
    scan.add_argument(
        "--output",
        choices=["console", "json", "list"],
        default="console",
        help="Output format: console (default), json, or list",
    )
    scan.add_argument(
        "--output-file",
        help="Write output to file instead of stdout",
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

    # ---------- API keys ----------
    parser.add_argument(
        "--comicvine-key",
        help="ComicVine API key (overrides env/default)",
    )
    parser.add_argument(
        "--kapowarr-key",
        help="Kapowarr API key (overrides env/default)",
    )

    args = parser.parse_args()

    # --- API key setup ---
    comicvine_key = (
        args.comicvine_key
        or os.getenv("COMICVINE_API_KEY")
    )
    kapowarr_key = (
        args.kapowarr_key
        or os.getenv("KAPOWARR_API_KEY")
    )

    # Validate required API keys
    if not comicvine_key:
        parser.error(
            "ComicVine API key required. Set COMICVINE_API_KEY environment variable "
            "or use --comicvine-key argument"
        )

    if args.cmd == "kapowarr-sync" and not kapowarr_key:
        parser.error(
            "Kapowarr API key required for sync command. Set KAPOWARR_API_KEY "
            "environment variable or use --kapowarr-key argument"
        )

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
            bad = find_files_needing_scraping(
                args.paths, 
                strict=args.strict,
                output_format=args.output,
                output_file=args.output_file
            )
            
            if args.output == "console":
                print(f"\n{len(bad)} files need scraping")
            
            exit_code = 1 if bad else 0

        elif args.cmd == "normalize":
            files = collect_cbz_from_paths(args.paths)
            if not files:
                print("No CBZ files found in specified paths", file=sys.stderr)
                sys.exit(1)
            normalize_comic_metadata(files, dry_run=args.dry_run)

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
