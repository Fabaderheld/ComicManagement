"""Metron API integration using mokkari"""
import sys
import os
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime
import re

try:
    import mokkari
    from mokkari.exceptions import ApiError
except ImportError:
    mokkari = None
    ApiError = Exception

from darkseid.comic import Comic, MetadataFormat
from darkseid.metadata import Metadata

from .utils import Colors


class MetronScraper:
    """Scraper for Metron API using mokkari library"""
    
    def __init__(self, username: str, password: str):
        """
        Initialize Metron scraper.
        
        Args:
            username: Metron username
            password: Metron password
        """
        if mokkari is None:
            raise ImportError("mokkari library not installed. Run: pip install mokkari")
        
        self.api = mokkari.api(username, password)
        self.cache = {}  # Simple cache for API results
    
    def search_series(self, series_name: str, year: Optional[int] = None, verbose: bool = False) -> List[Dict[str, Any]]:
        """
        Search for a series on Metron.
        
        Args:
            series_name: Name of the series
            year: Optional year to filter results
            verbose: Enable verbose output
            
        Returns:
            List of matching series
        """
        try:
            if verbose:
                print(f"  🔍 Searching for series: '{series_name}'" + (f" (year: {year})" if year else ""), file=sys.stderr)
            
            # Build search params - include year if provided
            search_params = {"name": series_name}
            if year:
                search_params["year_began"] = year
            
            results = self.api.series_list(params=search_params)
            
            if verbose and results:
                print(f"  📚 Found {len(results)} series result(s):", file=sys.stderr)
                for idx, s in enumerate(results[:5]):  # Show first 5
                    series_title = getattr(s, 'series_name', None) or getattr(s, 'display_name', None) or str(s.id)
                    year_info = f"({s.year_began})" if hasattr(s, 'year_began') and s.year_began else ""
                    volume_info = f"Vol. {s.volume}" if hasattr(s, 'volume') and s.volume else ""
                    print(f"    [{idx+1}] {series_title} {year_info} {volume_info} - ID: {s.id}", file=sys.stderr)
            
            # If we got results with year filter, return them
            if results:
                return results
            
            # If no results with year, try without year as fallback
            if year and not results:
                if verbose:
                    print(f"  {Colors.YELLOW}⚠{Colors.RESET} No results with year {year}, trying without year filter...", file=sys.stderr)
                
                results = self.api.series_list(params={"name": series_name})
                
                if verbose and results:
                    print(f"  📚 Found {len(results)} series without year filter:", file=sys.stderr)
                    for idx, s in enumerate(results[:5]):
                        series_title = getattr(s, 'series_name', None) or getattr(s, 'display_name', None) or str(s.id)
                        year_info = f"({s.year_began})" if hasattr(s, 'year_began') and s.year_began else ""
                        volume_info = f"Vol. {s.volume}" if hasattr(s, 'volume') and s.volume else ""
                        print(f"    [{idx+1}] {series_title} {year_info} {volume_info} - ID: {s.id}", file=sys.stderr)
            
            return results
            
        except ApiError as e:
            print(f"{Colors.RED}✗{Colors.RESET} Metron API error: {e}", file=sys.stderr)
            return []

    def search_issue(self, series_name: str, issue_number: str,
                    year: Optional[int] = None, verbose: bool = False) -> Optional[Any]:
        """
        Search for a specific issue on Metron.
        
        Args:
            series_name: Name of the series
            issue_number: Issue number (e.g., "1", "12.1")
            year: Optional year to narrow search
            verbose: Enable verbose output
            
        Returns:
            Issue object or None if not found
        """
        cache_key = f"{series_name}_{issue_number}_{year}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            # First, find the series
            series_results = self.search_series(series_name, year, verbose=verbose)
            
            if not series_results:
                print(f"  {Colors.YELLOW}⚠{Colors.RESET} No series found for: {series_name}",
                    file=sys.stderr)
                return None
            
            # Try each matching series until we find the issue
            for series in series_results:
                # Get series name using correct attribute
                series_title = getattr(series, 'display_name', None) or str(series.id)
                series_vol = getattr(series, 'volume', 'N/A')
                
                if verbose:
                    print(f"  ✓ Trying series: {series_title} (ID: {series.id}, Volume: {series_vol})", file=sys.stderr)
                
                # Search for the issue in this series
                if verbose:
                    print(f"  🔍 Searching for issue #{issue_number} in series ID {series.id}...", file=sys.stderr)
                
                # Build search params - mokkari requires series_id
                search_params = {
                    "series_id": series.id,
                    "number": issue_number
                }
                
                issues = self.api.issues_list(params=search_params)
                
                if issues:
                    # Get the full issue details (issues_list returns BaseIssue, we need full Issue)
                    base_issue = issues[0]
                    
                    if verbose:
                        print(f"  🔍 Fetching full issue details for ID {base_issue.id}...", file=sys.stderr)
                    
                    # Fetch complete issue data
                    full_issue = self.api.issue(base_issue.id)
                    
                    # DEBUG: Check story arcs
                    if hasattr(full_issue, 'arcs') and full_issue.arcs:
                        print(f"  [DEBUG] Found {len(full_issue.arcs)} story arc(s):", file=sys.stderr)
                        for arc in full_issue.arcs:
                            print(f"    - Type: {type(arc)}, Value: {arc}", file=sys.stderr)
                    else:
                        print(f"  [DEBUG] No arcs found on issue", file=sys.stderr)
                    
                    if verbose:
                        print(f"  {Colors.GREEN}✓{Colors.RESET} Found issue: {series_title} #{full_issue.number}", file=sys.stderr)
                    
                    self.cache[cache_key] = full_issue
                    return full_issue
                else:
                    if verbose:
                        print(f"  {Colors.YELLOW}⚠{Colors.RESET} Issue #{issue_number} not found in this series", file=sys.stderr)
            
            # If we get here, no series had the issue
            print(f"  {Colors.YELLOW}⚠{Colors.RESET} No issue #{issue_number} found in any matching series",
                file=sys.stderr)
            if verbose:
                print(f"  💡 Checked {len(series_results)} series. Try verifying the issue number.", file=sys.stderr)
            return None
            
        except ApiError as e:
            print(f"{Colors.RED}✗{Colors.RESET} Metron API error: {e}", file=sys.stderr)
            return None
    
    def get_issue_by_id(self, issue_id: int) -> Optional[Any]:
        """
        Get issue details by Metron ID.
        
        Args:
            issue_id: Metron issue ID
            
        Returns:
            Issue object or None if not found
        """
        try:
            return self.api.issue(issue_id)
        except ApiError as e:
            print(f"{Colors.RED}✗{Colors.RESET} Metron API error: {e}", file=sys.stderr)
            return None

    def get_publisher(self, publisher_id: int) -> Optional[Any]:
        """
        Get publisher details by Metron ID.

        Args:
            publisher_id: Metron publisher ID

        Returns:
            Publisher object or None if not found
        """
        try:
            return self.api.publisher(publisher_id)
        except ApiError as e:
            print(f"{Colors.RED}✗{Colors.RESET} Metron API error: {e}", file=sys.stderr)
            return None
    
    def issue_to_comicinfo(self, issue: Any) -> Metadata:
        """
        Convert a Metron issue object to Darkseid Metadata.
        
        Args:
            issue: Metron issue object
            
        Returns:
            Metadata object
        """
        md = Metadata()
        
        # Basic fields - use display_name instead of name
        if hasattr(issue, 'series') and issue.series:
            series_name = getattr(issue.series, 'display_name', None) or getattr(issue.series, 'series_name', None)
            if series_name:
                md.series = series_name
        
        if hasattr(issue, 'number') and issue.number:
            md.issue = str(issue.number)
        
        # Title
        if hasattr(issue, 'issue_name') and issue.issue_name:
            md.title = issue.issue_name
        elif hasattr(issue, 'name') and issue.name:
            md.title = issue.name
        
        # Description/Summary
        if hasattr(issue, 'desc') and issue.desc:
            md.comments = issue.desc
        elif hasattr(issue, 'summary') and issue.summary:
            md.comments = issue.summary
        
        # Publisher - fetch full publisher object if we have an ID
        if hasattr(issue, 'publisher') and issue.publisher:
            if hasattr(issue.publisher, 'id') and issue.publisher.id:
                # Fetch full publisher details
                full_publisher = self.get_publisher(issue.publisher.id)
                if full_publisher:
                    pub_name = getattr(full_publisher, 'name', None)
                    if pub_name:
                        # Check if existing publisher is an object
                        if hasattr(md.publisher, 'name'):
                            md.publisher.name = pub_name
                            if hasattr(full_publisher, 'id'):
                                md.publisher.id_ = full_publisher.id
                        else:
                            md.publisher = pub_name
            else:
                # No ID, just use the name
                pub_name = getattr(issue.publisher, 'name', None) or getattr(issue.publisher, 'publisher_name', None)
                if pub_name:
                    if hasattr(md.publisher, 'name'):
                        md.publisher.name = pub_name
                    else:
                        md.publisher = pub_name
        
        # Imprint
        if hasattr(issue, 'imprint') and issue.imprint:
            imprint_name = getattr(issue.imprint, 'name', None) or getattr(issue.imprint, 'display_name', None)
            if imprint_name:
                md.imprint = imprint_name
        
        # Dates
        if hasattr(issue, 'cover_date') and issue.cover_date:
            try:
                # Parse cover_date (format: YYYY-MM-DD)
                date_obj = datetime.strptime(str(issue.cover_date), "%Y-%m-%d")
                md.year = date_obj.year
                md.month = date_obj.month
                md.day = date_obj.day
            except:
                pass
        
        # Store date
        if hasattr(issue, 'store_date') and issue.store_date:
            md.store_date = str(issue.store_date)
        
        # Volume
        if hasattr(issue, 'series') and issue.series and hasattr(issue.series, 'volume') and issue.series.volume:
            md.volume = issue.series.volume
        
        # Issue count in series
        if hasattr(issue, 'series') and issue.series and hasattr(issue.series, 'issue_count') and issue.series.issue_count:
            md.issue_count = issue.series.issue_count
        
        # Page count
        if hasattr(issue, 'page_count') and issue.page_count:
            md.page_count = issue.page_count
        
        # Format (One-Shot, Limited Series, etc.)
        if hasattr(issue, 'series') and issue.series and hasattr(issue.series, 'series_type') and issue.series.series_type:
            type_name = getattr(issue.series.series_type, 'name', None)
            if type_name:
                md.format = type_name
        
        # Age Rating
        if hasattr(issue, 'rating') and issue.rating:
            rating_name = getattr(issue.rating, 'name', None)
            if rating_name:
                md.age_rating = rating_name
        
        # Credits (Writers, Pencillers, etc.)
        if hasattr(issue, 'credits') and issue.credits:
            writers = []
            pencillers = []
            inkers = []
            colorists = []
            letterers = []
            cover_artists = []
            editors = []
            
            for credit in issue.credits:
                if not hasattr(credit, 'role') or not credit.role:
                    continue
                
                # Get all role names
                role_list = credit.role if isinstance(credit.role, list) else [credit.role]
                role_names = []
                for r in role_list:
                    role_name = getattr(r, 'name', None)
                    if role_name:
                        role_names.append(role_name.lower())
                
                if not role_names:
                    continue
                
                # Creator is just a string!
                creator = None
                if hasattr(credit, 'creator') and credit.creator:
                    creator = str(credit.creator)
                
                if not creator:
                    continue
                
                # Match roles - check if any role matches
                matched = False
                for role in role_names:
                    if not matched and ("writer" in role or "plot" in role or "script" in role):
                        writers.append(creator)
                        matched = True
                    elif not matched and ("pencil" in role or ("artist" in role and "cover" not in role)):
                        pencillers.append(creator)
                        matched = True
                    elif not matched and "ink" in role:
                        inkers.append(creator)
                        matched = True
                    elif not matched and ("color" in role or "colour" in role):
                        colorists.append(creator)
                        matched = True
                    elif not matched and "letter" in role:
                        letterers.append(creator)
                        matched = True
                    elif not matched and "cover" in role:
                        cover_artists.append(creator)
                        matched = True
                    elif not matched and "editor" in role:
                        editors.append(creator)
                        matched = True
            
            if writers:
                md.writer = ", ".join(list(dict.fromkeys(writers)))  # Remove duplicates
            if pencillers:
                md.penciller = ", ".join(list(dict.fromkeys(pencillers)))
            if inkers:
                md.inker = ", ".join(list(dict.fromkeys(inkers)))
            if colorists:
                md.colorist = ", ".join(list(dict.fromkeys(colorists)))
            if letterers:
                md.letterer = ", ".join(list(dict.fromkeys(letterers)))
            if cover_artists:
                md.cover_artist = ", ".join(list(dict.fromkeys(cover_artists)))
            if editors:
                md.editor = ", ".join(list(dict.fromkeys(editors)))
        
        # Characters
        if hasattr(issue, 'characters') and issue.characters:
            char_names = []
            for char in issue.characters:
                # Characters might also be strings
                if isinstance(char, str):
                    char_names.append(char)
                else:
                    char_name = getattr(char, 'display_name', None) or getattr(char, 'character_name', None) or getattr(char, 'name', None)
                    if char_name:
                        char_names.append(char_name)
            if char_names:
                md.characters = ", ".join(char_names)
        
        # Teams
        if hasattr(issue, 'teams') and issue.teams:
            team_names = []
            for team in issue.teams:
                # Teams might also be strings
                if isinstance(team, str):
                    team_names.append(team)
                else:
                    team_name = getattr(team, 'display_name', None) or getattr(team, 'team_name', None) or getattr(team, 'name', None)
                    if team_name:
                        team_names.append(team_name)
            if team_names:
                md.teams = ", ".join(team_names)
        
        # Story Arcs - use 'arcs' attribute
        if hasattr(issue, 'arcs') and issue.arcs:
            arc_names = []
            for arc in issue.arcs:
                # Arcs might also be strings
                if isinstance(arc, str):
                    arc_names.append(arc)
                else:
                    arc_name = getattr(arc, 'display_name', None) or getattr(arc, 'arc_name', None) or getattr(arc, 'name', None)
                    if arc_name:
                        arc_names.append(arc_name)
            if arc_names:
                md.story_arc = ", ".join(arc_names)
        
        # Genres (if available)
        if hasattr(issue, 'genres') and issue.genres:
            genre_names = []
            for genre in issue.genres:
                if isinstance(genre, str):
                    genre_names.append(genre)
                else:
                    genre_name = getattr(genre, 'name', None) or getattr(genre, 'display_name', None)
                    if genre_name:
                        genre_names.append(genre_name)
            if genre_names:
                md.genres = ", ".join(genre_names)
        
        # Locations (if available)
        if hasattr(issue, 'locations') and issue.locations:
            location_names = []
            for location in issue.locations:
                if isinstance(location, str):
                    location_names.append(location)
                else:
                    location_name = getattr(location, 'display_name', None) or getattr(location, 'name', None)
                    if location_name:
                        location_names.append(location_name)
            if location_names:
                md.locations = ", ".join(location_names)
        
        # Universes (if available)
        if hasattr(issue, 'universes') and issue.universes:
            universe_names = []
            for universe in issue.universes:
                if isinstance(universe, str):
                    universe_names.append(universe)
                else:
                    universe_name = getattr(universe, 'display_name', None) or getattr(universe, 'name', None)
                    if universe_name:
                        universe_names.append(universe_name)
            if universe_names:
                # Store in notes or a custom field
                md.notes = f"Universe: {', '.join(universe_names)}"
        
        # Web link
        if hasattr(issue, 'id') and issue.id:
            md.web = f"https://metron.cloud/issue/{issue.id}/"

        # Add source info to notes - handle Notes object properly
        # scrape_note = f"Scraped from Metron on {datetime.now().strftime('%Y-%m-%d')}"
        # metron_id = f"Metron ID: {issue.id}" if hasattr(issue, 'id') and issue.id else ""

        # # Check if notes exists and what type it is
        # existing_notes = getattr(md, 'notes', None)

        # if existing_notes is None:
        #     # No existing notes - just set as string
        #     md.notes = f"{metron_id}\n{scrape_note}" if metron_id else scrape_note
        # elif hasattr(existing_notes, 'comic_rack'):
        #     # It's a Notes object - append to comic_rack field
        #     if existing_notes.comic_rack:
        #         existing_notes.comic_rack = f"{existing_notes.comic_rack}\n{scrape_note}"
        #     else:
        #         existing_notes.comic_rack = scrape_note
        #     if metron_id and hasattr(existing_notes, 'metron_info'):
        #         existing_notes.metron_info = metron_id
        # else:
        #     # It's a string - append to it
        #     md.notes = f"{existing_notes}\n{metron_id}\n{scrape_note}" if metron_id else f"{existing_notes}\n{scrape_note}"
        
        return md
    
    def merge_metadata(self, existing: Metadata, new: Metadata,
                       overwrite: bool = False) -> tuple[Metadata, List[Dict[str, str]]]:
        """
        Merge new metadata into existing, tracking changes.
        
        Args:
            existing: Existing Metadata
            new: New Metadata from Metron
            overwrite: If True, overwrite existing fields. If False, only fill empty fields.
            
        Returns:
            Tuple of (merged Metadata, list of changes)
        """
        changes = []
        
        # List of fields to check (using correct Darkseid field names)
        fields = [
            'series', 'issue', 'title', 'comments', 'year', 'month', 'day',
            'volume', 'writer', 'penciller', 'inker', 'colorist', 'letterer',
            'cover_artist', 'editor', 'characters', 'teams', 'story_arc',
            'page_count', 'web', 'notes'
        ]
        
        for field in fields:
            old_value = getattr(existing, field, None)
            new_value = getattr(new, field, None)
            
            # Skip if new value is empty
            if new_value is None or (isinstance(new_value, str) and not new_value.strip()):
                continue
            
            # Convert to string for comparison
            old_str = str(old_value) if old_value is not None else ""
            new_str = str(new_value) if new_value is not None else ""
            
            # Only update if overwrite=True or field is empty
            if overwrite or not old_str.strip():
                if old_str != new_str:
                    changes.append({
                        'field': field.replace('_', ' ').title(),
                        'old': old_str if old_str else '(empty)',
                        'new': new_str
                    })
                    setattr(existing, field, new_value)

            # Handle publisher separately to preserve object structure
            if hasattr(new, 'publisher') and new.publisher:
                new_pub = str(new.publisher) if new.publisher else ""
                if new_pub.strip():
                    if hasattr(existing, 'publisher') and hasattr(existing.publisher, 'name'):
                        # Existing is a Publisher object - update the name
                        old_pub = existing.publisher.name or ""
                        if overwrite or not old_pub.strip():
                            existing.publisher.name = new_pub
                            changes.append({
                                'field': 'Publisher',
                                'old': old_pub if old_pub else '(empty)',
                                'new': new_pub
                            })
                    else:
                        # Existing is None or string - set it
                        old_pub = str(existing.publisher) if hasattr(existing, 'publisher') and existing.publisher else ""
                        if overwrite or not old_pub.strip():
                            existing.publisher = new_pub
                            changes.append({
                                'field': 'Publisher',
                                'old': old_pub if old_pub else '(empty)',
                                'new': new_pub
                            })
        
        return existing, changes
    
    def scrape_file(self, cbz_path: str, overwrite: bool = False,
                    dry_run: bool = False, verbose: bool = False) -> bool:
        """
        Scrape metadata for a single CBZ file using darkseid.
        
        Args:
            cbz_path: Path to CBZ file
            overwrite: If True, overwrite existing metadata
            dry_run: If True, don't modify the file
            verbose: Enable verbose output
            
        Returns:
            True if file was modified (or would be in dry-run), False otherwise
        """
        path = Path(cbz_path)
        
        if verbose:
            print(f"\n{Colors.BLUE}[SCRAPING]{Colors.RESET} {path.name}", file=sys.stderr)
        
        try:
            # Load comic using darkseid
            comic = Comic(cbz_path)
            
            # Get existing metadata - specify ComicInfo format
            existing_md = comic.read_metadata(MetadataFormat.COMIC_INFO)
            
            if existing_md is None:
                existing_md = Metadata()
                if verbose:
                    print(f"  {Colors.YELLOW}⚠{Colors.RESET} No ComicInfo.xml, will create new one", file=sys.stderr)
            else:
                if verbose:
                    print(f"  {Colors.GREEN}✓{Colors.RESET} Found existing ComicInfo.xml", file=sys.stderr)
            
            # Get search parameters - use getattr with defaults for safety
            series_raw = getattr(existing_md, 'series', None)
            number_raw = getattr(existing_md, 'issue', None)
            year = getattr(existing_md, 'year', None)
            
            # Extract string values from Series objects if needed
            if series_raw:
                # Check if it's a Series object with a 'name' attribute
                if hasattr(series_raw, 'name'):
                    series = series_raw.name
                else:
                    series = str(series_raw) if series_raw else ""
            else:
                series = ""
            
            # Extract issue number
            if number_raw:
                number = str(number_raw) if number_raw else ""
            else:
                number = ""
            
            if verbose and (series or number or year):
                print(f"  Existing metadata: Series='{series}', Issue='{number}', Year='{year}'", file=sys.stderr)
            
            # Parse filename if metadata is missing
            if not series or not number:
                if verbose:
                    print(f"  {Colors.YELLOW}⚠{Colors.RESET} Missing metadata, parsing filename...", file=sys.stderr)
                
                filename = path.stem
                parsed_series, parsed_number, parsed_year = parse_filename(filename)
                
                if parsed_series and parsed_number:
                    series = series or parsed_series
                    number = number or parsed_number
                    year = year or parsed_year
                    if verbose:
                        print(f"  {Colors.GREEN}✓{Colors.RESET} Parsed: {series} #{number}" +
                            (f" ({year})" if year else ""), file=sys.stderr)
                else:
                    print(f"  {Colors.RED}✗{Colors.RESET} Could not parse series/number from filename", file=sys.stderr)
                    return False
            
            # Use filename year if ComicInfo year is missing
            if not year:
                _, _, parsed_year = parse_filename(path.stem)
                if parsed_year:
                    year = parsed_year
                    if verbose:
                        print(f"  Using year from filename: {year}", file=sys.stderr)
            
            if not series or not number:
                print(f"  {Colors.RED}✗{Colors.RESET} Missing Series or Number", file=sys.stderr)
                return False
            
            if verbose:
                print(f"  Searching Metron: {series} #{number}" + (f" ({year})" if year else ""), file=sys.stderr)
            
            # Search Metron
            issue = self.search_issue(series, number, year, verbose=verbose)
            
            if not issue:
                print(f"  {Colors.RED}✗{Colors.RESET} Not found on Metron", file=sys.stderr)
                return False
            
            if verbose:
                series_title = getattr(issue.series, 'display_name', 'Unknown') if issue.series else 'Unknown'
                print(f"  {Colors.GREEN}✓{Colors.RESET} Found: {series_title} #{issue.number}", file=sys.stderr)
            
            # Convert Metron issue to Metadata
            new_md = self.issue_to_comicinfo(issue)
            
            # Merge metadata
            merged_md, changes = self.merge_metadata(existing_md, new_md, overwrite=overwrite)
            
            if not changes:
                if verbose:
                    print(f"  {Colors.BLUE}ℹ{Colors.RESET} No changes needed", file=sys.stderr)
                return False
            
            if dry_run:
                print(f"  {Colors.BLUE}[DRY RUN]{Colors.RESET} Would update {len(changes)} field(s):", file=sys.stderr)
                for change in changes:
                    old_display = str(change['old'])[:50] + '...' if len(str(change['old'])) > 50 else str(change['old'])
                    new_display = str(change['new'])[:50] + '...' if len(str(change['new'])) > 50 else str(change['new'])
                    print(f"    {Colors.YELLOW}{change['field']}{Colors.RESET}: "
                        f"{Colors.RED}{old_display}{Colors.RESET} → "
                        f"{Colors.GREEN}{new_display}{Colors.RESET}", file=sys.stderr)
                return True
            
            # Write metadata using darkseid - specify ComicInfo format
            comic.write_metadata(merged_md, MetadataFormat.COMIC_INFO)
            
            if verbose:
                print(f"  {Colors.GREEN}✓{Colors.RESET} Updated {len(changes)} field(s):", file=sys.stderr)
                for change in changes:
                    old_display = str(change['old'])[:30] + '...' if len(str(change['old'])) > 30 else str(change['old'])
                    new_display = str(change['new'])[:30] + '...' if len(str(change['new'])) > 30 else str(change['new'])
                    print(f"    {Colors.CYAN}{change['field']}{Colors.RESET}: "
                        f"{old_display} → {new_display}", file=sys.stderr)
            
            return True
            
        except Exception as e:
            print(f"  {Colors.RED}✗ ERROR:{Colors.RESET} {e}", file=sys.stderr)
            if verbose:
                import traceback
                traceback.print_exc()
            return False
    
    def issue_to_metadata(self, issue: Any) -> Metadata:
        """
        Convert a Metron issue object to Darkseid Metadata.
        
        Args:
            issue: Metron issue object
            
        Returns:
            Metadata object with all available fields populated
        """
        md = Metadata()
        
        # Basic fields
        if hasattr(issue, 'series') and issue.series:
            md.series = issue.series.name
        
        if hasattr(issue, 'number') and issue.number:
            md.issue = str(issue.number)
        
        if hasattr(issue, 'story_titles') and issue.story_titles:
            if isinstance(issue.story_titles, list):
                md.title = "; ".join(issue.story_titles)
            else:
                md.title = str(issue.story_titles)
        
        if hasattr(issue, 'desc') and issue.desc:
            md.comments = issue.desc  # Darkseid uses 'comments' for description
        
        # Publisher
        if hasattr(issue, 'publisher') and issue.publisher:
            md.publisher = issue.publisher.name
        
        # Dates
        if hasattr(issue, 'cover_date') and issue.cover_date:
            try:
                date_obj = datetime.strptime(issue.cover_date, "%Y-%m-%d")
                md.year = date_obj.year
                md.month = date_obj.month
                md.day = date_obj.day
            except:
                pass
        
        # Volume
        if hasattr(issue, 'series') and issue.series and hasattr(issue.series, 'volume') and issue.series.volume:
            md.volume = issue.series.volume
        
        # Credits
        if hasattr(issue, 'credits') and issue.credits:
            writers = []
            pencillers = []
            inkers = []
            colorists = []
            letterers = []
            cover_artists = []
            editors = []
            
            for credit in issue.credits:
                role = credit.role[0].name.lower() if credit.role else ""
                creator = credit.creator.name if credit.creator else ""
                
                if not creator:
                    continue
                
                if "writer" in role:
                    writers.append(creator)
                elif "pencil" in role or "artist" in role:
                    pencillers.append(creator)
                elif "ink" in role:
                    inkers.append(creator)
                elif "color" in role:
                    colorists.append(creator)
                elif "letter" in role:
                    letterers.append(creator)
                elif "cover" in role:
                    cover_artists.append(creator)
                elif "editor" in role:
                    editors.append(creator)
            
            if writers:
                md.writer = ", ".join(writers)
            if pencillers:
                md.penciller = ", ".join(pencillers)
            if inkers:
                md.inker = ", ".join(inkers)
            if colorists:
                md.colorist = ", ".join(colorists)
            if letterers:
                md.letterer = ", ".join(letterers)
            if cover_artists:
                md.cover_artist = ", ".join(cover_artists)
            if editors:
                md.editor = ", ".join(editors)
        
        # Characters
        if hasattr(issue, 'characters') and issue.characters:
            char_names = [char.name for char in issue.characters if hasattr(char, 'name') and char.name]
            if char_names:
                md.characters = ", ".join(char_names)
        
        # Teams
        if hasattr(issue, 'teams') and issue.teams:
            team_names = [team.name for team in issue.teams if hasattr(team, 'name') and team.name]
            if team_names:
                md.teams = ", ".join(team_names)
        
        # Story arcs
        if hasattr(issue, 'arcs') and issue.arcs:
            arc_names = [arc.name for arc in issue.arcs if hasattr(arc, 'name') and arc.name]
            if arc_names:
                md.story_arc = ", ".join(arc_names)
        
        # Page count
        if hasattr(issue, 'page_count') and issue.page_count:
            md.page_count = issue.page_count
        
        # Web link
        if hasattr(issue, 'id') and issue.id:
            md.web = f"https://metron.cloud/issue/{issue.id}/"
            md.notes = f"Metron ID: {issue.id}"
        
        return md
    
    def extract_metadata_from_issue(self, issue: Any) -> Dict[str, str]:
        """
        Extract metadata from a Metron issue object.
        
        Args:
            issue: Metron issue object (BaseIssue from mokkari)
            
        Returns:
            Dictionary of tag_name -> value
        """
        metadata = {}
        
        # Basic fields
        if hasattr(issue, 'series') and issue.series:
            metadata['Series'] = issue.series.name
        
        if hasattr(issue, 'number') and issue.number:
            metadata['Number'] = str(issue.number)
        
        # Title - the actual issue title/story name
        if hasattr(issue, 'story_titles') and issue.story_titles:
            # story_titles is a list, join them if multiple
            if isinstance(issue.story_titles, list):
                metadata['Title'] = "; ".join(issue.story_titles)
            else:
                metadata['Title'] = str(issue.story_titles)
        
        if hasattr(issue, 'desc') and issue.desc:
            metadata['Summary'] = issue.desc
        
        # Publisher
        if hasattr(issue, 'publisher') and issue.publisher:
            metadata['Publisher'] = issue.publisher.name
        
        # Dates
        if hasattr(issue, 'cover_date') and issue.cover_date:
            try:
                date_obj = datetime.strptime(issue.cover_date, "%Y-%m-%d")
                metadata['Year'] = str(date_obj.year)
                metadata['Month'] = str(date_obj.month)
                metadata['Day'] = str(date_obj.day)
            except:
                pass
        
        # Volume
        if hasattr(issue, 'series') and issue.series and hasattr(issue.series, 'volume') and issue.series.volume:
            metadata['Volume'] = str(issue.series.volume)
        
        # Credits
        if hasattr(issue, 'credits') and issue.credits:
            writers = []
            pencillers = []
            inkers = []
            colorists = []
            letterers = []
            cover_artists = []
            editors = []
            
            for credit in issue.credits:
                role = credit.role[0].name.lower() if credit.role else ""
                creator = credit.creator.name if credit.creator else ""
                
                if not creator:
                    continue
                
                if "writer" in role:
                    writers.append(creator)
                elif "pencil" in role or "artist" in role:
                    pencillers.append(creator)
                elif "ink" in role:
                    inkers.append(creator)
                elif "color" in role:
                    colorists.append(creator)
                elif "letter" in role:
                    letterers.append(creator)
                elif "cover" in role:
                    cover_artists.append(creator)
                elif "editor" in role:
                    editors.append(creator)
            
            if writers:
                metadata['Writer'] = ", ".join(writers)
            if pencillers:
                metadata['Penciller'] = ", ".join(pencillers)
            if inkers:
                metadata['Inker'] = ", ".join(inkers)
            if colorists:
                metadata['Colorist'] = ", ".join(colorists)
            if letterers:
                metadata['Letterer'] = ", ".join(letterers)
            if cover_artists:
                metadata['CoverArtist'] = ", ".join(cover_artists)
            if editors:
                metadata['Editor'] = ", ".join(editors)
        
        # Characters
        if hasattr(issue, 'characters') and issue.characters:
            char_names = [char.name for char in issue.characters if hasattr(char, 'name') and char.name]
            if char_names:
                metadata['Characters'] = ", ".join(char_names)
        
        # Teams
        if hasattr(issue, 'teams') and issue.teams:
            team_names = [team.name for team in issue.teams if hasattr(team, 'name') and team.name]
            if team_names:
                metadata['Teams'] = ", ".join(team_names)
        
        # Story arcs
        if hasattr(issue, 'arcs') and issue.arcs:
            arc_names = [arc.name for arc in issue.arcs if hasattr(arc, 'name') and arc.name]
            if arc_names:
                metadata['StoryArc'] = ", ".join(arc_names)
        
        # Page count
        if hasattr(issue, 'page_count') and issue.page_count:
            metadata['PageCount'] = str(issue.page_count)
        
        # Web link
        if hasattr(issue, 'id') and issue.id:
            metadata['Web'] = f"https://metron.cloud/issue/{issue.id}/"
            metadata['Notes'] = f"Metron ID: {issue.id}"
        
        return metadata


