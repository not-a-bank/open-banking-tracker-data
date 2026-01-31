#!/usr/bin/env python3
"""
GoCardless Bank Account Data Scraper

This script parses the GoCardless Bank Account Data Coverage spreadsheet to extract:
1. The list of countries where GoCardless has bank coverage
2. Individual institution information

It updates:
- gocardless.json with market coverage
- Creates/updates account provider entries with 'gocardless' in apiAggregators
- Saves institution ID mappings for reference

Data Source: GoCardless Bank Account Data Coverage Overview spreadsheet
https://docs.google.com/spreadsheets/d/1EZ5n7QDGaRIot5M86dwqd5UFSGEDTeTRzEq3D9uEDkM/

Usage:
    # Parse from local CSV file (download from Google Sheets first)
    python scrapers/gocardless_scraper.py --csv-file path/to/coverage.csv
    
    # Only update market coverage (skip provider updates)
    python scrapers/gocardless_scraper.py --csv-file path/to/coverage.csv --coverage-only
    
    # Dry run - show what would be done without making changes
    python scrapers/gocardless_scraper.py --csv-file path/to/coverage.csv --dry-run
"""

import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional


# Paths relative to this script's location
BASE_PATH = Path(__file__).parent.parent
GOCARDLESS_JSON_PATH = BASE_PATH / "data" / "api-aggregators" / "gocardless.json"
ACCOUNT_PROVIDERS_PATH = BASE_PATH / "data" / "account-providers"
SCRAPED_DATA_PATH = BASE_PATH / "scraped-data" / "gocardless"

# Default CSV file location
DEFAULT_CSV_PATH = Path.home() / "Downloads" / "GoCardless Bank Account Data Coverage Overview - Coverage.csv"

# Valid two-letter country codes (ISO 3166-1 alpha-2)
VALID_COUNTRY_CODES = {
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR", "GB", 
    "GR", "HR", "HU", "IE", "IS", "IT", "LI", "LT", "LU", "LV", "MT", "NL", 
    "NO", "PL", "PT", "RO", "SE", "SI", "SK", "XX"  # XX is sandbox/test
}

# Country code to name mapping
COUNTRY_NAMES = {
    "AT": "Austria",
    "BE": "Belgium",
    "BG": "Bulgaria",
    "CY": "Cyprus",
    "CZ": "Czech Republic",
    "DE": "Germany",
    "DK": "Denmark",
    "EE": "Estonia",
    "ES": "Spain",
    "FI": "Finland",
    "FR": "France",
    "GB": "United Kingdom",
    "GR": "Greece",
    "HR": "Croatia",
    "HU": "Hungary",
    "IE": "Ireland",
    "IS": "Iceland",
    "IT": "Italy",
    "LI": "Liechtenstein",
    "LT": "Lithuania",
    "LU": "Luxembourg",
    "LV": "Latvia",
    "MT": "Malta",
    "NL": "Netherlands",
    "NO": "Norway",
    "PL": "Poland",
    "PT": "Portugal",
    "RO": "Romania",
    "SE": "Sweden",
    "SI": "Slovenia",
    "SK": "Slovakia",
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


def parse_countries(country_str: str) -> list[str]:
    """
    Parse a country string which may contain multiple country codes.
    
    Args:
        country_str: String like "GB", "SE NO FI DK", or "DE EEA"
        
    Returns:
        List of valid two-letter country codes
    """
    if not country_str:
        return []
    
    # Split by spaces and filter valid codes
    parts = country_str.strip().upper().split()
    countries = []
    
    for part in parts:
        # Skip non-country strings like "EEA", "ALL", etc.
        if part in VALID_COUNTRY_CODES and part != "XX":
            countries.append(part)
    
    return countries


def load_json(path: Path) -> dict:
    """Load a JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: dict) -> None:
    """Save data to a JSON file with consistent formatting."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
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
    suffixes = ['-bank', '-financial', '-credit-union', '-savings', '-trust', '-plc', '-limited', '-ltd', '-group', '-ag', '-sa', '-nv']
    country_suffixes = ['-gb', '-de', '-fr', '-nl', '-es', '-it', '-ie', '-be', '-at', '-se', '-dk', '-no', '-fi', '-pl', '-pt']
    
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
        bank_id.replace('-bank', ''),
    ]
    for var in variations:
        if var in existing_ids:
            return var
    
    return None


