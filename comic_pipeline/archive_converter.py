"""Archive format conversion functions (CBR/CB7 to CBZ)"""

import os
import sys
import zipfile
import tempfile
from pathlib import Path
from typing import List, Tuple

from .utils import Colors

try:
    import rarfile
except ImportError:
    rarfile = None

try:
    import py7zr
except ImportError:
    py7zr = None


def convert_cbr_to_cbz(cbr_path: str, delete_original: bool = False, verbose: bool = False) -> str:
    """
    Convert a CBR file to CBZ format.
    
    Args:
        cbr_path: Path to CBR file
        delete_original: If True, delete the original CBR after conversion
        verbose: Enable verbose output
        
    Returns:
        Path to the new CBZ file
        
    Raises:
        ImportError: If rarfile is not installed
        Exception: If conversion fails
    """
    if rarfile is None:
        raise ImportError("rarfile library required for CBR conversion. Install with: pip install rarfile")
    
    cbr_path = Path(cbr_path)
    cbz_path = cbr_path.with_suffix('.cbz')
    
    if verbose:
        print(f"{Colors.BLUE}[CONVERT]{Colors.RESET} {cbr_path.name} → {cbz_path.name}", file=sys.stderr)
    
    try:
        # Create temporary directory for extraction
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Extract CBR
            if verbose:
                print(f"  Extracting CBR...", file=sys.stderr)
            
            with rarfile.RarFile(str(cbr_path), 'r') as rf:
                rf.extractall(temp_path)
            
            # Create CBZ
            if verbose:
                print(f"  Creating CBZ...", file=sys.stderr)
            
            with zipfile.ZipFile(cbz_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(temp_path):
                    for file in files:
                        file_path = Path(root) / file
                        arcname = file_path.relative_to(temp_path)
                        zf.write(file_path, arcname)
        
        if verbose:
            print(f"  {Colors.GREEN}✓{Colors.RESET} Converted successfully", file=sys.stderr)
        
        # Delete original if requested
        if delete_original:
            cbr_path.unlink()
            if verbose:
                print(f"  {Colors.YELLOW}⚠{Colors.RESET} Deleted original CBR", file=sys.stderr)
        
        return str(cbz_path)
        
    except Exception as e:
        # Clean up partial CBZ if it exists
        if cbz_path.exists():
            cbz_path.unlink()
        raise Exception(f"Failed to convert {cbr_path.name}: {e}")


def convert_cb7_to_cbz(cb7_path: str, delete_original: bool = False, verbose: bool = False) -> str:
    """
    Convert a CB7 file to CBZ format.
    
    Args:
        cb7_path: Path to CB7 file
        delete_original: If True, delete the original CB7 after conversion
        verbose: Enable verbose output
        
    Returns:
        Path to the new CBZ file
        
    Raises:
        ImportError: If py7zr is not installed
        Exception: If conversion fails
    """
    if py7zr is None:
        raise ImportError("py7zr library required for CB7 conversion. Install with: pip install py7zr")
    
    cb7_path = Path(cb7_path)
    cbz_path = cb7_path.with_suffix('.cbz')
    
    if verbose:
        print(f"{Colors.BLUE}[CONVERT]{Colors.RESET} {cb7_path.name} → {cbz_path.name}", file=sys.stderr)
    
    try:
        # Create temporary directory for extraction
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Extract CB7
            if verbose:
                print(f"  Extracting CB7...", file=sys.stderr)
            
            with py7zr.SevenZipFile(str(cb7_path), 'r') as szf:
                szf.extractall(temp_path)
            
            # Create CBZ
            if verbose:
                print(f"  Creating CBZ...", file=sys.stderr)
            
            with zipfile.ZipFile(cbz_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(temp_path):
                    for file in files:
                        file_path = Path(root) / file
                        arcname = file_path.relative_to(temp_path)
                        zf.write(file_path, arcname)
        
        if verbose:
            print(f"  {Colors.GREEN}✓{Colors.RESET} Converted successfully", file=sys.stderr)
        
        # Delete original if requested
        if delete_original:
            cb7_path.unlink()
            if verbose:
                print(f"  {Colors.YELLOW}⚠{Colors.RESET} Deleted original CB7", file=sys.stderr)
        
        return str(cbz_path)
        
    except Exception as e:
        # Clean up partial CBZ if it exists
        if cbz_path.exists():
            cbz_path.unlink()
        raise Exception(f"Failed to convert {cb7_path.name}: {e}")


def batch_convert_to_cbz(paths: List[str], delete_original: bool = False, 
                        verbose: bool = False) -> Tuple[List[str], List[str]]:
    """
    Convert multiple comic files to CBZ format.
    
    Args:
        paths: List of file paths to convert
        delete_original: If True, delete originals after conversion
        verbose: Enable verbose output
        
    Returns:
        Tuple of (successful_conversions, failed_conversions)
    """
    successful = []
    failed = []
    
    for path in paths:
        path_obj = Path(path)
        suffix = path_obj.suffix.lower()
        
        try:
            if suffix == '.cbr':
                cbz_path = convert_cbr_to_cbz(path, delete_original, verbose)
                successful.append(cbz_path)
            elif suffix == '.cb7':
                cbz_path = convert_cb7_to_cbz(path, delete_original, verbose)
                successful.append(cbz_path)
            elif suffix == '.cbz':
                # Already CBZ, just add to successful
                successful.append(path)
            else:
                if verbose:
                    print(f"{Colors.YELLOW}⚠{Colors.RESET} Skipping unsupported format: {path_obj.name}", 
                          file=sys.stderr)
                failed.append(path)
        except Exception as e:
            print(f"{Colors.RED}✗{Colors.RESET} {path_obj.name}: {e}", file=sys.stderr)
            failed.append(path)
    
    return successful, failed