def parse_filename(filename: str) -> tuple[Optional[str], Optional[str], Optional[int]]:
    """
    Try to extract series, issue number, and year from filename.
    
    Examples:
        "Amazing Spider-Man (2022) #001.cbz" -> ("Amazing Spider-Man", "1", 2022)
        "Batman 050 (2018).cbz" -> ("Batman", "50", 2018)
        "Ultimates 009 (2016) GetComics.INFO" -> ("Ultimates", "9", 2016)
    
    Returns:
        Tuple of (series, issue_number, year) or (None, None, None)
    """
    # Remove common suffixes like "GetComics.INFO", "digital", etc.
    filename = re.sub(r'\s+(GetComics\.INFO|digital|c2c|web|HD|GDCP).*$', '', filename, flags=re.IGNORECASE)
    
    # Pattern: Series Name (Year) #Number or Series Name Number (Year)
    patterns = [
        r'^(.+?)\s+\((\d{4})\)\s+#?(\d+(?:\.\d+)?)',  # Series (Year) #123
        r'^(.+?)\s+#?(\d+(?:\.\d+)?)\s+\((\d{4})\)',  # Series #123 (Year)
        r'^(.+?)\s+(\d{3,})\s*$',                      # Series 001 (3+ digits, no year)
        r'^(.+?)\s+#?(\d+(?:\.\d+)?)$',                # Series 123 or Series #123
    ]
    
    for pattern in patterns:
        match = re.match(pattern, filename.strip())
        if match:
            groups = match.groups()
            if len(groups) == 3:
                # Check which group is the year
                if groups[1].isdigit() and len(groups[1]) == 4:
                    series, year, number = groups[0].strip(), int(groups[1]), groups[2]
                elif groups[2].isdigit() and len(groups[2]) == 4:
                    series, number, year = groups[0].strip(), groups[1], int(groups[2])
                else:
                    continue
                
                # Normalize issue number: remove leading zeros
                number = str(int(float(number))) if '.' not in number else number
                return series, number, year
            elif len(groups) == 2:
                series, number = groups[0].strip(), groups[1]
                # Normalize issue number: remove leading zeros
                number = str(int(float(number))) if '.' not in number else number
                return series, number, None
    
    return None, None, None