def create_account_provider(institution: dict) -> dict:
    """
    Create a new account provider entry from institution data.
    
    Args:
        institution: Dictionary with institution information
        
    Returns:
        A dictionary representing the account provider
    """
    name = institution.get("name", "Unknown")
    bank_id = slugify(name)
    countries = institution.get("countries", [])
    country = countries[0] if countries else "GB"
    swift = institution.get("swift", "")
    
    provider = {
        "id": bank_id,
        "type": ["account"],
        "bankType": ["retail"],
        "name": name,
        "legalName": name,
        "verified": False,
        "status": "live",
        "icon": f"https://icons.duckduckgo.com/ip3/www.{bank_id}.com.ico",
        "websiteUrl": None,
        "countryHQ": country,
        "countries": countries if countries else [country],
        "webApplication": True,
        "mobileApps": [],
        "compliance": [],
        "developerPortalUrl": None,
        "apiStandards": [],
        "apiProducts": [],
        "apiAggregators": ["gocardless"],
        "ownership": [],
        "stateOwned": False,
        "stockSymbol": None
    }
    
    # Add BIC/SWIFT code if available
    if swift:
        provider["bic"] = swift
    
    return provider


def add_gocardless_to_existing_provider(provider_path: Path, bic_code: str = None) -> tuple[bool, bool]:
    """
    Add 'gocardless' to an existing provider's apiAggregators list and optionally add BIC code.
    
    Args:
        provider_path: Path to the provider JSON file
        bic_code: Optional SWIFT/BIC code to add if not present
        
    Returns:
        Tuple of (aggregator_modified, bic_modified)
    """
    provider = load_json(provider_path)
    aggregator_modified = False
    bic_modified = False
    
    # Add gocardless to aggregators
    aggregators = provider.get("apiAggregators", [])
    if aggregators is None:
        aggregators = []
    
    if "gocardless" not in aggregators:
        aggregators.append("gocardless")
        aggregators.sort()
        provider["apiAggregators"] = aggregators
        aggregator_modified = True
    
    # Add BIC code if not present and we have one
    if bic_code and not provider.get("bic"):
        provider["bic"] = bic_code
        bic_modified = True
    
    if aggregator_modified or bic_modified:
        save_json(provider_path, provider)
    
    return aggregator_modified, bic_modified


def parse_csv_file(csv_path: Path) -> dict[str, list[dict]]:
    """
    Parse the GoCardless coverage CSV file.
    
    CSV columns:
    0: Bank Name (first column, no header in data)
    1: SWIFT
    2: Countries
    3: Maximum Transaction History
    4: GoCardless account selection
    5: Pending Transactions
    6: Private Accounts
    7: Business Accounts
    8: Corporate Accounts
    9: Institution_id
    10: Unique aspects of bank
    11: Banks status
    
    Args:
        csv_path: Path to the CSV file
        
    Returns:
        Dictionary mapping country codes to lists of institution data
    """
    print(f"\n=== Parsing CSV file: {csv_path} ===\n")
    
    all_institutions = {}
    seen_institutions = set()  # Track by institution_id to avoid duplicates
    row_count = 0
    skipped_count = 0
    
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        
        # Skip header row
        header = next(reader, None)
        
        for row in reader:
            row_count += 1
            
            if len(row) < 10:
                skipped_count += 1
                continue
            
            name = row[0].strip()
            swift = row[1].strip()
            country_str = row[2].strip()
            institution_id = row[9].strip() if len(row) > 9 else ""
            
            # Skip rows without a name or institution_id
            if not name or not institution_id:
                skipped_count += 1
                continue
            
            # Skip if we've already seen this institution
            if institution_id in seen_institutions:
                continue
            seen_institutions.add(institution_id)
            
            # Parse countries
            countries = parse_countries(country_str)
            
            # If no valid countries found, skip
            if not countries:
                skipped_count += 1
                continue
            
            institution = {
                "name": name,
                "swift": swift,
                "countries": countries,
                "institution_id": institution_id,
            }
            
            # Add to each country's list
            for country in countries:
                if country not in all_institutions:
                    all_institutions[country] = []
                all_institutions[country].append(institution)
    
    # Print summary
    total_unique = len(seen_institutions)
    print(f"  Processed {row_count} rows")
    print(f"  Skipped {skipped_count} invalid rows")
    print(f"  Found {total_unique} unique institutions")
    print(f"  Across {len(all_institutions)} countries")
    
    # Print per-country breakdown
    print("\n  Institutions per country:")
    for country in sorted(all_institutions.keys()):
        country_name = COUNTRY_NAMES.get(country, country)
        count = len(all_institutions[country])
        print(f"    {country} ({country_name}): {count}")
    
    return all_institutions


