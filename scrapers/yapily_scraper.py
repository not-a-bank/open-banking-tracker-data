#!/usr/bin/env python3
"""
Yapily Coverage Scraper

This script updates Yapily's coverage and bank providers.

REQUIREMENTS:
- Yapily API credentials (set via environment variables):
  - YAPILY_APPLICATION_UUID
  - YAPILY_SECRET

Without credentials, the script will not run.
With credentials, institutions are fetched and providers are created/updated.

Sources:
- https://docs.yapily.com/api/reference/#tag/Institutions
- https://api.yapily.com/institutions

Yapily covers banks across Europe and other regions.
"""

import argparse
import base64
import json
import os
import re
import time
from pathlib import Path
from typing import Optional

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    import subprocess

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
YAPILY_API_URL = "https://api.yapily.com"

# Paths
BASE_PATH = Path(__file__).parent.parent
YAPILY_JSON_PATH = BASE_PATH / "data" / "api-aggregators" / "yapily.json"
ACCOUNT_PROVIDERS_PATH = BASE_PATH / "data" / "account-providers"
YAPILY_INSTITUTION_IDS_PATH = Path(__file__).parent / "yapily_institution_ids.json"

# Request settings
REQUEST_TIMEOUT = 60

# Yapily sandbox/test institutions to skip
YAPILY_TEST_INSTITUTION_IDS = {
    "modelo-sandbox",
    "modelo-sandbox-business",
    "modelo-sandbox-payments",
    "modelo-sandbox-payments-business",
    "modelo-sandbox-stet",
    "modelo-sandbox-embedded",
    "modelo-sandbox-embedded-business",
    "modelo-sandbox-embedded-payments",
    "modelo-sandbox-vrp",
    "modelo-sandbox-recurring-payments",
    "yapily-mock",
    "yapily-mock-business",
}

# Known Yapily market coverage (from https://status-institutions.yapily.com/)
# These are the countries where Yapily has open banking coverage
YAPILY_KNOWN_COUNTRIES = [
    "AT",  # Austria (13 institutions)
    "BE",  # Belgium (17 institutions)
    "DE",  # Germany (36 institutions)
    "DK",  # Denmark (38 institutions)
    "EE",  # Estonia (6 institutions)
    "ES",  # Spain (32 institutions)
    "FI",  # Finland (11 institutions)
    "FR",  # France (50 institutions)
    "GB",  # United Kingdom (89 institutions)
    "IE",  # Ireland (17 institutions)
    "IS",  # Iceland (3 institutions)
    "IT",  # Italy (76 institutions)
    "LT",  # Lithuania (5 institutions)
    "LV",  # Latvia (5 institutions)
    "NL",  # Netherlands (14 institutions)
    "NO",  # Norway (9 institutions)
    "PL",  # Poland (10 institutions)
    "PT",  # Portugal (29 institutions)
    "SE",  # Sweden (13 institutions)
]

