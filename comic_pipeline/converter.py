"""Image format conversion functions"""

import os
import sys
import zipfile
import tempfile
import shutil
from pathlib import Path
from typing import List, Tuple
from PIL import Image as PILImage

from .models import ComicFormat
from .utils import Colors

try:
    import rarfile
except ImportError:
    rarfile = None

try:
    import py7zr
except ImportError:
    py7zr = None


def get_comic_format(comic_path: str) -> ComicFormat:
    """
    Determines the format of images within a .cbz file.
    
    Args:
        comic_path: The path to the comic file (.cbz format)
        
    Returns:
        ComicFormat object containing format information
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