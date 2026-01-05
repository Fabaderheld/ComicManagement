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
from darkseid.metadata import Metadata, Series, Publisher, Notes, AgeRatings, Credit, Role

from .utils import Colors

# Wrapper classes for metadata fields that darkseid expects as objects

class Imprint:
    """Imprint object with name attribute"""
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"Imprint(name='{self.name}')"

class Resource:
    """Generic resource object (characters, teams, etc.) with name attribute"""
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"Resource(name='{self.name}')"

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
                print(f"  🔍 Searching for series: \'{series_name}\'" + (f" (year: {year})" if year else ""), file=sys.stderr)

            # Build search params - include year if provided
            search_params = {"name": series_name}
            if year:
                search_params["year_began"] = year

            results = self.api.series_list(params=search_params)

            if verbose and results:
                print(f"  📚 Found {len(results)} series result(s):", file=sys.stderr)
                for idx, s in enumerate(results[:5]):  # Show first 5
                    series_title = getattr(s, 'display_name', None) or getattr(s, 'series_name', None) or str(s.id)
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
                        series_title = getattr(s, 'display_name', None) or getattr(s, 'series_name', None) or str(s.id)
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
                series_title = getattr(series, 'display_name', None) or getattr(series, 'series_name', None) or str(series.id)
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

                    # Optional debug output (only if DEBUG_METRON env var is set)
                    if verbose and os.getenv('DEBUG_METRON'):
                        self._debug_issue_object(full_issue)

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

    def _debug_issue_object(self, issue: Any):
        """Debug helper to inspect issue object structure"""
        print(f"\n[DEBUG] ===== FULL ISSUE OBJECT INSPECTION =====", file=sys.stderr)
        print(f"[DEBUG] Type: {type(issue)}", file=sys.stderr)
        print(f"\n[DEBUG] Issue attributes:", file=sys.stderr)
        for attr in dir(issue):
            if not attr.startswith('_'):
                try:
                    value = getattr(issue, attr)
                    if not callable(value):
                        print(f"  {attr}: {type(value)} = {repr(value)[:100]}", file=sys.stderr)
                except:
                    pass

        if hasattr(issue, 'series') and issue.series:
            print(f"\n[DEBUG] Series object:", file=sys.stderr)
            print(f"  Type: {type(issue.series)}", file=sys.stderr)
            for attr in dir(issue.series):
                if not attr.startswith('_'):
                    try:
                        value = getattr(issue.series, attr)
                        if not callable(value):
                            print(f"  series.{attr}: {type(value)} = {repr(value)[:100]}", file=sys.stderr)
                    except:
                        pass

        if hasattr(issue, 'publisher') and issue.publisher:
            print(f"\n[DEBUG] Publisher object:", file=sys.stderr)
            print(f"  Type: {type(issue.publisher)}", file=sys.stderr)
            for attr in dir(issue.publisher):
                if not attr.startswith('_'):
                    try:
                        value = getattr(issue.publisher, attr)
                        if not callable(value):
                            print(f"  publisher.{attr}: {type(value)} = {repr(value)[:100]}", file=sys.stderr)
                    except:
                        pass

        print(f"[DEBUG] ===== END INSPECTION =====\n", file=sys.stderr)

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

    def issue_to_metadata(self, issue: Any) -> Metadata:
        """
        Convert a Metron issue object to Darkseid Metadata.

        This is the main conversion method that maps all Metron fields to ComicInfo.xml format.

        Args:
            issue: Metron issue object from mokkari

        Returns:
            Metadata object with all available fields populated
        """
        md = Metadata()

        # ===== BASIC FIELDS =====

        # Series name - try multiple possible attribute names
        # Darkseid expects an object with .name attribute
        if hasattr(issue, 'series') and issue.series:
            series_name = (getattr(issue.series, 'display_name', None) or 
                          getattr(issue.series, 'series_name', None) or 
                          getattr(issue.series, 'name', None))
            if series_name:
                md.series = Series(
                    name=series_name,
                    volume=getattr(issue.series, "volume", None),
                    issue_count=getattr(issue.series, "issue_count", None),
                    language=getattr(issue.series, "language", None),
                    format=getattr(getattr(issue.series, "series_type", None), "name", None)
                )

        # Issue number
        if hasattr(issue, 'number') and issue.number:
            md.issue = str(issue.number)

        # Title - the actual issue/story title
        if hasattr(issue, 'issue_name') and issue.issue_name:
            md.title = issue.issue_name
        elif hasattr(issue, 'name') and issue.name:
            md.title = issue.name
        elif hasattr(issue, 'story_titles') and issue.story_titles:
            # story_titles might be a list
            if isinstance(issue.story_titles, list):
                md.title = "; ".join(issue.story_titles)
            else:
                md.title = str(issue.story_titles)

        # Description/Summary
        if hasattr(issue, 'desc') and issue.desc:
            md.comments = issue.desc
        elif hasattr(issue, 'summary') and issue.summary:
            md.comments = issue.summary

        # ===== PUBLISHER & IMPRINT =====

        # Publisher - try multiple attribute names
        # Darkseid expects an object with .name attribute
        if hasattr(issue, 'publisher') and issue.publisher:
            pub_name = (getattr(issue.publisher, 'name', None) or 
                       getattr(issue.publisher, 'publisher_name', None) or
                       getattr(issue.publisher, 'display_name', None))
            if pub_name:
                md.publisher = Publisher(pub_name)

        # Imprint (sub-brand of publisher, e.g., "Vertigo" under DC Comics)
        if hasattr(issue, 'imprint') and issue.imprint:
            imprint_name = (getattr(issue.imprint, 'name', None) or 
                           getattr(issue.imprint, 'display_name', None))
            if imprint_name:
                md.imprint = Imprint(imprint_name)

        # ===== DATES =====

        # Cover date (the date printed on the cover)
        if hasattr(issue, 'cover_date') and issue.cover_date:
            try:
                # cover_date might be a string or date object
                date_str = str(issue.cover_date)
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                md.year = date_obj.year
                md.month = date_obj.month
                md.day = date_obj.day
            except (ValueError, TypeError):
                pass

        # Store date (when it was actually released)
        if hasattr(issue, 'store_date') and issue.store_date:
            md.store_date = str(issue.store_date)

        # ===== VOLUME & COUNTS =====

        # Volume number
        if hasattr(issue, 'series') and issue.series:
            if hasattr(issue.series, 'volume') and issue.series.volume:
                md.volume = issue.series.volume

        # Issue count in series
        if hasattr(issue, 'series') and issue.series:
            if hasattr(issue.series, 'issue_count') and issue.series.issue_count:
                md.issue_count = issue.series.issue_count

        # Page count
        if hasattr(issue, 'page_count') and issue.page_count:
            md.page_count = issue.page_count

        # ===== FORMAT & RATING =====

        # Format (One-Shot, Limited Series, Ongoing Series, etc.)
        if hasattr(issue, 'series') and issue.series:
            if hasattr(issue.series, 'series_type') and issue.series.series_type:
                type_name = getattr(issue.series.series_type, 'name', None)
                if type_name:
                    md.format = type_name

        # Age Rating
        if hasattr(issue, 'rating') and issue.rating:
            rating_name = getattr(issue.rating, 'name', None)
            if rating_name:
                md.age_rating = AgeRatings(comic_rack=rating_name)

        # ===== CREDITS (CREATORS) =====
        from darkseid.metadata import Credit, Role

        if hasattr(issue, 'credits') and issue.credits:
            credits_list = []
            
            for credit in issue.credits:
                # Skip if no role
                if not hasattr(credit, 'role') or not credit.role:
                    continue

                # Role might be a single object or a list
                role_list = credit.role if isinstance(credit.role, list) else [credit.role]

                # Extract role names
                role_names = []
                for r in role_list:
                    role_name = getattr(r, 'name', None)
                    if role_name:
                        role_names.append(role_name)

                if not role_names:
                    continue

                # Get creator name
                creator_name = None
                if hasattr(credit, 'creator') and credit.creator:
                    creator_name = (getattr(credit.creator, 'name', None) or 
                                getattr(credit.creator, 'creator_name', None) or
                                str(credit.creator))

                if not creator_name:
                    continue

                # Create Credit objects for each role
                for role in role_names:
                    # Map Metron roles to ComicInfo roles
                    comicinfo_role = None
                    role_lower = role.lower()
                    
                    if "writer" in role_lower or "plot" in role_lower or "script" in role_lower:
                        comicinfo_role = "Writer"
                    elif "pencil" in role_lower or ("artist" in role_lower and "cover" not in role_lower):
                        comicinfo_role = "Penciller"
                    elif "ink" in role_lower:
                        comicinfo_role = "Inker"
                    elif "color" in role_lower or "colour" in role_lower:
                        comicinfo_role = "Colorist"
                    elif "letter" in role_lower:
                        comicinfo_role = "Letterer"
                    elif "cover" in role_lower:
                        comicinfo_role = "CoverArtist"
                    elif "editor" in role_lower:
                        comicinfo_role = "Editor"
                    elif "translat" in role_lower:
                        comicinfo_role = "Translator"
                    
                    if comicinfo_role:
                        # Create Role object as a LIST, then Credit object
                        role_obj = Role(name=comicinfo_role)
                        credits_list.append(Credit(person=creator_name, role=[role_obj]))

            # Debug: Show what we collected
            print(f"  DEBUG Credits collected: {len(credits_list)} credits")
            for c in credits_list:
                print(f"    {c.role[0].name}: {c.person}")

            # Set the credits list
            md.credits = credits_list

        # Teams - darkseid expects list of objects with .name attribute
        if hasattr(issue, 'teams') and issue.teams:
            team_list = []
            for team in issue.teams:
                if isinstance(team, str):
                    team_list.append(Resource(team))
                else:
                    team_name = (getattr(team, 'display_name', None) or 
                                getattr(team, 'team_name', None) or 
                                getattr(team, 'name', None))
                    if team_name:
                        team_list.append(Resource(team_name))
            if team_list:
                md.teams = team_list

        # ===== STORY ARCS =====

        # Story arcs (crossover events, etc.)
        if hasattr(issue, 'arcs') and issue.arcs:
            arc_names = []
            for arc in issue.arcs:
                if isinstance(arc, str):
                    arc_names.append(arc)
                else:
                    arc_name = (getattr(arc, 'display_name', None) or 
                               getattr(arc, 'arc_name', None) or 
                               getattr(arc, 'name', None))
                    if arc_name:
                        arc_names.append(arc_name)
            if arc_names:
                md.story_arc = ", ".join(arc_names)

        # ===== ADDITIONAL METADATA =====

        # Genres
        if hasattr(issue, 'genres') and issue.genres:
            genre_names = []
            for genre in issue.genres:
                if isinstance(genre, str):
                    genre_names.append(genre)
                else:
                    genre_name = (getattr(genre, 'name', None) or 
                                 getattr(genre, 'display_name', None))
                    if genre_name:
                        genre_names.append(genre_name)
            if genre_names:
                md.genre = ", ".join(genre_names)

        # Locations
        if hasattr(issue, 'locations') and issue.locations:
            location_names = []
            for location in issue.locations:
                if isinstance(location, str):
                    location_names.append(location)
                else:
                    location_name = (getattr(location, 'display_name', None) or 
                                    getattr(location, 'name', None))
                    if location_name:
                        location_names.append(location_name)
            if location_names:
                md.locations = ", ".join(location_names)

        # Universes (e.g., "Earth-616", "New 52")
        if hasattr(issue, 'universes') and issue.universes:
            universe_names = []
            for universe in issue.universes:
                if isinstance(universe, str):
                    universe_names.append(universe)
                else:
                    universe_name = (getattr(universe, 'display_name', None) or 
                                    getattr(universe, 'name', None))
                    if universe_name:
                        universe_names.append(universe_name)
            if universe_names:
                # Add to notes since there's no dedicated universe field
                universe_text = f"Universe: {', '.join(universe_names)}"
                if md.notes:
                    md.notes = Notes(f"{md.notes}\n{universe_text}")
                else:
                    md.notes = universe_text

        # ===== WEB LINK & SOURCE INFO =====

        # Web link to Metron page
        if hasattr(issue, 'id') and issue.id:
            md.web = f"https://metron.cloud/issue/{issue.id}/"

            # Add source info to notes
            scrape_info = f"Scraped from Metron on {datetime.now().strftime('%Y-%m-%d')}"
            metron_id = f"Metron ID: {issue.id}"

            if md.notes:
                md.notes = Notes(f"{md.notes}\n{metron_id}\n{scrape_info}")
            else:
                md.notes = Notes(f"{metron_id}\n{scrape_info}")

        return md

    def merge_metadata(self, existing: Metadata, new: Metadata, overwrite: bool = False) -> tuple[Metadata, List[Dict[str, str]]]:
        """
        Merge new metadata into existing, tracking changes.

        Args:
            existing: Existing Metadata object
            new: New Metadata from Metron
            overwrite: If True, overwrite existing fields. If False, only fill empty fields.

        Returns:
            Tuple of (merged Metadata, list of changes)
        """
        changes = []

        # List of fields to check (using correct Darkseid field names)
        fields = [
            'series', 'issue', 'title', 'comments', 'year', 'month', 'day',
            'volume', 'issue_count', 'writer', 'penciller', 'inker', 'colorist', 
            'letterer', 'cover_artist', 'editor', 'publisher', 'imprint',
            'story_arc', 'characters', 'teams', 'locations', 'genre',
            'page_count', 'format', 'age_rating', 'store_date', 'web', 'notes'
        ]

        for field in fields:
            old_value = getattr(existing, field, None)
            new_value = getattr(new, field, None)

            # Skip if new value is empty
            if new_value is None:
                continue

            # Handle different types for comparison
            if hasattr(new_value, 'name'):
                # It's an object with .name attribute
                new_str = new_value.name
            elif isinstance(new_value, list):
                # It's a list (characters, teams)
                new_str = ", ".join([getattr(item, 'name', str(item)) for item in new_value])
            elif isinstance(new_value, str):
                new_str = new_value.strip()
            else:
                new_str = str(new_value)

            # Skip if new value is empty string
            if not new_str:
                continue

            # Get old value as string
            if hasattr(old_value, 'name'):
                old_str = old_value.name
            elif isinstance(old_value, list):
                old_str = ", ".join([getattr(item, 'name', str(item)) for item in old_value])
            elif old_value is not None:
                old_str = str(old_value)
            else:
                old_str = ""

            # Only update if overwrite=True or field is empty
            if overwrite or not old_str.strip():
                if old_str != new_str:
                    changes.append({
                        'field': field.replace('_', ' ').title(),
                        'old': old_str if old_str else '(empty)',
                        'new': new_str
                    })
                    setattr(existing, field, new_value)

        return existing, changes

    def scrape_file(self, cbz_path: str, overwrite: bool = False,
                    dry_run: bool = False, verbose: bool = False) -> bool:
        """
        Scrape metadata for a single CBZ file using darkseid.

        Args:
            cbz_path: Path to the CBZ file
            overwrite: If True, overwrite all existing metadata
            dry_run: If True, only preview changes without writing
            verbose: Enable verbose output

        Returns:
            True if metadata was updated (or would be in dry_run), False otherwise
        """
        path = Path(cbz_path)

        if verbose:
            print(f"\n{Colors.BLUE}[SCRAPING]{Colors.RESET} {path.name}", file=sys.stderr)

        try:
            # Load comic using darkseid
            comic = Comic(cbz_path)

            # Get existing metadata (or create new if overwriting)
            if overwrite:
                if verbose:
                    print(f"  {Colors.YELLOW}[OVERWRITE MODE]{Colors.RESET} Creating fresh metadata", file=sys.stderr)
                existing_md = Metadata()
            else:
                existing_md = comic.read_metadata(MetadataFormat.COMIC_INFO)

                if existing_md is not None:
                    if verbose:
                        print(f"  {Colors.GREEN}✓{Colors.RESET} Found existing ComicInfo.xml", file=sys.stderr)
                else:
                    if verbose:
                        print(f"  {Colors.YELLOW}⚠{Colors.RESET} No ComicInfo.xml, will create new one", file=sys.stderr)
                    existing_md = Metadata()

            # Get search parameters from existing metadata or filename
            series = ''
            if hasattr(existing_md, 'series') and existing_md.series:
                if hasattr(existing_md.series, 'name'):
                    series = existing_md.series.name
                else:
                    series = str(existing_md.series)

            number = str(getattr(existing_md, 'issue', '') or '')
            year = getattr(existing_md, 'year', None)

            if verbose and (series or number or year):
                print(f"  Existing metadata: Series=\'{series}\', Issue=\'{number}\', Year=\'{year}\'", file=sys.stderr)

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
                series_title = 'Unknown'
                if hasattr(issue, 'series') and issue.series:
                    series_title = (getattr(issue.series, 'display_name', None) or 
                                   getattr(issue.series, 'series_name', None) or 
                                   'Unknown')
                print(f"  {Colors.GREEN}✓{Colors.RESET} Found: {series_title} #{issue.number}", file=sys.stderr)

            # Convert Metron issue to Metadata
            new_md = self.issue_to_metadata(issue)

            if overwrite:
                # Overwrite mode - use new metadata directly
                merged_md = new_md
                changes = [{'field': 'All', 'old': 'existing', 'new': 'overwritten'}]
            else:
                # Merge mode - merge with existing
                merged_md, changes = self.merge_metadata(existing_md, new_md, overwrite=False)

            if not changes:
                if verbose:
                    print(f"  {Colors.BLUE}ℹ{Colors.RESET} No changes needed", file=sys.stderr)
                return False

            if dry_run:
                if overwrite:
                    print(f"  {Colors.BLUE}[DRY RUN]{Colors.RESET} Would overwrite all metadata", file=sys.stderr)
                else:
                    print(f"  {Colors.BLUE}[DRY RUN]{Colors.RESET} Would update {len(changes)} field(s):", file=sys.stderr)
                    for change in changes:
                        old_display = str(change['old'])[:50] + '...' if len(str(change['old'])) > 50 else str(change['old'])
                        new_display = str(change['new'])[:50] + '...' if len(str(change['new'])) > 50 else str(change['new'])
                        print(f"    {Colors.YELLOW}{change['field']}{Colors.RESET}: "
                            f"{Colors.RED}{old_display}{Colors.RESET} → "
                            f"{Colors.GREEN}{new_display}{Colors.RESET}", file=sys.stderr)
                return True

            # Write metadata using darkseid
            try:
                comic.write_metadata(merged_md, MetadataFormat.COMIC_INFO)
            except Exception as write_error:
                print(f"  {Colors.RED}✗ ERROR writing metadata:{Colors.RESET} {write_error}", file=sys.stderr)
                if verbose:
                    import traceback
                    traceback.print_exc()
                return False

            if verbose:
                if overwrite:
                    print(f"  {Colors.GREEN}✓{Colors.RESET} Overwrote all metadata", file=sys.stderr)
                else:
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
                if verbose:
                    import traceback
                    traceback.print_exc()
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