# Known Yapily-supported banks (from documentation and status page)
# This list is used when API credentials are not configured
YAPILY_KNOWN_BANKS = [
    # United Kingdom
    {"name": "HSBC", "id": "hsbc", "countries": ["GB"]},
    {"name": "Barclays", "id": "barclays", "countries": ["GB"]},
    {"name": "Lloyds Bank", "id": "lloyds-bank", "countries": ["GB"]},
    {"name": "NatWest", "id": "natwest", "countries": ["GB"]},
    {"name": "Royal Bank of Scotland", "id": "royal-bank-of-scotland", "countries": ["GB"]},
    {"name": "Santander UK", "id": "santander-uk", "countries": ["GB"]},
    {"name": "Halifax", "id": "halifax", "countries": ["GB"]},
    {"name": "Bank of Scotland", "id": "bank-of-scotland", "countries": ["GB"]},
    {"name": "Nationwide", "id": "nationwide", "countries": ["GB"]},
    {"name": "First Direct", "id": "first-direct", "countries": ["GB"]},
    {"name": "Monzo", "id": "monzo", "countries": ["GB"]},
    {"name": "Starling Bank", "id": "starling-bank", "countries": ["GB"]},
    {"name": "Revolut", "id": "revolut", "countries": ["GB"]},
    {"name": "TSB", "id": "tsb", "countries": ["GB"]},
    {"name": "Metro Bank", "id": "metro-bank", "countries": ["GB"]},
    {"name": "Virgin Money", "id": "virgin-money", "countries": ["GB"]},
    {"name": "Clydesdale Bank", "id": "clydesdale-bank", "countries": ["GB"]},
    {"name": "Yorkshire Bank", "id": "yorkshire-bank", "countries": ["GB"]},
    {"name": "Ulster Bank", "id": "ulster-bank", "countries": ["GB", "IE"]},
    {"name": "Danske Bank", "id": "danske-bank", "countries": ["GB", "DK"]},
    {"name": "Bank of Ireland UK", "id": "bank-of-ireland-uk", "countries": ["GB"]},
    {"name": "AIB UK", "id": "aib-uk", "countries": ["GB"]},
    # Germany
    {"name": "Deutsche Bank", "id": "deutsche-bank", "countries": ["DE"]},
    {"name": "Commerzbank", "id": "commerzbank", "countries": ["DE"]},
    {"name": "DKB", "id": "dkb", "countries": ["DE"]},
    {"name": "ING Germany", "id": "ing-de", "countries": ["DE"]},
    {"name": "N26", "id": "n26", "countries": ["DE"]},
    {"name": "Sparkasse", "id": "sparkasse", "countries": ["DE"]},
    {"name": "Volksbank", "id": "volksbank", "countries": ["DE"]},
    {"name": "Postbank", "id": "postbank", "countries": ["DE"]},
    {"name": "Comdirect", "id": "comdirect", "countries": ["DE"]},
    {"name": "Targobank", "id": "targobank", "countries": ["DE"]},
    {"name": "HypoVereinsbank", "id": "hypovereinsbank", "countries": ["DE"]},
    # France
    {"name": "BNP Paribas", "id": "bnp-paribas", "countries": ["FR"]},
    {"name": "Société Générale", "id": "societe-generale", "countries": ["FR"]},
    {"name": "Crédit Agricole", "id": "credit-agricole", "countries": ["FR"]},
    {"name": "Crédit Mutuel", "id": "credit-mutuel", "countries": ["FR"]},
    {"name": "La Banque Postale", "id": "la-banque-postale", "countries": ["FR"]},
    {"name": "Boursorama", "id": "boursorama", "countries": ["FR"]},
    {"name": "CIC", "id": "cic", "countries": ["FR"]},
    {"name": "LCL", "id": "lcl", "countries": ["FR"]},
    {"name": "Caisse d'Epargne", "id": "caisse-depargne", "countries": ["FR"]},
    {"name": "Banque Populaire", "id": "banque-populaire", "countries": ["FR"]},
    # Netherlands
    {"name": "ING Netherlands", "id": "ing-nl", "countries": ["NL"]},
    {"name": "ABN AMRO", "id": "abn-amro", "countries": ["NL"]},
    {"name": "Rabobank", "id": "rabobank", "countries": ["NL"]},
    {"name": "SNS Bank", "id": "sns-bank", "countries": ["NL"]},
    {"name": "ASN Bank", "id": "asn-bank", "countries": ["NL"]},
    {"name": "Triodos Bank", "id": "triodos-bank", "countries": ["NL"]},
    {"name": "Bunq", "id": "bunq", "countries": ["NL"]},
    # Spain
    {"name": "BBVA", "id": "bbva", "countries": ["ES"]},
    {"name": "Santander Spain", "id": "santander-es", "countries": ["ES"]},
    {"name": "CaixaBank", "id": "caixabank", "countries": ["ES"]},
    {"name": "Sabadell", "id": "sabadell", "countries": ["ES"]},
    {"name": "Bankinter", "id": "bankinter", "countries": ["ES"]},
    {"name": "ING Spain", "id": "ing-es", "countries": ["ES"]},
    # Italy
    {"name": "Intesa Sanpaolo", "id": "intesa-sanpaolo", "countries": ["IT"]},
    {"name": "UniCredit", "id": "unicredit", "countries": ["IT"]},
    {"name": "Fineco", "id": "fineco", "countries": ["IT"]},
    {"name": "Banca Mediolanum", "id": "banca-mediolanum", "countries": ["IT"]},
    {"name": "Banca Sella", "id": "banca-sella", "countries": ["IT"]},
    # Ireland
    {"name": "AIB", "id": "aib", "countries": ["IE"]},
    {"name": "Bank of Ireland", "id": "bank-of-ireland", "countries": ["IE"]},
    {"name": "Permanent TSB", "id": "permanent-tsb", "countries": ["IE"]},
    # Nordic
    {"name": "Nordea", "id": "nordea", "countries": ["DK", "FI", "NO", "SE"]},
    {"name": "Danske Bank", "id": "danske-bank", "countries": ["DK"]},
    {"name": "Swedbank", "id": "swedbank", "countries": ["SE", "EE", "LT", "LV"]},
    {"name": "SEB", "id": "seb", "countries": ["SE"]},
    {"name": "Handelsbanken", "id": "handelsbanken", "countries": ["SE"]},
    {"name": "DNB", "id": "dnb", "countries": ["NO"]},
    {"name": "OP Financial Group", "id": "op-financial-group", "countries": ["FI"]},
    # Belgium
    {"name": "KBC", "id": "kbc", "countries": ["BE"]},
    {"name": "BNP Paribas Fortis", "id": "bnp-paribas-fortis", "countries": ["BE"]},
    {"name": "Belfius", "id": "belfius", "countries": ["BE"]},
    {"name": "ING Belgium", "id": "ing-be", "countries": ["BE"]},
    # Austria
    {"name": "Erste Bank", "id": "erste-bank", "countries": ["AT"]},
    {"name": "Raiffeisen Bank", "id": "raiffeisen-bank", "countries": ["AT"]},
    {"name": "Bank Austria", "id": "bank-austria", "countries": ["AT"]},
    # Portugal
    {"name": "Millennium BCP", "id": "millennium-bcp", "countries": ["PT"]},
    {"name": "Novo Banco", "id": "novo-banco", "countries": ["PT"]},
    {"name": "Santander Portugal", "id": "santander-pt", "countries": ["PT"]},
    {"name": "CGD", "id": "cgd", "countries": ["PT"]},
    # Poland
    {"name": "PKO Bank Polski", "id": "pko-bank-polski", "countries": ["PL"]},
    {"name": "mBank", "id": "mbank", "countries": ["PL"]},
    {"name": "ING Poland", "id": "ing-pl", "countries": ["PL"]},
    {"name": "Santander Poland", "id": "santander-pl", "countries": ["PL"]},
]

