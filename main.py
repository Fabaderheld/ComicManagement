import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
import shutil
import tempfile
from typing import List, Dict, Optional, Any
import requests
import json
from PIL import Image as PILImage


class ComicInfo:
    """Class to handle ComicInfo extraction and manipulation"""

    @staticmethod
    def get_comic_info(comic_path: str) -> Optional[ET.Element]:
        """
        Extracts and returns ComicInfo from a .cbz file.

        Args:
            comic_path: The path to the comic file (.cbz format)

        Returns:
            XML Element containing ComicInfo data, or None if not found

        Example:
            comic_info = ComicInfo.get_comic_info("/path/to/comic.cbz")
        """
        try:
            with zipfile.ZipFile(comic_path, 'r') as zip_file:
                # Find ComicInfo.xml file
                comic_info_file = None
                for file_name in zip_file.namelist():
                    if 'ComicInfo.xml' in file_name:
                        comic_info_file = file_name
                        break

                if not comic_info_file:
                    return None

                # Read and parse the XML content
                with zip_file.open(comic_info_file) as file:
                    xml_content = file.read()
                    root = ET.fromstring(xml_content)
                    return root
        except Exception as e:
            print(f"Error reading ComicInfo: {e}")
            return None


class APIKeys:
    """Class to manage API keys"""

    comic_vine_api_key: Optional[str] = None
    kapowarr_api_key: Optional[str] = None

    @classmethod
    def set_api_keys(cls, comic_vine_api_key: Optional[str] = None,
                     kapowarr_api_key: Optional[str] = None):
        """
        Sets the API keys for ComicVine and Kapowarr

        Args:
            comic_vine_api_key: API key for ComicVine
            kapowarr_api_key: API key for Kapowarr
        """
        if comic_vine_api_key:
            cls.comic_vine_api_key = comic_vine_api_key
        if kapowarr_api_key:
            cls.kapowarr_api_key = kapowarr_api_key


class ComicFormat:
    """Class to represent comic format information"""

    def __init__(self, path: str, webp: int, jpg: int, png: int):
        self.path = path
        self.webp = webp
        self.jpg = jpg
        self.png = png

    @property
    def need_conversion(self) -> bool:
        """Returns True if the comic needs conversion (has jpg or png images)"""
        return self.jpg > 0 or self.png > 0

    def __repr__(self):
        return f"ComicFormat(path={self.path}, webp={self.webp}, jpg={self.jpg}, png={self.png})"


