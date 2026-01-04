"""Image format conversion functions (WebP)"""

import zipfile
import tempfile
import shutil
from pathlib import Path
from typing import List
from PIL import Image as PILImage

from .models import ComicFormat


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