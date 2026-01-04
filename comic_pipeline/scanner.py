"""Comic scanning and validation functions"""

import os
import sys
import re
import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from darkseid.comic import Comic, MetadataFormat

from .utils import Colors, status_line


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
    
    # Check for year (4 digits)
    has_year = bool(re.search(r'\b(19|20)\d{2}\b', filename))
    
    # Check for issue number patterns
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

    # ---------- (D) Read ComicInfo ----------
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