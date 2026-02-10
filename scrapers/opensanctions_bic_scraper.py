#!/usr/bin/env python3
"""
OpenSanctions BIC Scraper

This script backfills missing banks from the OpenSanctions ISO 9362 BIC dataset.
It downloads the bulk data file and creates/updates account providers.

Source: https://www.opensanctions.org/datasets/iso9362_bic/
License: CC BY-NC 4.0 (non-commercial use)

Usage:
    python opensanctions_bic_scraper.py [--dry-run] [--limit N] [--banks-only]

Options:
    --dry-run     Show what would be done without making changes
    --limit N     Process only first N entities (for testing)
    --update      Only update existing providers with missing BICs (don't create new)
    --banks-only  Only include entities that appear to be banks (recommended)
    --all         Include all entities with BIC codes (corporations, asset managers, etc.)
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

# Paths
BASE_PATH = Path(__file__).parent.parent
ACCOUNT_PROVIDERS_PATH = BASE_PATH / "data" / "account-providers"
SCRAPED_DATA_PATH = BASE_PATH / "scraped-data"

# OpenSanctions data URL
# Note: Date in URL changes, but this redirects to latest
OPENSANCTIONS_URL = "https://data.opensanctions.org/datasets/latest/iso9362_bic/entities.ftm.json"

# BIC validation pattern
BIC_PATTERN = re.compile(r'^[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?$')

# Patterns to identify banks by name (case-insensitive)
BANK_NAME_PATTERNS = [
    r'\bbank\b', r'\bbanc[ao]?\b', r'\bbanque\b', r'\bbanka\b',
    r'\bsparkasse\b', r'\braiffeisen\b', r'\bvolksbank\b',
    r'\bcredit union\b', r'\bcaisse\b', r'\bcaja\b',
    r'\bsavings\b', r'\bbuilding society\b',
    r'\bbausparkasse\b', r'\blandesbank\b',
    r'\bcreditbank\b', r'\bsparebank\b',
    r'\bcoop[eé]rative? de cr[eé]dit\b',
    r'\bcr[eé]dit mutuel\b', r'\bcr[eé]dit agricole\b',
    r'\bbcc\b',  # Banche di Credito Cooperativo
]
BANK_NAME_REGEX = re.compile('|'.join(BANK_NAME_PATTERNS), re.IGNORECASE)

# Patterns to exclude (not banks, even if they have "bank" in name)
EXCLUDE_PATTERNS = [
    r'\bfood bank\b', r'\bblood bank\b', r'\bdata bank\b',
    r'\bworld bank\b', r'\bcentral bank\b',  # International/regulatory bodies
]
EXCLUDE_REGEX = re.compile('|'.join(EXCLUDE_PATTERNS), re.IGNORECASE)

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
    """Convert a name to a slug for use as provider ID."""
    slug = name
    for char, replacement in TRANSLITERATIONS.items():
        slug = slug.replace(char, replacement)
        slug = slug.replace(char.upper(), replacement)
    slug = slug.lower()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'\s+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug.strip('-')[:80]  # Limit length


def is_valid_bic(bic: str) -> bool:
    """Validate BIC format."""
    return bool(BIC_PATTERN.match(bic))


def is_likely_bank(name: str) -> bool:
    """Check if the entity name suggests it's a bank."""
    if EXCLUDE_REGEX.search(name):
        return False
    return bool(BANK_NAME_REGEX.search(name))


def download_data() -> Optional[str]:
    """Download the OpenSanctions BIC data file."""
    print(f"Downloading data from OpenSanctions...")
    print(f"  URL: {OPENSANCTIONS_URL}")

    # Create temp file
    temp_file = SCRAPED_DATA_PATH / "opensanctions_bic_data.json"
    SCRAPED_DATA_PATH.mkdir(exist_ok=True)

    try:
        result = subprocess.run(
            ["curl", "-s", "-L", "-o", str(temp_file), OPENSANCTIONS_URL],
            capture_output=True,
            text=True,
            timeout=300  # 5 min timeout for large file
        )

        if result.returncode != 0:
            print(f"  Error downloading: {result.stderr}")
            return None

        file_size = temp_file.stat().st_size / (1024 * 1024)
        print(f"  Downloaded {file_size:.1f} MB")
        return str(temp_file)

    except Exception as e:
        print(f"  Error: {e}")
        return None


