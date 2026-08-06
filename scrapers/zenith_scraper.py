#!/usr/bin/env python3
"""
Zenith Bank Coverage Scraper

This script fetches live bank coverage from Zenith's public API and updates:
1. zenith.json with market coverage and bank count
2. Account provider entries with 'zenith' in apiAggregators (matched by BIC)
3. Saves institution data for reference

Data Source: https://zenith-books.com/banks.json
- List of 2,000+ European banks with BIC codes and country coverage

Usage:
    # Fetch fresh data and update repo
    python scrapers/zenith_scraper.py

    # Dry run - show what would be done without making changes
    python scrapers/zenith_scraper.py --dry-run

    # Only update market coverage (skip bank provider updates)
    python scrapers/zenith_scraper.py --coverage-only
"""

import argparse
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:
    print("Error: requests library not found. Install with: pip install requests")
    sys.exit(1)


# Paths relative to this script's location
BASE_PATH = Path(__file__).parent.parent
ZENITH_JSON_PATH = BASE_PATH / "data" / "api-aggregators" / "zenith.json"
ACCOUNT_PROVIDERS_PATH = BASE_PATH / "data" / "account-providers"
SCRAPED_DATA_PATH = BASE_PATH / "scraped-data" / "zenith"

# Zenith API endpoint
ZENITH_API_URL = "https://zenith-books.com/banks.json"

# ISO 3166-1 alpha-2 country codes
VALID_COUNTRY_CODES = {
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR", "GB",
    "GR", "HR", "HU", "IE", "IS", "IT", "LT", "LU", "LV", "MT", "NL", "NO",
    "PL", "PT", "RO", "SE", "SI", "SK",
}


