#!/usr/bin/env python3
"""
Plaid Coverage Scraper

This script updates Plaid's coverage and bank providers.

REQUIREMENTS:
- Plaid API credentials (set via environment variables):
  - PLAID_CLIENT_ID
  - PLAID_SECRET
  - PLAID_ENV (optional, defaults to 'production')

Without credentials, only country-level coverage is updated.
With credentials, bank-level data is fetched and providers are created/updated.

Sources:
- https://plaid.com/docs/api/institutions/
- https://support.plaid.com/hc/en-us/articles/27895826947735
"""

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup

# Load .env file if it exists
ENV_FILE = Path(__file__).parent / ".env"
if ENV_FILE.exists():
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


# URLs
PLAID_PRODUCTS_URL = "https://support.plaid.com/hc/en-us/articles/27895826947735-What-Plaid-products-are-supported-in-each-country-and-region"
PLAID_API_URL = "https://production.plaid.com"
PLAID_SANDBOX_URL = "https://sandbox.plaid.com"

# Paths
BASE_PATH = Path(__file__).parent.parent
PLAID_JSON_PATH = BASE_PATH / "data" / "api-aggregators" / "plaid.json"
ACCOUNT_PROVIDERS_PATH = BASE_PATH / "data" / "account-providers"
PLAID_INSTITUTION_IDS_PATH = Path(__file__).parent / "plaid_institution_ids.json"

# Request settings
REQUEST_TIMEOUT = 30

# Plaid sandbox test institutions to skip (not real banks)
# See: https://plaid.com/docs/sandbox/institutions/
PLAID_TEST_INSTITUTION_IDS = {
    "ins_109508",  # First Platypus Bank
    "ins_109509",  # First Gingham Credit Union
    "ins_109510",  # Tattersall Federal Credit Union
    "ins_109511",  # Tartan Bank
    "ins_109512",  # Houndstooth Bank
    "ins_43",      # Tartan-Dominion Bank of Canada
    "ins_116834",  # Flexible Platypus Open Banking
    "ins_117650",  # Royal Bank of Plaid
    "ins_127287",  # Platypus OAuth Bank
    "ins_132241",  # First Platypus OAuth App2App Bank
    "ins_117181",  # Flexible Platypus Open Banking (QR)
    "ins_135858",  # Windowpane Bank
    "ins_132363",  # Unhealthy Platypus Bank - Degraded
    "ins_132361",  # Unhealthy Platypus Bank - Down
    "ins_133402",  # Unsupported Platypus Bank
    "ins_133502",  # Platypus Bank RUX Auth
    "ins_133503",  # Platypus Bank RUX Match
}

# Patterns to identify test institutions by name
PLAID_TEST_NAME_PATTERNS = [
    "platypus",
    "plaidypus",
    "gingham",
    "tattersall federal",
    "tartan bank",
    "tartan-dominion",
    "tartan finance",
    "tartan no products",
    "houndstooth",
    "windowpane",
    "royal bank of plaid",
    "plaid-partner",
]