def load_existing_providers() -> tuple[dict, dict]:
    """
    Load existing providers and build lookup indexes.
    Returns (providers_by_id, providers_by_bic)
    """
    providers_by_id = {}
    providers_by_bic = {}

    for json_file in ACCOUNT_PROVIDERS_PATH.glob("*.json"):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                provider = json.load(f)
                provider_id = json_file.stem
                providers_by_id[provider_id] = provider

                # Index by BIC if present
                bic = provider.get('bic')
                if bic and is_valid_bic(bic):
                    providers_by_bic[bic] = provider_id
        except Exception as e:
            print(f"  Warning: Failed to load {json_file}: {e}")

    return providers_by_id, providers_by_bic


def parse_entity(line: str) -> Optional[dict]:
    """Parse a single entity line from the data file."""
    try:
        entity = json.loads(line.strip())
        props = entity.get('properties', {})

        # Extract BIC codes
        bics = props.get('swiftBic', [])
        if not bics:
            return None

        # Filter valid BICs
        valid_bics = [b for b in bics if is_valid_bic(b)]
        if not valid_bics:
            return None

        # Extract country (use first one, uppercase)
        countries = props.get('country', [])
        country = countries[0].upper() if countries else None

        # Get name
        names = props.get('name', [])
        name = names[0] if names else entity.get('caption', '')

        if not name:
            return None

        return {
            'name': name,
            'bics': valid_bics,
            'country': country,
            'address': props.get('address', []),
        }
    except Exception:
        return None


def create_provider(entity: dict, bic: str) -> dict:
    """Create a new provider entry from OpenSanctions entity."""
    name = entity['name']
    country = entity['country'] or 'XX'

    # Generate provider ID
    provider_id = slugify(name)
    if country and country != 'XX':
        # Add country suffix if not already present
        country_lower = country.lower()
        if not provider_id.endswith(f'-{country_lower}'):
            provider_id = f"{provider_id}-{country_lower}"

    return {
        "id": provider_id,
        "type": ["account"],
        "bankType": ["retail"],
        "name": name,
        "legalName": name,
        "verified": False,
        "status": "live",
        "icon": f"https://icons.duckduckgo.com/ip3/www.{slugify(name)}.com.ico",
        "websiteUrl": None,
        "countryHQ": country,
        "countries": [country] if country else [],
        "webApplication": True,
        "mobileApps": [],
        "compliance": [],
        "developerPortalUrl": None,
        "apiStandards": [],
        "apiProducts": [],
        "apiAggregators": [],
        "ownership": [],
        "stateOwned": False,
        "stockSymbol": None,
        "bic": bic
    }


def save_provider(provider: dict) -> None:
    """Save a provider to disk."""
    provider_id = provider['id']
    path = ACCOUNT_PROVIDERS_PATH / f"{provider_id}.json"
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(provider, f, indent=2)
        f.write('\n')


