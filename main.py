#!/usr/bin/env python3
"""
Comic Pipeline CLI - A tool for managing and processing comic book archives

This tool provides commands for:
- Scanning comics for missing metadata
- Normalizing metadata (Volume, AlternateSeries)
- Converting images to WebP format
- Repairing archive structure
- Syncing with Kapowarr
- Running the full pipeline
"""

import sys
import argparse
import os

from comic_pipeline import (
    APIKeys,
    find_files_needing_scraping,
    find_files_needing_normalize,
    normalize_comic_metadata,
    convert_to_webp,
    repair_archive,
    update_kapowarr_volumes,
    metron_scrape,
    run_pipeline,
    collect_cbz_from_paths,
    Colors
)


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Comic Pipeline - Manage and process comic book archives",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scan for files needing metadata
  %(prog)s scan /path/to/comics

  # Normalize metadata with dry-run
  %(prog)s normalize --dry-run /path/to/comics

  # Convert to WebP
  %(prog)s webp /path/to/comics

  # Sync with Kapowarr
  %(prog)s kapowarr-sync --kapowarr-url http://localhost:5656

  # Run full pipeline
  %(prog)s pipeline /path/to/comics
        """
    )
    
    # Global arguments
    parser.add_argument(
        '--comicvine-key',
        help='ComicVine API key (or set COMICVINE_API_KEY env var)',
        default=os.getenv('COMICVINE_API_KEY')
    )
    parser.add_argument(
        '--kapowarr-key',
        help='Kapowarr API key (or set KAPOWARR_API_KEY env var)',
        default=os.getenv('KAPOWARR_API_KEY')
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose output'
    )
    # In the global arguments section (before subparsers), add:
    parser.add_argument(
        '--metron-user',
        help='Metron username (or set METRON_USER env var)',
        default=os.getenv('METRON_USER')
    )
    parser.add_argument(
        '--metron-pass',
        help='Metron password (or set METRON_PASS env var)',
        default=os.getenv('METRON_PASS')
    )


    
    # Subcommands
    sub = parser.add_subparsers(dest='cmd', help='Command to run')
    
    # scan command
    scan_parser = sub.add_parser('scan', help='Scan for files needing metadata scraping')
    scan_parser.add_argument('paths', nargs='+', help='Files or directories to scan')
    scan_parser.add_argument('--strict', action='store_true', help='Use strict validation')
    scan_parser.add_argument('--check-filenames', action='store_true', help='Check filename format')
    scan_parser.add_argument('--output-format', choices=['console', 'json', 'list'], 
                            default='console', help='Output format')
    scan_parser.add_argument('--output-file', help='Write output to file')
    
    # normalize command
    normalize_parser = sub.add_parser('normalize', help='Normalize comic metadata')
    normalize_parser.add_argument('paths', nargs='+', help='Files or directories to normalize')
    normalize_parser.add_argument('--dry-run', action='store_true', help='Preview changes without applying')
    normalize_parser.add_argument('--scan', action='store_true', help='Only scan, don\'t normalize')
    normalize_parser.add_argument('--output-format', choices=['console', 'json', 'list'], 
                                 default='console', help='Output format (scan mode only)')
    normalize_parser.add_argument('--output-file', help='Write output to file (scan mode only)')
    
    # webp command
    webp_parser = sub.add_parser('webp', help='Convert images to WebP format')
    webp_parser.add_argument('paths', nargs='+', help='Files or directories to convert')
    webp_parser.add_argument('--dry-run', action='store_true', help='Preview changes without applying')
    
    # repair command
    repair_parser = sub.add_parser('repair', help='Repair archive structure')
    repair_parser.add_argument('paths', nargs='+', help='Files or directories to repair')
    repair_parser.add_argument('--dry-run', action='store_true', help='Preview changes without applying')
    
    # kapowarr-sync command
    kapowarr_parser = sub.add_parser('kapowarr-sync', help='Sync volumes with Kapowarr')
    kapowarr_parser.add_argument('--kapowarr-url', default='http://localhost:5656',
                                help='Kapowarr URL (default: http://localhost:5656)')
    kapowarr_parser.add_argument('--comics-path', default='/mnt/comics',
                                help='Comics root path (default: /mnt/comics)')
    kapowarr_parser.add_argument('--dry-run', action='store_true', help='Preview changes without applying')
    
    # metron command
    metron_parser = sub.add_parser('metron', help='Scrape metadata using Metron API')
    metron_parser.add_argument('paths', nargs='+', help='Files or directories to scrape')
    metron_parser.add_argument('--overwrite', action='store_true',
                            help='Overwrite existing metadata fields (default: only fill empty fields)')
    metron_parser.add_argument('--dry-run', action='store_true',
                            help='Preview what would be scraped without modifying files')
    metron_parser.add_argument('--verbose', action='store_true',
                            help='Enable verbose output')
    
    # pipeline command
    pipeline_parser = sub.add_parser('pipeline', help='Run full processing pipeline')
    pipeline_parser.add_argument('paths', nargs='+', help='Files or directories to process')
    pipeline_parser.add_argument('--skip-scan', action='store_true', help='Skip scanning step')
    pipeline_parser.add_argument('--skip-normalize', action='store_true', help='Skip normalization step')
    pipeline_parser.add_argument('--skip-convert', action='store_true', help='Skip WebP conversion step')
    pipeline_parser.add_argument('--skip-repair', action='store_true', help='Skip repair step')
    pipeline_parser.add_argument('--dry-run', action='store_true', help='Preview all changes without applying')
    
    # convert command
    convert_parser = sub.add_parser('convert', help='Convert CBR/CB7 files to CBZ')
    convert_parser.add_argument('paths', nargs='+', help='Files or directories to convert')
    convert_parser.add_argument('--delete-original', action='store_true',
                            help='Delete original files after successful conversion')
    convert_parser.add_argument('--verbose', action='store_true',
                            help='Enable verbose output')

    # Parse arguments
    args = parser.parse_args()
    
    # Show help if no command
    if not args.cmd:
        parser.print_help()
        sys.exit(1)
    
    # Set API keys if provided
    if args.comicvine_key or args.kapowarr_key:
        APIKeys.set_api_keys(
            comic_vine_api_key=args.comicvine_key,
            kapowarr_api_key=args.kapowarr_key
        )
    
    # Validate API keys for kapowarr-sync
    if args.cmd == 'kapowarr-sync':
        if not args.comicvine_key:
            print(f"{Colors.RED}✗{Colors.RESET} ComicVine API key required for kapowarr-sync", file=sys.stderr)
            print("  Set via --comicvine-key or COMICVINE_API_KEY env var", file=sys.stderr)
            sys.exit(1)
        if not args.kapowarr_key:
            print(f"{Colors.RED}✗{Colors.RESET} Kapowarr API key required for kapowarr-sync", file=sys.stderr)
            print("  Set via --kapowarr-key or KAPOWARR_API_KEY env var", file=sys.stderr)
            sys.exit(1)
    
    # Execute command
    try:
        if args.cmd == 'scan':
            exit_code = find_files_needing_scraping(
                args.paths,
                strict=args.strict,
                check_filenames=args.check_filenames,
                output_format=args.output_format,
                output_file=args.output_file
            )
            sys.exit(exit_code)
        
        elif args.cmd == 'normalize':
            if args.scan:
                # Scan mode
                files = find_files_needing_normalize(
                    args.paths,
                    output_format=args.output_format,
                    output_file=args.output_file
                )
                sys.exit(1 if files else 0)
            else:
                # Normalize mode
                cbz_files = collect_cbz_from_paths(args.paths)
                if not cbz_files:
                    print(f"{Colors.RED}✗{Colors.RESET} No CBZ files found", file=sys.stderr)
                    sys.exit(1)
                normalize_comic_metadata(cbz_files, dry_run=args.dry_run, verbose=args.verbose)
        
        elif args.cmd == 'webp':
            cbz_files = collect_cbz_from_paths(args.paths)
            if not cbz_files:
                print(f"{Colors.RED}✗{Colors.RESET} No CBZ files found", file=sys.stderr)
                sys.exit(1)
            convert_to_webp(cbz_files, verbose=args.verbose, dry_run=args.dry_run)
        
        elif args.cmd == 'repair':
            cbz_files = collect_cbz_from_paths(args.paths)
            if not cbz_files:
                print(f"{Colors.RED}✗{Colors.RESET} No CBZ files found", file=sys.stderr)
                sys.exit(1)
            repaired = 0
            for file in cbz_files:
                if repair_archive(file, dry_run=args.dry_run, verbose=args.verbose):
                    repaired += 1
            print(f"\n{'[DRY RUN] Would repair' if args.dry_run else 'Repaired'} {repaired} file(s)")
        
        elif args.cmd == 'kapowarr-sync':
            update_kapowarr_volumes(
                kapowarr_url=args.kapowarr_url,
                comics_path=args.comics_path,
                verbose=args.verbose,
                dry_run=args.dry_run
            )
        
        elif args.cmd == 'metron':
            if not args.metron_user or not args.metron_pass:
                print(f"{Colors.RED}✗{Colors.RESET} Metron username and password required", file=sys.stderr)
                print("  Set via --metron-user/--metron-pass or METRON_USER/METRON_PASS env vars", file=sys.stderr)
                sys.exit(1)
            
            cbz_files = collect_cbz_from_paths(args.paths)
            if not cbz_files:
                print(f"{Colors.RED}✗{Colors.RESET} No CBZ files found", file=sys.stderr)
                sys.exit(1)
            
            metron_scrape(cbz_files, username=args.metron_user, password=args.metron_pass, 
                        overwrite=args.overwrite, dry_run=args.dry_run, verbose=args.verbose)

        elif args.cmd == 'convert':
            files = collect_cbz_from_paths(args.paths, include_cbr=True)
            files = [f for f in files if f.endswith(('.cbr', '.cb7'))]
            
            if not files:
                print(f"{Colors.RED}✗{Colors.RESET} No CBR or CB7 files found", file=sys.stderr)
                sys.exit(1)
            
            print(f"{Colors.BLUE}[CONVERT]{Colors.RESET} Converting {len(files)} file(s)...\n", file=sys.stderr)
            
            successful, failed = batch_convert_to_cbz(files, delete_original=args.delete_original,
                                                    verbose=args.verbose)
            
            print(f"\n{'='*60}", file=sys.stderr)
            print("CONVERSION SUMMARY", file=sys.stderr)
            print(f"{'='*60}", file=sys.stderr)
            print(f"Total files: {len(files)}", file=sys.stderr)
            print(f"{Colors.GREEN}✓{Colors.RESET} Converted: {len(successful)}", file=sys.stderr)
            print(f"{Colors.RED}✗{Colors.RESET} Failed: {len(failed)}", file=sys.stderr)
            print(f"{'='*60}", file=sys.stderr)
            
            sys.exit(0 if not failed else 1)
        
        elif args.cmd == 'pipeline':
            run_pipeline(
                args.paths,
                skip_scan=args.skip_scan,
                skip_normalize=args.skip_normalize,
                skip_convert=args.skip_convert,
                skip_repair=args.skip_repair,
                dry_run=args.dry_run,
                verbose=args.verbose
            )
    
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}⚠{Colors.RESET} Interrupted by user", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"{Colors.RED}✗ ERROR:{Colors.RESET} {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()