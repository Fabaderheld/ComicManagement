"""Comic archive repair functions"""

import os
import sys
import zipfile
import tempfile
import shutil

from .utils import Colors


def repair_archive(path: str, dry_run: bool = False, verbose: bool = False) -> bool:
    """
    Repair non-standard CBZ archive structure by flattening all files to root level.
    Returns True if repairs were made, False otherwise.
    """
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