# Patterns to identify test/sandbox institutions by name
YAPILY_TEST_NAME_PATTERNS = [
    "sandbox",
    "test bank",
    "demo bank",
    "modelo",
    "mock",
]

# Country code to name mapping
COUNTRY_NAMES = {
    "AT": "Austria",
    "BE": "Belgium",
    "BG": "Bulgaria",
    "CH": "Switzerland",
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


def get_auth_header() -> Optional[str]:
    """Generate the Basic Auth header for Yapily API."""
    app_uuid = os.environ.get("YAPILY_APPLICATION_UUID")
    secret = os.environ.get("YAPILY_SECRET")
    
    if not app_uuid or not secret:
        return None
    
    # Basic auth: base64(applicationUuid:secret)
    credentials = f"{app_uuid}:{secret}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return f"Basic {encoded}"


def yapily_api_request(endpoint: str, params: dict = None) -> Optional[dict]:
    """Make a GET request to Yapily API."""
    auth_header = get_auth_header()
    
    if not auth_header:
        return None
    
    url = f"{YAPILY_API_URL}{endpoint}"
    
    headers = {
        "Authorization": auth_header,
        "Accept": "application/json",
        "User-Agent": "OpenBankingTracker/1.0"
    }
    
    print(f"  API request to {endpoint}...")
    try:
        if HAS_REQUESTS:
            response = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
            if response.status_code == 200:
                return response.json()
            print(f"  Request failed: {response.status_code} - {response.text[:200]}")
            return None
        else:
            # Fallback to curl
            cmd = [
                "curl", "-s", "-X", "GET", url,
                "-H", f"Authorization: {auth_header}",
                "-H", "Accept: application/json",
                "-H", "User-Agent: OpenBankingTracker/1.0"
            ]
            
            if params:
                query_string = "&".join(f"{k}={v}" for k, v in params.items())
                cmd[4] = f"{url}?{query_string}"
            
            result = subprocess.run(
                cmd,
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


def get_yapily_institutions() -> list[dict]:
    """
    Fetch all institutions from Yapily API.
    
    Returns a list of institution dictionaries with:
    - id (institution ID)
    - name
    - fullName
    - countries (list of country objects with countryCode2)
    - media (logo info)
    - features (supported features)
    """
    print("Fetching institutions from Yapily API...")
    
    response = yapily_api_request("/institutions")
    
    if not response:
        print("  Failed to fetch institutions")
        return []
    
    # The response has a 'data' field containing the institutions list
    institutions = response.get("data", [])
    
    if not institutions:
        print("  No institutions found in response")
        return []
    
    print(f"  Fetched {len(institutions)} institutions")
    return institutions


def load_json(path: Path) -> dict:
    """Load a JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: dict) -> None:
    """Save data to a JSON file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
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
    
    suffixes = ['-bank', '-business', '-corporate', '-retail', '-sa', '-ag', '-nv', '-plc', '-ltd', '-group']
    country_suffixes = ['-gb', '-uk', '-nl', '-de', '-fr', '-es', '-it', '-be', '-at', '-ie', '-se', '-dk', '-no', '-fi', '-pl', '-pt', '-ch']
    
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


def load_yapily_institution_ids() -> dict:
    """Load the Yapily institution ID mappings."""
    if YAPILY_INSTITUTION_IDS_PATH.exists():
        with open(YAPILY_INSTITUTION_IDS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_yapily_institution_ids(mappings: dict) -> None:
    """Save the Yapily institution ID mappings."""
    with open(YAPILY_INSTITUTION_IDS_PATH, "w", encoding="utf-8") as f:
        json.dump(mappings, f, indent=2, ensure_ascii=False)
        f.write("\n")


def get_countries_from_institution(institution: dict) -> list[str]:
    """Extract country codes from institution data."""
    countries_data = institution.get("countries", [])
    countries = []
    
    for country in countries_data:
        # Country can be a dict with countryCode2 or just a string
        if isinstance(country, dict):
            code = country.get("countryCode2")
        else:
            code = country
        
        if code and isinstance(code, str) and len(code) == 2:
            countries.append(code.upper())
    
    return sorted(set(countries))


def get_icon_url_from_institution(institution: dict) -> Optional[str]:
    """Extract icon URL from institution media data."""
    media = institution.get("media", [])
    
    if not media:
        return None
    
    # Look for icon type first, then logo
    for item in media:
        if isinstance(item, dict):
            media_type = item.get("type", "").lower()
            source = item.get("source")
            if media_type == "icon" and source:
                return source
    
    # Fallback to logo
    for item in media:
        if isinstance(item, dict):
            media_type = item.get("type", "").lower()
            source = item.get("source")
            if media_type == "logo" and source:
                return source
    
    return None


def create_account_provider(institution: dict) -> dict:
    """Create a new account provider entry from Yapily institution data."""
    name = institution.get("name") or institution.get("fullName", "Unknown")
    bank_id = slugify(name)
    countries = get_countries_from_institution(institution)
    country_hq = countries[0] if countries else "GB"
    
    # Get icon URL
    icon_url = get_icon_url_from_institution(institution)
    if not icon_url:
        icon_url = f"https://icons.duckduckgo.com/ip3/www.{bank_id}.com.ico"
    
    provider = {
        "id": bank_id,
        "type": ["account"],
        "bankType": ["retail"],
        "name": name,
        "legalName": institution.get("fullName") or name,
        "verified": False,
        "status": "live",
        "icon": icon_url,
        "websiteUrl": None,
        "countryHQ": country_hq,
        "countries": countries if countries else [country_hq],
        "webApplication": True,
        "mobileApps": [],
        "compliance": [],
        "developerPortalUrl": None,
        "apiStandards": [],
        "apiProducts": [],
        "apiAggregators": ["yapily"],
        "ownership": [],
        "stateOwned": False,
        "stockSymbol": None
    }
    
    return provider


def add_yapily_to_existing_provider(provider_path: Path) -> bool:
    """Add 'yapily' to an existing provider's apiAggregators list."""
    provider = load_json(provider_path)
    
    aggregators = provider.get("apiAggregators", [])
    if aggregators is None:
        aggregators = []
    
    if "yapily" not in aggregators:
        aggregators.append("yapily")
        aggregators.sort()
        provider["apiAggregators"] = aggregators
        save_json(provider_path, provider)
        return True
    
    return False


def is_test_institution(institution: dict) -> bool:
    """Check if an institution is a test/sandbox institution."""
    inst_id = institution.get("id", "").lower()
    name = institution.get("name", "").lower()
    full_name = institution.get("fullName", "").lower()
    
    # Check by ID
    if inst_id in YAPILY_TEST_INSTITUTION_IDS:
        return True
    
    # Check by name patterns
    for pattern in YAPILY_TEST_NAME_PATTERNS:
        if pattern in name or pattern in full_name or pattern in inst_id:
            return True
    
    return False


def update_yapily_coverage(institutions: list[dict], use_known_coverage: bool = False) -> None:
    """Update yapily.json with market coverage based on fetched institutions."""
    print("\n=== Updating Yapily Market Coverage ===\n")
    
    if use_known_coverage or not institutions:
        # Use known coverage from Yapily's website
        country_codes = sorted(YAPILY_KNOWN_COUNTRIES)
        print(f"Using known Yapily coverage: {len(country_codes)} countries")
    else:
        # Collect all unique country codes from institutions
        all_countries = set()
        for institution in institutions:
            if is_test_institution(institution):
                continue
            countries = get_countries_from_institution(institution)
            all_countries.update(countries)
        
        # Sort country codes
        country_codes = sorted(all_countries)
    
    print(f"Coverage: {len(country_codes)} countries: {', '.join(country_codes)}")
    
    # Load and update yapily.json
    yapily_data = load_json(YAPILY_JSON_PATH)
    existing_coverage = yapily_data.get("marketCoverage", {}).get("live", [])
    
    yapily_data["marketCoverage"] = {"live": country_codes}
    save_json(YAPILY_JSON_PATH, yapily_data)
    
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


def update_bank_providers_from_known_list() -> None:
    """Update account providers using the known Yapily banks list."""
    print("\n=== Updating Bank Providers (from known list) ===\n")
    
    print(f"Processing {len(YAPILY_KNOWN_BANKS)} known Yapily banks...")
    
    existing_ids = get_existing_provider_ids()
    print(f"Found {len(existing_ids)} existing account providers")
    
    updated_count = 0
    skipped_count = 0
    not_found_count = 0
    
    for bank in YAPILY_KNOWN_BANKS:
        bank_id = bank["id"]
        name = bank["name"]
        
        # Try to find a matching existing provider
        matching_id = find_matching_provider(bank_id, existing_ids)
        
        if matching_id:
            provider_path = ACCOUNT_PROVIDERS_PATH / f"{matching_id}.json"
            if add_yapily_to_existing_provider(provider_path):
                updated_count += 1
                if matching_id != bank_id:
                    print(f"  Updated: {name} -> {matching_id}.json (added yapily)")
                else:
                    print(f"  Updated: {name} (added yapily)")
            else:
                skipped_count += 1
        else:
            not_found_count += 1
    
    print(f"\nSummary:")
    print(f"  {updated_count} providers updated with yapily aggregator")
    print(f"  {skipped_count} already had yapily (no changes needed)")
    print(f"  {not_found_count} not found in existing providers (skipped)")


def update_bank_providers(institutions: list[dict], skip_providers: bool = False) -> None:
    """Create/update account providers from fetched institution data."""
    print("\n=== Updating Bank Providers ===\n")
    
    if skip_providers:
        print("Skipping provider updates (--skip-providers flag set)")
        return
    
    print(f"Processing {len(institutions)} institutions...")
    
    existing_ids = get_existing_provider_ids()
    print(f"Found {len(existing_ids)} existing account providers")
    
    # Load existing Yapily institution ID mappings
    yapily_id_mappings = load_yapily_institution_ids()
    
    new_count = 0
    updated_count = 0
    skipped_count = 0
    skipped_test = 0
    
    for institution in institutions:
        name = institution.get("name") or institution.get("fullName", "")
        if not name:
            continue
        
        # Skip test institutions
        if is_test_institution(institution):
            skipped_test += 1
            continue
        
        inst_id = institution.get("id", "")
        bank_id = slugify(name)
        
        if not bank_id:
            continue
        
        matching_id = find_matching_provider(bank_id, existing_ids)
        
        if matching_id:
            provider_path = ACCOUNT_PROVIDERS_PATH / f"{matching_id}.json"
            if add_yapily_to_existing_provider(provider_path):
                updated_count += 1
                if matching_id != bank_id:
                    print(f"  Updated: {name} -> {matching_id}.json (added yapily)")
                else:
                    print(f"  Updated: {name} (added yapily)")
            else:
                skipped_count += 1
            # Save institution ID mapping
            if inst_id:
                yapily_id_mappings[matching_id] = inst_id
        else:
            provider_path = ACCOUNT_PROVIDERS_PATH / f"{bank_id}.json"
            provider = create_account_provider(institution)
            save_json(provider_path, provider)
            existing_ids.add(bank_id)
            new_count += 1
            print(f"  Created: {name} ({bank_id}.json)")
            # Save institution ID mapping
            if inst_id:
                yapily_id_mappings[bank_id] = inst_id
    
    # Save updated institution ID mappings
    save_yapily_institution_ids(yapily_id_mappings)
    print(f"\nSaved {len(yapily_id_mappings)} Yapily institution ID mappings to yapily_institution_ids.json")
    
    print(f"\nSummary:")
    print(f"  {new_count} new providers created")
    print(f"  {updated_count} updated with yapily aggregator")
    print(f"  {skipped_count} already had yapily (no changes needed)")
    print(f"  {skipped_test} test/sandbox institutions skipped")


def print_statistics(institutions: list[dict]) -> None:
    """Print statistics about the fetched institutions."""
    print("\n=== Institution Statistics ===\n")
    
    # Count by country
    country_counts = {}
    total_valid = 0
    
    for institution in institutions:
        if is_test_institution(institution):
            continue
        
        total_valid += 1
        countries = get_countries_from_institution(institution)
        
        for country in countries:
            country_counts[country] = country_counts.get(country, 0) + 1
    
    print(f"Total valid institutions: {total_valid}")
    print(f"\nInstitutions per country:")
    
    for country in sorted(country_counts.keys()):
        country_name = COUNTRY_NAMES.get(country, country)
        count = country_counts[country]
        print(f"  {country} ({country_name}): {count}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Fetch Yapily coverage data and update providers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run with credentials from .env file
    python yapily_scraper.py
    
    # Run with credentials from environment
    YAPILY_APPLICATION_UUID=xxx YAPILY_SECRET=yyy python yapily_scraper.py
    
    # Only update market coverage (skip provider updates)
    python yapily_scraper.py --coverage-only
    
    # Show statistics only (dry run)
    python yapily_scraper.py --dry-run

Credentials:
    Set the following environment variables:
    - YAPILY_APPLICATION_UUID: Your Yapily application UUID
    - YAPILY_SECRET: Your Yapily application secret
    
    Or create a .env file in the scrapers directory with:
    YAPILY_APPLICATION_UUID=your-uuid-here
    YAPILY_SECRET=your-secret-here
        """
    )
    parser.add_argument(
        "--coverage-only",
        action="store_true",
        help="Only update market coverage in yapily.json, skip provider updates"
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
    parser.add_argument(
        "--stats-only",
        action="store_true",
        help="Only show statistics, don't make any changes"
    )
    parser.add_argument(
        "--use-known-coverage",
        action="store_true",
        help="Update market coverage using known Yapily countries (no API call needed)"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Yapily Coverage Scraper")
    print("=" * 60)
    
    # Handle --use-known-coverage flag (doesn't need credentials)
    if args.use_known_coverage:
        print("\nUsing known Yapily coverage (no API call)...")
        if not args.dry_run:
            update_yapily_coverage([], use_known_coverage=True)
            if not args.coverage_only and not args.skip_providers:
                update_bank_providers_from_known_list()
        else:
            print(f"\n[DRY RUN] Would update market coverage with {len(YAPILY_KNOWN_COUNTRIES)} countries")
            print(f"[DRY RUN] Would update providers from {len(YAPILY_KNOWN_BANKS)} known banks")
        
        print("\n" + "=" * 60)
        print("Done!")
        print("=" * 60)
        return
    
    # Check for API credentials
    has_credentials = bool(os.environ.get("YAPILY_APPLICATION_UUID") and os.environ.get("YAPILY_SECRET"))
    
    if not has_credentials:
        print("\nError: Yapily API credentials not found.")
        print("\nSet the following environment variables:")
        print("  - YAPILY_APPLICATION_UUID")
        print("  - YAPILY_SECRET")
        print("\nOr create a .env file in the scrapers directory with:")
        print("  YAPILY_APPLICATION_UUID=your-uuid-here")
        print("  YAPILY_SECRET=your-secret-here")
        print("\nYou can get credentials from the Yapily dashboard:")
        print("  https://console.yapily.com/")
        return
    
    print("\nYapily API credentials detected.")
    
    # Fetch institutions
    institutions = get_yapily_institutions()
    
    if not institutions:
        print("\n" + "=" * 60)
        print("NOTE: No institutions found in your Yapily application.")
        print("=" * 60)
        print("\nYapily applications need institutions to be configured before")
        print("they appear in the API response.")
        print("\nTo add institutions to your application:")
        print("  1. Go to https://console.yapily.com/")
        print("  2. Select your application")
        print("  3. Go to 'Connected Institutions' tab")
        print("  4. Click 'Add Institutions' and add the banks you need")
        print("\nFor testing, add 'modelo-sandbox' (preconfigured sandbox bank)")
        print("\nUpdating using known Yapily data...")
        
        # Still update market coverage and providers using known data
        if not args.dry_run and not args.stats_only:
            update_yapily_coverage([], use_known_coverage=True)
            if not args.coverage_only and not args.skip_providers:
                update_bank_providers_from_known_list()
        
        print("\n" + "=" * 60)
        print("Done!")
        print("=" * 60)
        return
    
    # Print statistics
    print_statistics(institutions)
    
    if args.stats_only:
        print("\n[Stats only mode - no changes made]")
        print("\n" + "=" * 60)
        print("Done!")
        print("=" * 60)
        return
    
    # Update coverage
    if not args.dry_run:
        update_yapily_coverage(institutions)
    else:
        print("\n[DRY RUN] Would update market coverage")
    
    # Update providers
    if not args.coverage_only:
        if not args.dry_run:
            update_bank_providers(institutions, skip_providers=args.skip_providers)
        else:
            print("[DRY RUN] Would process bank providers")
    else:
        print("\nSkipping provider updates (--coverage-only flag set)")
    
    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)


if __name__ == "__main__":
    main()
