"""Comic metadata normalization functions"""
import os
import re
import json
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Optional, Any
from darkseid.comic import Comic, MetadataFormat
from .utils import get_tag_element


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
        
        # ✅ FIX: Use correct darkseid API
        if not comic.has_metadata(MetadataFormat.COMIC_INFO):
            reasons.append("no ComicInfo.xml")
            return reasons
        
        # ✅ FIX: Use correct darkseid API
        metadata = comic.read_metadata(MetadataFormat.COMIC_INFO)
        
        # Extract values from darkseid objects
        series_obj = getattr(metadata, "series", None)
        series = series_obj.name if series_obj and hasattr(series_obj, "name") else str(series_obj) if series_obj else ""
        
        publisher_obj = getattr(metadata, "publisher", None)
        publisher = publisher_obj.name if publisher_obj and hasattr(publisher_obj, "name") else ""
        
        # Get year from cover_date
        cover_date = getattr(metadata, "cover_date", None)
        year = ""
        if cover_date:
            if hasattr(cover_date, "year"):
                year = str(cover_date.year)
            elif isinstance(cover_date, str):
                match = re.search(r'(\d{4})', cover_date)
                if match:
                    year = match.group(1)
        
        volume = str(getattr(metadata, "volume", ""))
        
        story_arc = getattr(metadata, "story_arc", "") or ""
        alt_series = getattr(metadata, "alternate_series", "") or ""
        
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


def normalize_comic_metadata(cbz_files, dry_run=False, verbose=False):
    """
    Normalize comic metadata:
    - Set Volume to the start year of the series
    - Set AlternateSeries from StoryArc (or Series if StoryArc is empty)
    
    Always updates these fields, even if they already exist.
    """
    from darkseid.comic import Comic, MetadataFormat
    
    if dry_run:
        print("🔍 DRY RUN: normalize-comic-metadata")
    
    # Pass 1: Collect series and determine start years
    # Try MetronInfo first (has complete data), fallback to ComicInfo
    series_years = {}
    for cbz_path in cbz_files:
        try:
            comic = Comic(str(cbz_path))
            
            # Try MetronInfo first (has series.start_year)
            metadata = None
            if comic.has_metadata(MetadataFormat.METRON_INFO):
                metadata = comic.read_metadata(MetadataFormat.METRON_INFO)
                if verbose:
                    print(f"📖 Reading MetronInfo from {os.path.basename(cbz_path)}")
            elif comic.has_metadata(MetadataFormat.COMIC_INFO):
                metadata = comic.read_metadata(MetadataFormat.COMIC_INFO)
                if verbose:
                    print(f"📖 Reading ComicInfo from {os.path.basename(cbz_path)}")
            
            if not metadata:
                continue
            
            # Extract series
            series_obj = getattr(metadata, "series", None)
            series = ""
            start_year = None
            
            if series_obj:
                # MetronInfo has series.name and series.start_year
                if hasattr(series_obj, "name"):
                    series = series_obj.name
                    if hasattr(series_obj, "start_year"):
                        start_year = series_obj.start_year
                        if verbose:
                            print(f"  ✓ Found start_year from series object: {start_year}")
                else:
                    series = str(series_obj)
            
            if not series:
                continue
            
            # If we didn't get start_year from series object, try cover_date
            if not start_year:
                cover_date = getattr(metadata, "cover_date", None)
                if cover_date:
                    if hasattr(cover_date, "year"):
                        start_year = cover_date.year
                        if verbose:
                            print(f"  ✓ Found year from cover_date: {start_year}")
                    elif isinstance(cover_date, str):
                        match = re.search(r'(\d{4})', cover_date)
                        if match:
                            start_year = int(match.group(1))
                            if verbose:
                                print(f"  ✓ Extracted year from cover_date string: {start_year}")
            
            if not start_year:
                if verbose:
                    print(f"  ⚠️  No year found for {os.path.basename(cbz_path)}")
                continue
            
            if series not in series_years:
                series_years[series] = start_year
            else:
                series_years[series] = min(series_years[series], start_year)
                
        except Exception as e:
            print(f"⚠️  Error reading {cbz_path}: {e}")
            if verbose:
                import traceback
                traceback.print_exc()
            continue
    
    if verbose:
        print(f"\n📊 Found {len(series_years)} series with start years:")
        for series, year in sorted(series_years.items()):
            print(f"  - {series}: {year}")
    
    if not series_years:
        print("⚠️  No series with years found - cannot normalize")
        return
    
    # Pass 2: Update Volume and AlternateSeries in ComicInfo.xml
    changed = 0
    for cbz_path in cbz_files:
        try:
            with zipfile.ZipFile(cbz_path, 'r') as zf:
                if 'ComicInfo.xml' not in zf.namelist():
                    if verbose:
                        print(f"⚠️  No ComicInfo.xml in {os.path.basename(cbz_path)}")
                    continue
                
                xml_data = zf.read('ComicInfo.xml')
                root = ET.fromstring(xml_data)
                
                series = root.findtext('Series', '').strip()
                if not series:
                    if verbose:
                        print(f"⚠️  No Series in ComicInfo.xml for {os.path.basename(cbz_path)}")
                    continue
                    
                if series not in series_years:
                    if verbose:
                        print(f"⚠️  Series '{series}' not in start_years map for {os.path.basename(cbz_path)}")
                    continue
                
                start_year = series_years[series]
                file_changed = False
                
                # Always set Volume to start year
                volume_elem = get_tag_element(root, 'Volume')
                old_volume = volume_elem.text
                volume_elem.text = str(start_year)
                if old_volume != str(start_year):
                    file_changed = True
                    if dry_run or verbose:
                        print(f"  Volume: '{old_volume}' → '{start_year}' in {os.path.basename(cbz_path)}")
                
                # Always set AlternateSeries
                alt_elem = get_tag_element(root, 'AlternateSeries')
                story_arc = root.findtext('StoryArc', '').strip()
                story_arc_title = root.findtext('StoryArcTitle', '').strip()
                
                # Priority: StoryArc > StoryArcTitle > Series
                new_alt_value = story_arc or story_arc_title or series
                old_alt = alt_elem.text
                alt_elem.text = new_alt_value
                if old_alt != new_alt_value:
                    file_changed = True
                    if dry_run or verbose:
                        print(f"  AlternateSeries: '{old_alt}' → '{new_alt_value}' in {os.path.basename(cbz_path)}")
                
                # Write changes if not dry run
                if file_changed:
                    changed += 1
                    if not dry_run:
                        # Write back to CBZ
                        temp_path = cbz_path + '.tmp'
                        with zipfile.ZipFile(temp_path, 'w', zipfile.ZIP_DEFLATED) as new_zf:
                            for item in zf.namelist():
                                if item == 'ComicInfo.xml':
                                    new_zf.writestr(item, ET.tostring(root, encoding='utf-8'))
                                else:
                                    new_zf.writestr(item, zf.read(item))
                        os.replace(temp_path, cbz_path)
        except Exception as e:
            print(f"⚠️  Error processing {cbz_path}: {e}")
            if verbose:
                import traceback
                traceback.print_exc()
            continue
    
    if dry_run:
        print(f"\n✓ Would modify {changed} file(s)")
    else:
        print(f"✓ Modified {changed} file(s)")