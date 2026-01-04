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


from darkseid.comic import Comic
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
    
    def search_series(self, series_name: str, year: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Search for a series on Metron.
        
        Args:
            series_name: Name of the series
            year: Optional year to filter results
            
        Returns:
            List of matching series
        """
        try:
            results = self.api.series_list(params={"name": series_name})
            
            if year:
                # Filter by year if provided
                filtered = []
                for series in results:
                    series_year = series.year_began
                    if series_year and series_year == year:
                        filtered.append(series)
                return filtered
            
            return results
            
        except ApiError as e:
            print(f"{Colors.RED}✗{Colors.RESET} Metron API error: {e}", file=sys.stderr)
            return []
    
    def search_issue(self, series_name: str, issue_number: str, 
                     year: Optional[int] = None) -> Optional[Any]:
        """
        Search for a specific issue on Metron.
        
        Args:
            series_name: Name of the series
            issue_number: Issue number (e.g., "1", "12.1")
            year: Optional year to narrow search
            
        Returns:
            Issue object or None if not found
        """
        cache_key = f"{series_name}_{issue_number}_{year}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            # First, find the series
            series_results = self.search_series(series_name, year)
            
            if not series_results:
                print(f"{Colors.YELLOW}⚠{Colors.RESET} No series found for: {series_name}", 
                      file=sys.stderr)
                return None
            
            # Use the first (best) match
            series = series_results[0]
            
            # Search for the issue in this series
            issues = self.api.issues_list(params={
                "series_id": series.id,
                "number": issue_number
            })
            
            if not issues:
                print(f"{Colors.YELLOW}⚠{Colors.RESET} No issue #{issue_number} found in {series_name}", 
                      file=sys.stderr)
                return None
            
            issue = issues[0]
            self.cache[cache_key] = issue
            return issue
            
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
    
    def issue_to_comicinfo(self, issue: Any) -> Metadata:
        """
        Convert a Metron issue object to Darkseid Metadata.
        
        Args:
            issue: Metron issue object
            
        Returns:
            Metadata object
        """
        md = Metadata()
        
        # Basic fields
        if issue.series:
            md.series = issue.series.name
        if issue.number:
            md.issue = str(issue.number)
        if issue.name:
            md.title = issue.name
        if issue.desc:
            md.description = issue.desc  # Changed from 'summary'
        
        # Publisher
        if issue.publisher:
            md.publisher = issue.publisher.name
        
        # Dates
        if issue.cover_date:
            try:
                # Parse cover_date (format: YYYY-MM-DD)
                date_obj = datetime.strptime(issue.cover_date, "%Y-%m-%d")
                md.year = date_obj.year
                md.month = date_obj.month
                md.day = date_obj.day
            except:
                pass
        
        # Volume
        if issue.series and issue.series.volume:
            md.volume = issue.series.volume
        
        # Credits (Writers, Pencillers, etc.)
        if issue.credits:
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
        if issue.characters:
            char_names = [char.name for char in issue.characters if char.name]
            if char_names:
                md.characters = ", ".join(char_names)
        
        # Teams
        if issue.teams:
            team_names = [team.name for team in issue.teams if team.name]
            if team_names:
                md.teams = ", ".join
    
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
            'series', 'issue', 'title', 'description', 'publisher', 'year', 'month', 'day',
            'volume', 'writer', 'penciller', 'inker', 'colorist', 'letterer', 
            'cover_artist', 'editor', 'characters', 'teams', 'story_arc', 
            'page_count', 'web_link', 'notes'
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
        from darkseid.comic import Comic
        from darkseid.metadata import Metadata
        
        path = Path(cbz_path)
        if verbose:
            print(f"\n{Colors.BLUE}[SCRAPING]{Colors.RESET} {path.name}", file=sys.stderr)
        
        try:
            # Load comic using darkseid
            comic = Comic(cbz_path)
            
            # Get existing metadata - specify ComicInfo format
            existing_md = comic.read_metadata(ComicInfo)  # ← Add ComicInfo parameter
            if existing_md is None:
                existing_md = Metadata()
                if verbose:
                    print(f"  {Colors.YELLOW}⚠{Colors.RESET} No ComicInfo.xml, will create new one", file=sys.stderr)
            else:
                if verbose:
                    print(f"  {Colors.GREEN}✓{Colors.RESET} Found existing ComicInfo.xml", file=sys.stderr)
            
            # Get search parameters
            series = existing_md.series or ""
            number = existing_md.issue or ""
            year = existing_md.year
            
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
                print(f"  {Colors.GREEN}✓{Colors.RESET} Found: {issue.series.name} #{issue.number}", file=sys.stderr)
            
            # Convert Metron issue to Metadata
            new_md = self.issue_to_metadata(issue)
            
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
            comic.write_metadata(merged_md, ComicInfo)  # ← Add ComicInfo parameter
            
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
        from darkseid.metadata import Metadata
        
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
            md.web_link = f"https://metron.cloud/issue/{issue.id}/"
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
        r'^(.+?)\s+(\d+(?:\.\d+)?)$',                  # Series 123
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