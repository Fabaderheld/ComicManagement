"""Full pipeline orchestration"""

import sys
from typing import List

from .scanner import find_files_needing_scraping
from .normalizer import normalize_comic_metadata, find_files_needing_normalize
from .image_converter import convert_to_webp
from .repair import repair_archive
from .scraper import metron_scrape
from .utils import Colors, collect_cbz_from_paths


def run_pipeline(paths: List[str], 
                 skip_scan: bool = False,
                 skip_normalize: bool = False,
                 skip_convert: bool = False,
                 skip_repair: bool = False,
                 dry_run: bool = False,
                 verbose: bool = False):
    """
    Run the full comic processing pipeline.
    
    Steps:
    1. Scan for files needing scraping
    2. Scrape with Metron (if needed)
    3. Normalize metadata
    4. Convert to WebP
    5. Repair archive structure
    
    Args:
        paths: List of file or directory paths to process
        skip_scan: Skip the scanning step
        skip_normalize: Skip metadata normalization
        skip_convert: Skip WebP conversion
        skip_repair: Skip archive repair
        dry_run: Preview changes without making them
        verbose: Enable verbose output
    """
    print(f"\n{Colors.BOLD}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}COMIC PIPELINE{Colors.RESET}")
    if dry_run:
        print(f"{Colors.YELLOW}[DRY RUN MODE]{Colors.RESET}")
    print(f"{Colors.BOLD}{'='*60}{Colors.RESET}\n")
    
    # Collect all CBZ files
    all_files = collect_cbz_from_paths(paths)
    
    if not all_files:
        print(f"{Colors.RED}✗{Colors.RESET} No CBZ files found in provided paths", file=sys.stderr)
        sys.exit(1)
    
    print(f"Found {len(all_files)} CBZ file(s) to process\n")
    
    # Step 1: Scan and Scrape
    if not skip_scan:
        print(f"{Colors.CYAN}{'─'*60}{Colors.RESET}")
        print(f"{Colors.BOLD}STEP 1: SCAN & SCRAPE{Colors.RESET}")
        print(f"{Colors.CYAN}{'─'*60}{Colors.RESET}\n")
        
        exit_code = find_files_needing_scraping(
            paths, 
            strict=True, 
            check_filenames=False,
            output_format="list",
            output_file=None
        )
        
        if exit_code == 1:
            # Files need scraping
            print(f"\n{Colors.YELLOW}⚠{Colors.RESET} Some files need scraping. Run with metron or perdoo.", file=sys.stderr)
            if not dry_run:
                response = input("Continue anyway? [y/N]: ")
                if response.lower() != 'y':
                    sys.exit(1)
        else:
            print(f"{Colors.GREEN}✓{Colors.RESET} All files have valid metadata\n")
    
    # Step 2: Normalize
    if not skip_normalize:
        print(f"\n{Colors.CYAN}{'─'*60}{Colors.RESET}")
        print(f"{Colors.BOLD}STEP 2: NORMALIZE METADATA{Colors.RESET}")
        print(f"{Colors.CYAN}{'─'*60}{Colors.RESET}\n")
        
        normalize_comic_metadata(all_files, dry_run=dry_run, verbose=verbose)
    
    # Step 3: Convert to WebP
    if not skip_convert:
        print(f"\n{Colors.CYAN}{'─'*60}{Colors.RESET}")
        print(f"{Colors.BOLD}STEP 3: CONVERT TO WEBP{Colors.RESET}")
        print(f"{Colors.CYAN}{'─'*60}{Colors.RESET}\n")
        
        convert_to_webp(all_files, verbose=verbose, dry_run=dry_run)
    
    # Step 4: Repair archives
    if not skip_repair:
        print(f"\n{Colors.CYAN}{'─'*60}{Colors.RESET}")
        print(f"{Colors.BOLD}STEP 4: REPAIR ARCHIVES{Colors.RESET}")
        print(f"{Colors.CYAN}{'─'*60}{Colors.RESET}\n")
        
        repaired = 0
        for file in all_files:
            if repair_archive(file, dry_run=dry_run, verbose=verbose):
                repaired += 1
        
        if dry_run:
            print(f"\n{Colors.BLUE}[DRY RUN]{Colors.RESET} Would repair {repaired} file(s)")
        else:
            print(f"\n{Colors.GREEN}✓{Colors.RESET} Repaired {repaired} file(s)")
    
    # Final summary
    print(f"\n{Colors.BOLD}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}PIPELINE COMPLETE{Colors.RESET}")
    print(f"{Colors.BOLD}{'='*60}{Colors.RESET}\n")
    
    if dry_run:
        print(f"{Colors.YELLOW}This was a dry run. No files were modified.{Colors.RESET}")
        print(f"Run without --dry-run to apply changes.\n")