def get_comic_format(comic_path: str) -> ComicFormat:
    """
    Determines the format of images within a .cbz file.

    Args:
        comic_path: The path to the comic file (.cbz format)

    Returns:
        ComicFormat object containing format information

    Example:
        format_info = get_comic_format("/path/to/comic.cbz")
        if format_info.need_conversion:
            print("Comic needs conversion")
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


def convert_to_webp(comics: List[str], verbose: bool = False):
    """
    Converts image files in .cbz comic archives to webp format.

    Args:
        comics: List of paths to comic files (.cbz format)
        verbose: Enable verbose output

    Example:
        convert_to_webp(["/path/to/comic1.cbz", "/path/to/comic2.cbz"])
    """
    for comic in comics:
        comic_path = Path(comic)

        if verbose:
            print(f"Processing: {comic_path}")

        # Check if it's a directory
        if comic_path.is_dir():
            print(f"Scanning folder {comic_path}")

            # Find all .cbz files recursively
            all_comics = list(comic_path.rglob("*.cbz"))
            all_comics = [c for c in all_comics if '#recycle' not in str(c)]

            # Check which comics need conversion
            comics_to_convert = []
            for comic_file in all_comics:
                format_info = get_comic_format(str(comic_file))
                if format_info.need_conversion:
                    comics_to_convert.append(str(comic_file))

            if not comics_to_convert:
                print(f"No comics require conversion in the directory {comic}")
                continue
            else:
                print(f"{len(comics_to_convert)} comics to convert")

            # Recursively convert each comic
            for comic_to_convert in comics_to_convert:
                convert_to_webp([comic_to_convert], verbose)
        else:
            # Check if conversion is needed
            format_info = get_comic_format(str(comic_path))
            if not format_info.need_conversion:
                print(f"The comic {comic_path.name} does not require conversion.")
                continue

            # Create temporary directory
            temp_dir = Path(tempfile.gettempdir()) / comic_path.stem

            try:
                # Extract the archive
                with zipfile.ZipFile(comic_path, 'r') as zip_file:
                    zip_file.extractall(temp_dir)

                # Find images to convert
                image_extensions = ['.jpg', '.jpeg', '.png']
                images = [f for f in temp_dir.rglob('*') if f.suffix.lower() in image_extensions]

                # Check free space
                stat = shutil.disk_usage(comic_path.parent)
                free_space_gb = stat.free / (1024**3)
                comic_size_gb = comic_path.stat().st_size / (1024**3)

                if free_space_gb > comic_size_gb:
                    total_images = len(images)
                    print(f"Processing {comic_path.name}")
                    print(f"Converting images to webp format...")

                    for counter, image in enumerate(images, 1):
                        percent_complete = (counter / total_images) * 100
                        print(f"Progress: {counter}/{total_images} ({percent_complete:.1f}%)", end='\r')

                        try:
                            # Convert image to webp using Wand
                            output_path = image.parent / f"{image.stem}.webp"
                            convert_image_to_webp(str(image), str(output_path), quality=75)

                            # Remove original image
                            image.unlink()
                        except Exception as e:
                            print(f"\nError converting image {image}: {e}")

                    print()  # New line after progress

                    # Create new archive
                    with zipfile.ZipFile(comic_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                        for file in temp_dir.rglob('*'):
                            if file.is_file():
                                zip_file.write(file, file.relative_to(temp_dir))

                    print(f"Conversion complete for {comic_path.name}")
                else:
                    print(f"Not enough free space to convert images for {comic_path.name}")

            finally:
                # Clean up temporary directory
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)


def get_comic_vine_info(id: str, type: str) -> Optional[Dict[str, Any]]:
    """
    Fetches information about a comic entity from the ComicVine API.

    Args:
        id: The ID of the comic entity
        type: The type of entity (volume, issue, person, character, concept,
              location, object, origin, publisher, story_arc, team)

    Returns:
        Dictionary containing the comic entity information

    Example:
        info = get_comic_vine_info("12345", "volume")
    """
    valid_types = ["volume", "issue", "person", "character", "concept",
                   "location", "object", "origin", "publisher", "story_arc", "team"]

    if type not in valid_types:
        raise ValueError(f"Invalid type: {type}. Must be one of {valid_types}")

    # Check if API key is set
    if not APIKeys.comic_vine_api_key:
        raise ValueError("ComicVine API key not set. Please run APIKeys.set_api_keys()")

    # Determine type code
    type_codes = {
        "volume": "4050",
        "issue": "4000"
    }

    type_code = type_codes.get(type)
    if not type_code:
        raise ValueError(f"Unsupported type: {type}")

    # Prepare request
    params = {
        'api_key': APIKeys.comic_vine_api_key,
        'format': 'json'
    }

    url = f"https://comicvine.gamespot.com/api/{type}/{type_code}-{id}"

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        return data.get('results')
    except requests.exceptions.RequestException as e:
        try:
            error_data = response.json()
            error_message = error_data.get('error', str(e))

            if error_message == "CVRateLimitReached":
                print("ComicVine API rate limit reached, please try again later.")
            else:
                print(f"ComicVineAPI: {error_message}")
        except:
            print(f"Error fetching ComicVine info: {e}")
        return None


def update_kapowarr_volumes(kapowarr_url: str = "http://10.10.20.228:5656",
                            comics_path: str = "/mnt/comics",
                            verbose: bool = False):
    """
    Updates and synchronizes comic volumes with the Kapowarr system.

    Args:
        kapowarr_url: The URL of the Kapowarr instance
        comics_path: The root directory path where comic volumes are stored
        verbose: Enable verbose output

    Example:
        update_kapowarr_volumes("http://localhost:5656", "/mnt/comics")
    """
    # Check if API keys are set
    if not APIKeys.kapowarr_api_key:
        raise ValueError("Kapowarr API key not set. Please run APIKeys.set_api_keys()")

    if not APIKeys.comic_vine_api_key:
        raise ValueError("ComicVine API key not set. Please run APIKeys.set_api_keys()")

    params = {'api_key': APIKeys.kapowarr_api_key}

    try:
        # Fetch all volumes from Kapowarr
        response = requests.get(f"{kapowarr_url}/api/volumes", params=params)
        response.raise_for_status()
        kapowarr_volumes = response.json()['result']

        # Fetch details for each volume
        kapowarr_volumes_details = []
        for volume in kapowarr_volumes:
            response = requests.get(f"{kapowarr_url}/api/volumes/{volume['id']}", params=params)
            response.raise_for_status()
            kapowarr_volumes_details.append(response.json()['result'])

        # Get volumes with incorrect paths
        wrong_volumes = [v for v in kapowarr_volumes_details if 'Volume' in v.get('volume_folder', '')]

        for wrong_volume in wrong_volumes:
            volume_path = f"{comics_path}/{wrong_volume['publisher']}/{wrong_volume['title']} ({wrong_volume['year']})"
            print(volume_path)
            print(Path(volume_path).exists())

        # Get comic folders
        comics_path_obj = Path(comics_path)
        comic_folders = [f for f in comics_path_obj.iterdir()
                        if f.is_dir() and '#recycle' not in f.name and '(' not in f.name and ')' not in f.name]

        # Process each comic folder
        for comic in comic_folders:
            volumes = list(comic.iterdir())

            for volume in volumes:
                if not volume.is_dir():
                    continue

                if verbose:
                    print(f"Processing volume: {volume}")

                # Construct volume path
                volume_path = str(volume).split('/comics/')[-1]

                # Check if volume already exists
                existing_folders = [v.get('volume_folder') for v in kapowarr_volumes_details]
                if volume_path in existing_folders:
                    print(f"Volume already exists in Kapowarr: {volume_path}")
                    continue

                # Get issues in the volume
                issues = list(volume.glob("*.cbz"))
                if not issues:
                    print(f"Empty folder: {volume}, skipping...")
                    continue

                try:
                    # Extract ComicInfo from first issue
                    comic_info = ComicInfo.get_comic_info(str(issues[0]))
                    if comic_info is None:
                        print(f"Error reading ComicInfo.xml file in {issues[0]}")
                        continue

                    # Extract Issue ID
                    notes = comic_info.find('Notes')
                    if notes is None or not notes.text:
                        print(f"Issue ID not found in ComicInfo.xml for {issues[0]}")
                        continue

                    import re
                    match = re.search(r'CVDB(\d+)', notes.text)
                    if not match:
                        print(f"Issue ID not found in ComicInfo.xml for {issues[0]}")
                        continue

                    issue_id = match.group(1)
                    if verbose:
                        print(f"Issue ID: {issue_id}")

                    # Check for series.json
                    series_json_path = volume / "series.json"
                    if series_json_path.exists():
                        with open(series_json_path, 'r') as f:
                            volume_cv_info = json.load(f)
                        volume_id = volume_cv_info['id']
                    else:
                        # Fetch from ComicVine
                        issue_cv_info = get_comic_vine_info(issue_id, "issue")
                        if not issue_cv_info:
                            continue

                        volume_cv_info = get_comic_vine_info(str(issue_cv_info['volume']['id']), "volume")
                        if not volume_cv_info:
                            continue

                        volume_id = volume_cv_info['id']

                        # Save series.json
                        with open(series_json_path, 'w') as f:
                            json.dump(volume_cv_info, f, indent=2)

                    # Add volume to Kapowarr
                    body = {
                        'comicvine_id': str(volume_id),
                        'root_folder_id': 1,
                        'monitor': True,
                        'volume_folder': volume_path,
                        'auto_search': False
                    }

                    try:
                        response = requests.post(
                            f"{kapowarr_url}/api/volumes",
                            params=params,
                            json=body
                        )
                        response.raise_for_status()
                        print(f"Added Volume to Kapowarr: {volume_path}")
                    except requests.exceptions.RequestException as e:
                        try:
                            error_data = response.json()
                            error_message = error_data.get('error', str(e))

                            if error_message == "CVRateLimitReached":
                                print("ComicVine API rate limit reached, please try again later.")
                                continue
                            elif error_message == "VolumeAlreadyAdded":
                                print(f"Volume already added, updating path in Kapowarr for: {volume_path}")

                                # Find Kapowarr volume
                                kapowarr_volume = next(
                                    (v for v in kapowarr_volumes_details if v.get('comicvine_id') == volume_id),
                                    None
                                )

                                if kapowarr_volume:
                                    update_body = {
                                        'root_folder': 1,
                                        'monitored': True,
                                        'volume_folder': volume_path,
                                        'special_version_locked': False
                                    }

                                    response = requests.put(
                                        f"{kapowarr_url}/api/volumes/{kapowarr_volume['id']}",
                                        params=params,
                                        json=update_body
                                    )
                                    response.raise_for_status()
                            else:
                                print(f"Kapowarr: {error_message}")
                                continue
                        except:
                            print(f"Error adding volume: {e}")

                except Exception as e:
                    print(f"Error processing volume {volume}: {e}")
                    continue

        # Update all volumes in Kapowarr
        update_body = {'cmd': 'update_all'}
        requests.post(
            f"{kapowarr_url}/api/system/tasks",
            params=params,
            json=update_body
        )

    except requests.exceptions.RequestException as e:
        print(f"Error communicating with Kapowarr: {e}")


# Example usage:
if __name__ == "__main__":
    # Set API keys
    APIKeys.set_api_keys(
        comic_vine_api_key="your_comicvine_api_key",
        kapowarr_api_key="your_kapowarr_api_key"
    )

    # Example: Get comic info
    # comic_info = ComicInfo.get_comic_info("/path/to/comic.cbz")

    # Example: Check comic format
    # format_info = get_comic_format("/path/to/comic.cbz")
    # print(format_info.need_conversion)

    # Example: Convert to webp
    # convert_to_webp(["/path/to/comic.cbz"])

    # Example: Update Kapowarr volumes
    # update_kapowarr_volumes("http://localhost:5656", "/mnt/comics")