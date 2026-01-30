#!/usr/bin/env python3
"""
Flinks Bank Coverage Scraper

This script scrapes the Flinks status page to extract:
1. The list of countries where Flinks has bank coverage
2. Individual bank information from the status page

It updates:
- flinks.json with market coverage
- Creates/updates account provider entries for banks with 'flinks' in apiAggregators

Source: https://status.flinks.com/

REQUIREMENTS:
- requests (pip install requests)
- beautifulsoup4 (pip install beautifulsoup4)

Usage:
    # Scrape from status page
    python scrapers/flinks_scraper.py
    
    # Only update market coverage (quick mode)
    python scrapers/flinks_scraper.py --coverage-only
    
    # Dry run - show what would be done without making changes
    python scrapers/flinks_scraper.py --dry-run
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Try to import requests and BeautifulSoup
DEPS_AVAILABLE = False
try:
    import requests
    from bs4 import BeautifulSoup
    DEPS_AVAILABLE = True
except ImportError:
    pass


# URLs
FLINKS_STATUS_URL = "https://status.flinks.com/"
FLINKS_DOCS_URL = "https://docs.flinks.com/guides/connect/connect-bank-accounts"

# Paths relative to this script's location
BASE_PATH = Path(__file__).parent.parent
FLINKS_JSON_PATH = BASE_PATH / "data" / "api-aggregators" / "flinks.json"
ACCOUNT_PROVIDERS_PATH = BASE_PATH / "data" / "account-providers"
SCRAPED_DATA_PATH = BASE_PATH / "scraped-data" / "flinks"

# Request settings
REQUEST_TIMEOUT = 30

# Flinks market coverage - known markets
FLINKS_MARKETS = {
    "CA": "Canada",
    "US": "United States",
}

# Bank name mappings - map status page names to standardized names
# Set to None to skip (e.g., test banks or non-bank services)
BANK_NAME_MAPPINGS = {
    # Skip payment services (not banks)
    "Electronic Funds Transfer": None,
    "Interac® e-Transfer": None,
    # Canadian banks
    "ATB": "ATB Financial",
    "BMO": "Bank of Montreal",
    "CIBC": "CIBC",
    "CoastCapital": "Coast Capital Savings",
    "Desjardins": "Desjardins",
    "EQBank": "EQ Bank",
    "FlinksCapital": None,  # Test bank - skip
    "HSBC": "HSBC Canada",
    "Laurentienne": "Laurentian Bank",
    "Meridian": "Meridian Credit Union",
    "National": "National Bank of Canada",
    "RBC": "Royal Bank of Canada",
    "Scotia": "Scotiabank",
    "Simplii": "Simplii Financial",
    "Tangerine": "Tangerine",
    "TD": "TD Canada Trust",
    "Vancity": "Vancity",
    "Neo Financial": "Neo Financial",
    "PC Financial": "PC Financial",
    "KOHO": "KOHO",
    "Servus Credit Union": "Servus Credit Union",
    "Wealthsimple Retail": "Wealthsimple",
    # US banks
    "Ally Bank": "Ally Bank",
    "Bank of America": "Bank of America",
    "Bank of the West": "Bank of the West",
    "BBVA": "BBVA USA",
    "Capital One": "Capital One",
    "Chase Bank": "Chase",
    "Chime": "Chime",
    "Citibank Online": "Citibank",
    "Citizen's Bank": "Citizens Bank",
    "Discover": "Discover",
    "Fifth Third Bank": "Fifth Third Bank",
    "Key Bank": "KeyBank",
    "Marcus": "Marcus by Goldman Sachs",
    "Navy Federal Credit Union": "Navy Federal Credit Union",
    "PNC Bank": "PNC Bank",
    "SunTrust": "SunTrust Bank",
    "TD Bank USA": "TD Bank",
    "US Bank": "U.S. Bank",
    "USAA": "USAA",
    "Wells Fargo Bank Online": "Wells Fargo",
    "Alliance Capital": "Alliance Capital",
    "Regions": "Regions Bank",
    # Wealth institutions
    "Wealthsimple": "Wealthsimple",
    "Sun Life": "Sun Life",
    "Questrade": "Questrade",
    "Manulife Group retirement solutions": "Manulife",
    "Desjardins Insurance Retirement": "Desjardins",
    "TD (Direct Investing) (Waterhouse)": "TD Direct Investing",
    "Edward Jones": "Edward Jones",
    "Solium Shareworks": "Solium Shareworks",
    "BMO Nesbitt Burns": "BMO Nesbitt Burns",
}

# Transliteration map for special characters
TRANSLITERATIONS = {
    'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss',
    'Ä': 'ae', 'Ö': 'oe', 'Ü': 'ue',
    'á': 'a', 'à': 'a', 'â': 'a', 'ã': 'a', 'å': 'a', 'ą': 'a',
    'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e', 'ę': 'e', 'ě': 'e',
    'í': 'i', 'ì': 'i', 'î': 'i', 'ï': 'i',
    'ó': 'o', 'ò': 'o', 'ô': 'o', 'õ': 'o', 'ø': 'o', 'ő': 'o',
    'ú': 'u', 'ù': 'u', 'û': 'u', 'ű': 'u',
    'ý': 'y', 'ÿ': 'y',
    'ñ': 'n', 'ń': 'n',
    'ç': 'c', 'ć': 'c', 'č': 'c',
    'ş': 's', 'ś': 's', 'š': 's',
    'ž': 'z', 'ź': 'z', 'ż': 'z',
    'ł': 'l', 'đ': 'd', 'ř': 'r',
    'ţ': 't', 'ť': 't',
    'æ': 'ae', 'œ': 'oe',
    'ă': 'a', 'ș': 's', 'ț': 't',
}


def slugify(name: str) -> str:
    """
    Convert a bank name to a slug suitable for use as an ID.
    
    Args:
        name: The bank name to convert
        
    Returns:
        A lowercase, hyphenated slug
        
    Example:
        >>> slugify("Royal Bank of Canada")
        'royal-bank-of-canada'
    """
    # Apply transliterations
    slug = name
    for char, replacement in TRANSLITERATIONS.items():
        slug = slug.replace(char, replacement)
        slug = slug.replace(char.upper(), replacement)
    
    # Convert to lowercase
    slug = slug.lower()
    # Remove special characters, keep alphanumeric and spaces
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    # Replace spaces with hyphens
    slug = re.sub(r'\s+', '-', slug)
    # Remove multiple consecutive hyphens
    slug = re.sub(r'-+', '-', slug)
    # Remove leading/trailing hyphens
    slug = slug.strip('-')
    return slug


def fetch_url(url: str) -> Optional[str]:
    """
    Fetch content from a URL.
    
    Args:
        url: The URL to fetch
        
    Returns:
        The response text, or None if the request failed
    """
    print(f"Fetching {url}...")
    
    if DEPS_AVAILABLE:
        try:
            response = requests.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response.text
        except Exception as e:
            print(f"  Warning: Failed to fetch {url}: {e}")
            return None
    else:
        # Fallback to curl
        try:
            result = subprocess.run(
                ["curl", "-s", "-L", "--connect-timeout", str(REQUEST_TIMEOUT), url],
                capture_output=True,
                text=True,
                timeout=REQUEST_TIMEOUT + 10
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout
            return None
        except Exception as e:
            print(f"  Warning: Failed to fetch {url}: {e}")
            return None


def load_json(path: Path) -> dict:
    """Load a JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: dict) -> None:
    """Save data to a JSON file with consistent formatting."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def get_existing_provider_ids() -> set[str]:
    """
    Get the set of existing account provider IDs.
    
    Returns:
        A set of provider ID strings
    """
    provider_ids = set()
    for json_file in ACCOUNT_PROVIDERS_PATH.glob("*.json"):
        provider_ids.add(json_file.stem)
    return provider_ids


def find_matching_provider(bank_id: str, existing_ids: set[str]) -> Optional[str]:
    """
    Find an existing provider ID that matches the given bank ID.
    
    Args:
        bank_id: The slugified bank ID
        existing_ids: Set of existing provider IDs
        
    Returns:
        The matching existing provider ID, or None if no match
    """
    # Exact match
    if bank_id in existing_ids:
        return bank_id
    
    # Common suffixes to try removing/adding
    suffixes = ['-bank', '-financial', '-credit-union', '-savings', '-trust', '-usa', '-canada']
    country_suffixes = ['-ca', '-us']
    
    # Try removing country suffixes first
    for suffix in country_suffixes:
        if bank_id.endswith(suffix):
            base_id = bank_id[:-len(suffix)]
            if base_id in existing_ids:
                return base_id
    
    # Try removing common suffixes
    for suffix in suffixes:
        if bank_id.endswith(suffix):
            base_id = bank_id[:-len(suffix)]
            if base_id in existing_ids:
                return base_id
    
    # Try adding suffixes
    for suffix in suffixes:
        if f"{bank_id}{suffix}" in existing_ids:
            return f"{bank_id}{suffix}"
    
    # Try common name variations
    variations = [
        bank_id.replace('-and-', '-'),
        bank_id.replace('-', ''),
        bank_id.replace('bank-of-', ''),
    ]
    for var in variations:
        if var in existing_ids:
            return var
    
    return None


def create_account_provider(bank: dict) -> dict:
    """
    Create a new account provider entry from bank data.
    
    Args:
        bank: Dictionary with bank information (name, country)
        
    Returns:
        A dictionary representing the account provider
    """
    bank_id = slugify(bank["name"])
    country = bank.get("country", "CA")
    
    provider = {
        "id": bank_id,
        "type": ["account"],
        "bankType": ["retail"],
        "name": bank["name"],
        "legalName": bank["name"],
        "verified": False,
        "status": "live",
        "icon": f"https://icons.duckduckgo.com/ip3/www.{bank_id}.com.ico",
        "websiteUrl": None,
        "countryHQ": country,
        "countries": [country],
        "webApplication": True,
        "mobileApps": [],
        "compliance": [],
        "developerPortalUrl": None,
        "apiStandards": [],
        "apiProducts": [],
        "apiAggregators": ["flinks"],
        "ownership": [],
        "stateOwned": False,
        "stockSymbol": None
    }
    
    return provider


def add_flinks_to_existing_provider(provider_path: Path) -> bool:
    """
    Add 'flinks' to an existing provider's apiAggregators list.
    
    Args:
        provider_path: Path to the provider JSON file
        
    Returns:
        True if the file was modified, False otherwise
    """
    provider = load_json(provider_path)
    
    aggregators = provider.get("apiAggregators", [])
    if aggregators is None:
        aggregators = []
    
    if "flinks" not in aggregators:
        aggregators.append("flinks")
        aggregators.sort()
        provider["apiAggregators"] = aggregators
        save_json(provider_path, provider)
        return True
    
    return False


def parse_status_page(html: str) -> dict[str, list[dict]]:
    """
    Parse the Flinks status page to extract bank information.
    
    The status page has sections for:
    - Major Financial Institutions - Canada
    - Major Financial Institutions - USA
    - Wealth Financial Institutions
    
    Args:
        html: The HTML content of the status page
        
    Returns:
        A dictionary mapping country codes to lists of bank data
    """
    if not DEPS_AVAILABLE:
        print("  Warning: beautifulsoup4 not available, using regex parsing")
        return parse_status_page_regex(html)
    
    soup = BeautifulSoup(html, 'html.parser')
    all_banks = {"CA": [], "US": []}
    seen_names = set()
    
    # Find all component groups (sections)
    sections = soup.find_all('div', class_='component-group')
    
    for section in sections:
        # Get section title
        title_elem = section.find('h2') or section.find('h3')
        if not title_elem:
            continue
        
        title = title_elem.get_text(strip=True)
        
        # Determine country from section title
        if "Canada" in title:
            country = "CA"
        elif "USA" in title or "US" in title:
            country = "US"
        elif "Wealth" in title:
            # Wealth institutions are typically Canadian
            country = "CA"
        elif "FlinksPay" in title or "Pay" in title:
            # Skip payment services section (EFT, Interac, etc.)
            continue
        else:
            continue
        
        # Find all bank links in this section
        links = section.find_all('a', href=True)
        
        for link in links:
            href = link.get('href', '')
            # Only process component links (not issue links)
            if '/components/' not in href:
                continue
            
            bank_name = link.get_text(strip=True)
            
            # Skip empty or already seen
            if not bank_name or bank_name in seen_names:
                continue
            
            # Apply name mapping
            mapped_name = BANK_NAME_MAPPINGS.get(bank_name, bank_name)
            
            # Skip if mapping returns None (e.g., test banks)
            if mapped_name is None:
                continue
            
            seen_names.add(bank_name)
            
            all_banks[country].append({
                "name": mapped_name,
                "country": country,
                "status_page_name": bank_name,
            })
    
    # If BeautifulSoup didn't find anything, try regex
    if not all_banks["CA"] and not all_banks["US"]:
        return parse_status_page_regex(html)
    
    return all_banks


def parse_status_page_regex(html: str) -> dict[str, list[dict]]:
    """
    Parse the Flinks status page using regex (fallback method).
    
    Args:
        html: The HTML content of the status page
        
    Returns:
        A dictionary mapping country codes to lists of bank data
    """
    all_banks = {"CA": [], "US": []}
    seen_names = set()
    
    # Find bank links with pattern: <a href="/components/...">Bank Name</a>
    # The sections are marked with headers like "Major Financial Institutions - Canada"
    
    # Split by section headers
    canada_section = ""
    usa_section = ""
    wealth_section = ""
    
    # Find Canada section
    canada_match = re.search(
        r'Major Financial Institutions - Canada.*?(?=Major Financial Institutions - USA|Wealth Financial|$)',
        html, re.DOTALL | re.IGNORECASE
    )
    if canada_match:
        canada_section = canada_match.group(0)
    
    # Find USA section  
    usa_match = re.search(
        r'Major Financial Institutions - USA.*?(?=Wealth Financial|FlinksPay|Recent History|$)',
        html, re.DOTALL | re.IGNORECASE
    )
    if usa_match:
        usa_section = usa_match.group(0)
    
    # Note: We skip the FlinksPay section as it contains payment services (EFT, Interac)
    # not financial institutions
    
    # Find Wealth section
    wealth_match = re.search(
        r'Wealth Financial Institutions.*?(?=FlinksPay|Recent History|$)',
        html, re.DOTALL | re.IGNORECASE
    )
    if wealth_match:
        wealth_section = wealth_match.group(0)
    
    # Extract bank names from each section
    link_pattern = re.compile(r'href="[^"]*?/components/[^"]*?"[^>]*>([^<]+)</a>', re.IGNORECASE)
    
    # Process Canada section
    for match in link_pattern.finditer(canada_section):
        bank_name = match.group(1).strip()
        if bank_name and bank_name not in seen_names:
            mapped_name = BANK_NAME_MAPPINGS.get(bank_name, bank_name)
            if mapped_name is not None:
                seen_names.add(bank_name)
                all_banks["CA"].append({
                    "name": mapped_name,
                    "country": "CA",
                    "status_page_name": bank_name,
                })
    
    # Process USA section
    for match in link_pattern.finditer(usa_section):
        bank_name = match.group(1).strip()
        if bank_name and bank_name not in seen_names:
            mapped_name = BANK_NAME_MAPPINGS.get(bank_name, bank_name)
            if mapped_name is not None:
                seen_names.add(bank_name)
                all_banks["US"].append({
                    "name": mapped_name,
                    "country": "US",
                    "status_page_name": bank_name,
                })
    
    # Process Wealth section (add to Canada)
    for match in link_pattern.finditer(wealth_section):
        bank_name = match.group(1).strip()
        if bank_name and bank_name not in seen_names:
            mapped_name = BANK_NAME_MAPPINGS.get(bank_name, bank_name)
            if mapped_name is not None:
                seen_names.add(bank_name)
                all_banks["CA"].append({
                    "name": mapped_name,
                    "country": "CA",
                    "status_page_name": bank_name,
                })
    
    return all_banks


def scrape_flinks_coverage() -> dict[str, list[dict]]:
    """
    Scrape Flinks status page for bank coverage.
    
    Returns:
        A dictionary mapping country codes to lists of bank data
    """
    print("\n=== Scraping Flinks Status Page ===\n")
    
    html = fetch_url(FLINKS_STATUS_URL)
    
    if not html:
        print("  Error: Failed to fetch status page")
        return {}
    
    all_banks = parse_status_page(html)
    
    # Print summary
    for country, banks in all_banks.items():
        print(f"  {FLINKS_MARKETS.get(country, country)}: {len(banks)} banks")
    
    return all_banks


def update_flinks_coverage(country_codes: list[str]) -> None:
    """
    Update flinks.json with market coverage.
    
    Args:
        country_codes: List of country codes where Flinks has coverage
    """
    print("\n=== Updating Flinks Market Coverage ===\n")
    
    print(f"Found {len(country_codes)} countries: {', '.join(sorted(country_codes))}")
    
    # Load and update flinks.json
    flinks_data = load_json(FLINKS_JSON_PATH)
    existing_coverage = flinks_data.get("marketCoverage", {}).get("live", [])
    
    flinks_data["marketCoverage"] = {"live": sorted(country_codes)}
    save_json(FLINKS_JSON_PATH, flinks_data)
    
    # Report changes
    existing_set = set(existing_coverage)
    new_set = set(country_codes)
    added = new_set - existing_set
    removed = existing_set - new_set
    
    if added:
        print(f"  Added countries: {', '.join(sorted(added))}")
    if removed:
        print(f"  Removed countries: {', '.join(sorted(removed))}")
    if not added and not removed:
        print("  No changes to market coverage.")


def update_bank_providers(all_banks: dict[str, list[dict]]) -> None:
    """
    Create/update account providers from scraped bank data.
    
    Args:
        all_banks: Dictionary mapping country codes to lists of bank data
    """
    print("\n=== Updating Bank Providers ===\n")
    
    # Count total banks
    total_banks = sum(len(banks) for banks in all_banks.values())
    print(f"Processing {total_banks} banks from {len(all_banks)} markets...")
    
    # Get existing provider IDs
    existing_ids = get_existing_provider_ids()
    print(f"Found {len(existing_ids)} existing account providers")
    
    # Track statistics
    new_count = 0
    updated_count = 0
    skipped_count = 0
    
    # Process all banks
    for country_code, banks in all_banks.items():
        for bank in banks:
            bank_id = slugify(bank["name"])
            
            if not bank_id:
                continue
            
            # Try to find a matching existing provider
            matching_id = find_matching_provider(bank_id, existing_ids)
            
            if matching_id:
                # Add Flinks to existing provider's aggregators
                provider_path = ACCOUNT_PROVIDERS_PATH / f"{matching_id}.json"
                if add_flinks_to_existing_provider(provider_path):
                    updated_count += 1
                    if matching_id != bank_id:
                        print(f"  Updated: {bank['name']} -> {matching_id}.json (added flinks)")
                    else:
                        print(f"  Updated: {bank['name']} (added flinks)")
                else:
                    skipped_count += 1
            else:
                # Create new provider
                provider_path = ACCOUNT_PROVIDERS_PATH / f"{bank_id}.json"
                provider = create_account_provider(bank)
                save_json(provider_path, provider)
                existing_ids.add(bank_id)
                new_count += 1
                print(f"  Created: {bank['name']} ({bank_id}.json)")
    
    print(f"\nSummary: {new_count} new, {updated_count} updated, {skipped_count} already had flinks")


def save_scraped_data(all_banks: dict[str, list[dict]]) -> None:
    """
    Save all scraped data to a JSON file for reference.
    
    Args:
        all_banks: Dictionary mapping country codes to lists of bank data
    """
    SCRAPED_DATA_PATH.mkdir(parents=True, exist_ok=True)
    
    output = {
        "source": FLINKS_STATUS_URL,
        "scraped_at": datetime.now().isoformat(),
        "markets": {}
    }
    
    for country_code, banks in all_banks.items():
        output["markets"][country_code] = {
            "bank_count": len(banks),
            "banks": [bank["name"] for bank in banks]
        }
    
    output_path = SCRAPED_DATA_PATH / "flinks-coverage.json"
    save_json(output_path, output)
    print(f"\nSaved scraped data to {output_path}")


def main():
    """Main entry point with argument parsing."""
    parser = argparse.ArgumentParser(
        description="Scrape Flinks bank coverage data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Full scrape (status page + update providers)
    python flinks_scraper.py
    
    # Only update market coverage (no provider updates)
    python flinks_scraper.py --coverage-only
    
    # Show what would be done without making changes
    python flinks_scraper.py --dry-run
        """
    )
    parser.add_argument(
        "--coverage-only",
        action="store_true",
        help="Only update market coverage in flinks.json, skip provider updates"
    )
    parser.add_argument(
        "--skip-providers",
        action="store_true",
        help="Skip creating/updating account provider files"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Flinks Bank Coverage Scraper")
    print("=" * 60)
    
    # Check for dependencies
    if not DEPS_AVAILABLE:
        print("\nNote: requests/beautifulsoup4 not available, using fallback methods.")
        print("Install for better parsing: pip install requests beautifulsoup4")
    
    all_banks = {}
    
    if args.coverage_only:
        # Just update market coverage with known markets
        print("\nUpdating market coverage only...")
        country_codes = list(FLINKS_MARKETS.keys())
        if not args.dry_run:
            update_flinks_coverage(country_codes)
        else:
            print(f"  Would update with {len(country_codes)} countries: {', '.join(sorted(country_codes))}")
        print("\n" + "=" * 60)
        print("Done!")
        print("=" * 60)
        return
    
    # Scrape the status page
    all_banks = scrape_flinks_coverage()
    
    if not all_banks or all(len(banks) == 0 for banks in all_banks.values()):
        print("\nNo bank data obtained. Using known markets for coverage only.")
        country_codes = list(FLINKS_MARKETS.keys())
    else:
        country_codes = [code for code, banks in all_banks.items() if banks]
    
    # Update flinks.json with market coverage
    if not args.dry_run:
        update_flinks_coverage(country_codes)
    else:
        print(f"\n[DRY RUN] Would update market coverage with {len(country_codes)} countries")
    
    # Save scraped data for reference
    if all_banks and not args.dry_run:
        save_scraped_data(all_banks)
    elif all_banks:
        total_banks = sum(len(banks) for banks in all_banks.values())
        print(f"[DRY RUN] Would save data for {total_banks} banks")
    
    # Update bank providers (unless skipped)
    if not args.skip_providers and not args.coverage_only and all_banks:
        if not args.dry_run:
            update_bank_providers(all_banks)
        else:
            print(f"[DRY RUN] Would process bank providers")
    else:
        print("\nSkipping provider updates.")
    
    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)


if __name__ == "__main__":
    main()