# Plaid country coverage
PLAID_COUNTRIES = {
    "US": "United States",
    "CA": "Canada",
    "AT": "Austria",
    "BE": "Belgium",
    "DE": "Germany",
    "DK": "Denmark",
    "EE": "Estonia",
    "ES": "Spain",
    "FI": "Finland",
    "FR": "France",
    "GB": "United Kingdom",
    "IE": "Ireland",
    "IT": "Italy",
    "LT": "Lithuania",
    "LV": "Latvia",
    "NL": "Netherlands",
    "NO": "Norway",
    "PL": "Poland",
    "PT": "Portugal",
    "SE": "Sweden",
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
    """Convert a name to a slug."""
    slug = name
    for char, replacement in TRANSLITERATIONS.items():
        slug = slug.replace(char, replacement)
        slug = slug.replace(char.upper(), replacement)
    slug = slug.lower()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'\s+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug.strip('-')


def fetch_url(url: str) -> Optional[str]:
    """Fetch content from a URL using curl."""
    print(f"Fetching {url}...")
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


def plaid_api_request(endpoint: str, data: dict) -> Optional[dict]:
    """Make a request to Plaid API."""
    client_id = os.environ.get("PLAID_CLIENT_ID")
    secret = os.environ.get("PLAID_SECRET")
    env = os.environ.get("PLAID_ENV", "production")
    
    if not client_id or not secret:
        return None
    
    base_url = PLAID_SANDBOX_URL if env == "sandbox" else PLAID_API_URL
    url = f"{base_url}{endpoint}"
    
    payload = {
        "client_id": client_id,
        "secret": secret,
        **data
    }
    
    print(f"  API request to {endpoint}...")
    try:
        result = subprocess.run(
            [
                "curl", "-s", "-X", "POST", url,
                "-H", "Content-Type: application/json",
                "-d", json.dumps(payload)
            ],
            capture_output=True,
            text=True,
            timeout=REQUEST_TIMEOUT
        )
        if result.returncode == 0 and result.stdout:
            return json.loads(result.stdout)
        return None
    except Exception as e:
        print(f"  Warning: API request failed: {e}")
        return None


def get_plaid_institutions() -> list[dict]:
    """
    Fetch all institutions from Plaid API.
    
    Returns a list of institution dictionaries with:
    - institution_id
    - name
    - country_codes
    - url (website)
    - logo (base64)
    """
    institutions = []
    
    # Check for credentials
    if not os.environ.get("PLAID_CLIENT_ID"):
        print("  No PLAID_CLIENT_ID set. Skipping institution fetch.")
        print("  Set PLAID_CLIENT_ID and PLAID_SECRET to fetch bank data.")
        return institutions
    
    print("Fetching institutions from Plaid API...")
    
    # Fetch institutions for each country
    for country_code in PLAID_COUNTRIES.keys():
        offset = 0
        count = 500  # Max per request
        
        while True:
            response = plaid_api_request("/institutions/get", {
                "count": count,
                "offset": offset,
                "country_codes": [country_code],
                "options": {
                    "include_optional_metadata": True
                }
            })
            
            if not response or "institutions" not in response:
                if response and "error_code" in response:
                    print(f"  Error for {country_code}: {response.get('error_message', 'Unknown error')}")
                break
            
            batch = response["institutions"]
            if not batch:
                break
            
            institutions.extend(batch)
            print(f"  {country_code}: Fetched {len(batch)} institutions (total: {len(institutions)})")
            
            # Check if there are more
            total = response.get("total", 0)
            offset += len(batch)
            if offset >= total:
                break
            
            time.sleep(0.5)  # Rate limiting
    
    return institutions


def load_json(path: Path) -> dict:
    """Load a JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: dict) -> None:
    """Save data to a JSON file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def get_existing_provider_ids() -> set[str]:
    """Get the set of existing account provider IDs."""
    provider_ids = set()
    for json_file in ACCOUNT_PROVIDERS_PATH.glob("*.json"):
        provider_ids.add(json_file.stem)
    return provider_ids


def find_matching_provider(bank_id: str, existing_ids: set[str]) -> Optional[str]:
    """Find an existing provider ID that matches the given bank ID."""
    if bank_id in existing_ids:
        return bank_id
    
    suffixes = ['-bank', '-business', '-corporate', '-retail', '-sa', '-ag', '-nv', '-plc', '-ltd']
    country_suffixes = ['-gb', '-uk', '-nl', '-de', '-fr', '-es', '-it', '-be', '-at', '-ie', '-us', '-ca']
    
    # Try removing suffixes
    for suffix in country_suffixes + suffixes:
        if bank_id.endswith(suffix):
            base_id = bank_id[:-len(suffix)]
            if base_id in existing_ids:
                return base_id
    
    # Try adding suffixes
    for suffix in suffixes:
        if f"{bank_id}{suffix}" in existing_ids:
            return f"{bank_id}{suffix}"
    
    return None


def load_plaid_institution_ids() -> dict:
    """Load the Plaid institution ID mappings."""
    if PLAID_INSTITUTION_IDS_PATH.exists():
        with open(PLAID_INSTITUTION_IDS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_plaid_institution_ids(mappings: dict) -> None:
    """Save the Plaid institution ID mappings."""
    with open(PLAID_INSTITUTION_IDS_PATH, "w", encoding="utf-8") as f:
        json.dump(mappings, f, indent=2)
        f.write("\n")


def create_account_provider(institution: dict) -> dict:
    """Create a new account provider entry from Plaid institution data."""
    name = institution.get("name", "Unknown")
    bank_id = slugify(name)
    countries = institution.get("country_codes", ["US"])
    country_hq = countries[0] if countries else "US"
    
    provider = {
        "id": bank_id,
        "type": ["account"],
        "bankType": ["retail"],
        "name": name,
        "legalName": name,
        "verified": False,
        "status": "live",
        "icon": f"https://icons.duckduckgo.com/ip3/www.{bank_id}.com.ico",
        "websiteUrl": institution.get("url"),
        "countryHQ": country_hq,
        "countries": countries,
        "webApplication": True,
        "mobileApps": [],
        "compliance": [],
        "developerPortalUrl": None,
        "apiStandards": [],
        "apiProducts": [],
        "apiAggregators": ["plaid"],
        "ownership": [],
        "stateOwned": False,
        "stockSymbol": None
    }
    
    return provider


def add_plaid_to_existing_provider(provider_path: Path) -> bool:
    """Add 'plaid' to an existing provider's apiAggregators list."""
    provider = load_json(provider_path)
    
    aggregators = provider.get("apiAggregators", [])
    if aggregators is None:
        aggregators = []
    
    if "plaid" not in aggregators:
        aggregators.append("plaid")
        aggregators.sort()
        provider["apiAggregators"] = aggregators
        save_json(provider_path, provider)
        return True
    
    return False


def update_plaid_coverage() -> None:
    """Update plaid.json with market coverage."""
    print("\n=== Updating Plaid Market Coverage ===\n")
    
    country_codes = sorted(PLAID_COUNTRIES.keys())
    print(f"Coverage: {len(country_codes)} countries: {', '.join(country_codes)}")
    
    plaid_data = load_json(PLAID_JSON_PATH)
    existing_coverage = plaid_data.get("marketCoverage", {}).get("live", [])
    
    plaid_data["marketCoverage"] = {"live": country_codes}
    save_json(PLAID_JSON_PATH, plaid_data)
    
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


def update_bank_providers() -> None:
    """Fetch bank data from Plaid API and create/update account providers."""
    print("\n=== Updating Bank Providers ===\n")
    
    institutions = get_plaid_institutions()
    
    if not institutions:
        print("No institutions fetched. Skipping provider updates.")
        return
    
    print(f"Processing {len(institutions)} institutions...")
    
    existing_ids = get_existing_provider_ids()
    print(f"Found {len(existing_ids)} existing account providers")
    
    # Load existing Plaid institution ID mappings
    plaid_id_mappings = load_plaid_institution_ids()
    
    new_count = 0
    updated_count = 0
    skipped_count = 0
    
    skipped_test = 0
    for institution in institutions:
        name = institution.get("name", "")
        if not name:
            continue
        
        # Skip test institutions
        inst_id = institution.get("institution_id", "")
        if inst_id in PLAID_TEST_INSTITUTION_IDS:
            skipped_test += 1
            continue
        
        # Skip by name pattern
        name_lower = name.lower()
        if any(pattern in name_lower for pattern in PLAID_TEST_NAME_PATTERNS):
            skipped_test += 1
            continue
        
        bank_id = slugify(name)
        matching_id = find_matching_provider(bank_id, existing_ids)
        
        if matching_id:
            provider_path = ACCOUNT_PROVIDERS_PATH / f"{matching_id}.json"
            if add_plaid_to_existing_provider(provider_path):
                updated_count += 1
                if matching_id != bank_id:
                    print(f"  Updated: {name} -> {matching_id}.json (added plaid)")
                else:
                    print(f"  Updated: {name} (added plaid)")
            else:
                skipped_count += 1
            # Save institution ID mapping
            if inst_id:
                plaid_id_mappings[matching_id] = inst_id
        else:
            provider_path = ACCOUNT_PROVIDERS_PATH / f"{bank_id}.json"
            provider = create_account_provider(institution)
            save_json(provider_path, provider)
            existing_ids.add(bank_id)
            new_count += 1
            print(f"  Created: {name} ({bank_id}.json)")
            # Save institution ID mapping
            if inst_id:
                plaid_id_mappings[bank_id] = inst_id
    
    # Save updated institution ID mappings
    save_plaid_institution_ids(plaid_id_mappings)
    print(f"Saved {len(plaid_id_mappings)} Plaid institution ID mappings")
    
    print(f"\nSummary: {new_count} new, {updated_count} updated, {skipped_count} already had plaid, {skipped_test} test institutions skipped")


def main():
    """Main entry point."""
    print("=" * 60)
    print("Plaid Coverage Scraper")
    print("=" * 60)
    
    # Check for API credentials
    has_credentials = bool(os.environ.get("PLAID_CLIENT_ID"))
    if has_credentials:
        print("\nPlaid API credentials detected.")
    else:
        print("\nNo Plaid API credentials found.")
        print("Set PLAID_CLIENT_ID and PLAID_SECRET to fetch bank data.")
    
    # Update market coverage (always)
    update_plaid_coverage()
    
    # Update bank providers (if credentials available)
    if has_credentials:
        update_bank_providers()
    
    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)


if __name__ == "__main__":
    main()