def update_gocardless_coverage(country_codes: list[str]) -> None:
    """
    Update gocardless.json with market coverage.
    
    Args:
        country_codes: List of country codes where GoCardless has coverage
    """
    print("\n=== Updating GoCardless Market Coverage ===\n")
    
    # Filter out XX (sandbox) from market coverage
    country_codes = [c for c in country_codes if c != "XX"]
    
    print(f"Found {len(country_codes)} countries: {', '.join(sorted(country_codes))}")
    
    # Load and update gocardless.json
    gocardless_data = load_json(GOCARDLESS_JSON_PATH)
    existing_coverage = gocardless_data.get("marketCoverage", {}).get("live", [])
    
    gocardless_data["marketCoverage"] = {"live": sorted(country_codes)}
    save_json(GOCARDLESS_JSON_PATH, gocardless_data)
    
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


def update_bank_providers(all_institutions: dict[str, list[dict]]) -> None:
    """
    Create/update account providers from parsed institution data.
    
    Args:
        all_institutions: Dictionary mapping country codes to lists of institution data
    """
    print("\n=== Updating Bank Providers ===\n")
    
    # Get unique institutions (they may appear in multiple countries)
    unique_institutions = {}
    for country_code, institutions in all_institutions.items():
        for inst in institutions:
            inst_id = inst.get("institution_id")
            if inst_id and inst_id not in unique_institutions:
                unique_institutions[inst_id] = inst
    
    print(f"Processing {len(unique_institutions)} unique institutions...")
    
    # Get existing provider IDs
    existing_ids = get_existing_provider_ids()
    print(f"Found {len(existing_ids)} existing account providers")
    
    # Track statistics
    new_count = 0
    updated_aggregator_count = 0
    updated_bic_count = 0
    skipped_count = 0
    
    # Process all institutions
    for inst_id, institution in unique_institutions.items():
        name = institution.get("name", "")
        if not name:
            continue
            
        bank_id = slugify(name)
        bic_code = institution.get("swift", "")
        
        if not bank_id:
            continue
        
        # Try to find a matching existing provider
        matching_id = find_matching_provider(bank_id, existing_ids)
        
        if matching_id:
            # Add GoCardless to existing provider's aggregators and optionally BIC
            provider_path = ACCOUNT_PROVIDERS_PATH / f"{matching_id}.json"
            aggregator_modified, bic_modified = add_gocardless_to_existing_provider(provider_path, bic_code)
            
            if aggregator_modified or bic_modified:
                updates = []
                if aggregator_modified:
                    updates.append("gocardless")
                    updated_aggregator_count += 1
                if bic_modified:
                    updates.append(f"bic={bic_code}")
                    updated_bic_count += 1
                
                if matching_id != bank_id:
                    print(f"  Updated: {name} -> {matching_id}.json (added {', '.join(updates)})")
                else:
                    print(f"  Updated: {name} (added {', '.join(updates)})")
            else:
                skipped_count += 1
        else:
            # Create new provider
            provider_path = ACCOUNT_PROVIDERS_PATH / f"{bank_id}.json"
            provider = create_account_provider(institution)
            save_json(provider_path, provider)
            existing_ids.add(bank_id)
            new_count += 1
            bic_info = f", bic={bic_code}" if bic_code else ""
            print(f"  Created: {name} ({bank_id}.json{bic_info})")
    
    print(f"\nSummary:")
    print(f"  {new_count} new providers created")
    print(f"  {updated_aggregator_count} updated with gocardless aggregator")
    print(f"  {updated_bic_count} updated with BIC code")
    print(f"  {skipped_count} already had gocardless (no changes needed)")