def fetch_zenith_banks() -> Optional[list[dict]]:
    """
    Fetch bank data from Zenith's public API endpoint.

    Returns:
        List of bank dictionaries with bic, name, country, etc., or None on error
    """
    print(f"\n=== Fetching from {ZENITH_API_URL} ===\n")

    try:
        response = requests.get(ZENITH_API_URL, timeout=30)
        response.raise_for_status()
        banks = response.json()

        if isinstance(banks, list):
            print(f"✓ Fetched {len(banks)} banks")
            return banks
        else:
            print(f"✗ Unexpected response format: {type(banks)}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"✗ Failed to fetch: {e}")
        return None


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
    """Get the set of existing account provider IDs (filenames without .json)."""
    provider_ids = set()
    for json_file in ACCOUNT_PROVIDERS_PATH.glob("*.json"):
        provider_ids.add(json_file.stem)
    return provider_ids


def extract_countries(banks: list[dict]) -> set[str]:
    """
    Extract unique country codes from bank data.

    Args:
        banks: List of bank dictionaries

    Returns:
        Set of ISO country codes
    """
    countries = set()
    for bank in banks:
        country = bank.get("country", "").upper()
        if country and country in VALID_COUNTRY_CODES:
            countries.add(country)
    return countries


def add_zenith_to_provider(provider_path: Path, bic_code: Optional[str] = None) -> bool:
    """
    Add 'zenith' to an existing provider's apiAggregators list and optionally BIC code.

    Args:
        provider_path: Path to the provider JSON file
        bic_code: Optional SWIFT/BIC code to add if not present

    Returns:
        True if modified, False otherwise
    """
    provider = load_json(provider_path)
    modified = False

    # Add zenith to aggregators if not present
    aggregators = provider.get("apiAggregators", [])
    if aggregators is None:
        aggregators = []

    if "zenith" not in aggregators:
        # Append only. Re-sorting the whole list would rewrite entries owned by
        # other aggregators and add unrelated noise to the diff.
        aggregators.append("zenith")
        provider["apiAggregators"] = aggregators
        modified = True

    # Add BIC code if not present and we have one
    if bic_code and not provider.get("bic"):
        provider["bic"] = bic_code
        modified = True

    if modified:
        save_json(provider_path, provider)

    return modified


def update_zenith_coverage(banks: list[dict], countries: set[str]) -> None:
    """
    Update zenith.json with market coverage and bank count.

    Args:
        banks: List of bank dictionaries
        countries: Set of country codes where Zenith has coverage
    """
    print("\n=== Updating Zenith Market Coverage ===\n")

    # Load and update zenith.json
    zenith_data = load_json(ZENITH_JSON_PATH)
    existing_coverage = zenith_data.get("marketCoverage", {}).get("live", [])

    sorted_countries = sorted(countries)
    zenith_data["marketCoverage"] = {"live": sorted_countries}
    zenith_data["lastUpdated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # bankCount is the headline figure; coverage.byCountry must sum to it.
    by_country: dict[str, int] = {}
    for bank in banks:
        country = bank.get("country", "").upper()
        if country in VALID_COUNTRY_CODES:
            by_country[country] = by_country.get(country, 0) + 1

    zenith_data["bankCount"] = len(banks)
    zenith_data["coverage"] = {
        "total": len(banks),
        "byCountry": dict(sorted(by_country.items())),
    }

    save_json(ZENITH_JSON_PATH, zenith_data)

    # Report changes
    existing_set = set(existing_coverage)
    new_set = set(sorted_countries)
    added = new_set - existing_set
    removed = existing_set - new_set

    print(f"Coverage: {len(sorted_countries)} countries, {len(banks)} banks")
    if added:
        print(f"  Added countries: {', '.join(sorted(added))}")
    if removed:
        print(f"  Removed countries: {', '.join(sorted(removed))}")
    if not added and not removed:
        print("  No changes to market coverage.")


NAME_STOPWORDS = {
    "bank", "banca", "banque", "banco", "the", "and",
    "fur", "von", "der", "die", "des",
}

# German/Nordic transliterations: tracker records are inconsistent about whether
# umlauts are spelled out (MUENCHEN) or kept (MÜNCHEN).
TRANSLITERATIONS = (
    ("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss"),
    ("å", "aa"), ("æ", "ae"), ("ø", "oe"),
)


def _tight(name: str) -> str:
    """Normalize a bank name to a comparable alphanumeric key."""
    s = (name or "").lower()
    for src, dst in TRANSLITERATIONS:
        s = s.replace(src, dst)
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", s)


def _tokens(name: str) -> set[str]:
    """Significant word tokens of a bank name, for fuzzy comparison."""
    s = (name or "").lower()
    for src, dst in TRANSLITERATIONS:
        s = s.replace(src, dst)
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return {
        t for t in re.split(r"[^a-z0-9]+", s)
        if len(t) > 2 and t not in NAME_STOPWORDS
    }


def match_banks_to_providers(banks: list[dict], providers: list[dict]) -> dict[str, dict]:
    """
    Map each Zenith bank to at most one account-provider file.

    A plain BIC match is not usable here. German cooperative and savings banks
    share a network BIC (GENODEF1 alone covers ~600 provider files) where the
    branch code carries the identity, so matching on the 8-character prefix
    tags hundreds of institutions Zenith does not actually connect to.

    Matching is therefore tiered, strongest evidence first, and each provider
    file can be claimed by only one bank. Candidates are always restricted to
    providers in the same country as the Zenith record.

    Args:
        banks: Zenith bank dicts with 'bic', 'name' and 'country'
        providers: Provider dicts with 'file', 'bic', 'name', 'countryHQ', 'countries'

    Returns:
        Mapping of provider filename -> the Zenith bank that claimed it
    """
    by_11: dict[str, list[dict]] = {}
    by_8: dict[str, list[dict]] = {}
    for p in providers:
        bic = p["bic"]
        if len(bic) >= 11:
            by_11.setdefault(bic[:11], []).append(p)
        if len(bic) >= 8:
            by_8.setdefault(bic[:8], []).append(p)

    claimed: dict[str, dict] = {}

    def candidates(bank: dict, use_11: bool) -> list[dict]:
        bic = bank["_bic"]
        if use_11:
            pool = by_11.get(bic[:11], []) if len(bic) >= 11 else []
        else:
            pool = by_8.get(bic[:8], []) if len(bic) >= 8 else []
        country = bank.get("country", "").upper()
        return [
            p for p in pool
            if p["file"] not in claimed
            and (p["countryHQ"] == country or country in p["countries"])
        ]

    def name_agrees(bank: dict, p: dict) -> bool:
        a, b = bank["_tight"], p["tight"]
        return a == b or a.startswith(b) or b.startswith(a)

    def tier_bic11_name(bank):
        return next((p for p in candidates(bank, True) if name_agrees(bank, p)), None)

    def tier_bic11(bank):
        pool = candidates(bank, True)
        return pool[0] if pool else None

    def tier_bic8_name(bank):
        return next((p for p in candidates(bank, False) if name_agrees(bank, p)), None)

    def tier_bic8_tokens(bank):
        # Only trust a prefix match when the BIC is not a shared network code.
        pool = candidates(bank, False)
        if len(pool) > 3:
            return None
        scored = [(len(bank["_tokens"] & p["tokens"]), p) for p in pool]
        scored = sorted((s for s in scored if s[0] > 0), key=lambda x: -x[0])
        return scored[0][1] if scored else None

    def tier_bic8_unique(bank):
        pool = candidates(bank, False)
        return pool[0] if len(pool) == 1 else None

    tiers = [
        tier_bic11_name,
        tier_bic11,
        tier_bic8_name,
        tier_bic8_tokens,
        tier_bic8_unique,
    ]

    pending = list(banks)
    for tier in tiers:
        still_pending = []
        for bank in pending:
            hit = tier(bank)
            if hit:
                claimed[hit["file"]] = bank
            else:
                still_pending.append(bank)
        pending = still_pending

    if pending:
        print(f"  {len(pending)} Zenith banks have no account-provider file in the tracker")

    return claimed


def update_bank_providers(banks: list[dict]) -> None:
    """
    Update account provider files by adding 'zenith' to matching banks.

    Args:
        banks: List of bank dictionaries with 'bic', 'name' and 'country'
    """
    print("\n=== Updating Bank Providers ===\n")

    for bank in banks:
        bank["_bic"] = bank.get("bic", "").upper().strip()
        bank["_tight"] = _tight(bank.get("name"))
        bank["_tokens"] = _tokens(bank.get("name"))

    providers = []
    for json_file in sorted(ACCOUNT_PROVIDERS_PATH.glob("*.json")):
        provider = load_json(json_file)
        providers.append({
            "file": json_file.name,
            "path": json_file,
            "bic": (provider.get("bic") or "").upper().strip(),
            "tight": _tight(provider.get("name")),
            "tokens": _tokens(provider.get("name")),
            "countryHQ": (provider.get("countryHQ") or "").upper(),
            "countries": [c.upper() for c in (provider.get("countries") or []) if c],
        })

    print(f"Matching {len(banks)} Zenith banks against {len(providers)} account providers")

    claimed = match_banks_to_providers(banks, providers)

    updated_count = 0
    by_country: dict[str, int] = {}
    for p in providers:
        bank = claimed.get(p["file"])
        if not bank:
            continue
        country = bank.get("country", "").upper()
        by_country[country] = by_country.get(country, 0) + 1
        if add_zenith_to_provider(p["path"], p["bic"]):
            updated_count += 1
            print(f"  ✓ {bank.get('name')} ({p['bic']})")

    zenith_by_country: dict[str, int] = {}
    for bank in banks:
        c = bank.get("country", "").upper()
        zenith_by_country[c] = zenith_by_country.get(c, 0) + 1

    print(f"\nSummary:")
    print(f"  {len(claimed)} providers matched (of {len(banks)} Zenith banks)")
    print(f"  {updated_count} providers newly tagged with zenith")
    print(f"\nPer-country reconciliation (zenith feed vs tagged providers):")
    for country in sorted(zenith_by_country):
        tagged = by_country.get(country, 0)
        total = zenith_by_country[country]
        flag = "" if tagged <= total else "  <-- OVER-TAGGED"
        print(f"  {country}: {total} banks, {tagged} tagged{flag}")


def save_scraped_data(banks: list[dict]) -> None:
    """
    Save all scraped bank data to a reference file.

    Args:
        banks: List of bank dictionaries
    """
    SCRAPED_DATA_PATH.mkdir(parents=True, exist_ok=True)

    output = {
        "source": "Zenith Books public API",
        "source_url": ZENITH_API_URL,
        "scraped_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bank_count": len(banks),
        "banks": banks,
    }

    output_path = SCRAPED_DATA_PATH / "zenith-banks.json"
    save_json(output_path, output)
    print(f"\nSaved bank data to {output_path}")

    # Save BIC mappings for reference
    bic_to_bank = {}
    for bank in banks:
        bic = bank.get("bic", "").upper()
        if bic:
            bic_to_bank[bic] = {
                "name": bank.get("name"),
                "country": bank.get("country"),
            }

    mappings_path = SCRAPED_DATA_PATH / "zenith-bic-mappings.json"
    save_json(mappings_path, bic_to_bank)
    print(f"Saved BIC mappings to {mappings_path}")


def main():
    """Main entry point with argument parsing."""
    parser = argparse.ArgumentParser(
        description="Fetch Zenith bank coverage and update repository",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Fetch fresh data and update everything
    python scrapers/zenith_scraper.py

    # Only update market coverage (no bank provider updates)
    python scrapers/zenith_scraper.py --coverage-only

    # Show what would be done without making changes
    python scrapers/zenith_scraper.py --dry-run

Data Source:
    https://zenith-books.com/banks.json
    Public JSON feed of Zenith's live bank coverage
        """
    )
    parser.add_argument(
        "--coverage-only",
        action="store_true",
        help="Only update market coverage in zenith.json, skip bank provider updates"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Zenith Bank Coverage Scraper")
    print("=" * 60)

    # Fetch bank data
    banks = fetch_zenith_banks()
    if not banks:
        print("\nFailed to fetch bank data. Exiting.")
        return

    # Extract country codes
    countries = extract_countries(banks)
    if not countries:
        print("\nNo valid country codes found. Exiting.")
        return

    print(f"Found coverage in {len(countries)} countries: {', '.join(sorted(countries))}")

    # Update zenith.json with market coverage
    if not args.dry_run:
        update_zenith_coverage(banks, countries)
    else:
        print(f"\n[DRY RUN] Would update coverage with {len(countries)} countries and {len(banks)} banks")

    # Save scraped data for reference
    if not args.dry_run:
        save_scraped_data(banks)
    else:
        print(f"[DRY RUN] Would save bank data for {len(banks)} institutions")

    # Update bank providers (unless skipped)
    if not args.coverage_only:
        if not args.dry_run:
            update_bank_providers(banks)
        else:
            print(f"[DRY RUN] Would update bank providers")
    else:
        print("\nSkipping provider updates.")

    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)


if __name__ == "__main__":
    main()
