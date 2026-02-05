"""
Automated Politician Status Checker using Congress.gov API

This module automatically checks politician statuses by comparing the politician
registry against current members of Congress from the official Congress.gov API.

Option C: Fully automated - zero manual maintenance required.

Congress.gov API Documentation:
- https://api.congress.gov
- https://github.com/LibraryOfCongress/api.congress.gov
- Rate limit: 5,000 requests/hour (more than sufficient for daily checks)
- Free API key signup: https://api.congress.gov/sign-up/
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set
from datetime import datetime
import time

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AutomatedPoliticianStatusChecker:
    """
    Automated politician status checker using Congress.gov API.

    Fetches current House and Senate members from Congress.gov and compares
    against the politician registry to automatically detect politicians who
    have left office.
    """

    # Congress.gov API configuration
    CONGRESS_GOV_API_BASE = "https://api.congress.gov/v3"
    CURRENT_CONGRESS = 119  # 119th Congress: Jan 2025 - Jan 2027

    # Name normalization mappings for common variations
    NAME_MAPPINGS = {
        'Nancy Pelosi': ['Nancy Pelosi', 'Nancy Patricia Pelosi', 'Pelosi, Nancy'],
        'Paul Pelosi': ['Paul Pelosi', 'Paul F. Pelosi', 'Pelosi, Paul'],
        'Josh Gottheimer': ['Josh Gottheimer', 'Joshua Gottheimer', 'Gottheimer, Josh', 'Gottheimer, Joshua'],
        'Mark Green': ['Mark Green', 'Mark E. Green', 'Green, Mark'],
        'Dan Crenshaw': ['Dan Crenshaw', 'Daniel Crenshaw', 'Crenshaw, Dan', 'Crenshaw, Daniel'],
        'French Hill': ['French Hill', 'J. French Hill', 'Hill, French'],
        'Michael McCaul': ['Michael McCaul', 'Michael T. McCaul', 'McCaul, Michael'],
        'John Curtis': ['John Curtis', 'John R. Curtis', 'Curtis, John'],
        'Brian Higgins': ['Brian Higgins', 'Brian M. Higgins', 'Higgins, Brian'],
        'Tommy Tuberville': ['Tommy Tuberville', 'Thomas Tuberville', 'Tuberville, Tommy'],
        'Shelley Moore Capito': ['Shelley Moore Capito', 'Shelley Capito', 'Capito, Shelley Moore'],
    }

    def __init__(self, api_key: Optional[str] = None, registry_path: Optional[Path] = None):
        """
        Initialize the automated status checker.

        Args:
            api_key: Congress.gov API key (from https://api.congress.gov/sign-up/)
            registry_path: Path to politician_registry.json
        """
        self.api_key = api_key

        if not self.api_key:
            logger.warning("No API key provided - automated status checking disabled")
            logger.warning("Get free API key at: https://api.congress.gov/sign-up/")

        if registry_path is None:
            data_dir = Path(__file__).parent.parent / 'data'
            self.registry_path = data_dir / 'politician_registry.json'
        else:
            self.registry_path = Path(registry_path)

        if not REQUESTS_AVAILABLE:
            logger.warning("requests library not available - automated checking disabled")

    def _make_api_request(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """
        Make an API request to Congress.gov.

        Args:
            endpoint: API endpoint path (e.g., '/member/congress/119')
            params: Additional query parameters

        Returns:
            JSON response dict or None on failure
        """
        if not REQUESTS_AVAILABLE:
            logger.error("requests library not available")
            return None

        if not self.api_key:
            logger.error("No API key provided")
            return None

        url = f"{self.CONGRESS_GOV_API_BASE}{endpoint}"

        # Build query parameters
        query_params = params or {}
        query_params['api_key'] = self.api_key
        query_params['format'] = 'json'

        try:
            logger.debug(f"Making request to: {url}")
            response = requests.get(url, params=query_params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                logger.error(f"Access denied (403) - check your Congress.gov API key")
                logger.error(f"Sign up for free key at: https://api.congress.gov/sign-up/")
            else:
                logger.error(f"HTTP error: {e}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            return None

    def fetch_current_congress_members(self) -> Set[str]:
        """
        Fetch all current members of the 119th Congress (House + Senate).

        Returns:
            Set of normalized politician names currently serving in Congress
        """
        current_members = set()

        # Fetch current members from the current Congress
        logger.info(f"Fetching members from {self.CURRENT_CONGRESS}th Congress...")

        # Get all members with pagination
        offset = 0
        limit = 250  # Maximum allowed by API

        while True:
            params = {
                'currentMember': 'true',
                'limit': limit,
                'offset': offset
            }

            data = self._make_api_request(f'/member/congress/{self.CURRENT_CONGRESS}', params)

            if not data or 'members' not in data:
                logger.warning(f"No member data returned (offset={offset})")
                break

            members = data.get('members', [])

            if not members:
                logger.debug(f"No more members at offset {offset}")
                break

            for member in members:
                # Extract member name
                name = member.get('name')
                if name:
                    normalized_name = self._normalize_name(name)
                    current_members.add(normalized_name)
                    logger.debug(f"Found active member: {normalized_name}")

            logger.info(f"Fetched {len(members)} members (offset={offset})")

            # Check if there are more results
            pagination = data.get('pagination', {})
            total_count = pagination.get('count', 0)

            offset += len(members)

            if offset >= total_count:
                break

            # Rate limiting: brief pause between requests
            time.sleep(0.5)

        logger.info(f"Total active Congress members found: {len(current_members)}")
        return current_members

    def _normalize_name(self, name: str) -> str:
        """
        Normalize a politician name for comparison.

        Handles:
        - "Last, First" -> "First Last"
        - Middle names and initials
        - Common variations

        Args:
            name: Raw name from API or registry

        Returns:
            Normalized name for comparison
        """
        if not name:
            return ""

        # Handle "Last, First" format from Congress.gov
        if ',' in name:
            parts = name.split(',', 1)
            if len(parts) == 2:
                last = parts[0].strip()
                first = parts[1].strip()
                # Remove middle names/initials - just use first name and last name
                first_parts = first.split()
                if first_parts:
                    name = f"{first_parts[0]} {last}"

        # Remove extra whitespace
        name = ' '.join(name.split())

        # Check if this name matches any known variations
        for canonical, variations in self.NAME_MAPPINGS.items():
            if name in variations:
                return canonical

        return name

    def _check_term_ended_dates(self, registry: Dict) -> List[Dict]:
        """
        Check if any 'retiring' politicians have passed their term_ended date
        and auto-transition them to 'retired' status.

        This is critical for proper time-decay weighting calculation:
        - Retiring politicians get 1.5x boost (lame duck multiplier)
        - Retired politicians get exponential decay based on days since retirement

        Without this check, politicians can stay in 'retiring' status indefinitely
        after their term ends, receiving incorrect 1.5x boost instead of decay.

        Args:
            registry: The politician registry dictionary

        Returns:
            List of changes made (for logging)
        """
        changes = []
        politicians = registry.get('politicians', {})
        today = datetime.utcnow().date()

        for politician_name, politician_data in politicians.items():
            # Only check politicians marked as 'retiring'
            if politician_data.get('current_status') != 'retiring':
                continue

            term_ended = politician_data.get('term_ended')
            if not term_ended:
                logger.debug(f"{politician_name} is retiring but has no term_ended date")
                continue

            try:
                # Parse the term_ended date
                end_date = datetime.fromisoformat(term_ended).date()

                # If term has ended, transition to 'retired'
                if end_date < today:
                    days_since_ended = (today - end_date).days

                    # Update status to retired
                    politician_data['current_status'] = 'retired'
                    politician_data['last_updated'] = datetime.utcnow().strftime('%Y-%m-%d')

                    changes.append({
                        'politician': politician_name,
                        'old_status': 'retiring',
                        'new_status': 'retired',
                        'date': term_ended,
                        'days_since_ended': days_since_ended,
                        'reason': 'term_ended_date_passed'
                    })

                    logger.info(f"Auto-transitioned: {politician_name} (retiring → retired, "
                              f"term ended {term_ended}, {days_since_ended} days ago)")
                else:
                    # Term hasn't ended yet - still retiring
                    days_until_end = (end_date - today).days
                    logger.debug(f"{politician_name} still retiring (term ends in {days_until_end} days)")

            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid term_ended date for {politician_name}: {e}")
                continue

        return changes

    def check_and_update_statuses(self, registry_path: Optional[Path] = None) -> Dict:
        """
        Check politician statuses and update registry automatically.

        Compares politicians in the registry against current Congress members
        and automatically updates statuses for politicians who left office.

        Args:
            registry_path: Optional override for registry path

        Returns:
            Dict with status and changes made:
            {
                'status': 'success' | 'error' | 'skipped',
                'changes': [{'politician': str, 'old_status': str, 'new_status': str, 'date': str}],
                'active_count': int,
                'reason': str  # if skipped or error
            }
        """
        if not REQUESTS_AVAILABLE:
            return {
                'status': 'skipped',
                'reason': 'requests_library_not_available',
                'changes': []
            }

        if not self.api_key:
            logger.warning("Skipping automated status check (no API key)")
            return {
                'status': 'skipped',
                'reason': 'no_api_key',
                'changes': []
            }

        path = registry_path or self.registry_path

        if not path.exists():
            logger.error(f"Registry not found: {path}")
            return {
                'status': 'error',
                'reason': 'registry_not_found',
                'changes': []
            }

        try:
            # Load registry
            with open(path, 'r') as f:
                registry = json.load(f)

            # FIRST: Check for retiring politicians who have passed their term_ended date
            # This ensures correct time-decay weighting calculation
            logger.info("Checking for retiring politicians past their term_ended date...")
            date_based_changes = self._check_term_ended_dates(registry)
            changes = date_based_changes

            if date_based_changes:
                logger.info(f"Found {len(date_based_changes)} politicians to auto-transition based on term_ended dates")

            # SECOND: Fetch current members from Congress.gov
            current_members = self.fetch_current_congress_members()

            if not current_members:
                logger.warning("No current members fetched - API may be unavailable")
                # Still return date_based_changes even if API fails
                if changes:
                    # Save changes made from date checks
                    registry['last_automated_check'] = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
                    with open(path, 'w') as f:
                        json.dump(registry, f, indent=2)
                    logger.info(f"Registry updated with {len(changes)} status changes (date-based only)")

                return {
                    'status': 'partial' if changes else 'error',
                    'reason': 'no_members_fetched_but_date_checks_completed' if changes else 'no_members_fetched',
                    'changes': changes
                }

            # THIRD: Check each politician in registry against Congress.gov API
            politicians = registry.get('politicians', {})

            for politician_name, politician_data in politicians.items():
                current_status = politician_data.get('current_status', 'active')
                normalized_name = self._normalize_name(politician_name)

                is_currently_serving = normalized_name in current_members

                # Auto-update: If politician is marked active/retiring but NOT in Congress -> retired
                if current_status in ['active', 'retiring'] and not is_currently_serving:
                    old_status = current_status
                    new_status = 'retired'

                    # Update status
                    politician_data['current_status'] = new_status
                    politician_data['term_ended'] = datetime.utcnow().strftime('%Y-%m-%d')
                    politician_data['last_updated'] = datetime.utcnow().strftime('%Y-%m-%d')

                    changes.append({
                        'politician': politician_name,
                        'old_status': old_status,
                        'new_status': new_status,
                        'date': politician_data['term_ended']
                    })

                    logger.info(f"Auto-updated: {politician_name} ({old_status} → {new_status})")

            # Save updated registry if changes were made
            if changes:
                registry['last_automated_check'] = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

                with open(path, 'w') as f:
                    json.dump(registry, f, indent=2)

                logger.info(f"Registry updated with {len(changes)} status changes")

            return {
                'status': 'success',
                'changes': changes,
                'active_count': len(current_members),
                'checked_politicians': len(politicians)
            }

        except Exception as e:
            logger.error(f"Failed to check and update statuses: {e}")
            return {
                'status': 'error',
                'reason': str(e),
                'changes': []
            }


def create_automated_checker(api_key: Optional[str] = None, registry_path: Optional[Path] = None) -> AutomatedPoliticianStatusChecker:
    """
    Factory function to create an automated politician status checker.

    Args:
        api_key: Congress.gov API key (or None to read from environment)
        registry_path: Optional path to politician_registry.json

    Returns:
        AutomatedPoliticianStatusChecker instance
    """
    if api_key is None:
        api_key = os.getenv('CONGRESS_GOV_API_KEY')

    return AutomatedPoliticianStatusChecker(api_key=api_key, registry_path=registry_path)
