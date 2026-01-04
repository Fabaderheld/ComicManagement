"""API clients for ComicVine and Kapowarr"""

import requests
from typing import Optional, Dict, Any


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