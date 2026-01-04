"""Full pipeline orchestration"""
import sys
from typing import List
from .scanner import find_files_needing_scraping
from .normalizer import normalize_comic_metadata
from .image_converter import convert_to_webp
from .repair import repair_archive
from .scraper import metron_scrape
from .archive_converter import batch_convert_to_cbz
from .utils import Colors, collect_cbz_from_paths


def run_pipeline(paths: List[str],
                 skip_convert: bool = False,
                 skip_repair: bool = False,
                 skip_scan: bool = False,
                 skip_normalize: bool = False,
                 skip_webp: bool = False,
                 metron_user: str = None,
                 metron_pass: str = None,
                 dry_run: bool = False,
                 verbose: bool = False):
    """
    Run the full comic processing pipeline.
    
    Correct order:
    1. Convert CBR/CB7 to CBZ
    2. Repair archive structure (flatten to root)
    3. Scan and scrape metadata
    4. Normalize metadata (Volume, AlternateSeries)
    5. Convert images to WebP
    
    Args:
        paths: List of file or directory paths to process
        skip_convert: Skip CBR/CB7 to CBZ conversion
        skip_repair: Skip archive repair
        skip_scan: Skip scanning/scraping step
        skip_normalize: Skip metadata normalization
        skip_webp: Skip WebP conversion
        metron_user: Metron username for scraping
        metron_pass: Metron password for scraping
        dry_run: Preview changes without making them
        verbose: Enable verbose output
    """
    print(f"\n{Colors.BOLD}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}COMIC PIPELINE{Colors.RESET}")
    if dry_run:
        print(f"{Colors.YELLOW}[DRY RUN MODE]{Colors.RESET}")
    print(f"{Colors.BOLD}{'='*60}{Colors.RESET}\n")

    # Step 1: Convert CBR/CB7 to CBZ
    if not skip_convert:
        print(f"{Colors.CYAN}{'─'*60}{Colors.RESET}")
        print(f"{Colors.BOLD}STEP 1: CONVERT TO CBZ{Colors.RESET}")
        print(f"{Colors.CYAN}{'─'*60}{Colors.RESET}\n")
        
        # Find CBR/CB7 files
        all_files = collect_cbz_from_paths(paths, include_cbr=True)
        cbr_files = [f for f in all_files if f.endswith(('.cbr', '.cb7'))]
        
        if cbr_files:
            print(f"Found {len(cbr_files)} CBR/CB7 file(s) to convert\n")
            if not dry_run:
                successful, failed = batch_convert_to_cbz(cbr_files, delete_original=True, verbose=verbose)
                print(f"\n{Colors.GREEN}✓{Colors.RESET} Converted {len(successful)} file(s)")
                if failed:
                    print(f"{Colors.RED}✗{Colors.RESET} Failed to convert {len(failed)} file(s)")
            else:
                print(f"{Colors.BLUE}[DRY RUN]{Colors.RESET} Would convert {len(cbr_files)} file(s)\n")
        else:
            print(f"{Colors.GREEN}✓{Colors.RESET} No CBR/CB7 files found, skipping conversion\n")

    # Step 2: Repair archives (flatten structure)
    if not skip_repair:
        print(f"\n{Colors.CYAN}{'─'*60}{Colors.RESET}")
        print(f"{Colors.BOLD}STEP 2: REPAIR ARCHIVES{Colors.RESET}")
        print(f"{Colors.CYAN}{'─'*60}{Colors.RESET}\n")
        
        cbz_files = collect_cbz_from_paths(paths)
        if not cbz_files:
            print(f"{Colors.RED}✗{Colors.RESET} No CBZ files found", file=sys.stderr)
            sys.exit(1)
        
        repaired = 0
        for file in cbz_files:
            if repair_archive(file, dry_run=dry_run, verbose=verbose):
                repaired += 1
        
        if dry_run:
            print(f"\n{Colors.BLUE}[DRY RUN]{Colors.RESET} Would repair {repaired} file(s)")
        else:
            print(f"\n{Colors.GREEN}✓{Colors.RESET} Repaired {repaired} file(s)")

    # Collect CBZ files for remaining steps
    cbz_files = collect_cbz_from_paths(paths)
    if not cbz_files:
        print(f"{Colors.RED}✗{Colors.RESET} No CBZ files found in provided paths", file=sys.stderr)
        sys.exit(1)
    
    print(f"\nProcessing {len(cbz_files)} CBZ file(s)\n")

    # Step 3: Scan and Scrape
    if not skip_scan:
        print(f"\n{Colors.CYAN}{'─'*60}{Colors.RESET}")
        print(f"{Colors.BOLD}STEP 3: SCAN & SCRAPE{Colors.RESET}")
        print(f"{Colors.CYAN}{'─'*60}{Colors.RESET}\n")
        
        exit_code = find_files_needing_scraping(
            paths,
            strict=True,
            check_filenames=False,
            output_format="console",
            output_file=None
        )
        
        if exit_code == 1:
            # Files need scraping
            print(f"\n{Colors.YELLOW}⚠{Colors.RESET} Some files need scraping.")
            
            if metron_user and metron_pass:
                print(f"{Colors.BLUE}[SCRAPING]{Colors.RESET} Scraping with Metron...\n")
                if not dry_run:
                    metron_scrape(cbz_files, username=metron_user, password=metron_pass,
                                overwrite=False, dry_run=False, verbose=verbose)
                else:
                    print(f"{Colors.BLUE}[DRY RUN]{Colors.RESET} Would scrape {len(cbz_files)} file(s)\n")
            else:
                print(f"{Colors.YELLOW}⚠{Colors.RESET} No Metron credentials provided. Skipping scraping.")
                print("  Provide --metron-user and --metron-pass to enable scraping.")
                if not dry_run:
                    response = input("\nContinue without scraping? [y/N]: ")
                    if response.lower() != 'y':
                        sys.exit(1)
        else:
            print(f"{Colors.GREEN}✓{Colors.RESET} All files have valid metadata\n")

    # Step 4: Normalize metadata
    if not skip_normalize:
        print(f"\n{Colors.CYAN}{'─'*60}{Colors.RESET}")
        print(f"{Colors.BOLD}STEP 4: NORMALIZE METADATA{Colors.RESET}")
        print(f"{Colors.CYAN}{'─'*60}{Colors.RESET}\n")
        normalize_comic_metadata(cbz_files, dry_run=dry_run, verbose=verbose)

    # Step 5: Convert to WebP
    if not skip_webp:
        print(f"\n{Colors.CYAN}{'─'*60}{Colors.RESET}")
        print(f"{Colors.BOLD}STEP 5: CONVERT TO WEBP{Colors.RESET}")
        print(f"{Colors.CYAN}{'─'*60}{Colors.RESET}\n")
        convert_to_webp(cbz_files, verbose=verbose, dry_run=dry_run)

    # Final summary
    print(f"\n{Colors.BOLD}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}PIPELINE COMPLETE{Colors.RESET}")
    print(f"{Colors.BOLD}{'='*60}{Colors.RESET}\n")
    
    if dry_run:
        print(f"{Colors.YELLOW}This was a dry run. No files were modified.{Colors.RESET}")
        print(f"Run without --dry-run to apply changes.\n")