"""Kapowarr integration functions"""

import os
import re
import json
import sys
import zipfile
from pathlib import Path
import requests
import xml.etree.ElementTree as ET

from .api import APIKeys, get_comic_vine_info


class ComicInfo:
    """Helper class for reading ComicInfo.xml"""
    
    @staticmethod
    def get_comic_info(cbz_path: str):
        """Extract ComicInfo.xml from a CBZ file"""
        try:
            with zipfile.ZipFile(cbz_path, 'r') as zf:
                if 'ComicInfo.xml' in zf.namelist():
                    xml_data = zf.read('ComicInfo.xml')
                    return ET.fromstring(xml_data)
        except Exception:
            pass
        return None


def update_kapowarr_volumes(kapowarr_url: str = "http://localhost:5656",
                            comics_path: str = "/mnt/comics",
                            verbose: bool = False,
                            dry_run: bool = False):
    """
    Updates and synchronizes comic volumes with the Kapowarr system.
    
    Args:
        kapowarr_url: The URL of the Kapowarr instance
        comics_path: The root directory path where comic volumes are stored
        verbose: Enable verbose output
        dry_run: If True, only preview changes without making modifications
    """
    if dry_run:
        print("[DRY RUN MODE] No changes will be made to Kapowarr\n")
    
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
        wrong_volumes = [v for v in kapowarr_volumes_details 
                        if 'Volume' in v.get('volume_folder', '')]
        
        if wrong_volumes and verbose:
            print(f"Found {len(wrong_volumes)} volumes with incorrect paths")
        
        for wrong_volume in wrong_volumes:
            volume_path = f"{comics_path}/{wrong_volume['publisher']}/{wrong_volume['title']} ({wrong_volume['year']})"
            if verbose:
                print(f"{'[DRY RUN] Would fix' if dry_run else 'Fixing'} path: {volume_path}")
                print(f"  Path exists: {Path(volume_path).exists()}")
        
        # Get comic folders
        comics_path_obj = Path(comics_path)
        comic_folders = [f for f in comics_path_obj.iterdir() 
                        if f.is_dir() and '#recycle' not in f.name 
                        and '(' not in f.name and ')' not in f.name]
        
        volumes_to_add = 0
        volumes_to_update = 0
        
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
                    if verbose:
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
                        if dry_run:
                            print(f"[DRY RUN] Would fetch ComicVine info for issue {issue_id}")
                            continue
                        
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
                    
                    if dry_run:
                        print(f"[DRY RUN] Would add volume to Kapowarr: {volume_path}")
                        volumes_to_add += 1
                        continue
                    
                    try:
                        response = requests.post(
                            f"{kapowarr_url}/api/volumes",
                            params=params,
                            json=body
                        )
                        response.raise_for_status()
                        print(f"Added Volume to Kapowarr: {volume_path}")
                        volumes_to_add += 1
                        
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
                                    (v for v in kapowarr_volumes_details 
                                     if v.get('comicvine_id') == volume_id),
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
                                    volumes_to_update += 1
                            else:
                                print(f"Kapowarr: {error_message}")
                                continue
                        except:
                            print(f"Error adding volume: {e}")
                            
                except Exception as e:
                    print(f"Error processing volume {volume}: {e}")
                    continue
        
        # Update all volumes in Kapowarr
        if not dry_run and (volumes_to_add > 0 or volumes_to_update > 0):
            update_body = {'cmd': 'update_all'}
            requests.post(
                f"{kapowarr_url}/api/system/tasks",
                params=params,
                json=update_body
            )
            print(f"\nTriggered Kapowarr update for all volumes")
        
        print(f"\n{'[DRY RUN] Would add' if dry_run else 'Added'} {volumes_to_add} volumes")
        print(f"{'[DRY RUN] Would update' if dry_run else 'Updated'} {volumes_to_update} volumes")
        
    except requests.exceptions.RequestException as e:
        print(f"Error communicating with Kapowarr: {e}", file=sys.stderr)
        sys.exit(1)