def save_scraped_data(all_institutions: dict[str, list[dict]]) -> None:
    """
    Save all scraped data to a JSON file for reference.
    
    Args:
        all_institutions: Dictionary mapping country codes to lists of institution data
    """
    SCRAPED_DATA_PATH.mkdir(parents=True, exist_ok=True)
    
    output = {
        "source": "GoCardless Bank Account Data Coverage Overview spreadsheet",
        "source_url": "https://docs.google.com/spreadsheets/d/1EZ5n7QDGaRIot5M86dwqd5UFSGEDTeTRzEq3D9uEDkM/",
        "scraped_at": datetime.now().isoformat(),
        "markets": {}
    }
    
    for country_code in sorted(all_institutions.keys()):
        institutions = all_institutions[country_code]
        output["markets"][country_code] = {
            "country_name": COUNTRY_NAMES.get(country_code, country_code),
            "institution_count": len(institutions),
            "institutions": [
                {
                    "name": inst.get("name"),
                    "institution_id": inst.get("institution_id"),
                    "swift": inst.get("swift"),
                }
                for inst in institutions
            ]
        }
    
    output_path = SCRAPED_DATA_PATH / "gocardless-coverage.json"
    save_json(output_path, output)
    print(f"\nSaved scraped data to {output_path}")
    
    # Also save institution ID mappings for reference
    id_mappings = {}
    for country_code, institutions in all_institutions.items():
        for inst in institutions:
            gocardless_id = inst.get("institution_id")
            name = inst.get("name", "")
            if gocardless_id and name:
                bank_id = slugify(name)
                if bank_id not in id_mappings:
                    id_mappings[bank_id] = {
                        "gocardless_id": gocardless_id,
                        "name": name,
                        "countries": inst.get("countries", []),
                        "swift": inst.get("swift"),
                    }
    
    mappings_path = SCRAPED_DATA_PATH / "gocardless-institution-ids.json"
    save_json(mappings_path, id_mappings)
    print(f"Saved institution ID mappings to {mappings_path}")


def main():
    """Main entry point with argument parsing."""
    parser = argparse.ArgumentParser(
        description="Parse GoCardless Bank Account Data Coverage spreadsheet",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Parse from downloaded CSV file
    python gocardless_scraper.py --csv-file ~/Downloads/coverage.csv
    
    # Use default CSV location
    python gocardless_scraper.py
    
    # Only update market coverage (no provider updates)
    python gocardless_scraper.py --coverage-only
    
    # Show what would be done without making changes
    python gocardless_scraper.py --dry-run

Data Source:
    Download the CSV from:
    https://docs.google.com/spreadsheets/d/1EZ5n7QDGaRIot5M86dwqd5UFSGEDTeTRzEq3D9uEDkM/
    
    File > Download > Comma-separated values (.csv)
        """
    )
    parser.add_argument(
        "--csv-file",
        type=str,
        default=str(DEFAULT_CSV_PATH),
        help=f"Path to the CSV file (default: {DEFAULT_CSV_PATH})"
    )
    parser.add_argument(
        "--coverage-only",
        action="store_true",
        help="Only update market coverage in gocardless.json, skip provider updates"
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
    print("GoCardless Bank Account Data Scraper")
    print("=" * 60)
    
    csv_path = Path(args.csv_file)
    
    if not csv_path.exists():
        print(f"\nError: CSV file not found: {csv_path}")
        print("\nPlease download the CSV from:")
        print("https://docs.google.com/spreadsheets/d/1EZ5n7QDGaRIot5M86dwqd5UFSGEDTeTRzEq3D9uEDkM/")
        print("\nFile > Download > Comma-separated values (.csv)")
        return
    
    # Parse the CSV file
    all_institutions = parse_csv_file(csv_path)
    
    if not all_institutions:
        print("\nNo institution data found in CSV file.")
        return
    
    country_codes = list(all_institutions.keys())
    
    # Update gocardless.json with market coverage
    if not args.dry_run:
        update_gocardless_coverage(country_codes)
    else:
        filtered = [c for c in country_codes if c != "XX"]
        print(f"\n[DRY RUN] Would update market coverage with {len(filtered)} countries")
    
    # Save scraped data for reference
    if not args.dry_run:
        save_scraped_data(all_institutions)
    else:
        total = sum(len(inst) for inst in all_institutions.values())
        print(f"[DRY RUN] Would save data for {total} institution entries")
    
    # Update bank providers (unless skipped)
    if not args.skip_providers and not args.coverage_only:
        if not args.dry_run:
            update_bank_providers(all_institutions)
        else:
            print(f"[DRY RUN] Would process bank providers")
    else:
        print("\nSkipping provider updates.")
    
    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)


if __name__ == "__main__":
    main()