def main():
    """Main entry point."""
    print("=" * 60)
    print("OpenSanctions BIC Scraper")
    print("=" * 60)

    # Parse arguments
    args = sys.argv[1:]
    dry_run = '--dry-run' in args
    update_only = '--update' in args
    banks_only = '--banks-only' in args or '--all' not in args  # Default to banks-only
    include_all = '--all' in args
    limit = None
    if '--limit' in args:
        idx = args.index('--limit')
        if idx + 1 < len(args):
            limit = int(args[idx + 1])

    if dry_run:
        print("\n*** DRY RUN - No files will be modified ***\n")

    if banks_only and not include_all:
        print("Filter: Banks only (use --all to include all entities)\n")
    else:
        print("Filter: All entities with BIC codes\n")

    # Download data
    data_file = download_data()
    if not data_file:
        print("Failed to download data. Exiting.")
        return 1

    # Load existing providers
    print("\nLoading existing providers...")
    providers_by_id, providers_by_bic = load_existing_providers()
    print(f"  Found {len(providers_by_id)} existing providers")
    print(f"  Found {len(providers_by_bic)} providers with BIC codes")

    # Process entities
    print("\nProcessing OpenSanctions entities...")

    stats = {
        'total': 0,
        'skipped_no_bic': 0,
        'skipped_not_bank': 0,
        'already_exists': 0,
        'updated_bic': 0,
        'created': 0,
        'skipped_duplicate_id': 0,
    }

    new_provider_ids = set()  # Track newly created IDs to avoid duplicates

    with open(data_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            if limit and stats['total'] >= limit:
                break

            entity = parse_entity(line)
            if not entity:
                stats['skipped_no_bic'] += 1
                continue

            # Filter to banks only if requested (default)
            if banks_only and not include_all:
                if not is_likely_bank(entity['name']):
                    stats['skipped_not_bank'] += 1
                    continue

            stats['total'] += 1

            # Use primary BIC (first valid one)
            primary_bic = entity['bics'][0]

            # Check if BIC already exists
            if primary_bic in providers_by_bic:
                stats['already_exists'] += 1
                continue

            # Check if we can update an existing provider by name match
            provider_id = slugify(entity['name'])
            country = entity['country']
            if country:
                provider_id_with_country = f"{provider_id}-{country.lower()}"
            else:
                provider_id_with_country = provider_id

            # Try to find existing provider
            existing_id = None
            for try_id in [provider_id, provider_id_with_country]:
                if try_id in providers_by_id:
                    existing_id = try_id
                    break

            if existing_id:
                # Update existing provider with BIC if missing
                provider = providers_by_id[existing_id]
                if not provider.get('bic'):
                    if not dry_run:
                        provider['bic'] = primary_bic
                        save_provider(provider)
                    print(f"  Updated: {existing_id} <- BIC: {primary_bic}")
                    stats['updated_bic'] += 1
                    providers_by_bic[primary_bic] = existing_id
                else:
                    stats['already_exists'] += 1
                continue

            # Skip if update-only mode
            if update_only:
                continue

            # Create new provider
            new_provider = create_provider(entity, primary_bic)
            new_id = new_provider['id']

            # Ensure unique ID
            if new_id in providers_by_id or new_id in new_provider_ids:
                # Add BIC suffix to make unique
                new_id = f"{new_id}-{primary_bic.lower()}"
                new_provider['id'] = new_id

                if new_id in providers_by_id or new_id in new_provider_ids:
                    stats['skipped_duplicate_id'] += 1
                    continue

            if not dry_run:
                save_provider(new_provider)

            new_provider_ids.add(new_id)
            providers_by_bic[primary_bic] = new_id
            print(f"  Created: {new_id} ({entity['name'][:40]}...) BIC: {primary_bic}")
            stats['created'] += 1

            # Progress indicator
            if stats['total'] % 5000 == 0:
                print(f"  ... processed {stats['total']} entities ...")

    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"  Total entities processed: {stats['total']}")
    print(f"  Skipped (no valid BIC):   {stats['skipped_no_bic']}")
    if banks_only and not include_all:
        print(f"  Skipped (not a bank):     {stats['skipped_not_bank']}")
    print(f"  Already exists:           {stats['already_exists']}")
    print(f"  Updated with BIC:         {stats['updated_bic']}")
    print(f"  Created new:              {stats['created']}")
    print(f"  Skipped (duplicate ID):   {stats['skipped_duplicate_id']}")

    if dry_run:
        print("\n*** DRY RUN - No files were modified ***")

    print("\nDone!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
