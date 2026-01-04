"""Comic metadata normalization functions"""

import os
import re
import json
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Optional, Any

from .utils import get_tag_element


def needs_normalize(comic_path: str, start_years: Optional[Dict[tuple, int]] = None) -> List[str]:
    """
    Determine if a CBZ needs normalization using Darkseid.
    """
    from darkseid.comic import Comic
    
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


def normalize_comic_metadata(cbz_files, dry_run=False, verbose=False):
    """
    Normalize comic metadata:
    - Set Volume to the start year of the series
    - Set AlternateSeries from StoryArc (or Series if StoryArc is empty)
    
    Always updates these fields, even if they already exist.
    """
    if dry_run:
        print("🔍 DRY RUN: normalize-comic-metadata")
    
    # Pass 1: Collect series and determine start years
    series_years = {}
    for cbz_path in cbz_files:
        try:
            with zipfile.ZipFile(cbz_path, 'r') as zf:
                if 'ComicInfo.xml' not in zf.namelist():
                    continue
                xml_data = zf.read('ComicInfo.xml')
                root = ET.fromstring(xml_data)
                
                series = root.findtext('Series', '').strip()
                year_text = root.findtext('Year', '').strip()
                
                if not series or not year_text:
                    continue
                
                try:
                    year = int(year_text)
                except ValueError:
                    continue
                
                if series not in series_years:
                    series_years[series] = year
                else:
                    series_years[series] = min(series_years[series], year)
        except Exception as e:
            print(f"⚠️  Error reading {cbz_path}: {e}")
            continue
    
    # Pass 2: Update Volume and AlternateSeries
    changed = 0
    for cbz_path in cbz_files:
        try:
            with zipfile.ZipFile(cbz_path, 'r') as zf:
                if 'ComicInfo.xml' not in zf.namelist():
                    continue
                xml_data = zf.read('ComicInfo.xml')
                root = ET.fromstring(xml_data)
                
                series = root.findtext('Series', '').strip()
                if not series or series not in series_years:
                    continue
                
                start_year = series_years[series]
                file_changed = False
                
                # Always set Volume to start year
                volume_elem = get_tag_element(root, 'Volume')
                old_volume = volume_elem.text
                volume_elem.text = str(start_year)
                if old_volume != str(start_year):
                    file_changed = True
                    if dry_run:
                        print(f"  Would update Volume: {old_volume} → {start_year} in {cbz_path}")
                
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
                    if dry_run:
                        print(f"  Would update AlternateSeries: '{old_alt}' → '{new_alt_value}' in {cbz_path}")
                
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
            continue
    
    if dry_run:
        print(f"\n✓ Would modify {changed} file(s)")
    else:
        print(f"✓ Modified {changed} file(s)")