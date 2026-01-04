"""Metron scraping functions"""

import subprocess
import sys
from pathlib import Path
from typing import List

from .utils import Colors


def metron_scrape(files: List[str], dry_run: bool = False, verbose: bool = False):
    """
    Scrape comic metadata using Metron (darkseid).
    
    Args:
        files: List of comic file paths to scrape
        dry_run: If True, only preview what would be scraped
        verbose: Enable verbose output
    """
    if not files:
        print(f"{Colors.YELLOW}⚠{Colors.RESET} No files to scrape", file=sys.stderr)
        return
    
    if dry_run:
        print(f"{Colors.BLUE}[DRY RUN]{Colors.RESET} Would scrape {len(files)} file(s):", file=sys.stderr)
        for f in files[:10]:  # Show first 10
            print(f"  - {Path(f).name}", file=sys.stderr)
        if len(files) > 10:
            print(f"  ... and {len(files) - 10} more", file=sys.stderr)
        return
    
    print(f"{Colors.BLUE}[METRON]{Colors.RESET} Scraping {len(files)} file(s)...", file=sys.stderr)
    
    # Call darkseid/metron CLI
    try:
        cmd = ["metron", "scrape"] + files
        if verbose:
            print(f"Running: {' '.join(cmd)}", file=sys.stderr)
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"{Colors.GREEN}✓{Colors.RESET} Scraping completed successfully", file=sys.stderr)
            if verbose and result.stdout:
                print(result.stdout)
        else:
            print(f"{Colors.RED}✗{Colors.RESET} Scraping failed", file=sys.stderr)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            sys.exit(1)
            
    except FileNotFoundError:
        print(f"{Colors.RED}✗{Colors.RESET} 'metron' command not found. Is darkseid installed?", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"{Colors.RED}✗{Colors.RESET} Error running metron: {e}", file=sys.stderr)
        sys.exit(1)