def metron_scrape(files: List[str], username: str, password: str, overwrite: bool = False,
                  dry_run: bool = False, verbose: bool = False):
    """
    Scrape comic metadata using Metron API.
    
    Args:
        files: List of comic file paths to scrape
        username: Metron username
        password: Metron password
        overwrite: If True, overwrite existing metadata fields
        dry_run: If True, only preview what would be scraped
        verbose: Enable verbose output
    """
    if not files:
        print(f"{Colors.YELLOW}⚠{Colors.RESET} No files to scrape", file=sys.stderr)
        return
    
    if not username or not password:
        print(f"{Colors.RED}✗{Colors.RESET} Metron username and password required", file=sys.stderr)
        print("  Set via --metron-user/--metron-pass or METRON_USER/METRON_PASS env vars", file=sys.stderr)
        sys.exit(1)
    
    if dry_run:
        print(f"{Colors.BLUE}[DRY RUN]{Colors.RESET} Metron scraping preview\n", file=sys.stderr)
    
    print(f"{Colors.BLUE}[METRON]{Colors.RESET} Scraping {len(files)} file(s)...\n", file=sys.stderr)
    
    try:
        scraper = MetronScraper(username, password)
        
        success = 0
        skipped = 0
        failed = 0
        
        for i, file_path in enumerate(files, 1):
            if verbose:
                print(f"\n[{i}/{len(files)}]", file=sys.stderr)
            
            try:
                result = scraper.scrape_file(file_path, overwrite=overwrite,
                                            dry_run=dry_run, verbose=verbose)
                if result:
                    success += 1
                else:
                    skipped += 1
            except Exception as e:
                print(f"{Colors.RED}✗{Colors.RESET} Failed: {Path(file_path).name} - {e}",
                      file=sys.stderr)
                failed += 1
        
        # Summary
        print(f"\n{Colors.BOLD}{'='*60}{Colors.RESET}", file=sys.stderr)
        print(f"{Colors.BOLD}SCRAPING SUMMARY{Colors.RESET}", file=sys.stderr)
        print(f"{Colors.BOLD}{'='*60}{Colors.RESET}", file=sys.stderr)
        print(f"Total files: {len(files)}", file=sys.stderr)
        print(f"{Colors.GREEN}✓{Colors.RESET} {'Would update' if dry_run else 'Updated'}: {success}",
              file=sys.stderr)
        print(f"{Colors.BLUE}ℹ{Colors.RESET} Skipped: {skipped}", file=sys.stderr)
        print(f"{Colors.RED}✗{Colors.RESET} Failed: {failed}", file=sys.stderr)
        print(f"{Colors.BOLD}{'='*60}{Colors.RESET}\n", file=sys.stderr)
        
    except ImportError as e:
        print(f"{Colors.RED}✗{Colors.RESET} {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"{Colors.RED}✗ ERROR:{Colors.RESET} {e}", file=sys.stderr)
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)