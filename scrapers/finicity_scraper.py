#!/usr/bin/env python3
"""
Finicity (Mastercard Open Finance) Coverage Scraper

This script updates Finicity's market coverage and bank providers using the
public endpoint that backs the "Supported Institutions" page on the Mastercard
Developers portal.

Sources:
- https://developer.mastercard.com/open-finance-us/documentation/financial-institution/supported-institutions/
- https://developer.mastercard.com/devzone/api/portal/open-banking-institutions

NOTE: The endpoint is unauthenticated but heavily rate limited. Bursting
concurrent requests trips a server-side circuit breaker that returns
`INSTITUTIONS_ERROR` (HTTP 500) for several minutes, for every client. This
scraper therefore fetches strictly sequentially with a delay between requests
and backs off exponentially on errors. Do not parallelise it.

NOTE: Unlike the other scrapers, this one does not create account provider
files. The endpoint only exposes an ID, a display name and product flags, while
`schema.json` requires non-null `icon` and `websiteUrl` URLs. Institutions with
no existing provider are written to
`scraped-data/finicity/finicity-unmatched.json` for deliberate follow-up.
"""

import argparse
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional

from plaid_scraper import (
    ACCOUNT_PROVIDERS_PATH,
    find_matching_provider,
    get_existing_provider_ids,
    load_json,
    save_json,
    slugify,
)

# API
API_URL = "https://developer.mastercard.com/devzone/api/portal/open-banking-institutions"
DOCS_URL = (
    "https://developer.mastercard.com/open-finance-us/documentation/"
    "financial-institution/supported-institutions/"
)
PAGE_SIZE = 20  # fixed server side, no page-size parameter is honoured

# Paths
BASE_PATH = Path(__file__).parent.parent
FINICITY_JSON_PATH = BASE_PATH / "data" / "api-aggregators" / "finicity.json"
SCRAPED_DATA_PATH = BASE_PATH / "scraped-data" / "finicity"

# Request settings
REQUEST_TIMEOUT = 30
REQUEST_DELAY = 0.5  # seconds between requests
MAX_RETRIES = 6
BACKOFF_BASE = 5  # seconds; doubles per retry

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# The `country` query parameter only behaves as a real filter for the two
# markets the Open Finance US portal serves. Other ISO codes fall through to a
# fuzzy name search on the backend (e.g. `country=au` returns the single
# institution named "FinBank P Australia"), so they are not usable as filters
# and are deliberately not queried here.
FINICITY_COUNTRIES = {
    "us": "US",
    "ca": "CA",
}

COUNTRY_NAMES = {
    "US": "United States",
    "CA": "Canada",
}

# Product flags returned per institution, mapped to the abbreviations and
# titles used by the Supported Institutions table.
PRODUCT_FIELDS = [
    ("accountOwner", "AO", "Account Owner"),
    ("abc", "ABC", "Account Balance Check"),
    ("transAgg", "TA", "Transaction Aggregation"),
    ("voi", "VOI", "Verification of Income"),
    ("voa", "VOA", "Verification of Assets"),
    ("ach", "ACH", "Account ACH Details"),
    ("stateAgg", "SA", "Statements"),
    ("aha", "AHA", "Account History Aggregation"),
    ("loanPaymentDetails", "LPD", "Account Loan Payment Details"),
    ("studentLoanData", "SLD", "Account Student Loan Data"),
]

# Finicity lists one entry per *connection*, not per institution. The same bank
# shows up several times with a trailing qualifier describing which online
# banking portal the connection targets. These qualifiers are stripped so the
# variants collapse onto a single account provider.
#
# Parenthetical qualifiers are deliberately NOT stripped: they disambiguate
# genuinely different institutions that share a name -- "Citizens Bank (NM)" is
# not the same company as "Citizens Bank", and "First Financial Bank (Terre
# Haute,IN)" is not "First Financial Bank".
CONNECTION_QUALIFIERS = {
    "personal banking",
    "personal",
    "business banking",
    "business",
    "small business",
    "business online banking",
    "cash management",
    "commercial banking",
    "commercial",
    "corporate banking",
    "corporate",
    "consumer banking",
    "consumer",
    "retail banking",
    "retail",
    "online banking",
    "online",
    "credit card",
    "credit cards",
    "cards",
    "direct",
    "investments",
    "investing",
    "brokerage",
    "wealth management",
    "mortgage",
    "loans",
    "student loans",
    "new online banking",
    "new platform",
    "legacy",
}

# Bracketed suffixes that describe scope rather than identity.
SCOPE_SUFFIX_RE = re.compile(
    r"\s*\((?:all account types|all accounts|personal|business|new)\)\s*$",
    re.IGNORECASE,
)


def normalize_institution_name(name: str) -> str:
    """
    Strip connection-variant qualifiers from a Finicity institution name.

    "Central Bank - Personal Banking"          -> "Central Bank"
    "Discover Card (All Account Types)"        -> "Discover Card"
    "Citizens Bank (NM)"                       -> "Citizens Bank (NM)"   (kept)
    """
    cleaned = SCOPE_SUFFIX_RE.sub("", name).strip()

    # Strip repeated trailing " - <qualifier>" segments.
    while True:
        parts = cleaned.rsplit(" - ", 1)
        if len(parts) != 2:
            break
        head, tail = parts[0].strip(), parts[1].strip()
        if not head or tail.lower() not in CONNECTION_QUALIFIERS:
            break
        cleaned = head

    return cleaned or name.strip()


# Suffixes that existing providers use to disambiguate same-named banks.
GENERIC_SUFFIXES = ["-bank", "-bank-na", "-na", "-corporation", "-inc"]

# Finicity abbreviates where the tracker usually spells things out ("Aloha
# Pacific FCU" vs the existing `aloha-pacific-federal-credit-union.json`).
# Expanding both sides to a canonical form recovers those matches. Only pure
# synonyms belong here -- anything that changes which institution is meant
# (state qualifiers, "Federal" appearing or disappearing) must not be listed.
SLUG_ABBREVIATIONS = {
    "fcu": "federal-credit-union",
    "cu": "credit-union",
    "fsb": "federal-savings-bank",
    "fed": "federal",
    "cred": "credit",
    "svgs": "savings",
    "natl": "national",
    "assn": "association",
    "coop": "cooperative",
    "co-op": "cooperative",
}


def canonicalize_slug(slug: str) -> str:
    """Expand known abbreviations so equivalent names collapse to one form."""
    tokens = []
    for token in slug.split("-"):
        tokens.extend(SLUG_ABBREVIATIONS.get(token, token).split("-"))
    return "-".join(tokens)


def build_canonical_index(existing_ids: set[str]) -> dict[str, list[str]]:
    """
    Map canonical slug -> existing provider IDs, shortest first.

    The shortest ID is the least qualified and therefore the most likely base
    entry, but it is not always the right country: `chase` (GB) and `chase-us`
    share a canonical form. Keeping every candidate lets the country gate in
    `find_provider_match` fall through to the next one instead of giving up.
    """
    index: dict[str, list[str]] = {}
    for provider_id in existing_ids:
        index.setdefault(canonicalize_slug(provider_id), []).append(provider_id)
    for candidates in index.values():
        candidates.sort(key=lambda pid: (len(pid), pid))
    return index


# Institution names collide across borders. Finicity's "Chase" is the US bank,
# not `chase.json` (GB); its "ACB" is not Vietnam's Asia Commercial Bank. The
# Open Finance US portal serves US and CA only, so a provider whose own country
# data cannot overlap the institution's is the wrong bank however well the slug
# matches.
US_TERRITORIES = {"PR", "VI", "GU", "AS", "MP"}


def expand_countries(codes) -> set[str]:
    """Normalise country codes; US institutions cover the US territories too."""
    expanded = {code.upper() for code in codes if code}
    if "US" in expanded:
        expanded |= US_TERRITORIES
    return expanded


def build_provider_countries() -> dict[str, set[str]]:
    """Map provider ID -> every country code that provider claims."""
    index: dict[str, set[str]] = {}
    for path in ACCOUNT_PROVIDERS_PATH.glob("*.json"):
        try:
            provider = load_json(path)
        except (json.JSONDecodeError, OSError):
            continue
        codes = set(provider.get("countries") or [])
        if provider.get("countryHQ"):
            codes.add(provider["countryHQ"])
        index[path.stem] = expand_countries(codes)
    return index


def country_compatible(provider_id: str, countries: list[str],
                       provider_countries: dict[str, set[str]]) -> bool:
    """
    Whether a candidate provider could be the institution Finicity listed.

    Providers carrying no country data at all are accepted: missing metadata
    should not cost a genuine match. 178 of the 57k providers are in that state.
    """
    known = provider_countries.get(provider_id)
    if not known:
        return True
    return bool(known & expand_countries(countries))


def find_provider_match(slug: str, countries: list[str], existing_ids: set[str],
                        canonical_index: Optional[dict[str, list[str]]] = None,
                        provider_countries: Optional[dict[str, set[str]]] = None
                        ) -> Optional[str]:
    """
    Find an existing provider for a Finicity institution.

    Extends the shared `find_matching_provider` with country-suffixed lookups.
    The shared helper only *strips* country suffixes from the incoming slug; it
    never tries adding one, so a US-heavy dataset like this would miss the very
    common `<name>-us` form (e.g. `fifth-third-bank` vs the existing
    `fifth-third-bank-us.json`) and create thousands of duplicate stubs.

    Every candidate is then gated on country, so a name that exists only as a
    foreign provider goes to the unmatched list rather than tagging that bank.
    """
    def acceptable(candidate: Optional[str]) -> bool:
        if not candidate:
            return False
        if provider_countries is None:
            return True
        return country_compatible(candidate, countries, provider_countries)

    if slug in existing_ids and acceptable(slug):
        return slug

    country_suffixes = [f"-{c.lower()}" for c in countries]

    for suffix in country_suffixes:
        if f"{slug}{suffix}" in existing_ids and acceptable(f"{slug}{suffix}"):
            return f"{slug}{suffix}"

    if canonical_index is not None:
        canonical = canonicalize_slug(slug)
        for key in [canonical] + [f"{canonical}{s}" for s in country_suffixes]:
            for candidate in canonical_index.get(key, []):
                if acceptable(candidate):
                    return candidate

    shared_match = find_matching_provider(slug, existing_ids)
    if acceptable(shared_match):
        return shared_match

    for generic in GENERIC_SUFFIXES:
        if slug.endswith(generic):
            continue
        for suffix in country_suffixes:
            candidate = f"{slug}{generic}{suffix}"
            if candidate in existing_ids and acceptable(candidate):
                return candidate

    return None


def api_request(page: int, country: str, search: Optional[str] = None) -> Optional[dict]:
    """Fetch one page of institutions, retrying with exponential backoff."""
    params = {
        "page": page,
        "country": country,
        "is_oauth_enabled_only": "false",
    }
    if search:
        params["search"] = search
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"

    delay = BACKOFF_BASE
    for attempt in range(1, MAX_RETRIES + 1):
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "Referer": DOCS_URL,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as e:
            reason = f"HTTP {e.code}"
        except Exception as e:  # noqa: BLE001 - network errors are all retryable here
            reason = str(e)

        if attempt == MAX_RETRIES:
            print(f"  Error: {country} page {page} failed after {MAX_RETRIES} attempts ({reason})")
            return None

        print(f"  {reason} on {country} page {page}, retrying in {delay}s "
              f"(attempt {attempt}/{MAX_RETRIES})...")
        time.sleep(delay)
        delay *= 2

    return None


def fetch_institutions(country: str, max_pages: Optional[int] = None,
                       delay: float = REQUEST_DELAY) -> tuple[dict[int, dict], bool]:
    """
    Fetch every institution for a country query, keyed by Finicity ID.

    Returns (institutions, complete). `complete` is False when the walk stopped
    early -- either because --max-pages was hit or because a page could not be
    fetched -- so callers can avoid overwriting a good cache with partial data.
    """
    label = FINICITY_COUNTRIES[country]
    print(f"\nFetching {label} institutions...")

    institutions: dict[int, dict] = {}
    page = 1
    complete = True

    while True:
        if max_pages and page > max_pages:
            print(f"  Stopping at --max-pages {max_pages}")
            complete = False
            break

        data = api_request(page, country)
        if data is None:
            print(f"  Aborting {label} at page {page} (unrecoverable error)")
            complete = False
            break

        items = data.get("items") or []
        for item in items:
            institution_id = item.get("id")
            if institution_id is not None:
                institutions[institution_id] = item

        if page % 25 == 0 or not data.get("hasNext"):
            print(f"  {label}: {len(institutions)} institutions after page {page}")

        if not data.get("hasNext") or not items:
            break

        page += 1
        time.sleep(delay)

    status = "" if complete else " (INCOMPLETE)"
    print(f"  {label}: {len(institutions)} unique institutions across {page} pages{status}")
    return institutions, complete


def build_institution_record(item: dict, countries: list[str]) -> dict:
    """Shape a raw API item into the record this scraper works with."""
    name = (item.get("name") or "").strip()
    products = [
        abbreviation
        for field, abbreviation, _ in PRODUCT_FIELDS
        if item.get(field)
    ]
    return {
        "institution_id": item["id"],
        "name": name,
        "normalized_name": normalize_institution_name(name),
        "countries": countries,
        "products": products,
    }


def collect_institutions(max_pages: Optional[int] = None,
                         delay: float = REQUEST_DELAY) -> tuple[dict[str, list[dict]], bool]:
    """
    Fetch all markets and group institutions by country.

    The `country=us` query is checked against the Canadian result set: if the US
    response turns out to be unfiltered, Canadian institutions are removed from
    it rather than being mislabelled as US.

    Returns (institutions_by_country, complete).
    """
    raw_by_country: dict[str, dict[int, dict]] = {}
    complete = True
    for country in FINICITY_COUNTRIES:
        raw_by_country[country], country_complete = fetch_institutions(
            country, max_pages, delay
        )
        complete = complete and country_complete

    us_ids = set(raw_by_country.get("us", {}))
    ca_ids = set(raw_by_country.get("ca", {}))
    overlap = us_ids & ca_ids
    if ca_ids and overlap == ca_ids:
        # Every Canadian institution also appears under `country=us`, which means
        # that query is not actually filtering. Treat the shared IDs as CA-only.
        print(f"\n  Note: `country=us` returned all {len(ca_ids)} CA institutions; "
              f"treating them as CA-only.")
        for institution_id in overlap:
            raw_by_country["us"].pop(institution_id, None)
    elif overlap:
        print(f"\n  Note: {len(overlap)} institutions are listed in both US and CA.")

    all_institutions: dict[str, list[dict]] = {}
    for country, items in raw_by_country.items():
        code = FINICITY_COUNTRIES[country]
        for item in items.values():
            countries = [code]
            if item["id"] in overlap and overlap != ca_ids:
                countries = sorted({FINICITY_COUNTRIES[c] for c in FINICITY_COUNTRIES})
            all_institutions.setdefault(code, []).append(
                build_institution_record(item, countries)
            )

    print("\n  Institutions per country:")
    for code in sorted(all_institutions):
        print(f"    {code} ({COUNTRY_NAMES.get(code, code)}): {len(all_institutions[code])}")

    return all_institutions, complete


def update_finicity_coverage(country_codes: list[str], replace: bool = False,
                             dry_run: bool = False) -> None:
    """
    Update finicity.json with market coverage.

    Coverage is merged by default. The scraped endpoint only serves the Open
    Finance *US* portal (US and CA), so it cannot confirm or deny coverage in
    other markets already recorded for Finicity -- dropping them would lose
    real information. Pass --replace-coverage to overwrite instead.
    """
    print("\n=== Updating Finicity Market Coverage ===\n")

    finicity_data = load_json(FINICITY_JSON_PATH)
    existing = finicity_data.get("marketCoverage", {}).get("live", []) or []

    if replace:
        new_coverage = sorted(set(country_codes))
    else:
        new_coverage = sorted(set(existing) | set(country_codes))

    print(f"  Scraped: {', '.join(sorted(country_codes)) or '(none)'}")
    print(f"  Existing: {', '.join(sorted(existing)) or '(none)'}")
    print(f"  Result: {', '.join(new_coverage) or '(none)'}")

    added = set(new_coverage) - set(existing)
    removed = set(existing) - set(new_coverage)
    if added:
        print(f"  Added countries: {', '.join(sorted(added))}")
    if removed:
        print(f"  Removed countries: {', '.join(sorted(removed))}")
    if not added and not removed:
        print("  No changes to market coverage.")
        return

    if dry_run:
        print("  [dry-run] finicity.json not written")
        return

    finicity_data["marketCoverage"] = {"live": new_coverage}
    save_json(FINICITY_JSON_PATH, finicity_data)


def add_finicity_to_existing_provider(provider_path: Path, dry_run: bool = False) -> bool:
    """Add `finicity` to an existing provider's apiAggregators. Returns True if changed."""
    provider = load_json(provider_path)

    aggregators = provider.get("apiAggregators") or []
    if "finicity" in aggregators:
        return False

    if dry_run:
        return True

    aggregators.append("finicity")
    aggregators.sort()
    provider["apiAggregators"] = aggregators
    save_json(provider_path, provider)
    return True


def prune_incompatible_tags(markets: list[str],
                            provider_countries: dict[str, set[str]],
                            dry_run: bool = False) -> list[str]:
    """
    Remove `finicity` from providers no Open Finance US market can reach.

    The first run of this scraper matched on name alone and tagged Barclays
    (GB), Chase (GB), Citibank (CO) and ACB (VN) among others. The country gate
    stops new ones; this clears the ones already written. It only ever removes
    tags that contradict the endpoint's own markets, so a provider with no
    country data keeps its tag.
    """
    allowed = expand_countries(markets)
    removed: list[str] = []

    for path in sorted(ACCOUNT_PROVIDERS_PATH.glob("*.json")):
        known = provider_countries.get(path.stem)
        if not known or known & allowed:
            continue

        provider = load_json(path)
        aggregators = provider.get("apiAggregators") or []
        if "finicity" not in aggregators:
            continue

        removed.append(path.stem)
        if dry_run:
            continue

        provider["apiAggregators"] = sorted(a for a in aggregators if a != "finicity")
        save_json(path, provider)

    prefix = "[dry-run] " if dry_run else ""
    if removed:
        print(f"\n  {prefix}Untagged {len(removed)} providers outside "
              f"{'/'.join(sorted(allowed - US_TERRITORIES))}:")
        for provider_id in removed:
            print(f"    - {provider_id} ({'/'.join(sorted(provider_countries[provider_id]))})")
    else:
        print("\n  No country-incompatible finicity tags to remove")
    return removed


def update_bank_providers(all_institutions: dict[str, list[dict]],
                          dry_run: bool = False, verbose: bool = False,
                          prune: bool = True) -> list[dict]:
    """
    Tag matching account providers with the `finicity` aggregator.

    This scraper deliberately does NOT create new provider files. `schema.json`
    requires `icon` and `websiteUrl` to be non-null URL strings, and the
    Supported Institutions endpoint returns neither -- it only exposes an ID, a
    display name and product flags. Generating stubs would either fail
    `npm run validate-providers` (which all 57k existing providers currently
    pass) or require inventing a domain per bank.

    Institutions with no match are returned so they can be written out for
    review and added deliberately with real metadata.
    """
    print("\n=== Updating Bank Providers ===\n")

    # Collapse connection variants onto one provider slug, merging countries.
    by_slug: dict[str, dict] = {}
    for institutions in all_institutions.values():
        for institution in institutions:
            if not institution["normalized_name"]:
                continue
            slug = slugify(institution["normalized_name"])
            if not slug:
                continue
            entry = by_slug.setdefault(slug, {
                "normalized_name": institution["normalized_name"],
                "countries": set(),
                "finicity_ids": [],
                "names": set(),
                "products": set(),
            })
            entry["countries"].update(institution["countries"])
            entry["finicity_ids"].append(institution["institution_id"])
            entry["names"].add(institution["name"])
            entry["products"].update(institution["products"])

    total_connections = sum(len(v) for v in all_institutions.values())
    print(f"Collapsed {total_connections} connections into {len(by_slug)} institutions")

    existing_ids = get_existing_provider_ids()
    canonical_index = build_canonical_index(existing_ids)
    provider_countries = build_provider_countries()
    print(f"Found {len(existing_ids)} existing account providers")

    updated_count = 0
    skipped_count = 0
    unmatched: list[dict] = []

    for slug, entry in sorted(by_slug.items()):
        countries = sorted(entry["countries"])
        matching_id = find_provider_match(slug, countries, existing_ids,
                                          canonical_index, provider_countries)

        if matching_id:
            provider_path = ACCOUNT_PROVIDERS_PATH / f"{matching_id}.json"
            if add_finicity_to_existing_provider(provider_path, dry_run):
                updated_count += 1
                if verbose:
                    target = f" -> {matching_id}.json" if matching_id != slug else ""
                    print(f"  Updated: {entry['normalized_name']}{target}")
            else:
                skipped_count += 1
        else:
            unmatched.append({
                "suggested_id": slug,
                "name": entry["normalized_name"],
                "countries": countries,
                "finicity_ids": sorted(entry["finicity_ids"]),
                "connection_names": sorted(entry["names"]),
                "products": sorted(entry["products"]),
            })
            if verbose:
                print(f"  Unmatched: {entry['normalized_name']} ({slug})")

    prefix = "[dry-run] " if dry_run else ""
    print(f"\nSummary:")
    print(f"  {prefix}{updated_count} providers tagged with finicity")
    print(f"  {skipped_count} already had finicity (no changes needed)")
    print(f"  {len(unmatched)} institutions had no matching provider")

    if prune:
        prune_incompatible_tags(sorted(all_institutions), provider_countries, dry_run)

    return unmatched


def save_unmatched(unmatched: list[dict], dry_run: bool = False) -> None:
    """Write institutions with no matching provider for manual review."""
    if not unmatched:
        return
    if dry_run:
        print(f"\n[dry-run] {len(unmatched)} unmatched institutions not written")
        return

    SCRAPED_DATA_PATH.mkdir(parents=True, exist_ok=True)
    path = SCRAPED_DATA_PATH / "finicity-unmatched.json"
    save_json(path, {
        "note": (
            "Finicity institutions with no matching account provider. This scraper does "
            "not auto-create providers because schema.json requires non-null `icon` and "
            "`websiteUrl`, which the Supported Institutions endpoint does not return. "
            "Add these deliberately with real metadata."
        ),
        "source_url": DOCS_URL,
        "generated_at": datetime.now().isoformat(),
        "count": len(unmatched),
        "institutions": sorted(unmatched, key=lambda i: i["suggested_id"]),
    })
    print(f"Saved {len(unmatched)} unmatched institutions to {path}")


def save_scraped_data(all_institutions: dict[str, list[dict]], dry_run: bool = False) -> None:
    """Save the scraped data and Finicity ID mappings for reference."""
    if dry_run:
        print("\n[dry-run] scraped-data not written")
        return

    SCRAPED_DATA_PATH.mkdir(parents=True, exist_ok=True)

    output = {
        "source": "Mastercard Open Finance US - Supported Institutions",
        "source_url": DOCS_URL,
        "api_url": API_URL,
        "scraped_at": datetime.now().isoformat(),
        "products": {
            abbreviation: title for _, abbreviation, title in PRODUCT_FIELDS
        },
        "markets": {},
    }

    for code in sorted(all_institutions):
        institutions = sorted(all_institutions[code], key=lambda i: i["institution_id"])
        output["markets"][code] = {
            "country_name": COUNTRY_NAMES.get(code, code),
            "institution_count": len(institutions),
            "institutions": [
                {
                    "institution_id": i["institution_id"],
                    "name": i["name"],
                    "products": i["products"],
                }
                for i in institutions
            ],
        }

    coverage_path = SCRAPED_DATA_PATH / "finicity-coverage.json"
    save_json(coverage_path, output)
    print(f"\nSaved scraped data to {coverage_path}")

    # Map provider slug -> the Finicity connection IDs that roll up into it.
    id_mappings: dict[str, dict] = {}
    for institutions in all_institutions.values():
        for institution in institutions:
            slug = slugify(institution["normalized_name"])
            if not slug:
                continue
            mapping = id_mappings.setdefault(slug, {
                "name": institution["normalized_name"],
                "finicity_ids": [],
                "connection_names": [],
                "countries": [],
                "products": [],
            })
            mapping["finicity_ids"].append(institution["institution_id"])
            if institution["name"] not in mapping["connection_names"]:
                mapping["connection_names"].append(institution["name"])
            for country in institution["countries"]:
                if country not in mapping["countries"]:
                    mapping["countries"].append(country)
            for product in institution["products"]:
                if product not in mapping["products"]:
                    mapping["products"].append(product)

    for mapping in id_mappings.values():
        mapping["finicity_ids"].sort()
        mapping["countries"].sort()
        mapping["products"].sort()

    mappings_path = SCRAPED_DATA_PATH / "finicity-institution-ids.json"
    save_json(mappings_path, dict(sorted(id_mappings.items())))
    print(f"Saved institution ID mappings to {mappings_path}")


def load_cached_institutions() -> Optional[dict[str, list[dict]]]:
    """Rebuild the institution data from a previous run's scraped-data file."""
    coverage_path = SCRAPED_DATA_PATH / "finicity-coverage.json"
    if not coverage_path.exists():
        print(f"Error: no cached data at {coverage_path}")
        return None

    data = load_json(coverage_path)
    print(f"Loaded cached data scraped at {data.get('scraped_at')}")

    all_institutions: dict[str, list[dict]] = {}
    for code, market in data.get("markets", {}).items():
        for institution in market.get("institutions", []):
            name = institution["name"]
            all_institutions.setdefault(code, []).append({
                "institution_id": institution["institution_id"],
                "name": name,
                "normalized_name": normalize_institution_name(name),
                "countries": [code],
                "products": institution.get("products", []),
            })
    return all_institutions


def main():
    parser = argparse.ArgumentParser(
        description="Scrape Finicity (Mastercard Open Finance) supported institutions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full run
  python3 scrapers/finicity_scraper.py

  # Preview without writing anything
  python3 scrapers/finicity_scraper.py --dry-run

  # Quick smoke test against the first few pages
  python3 scrapers/finicity_scraper.py --max-pages 3 --dry-run --verbose

  # Re-process the last scrape without hitting the API again
  python3 scrapers/finicity_scraper.py --from-cache

The API is rate limited. If you see repeated INSTITUTIONS_ERROR responses,
wait a few minutes and raise --delay.
""",
    )
    parser.add_argument("--coverage-only", action="store_true",
                        help="Only update market coverage (skip provider updates)")
    parser.add_argument("--skip-providers", action="store_true",
                        help="Skip tagging account provider files")
    parser.add_argument("--replace-coverage", action="store_true",
                        help="Replace marketCoverage instead of merging with existing")
    parser.add_argument("--from-cache", action="store_true",
                        help="Reuse scraped-data/finicity/finicity-coverage.json")
    parser.add_argument("--max-pages", type=int,
                        help="Stop after N pages per country (for testing)")
    parser.add_argument("--delay", type=float, default=REQUEST_DELAY,
                        help=f"Seconds between requests (default: {REQUEST_DELAY})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be done without writing files")
    parser.add_argument("--verbose", action="store_true",
                        help="Log every created/updated provider")
    args = parser.parse_args()

    print("=" * 60)
    print("Finicity (Mastercard Open Finance) Coverage Scraper")
    print("=" * 60)
    if args.dry_run:
        print("\n*** DRY RUN - no files will be written ***")

    complete = True
    if args.from_cache:
        all_institutions = load_cached_institutions()
        if all_institutions is None:
            return 1
    else:
        all_institutions, complete = collect_institutions(args.max_pages, args.delay)

    if not all_institutions:
        print("\nNo institutions found. Aborting without changes.")
        return 1

    if not complete:
        print("\n*** Scrape is INCOMPLETE - coverage and scraped-data will not be written. ***")
        print("*** Provider tagging still runs; it is additive and safe on partial data. ***")

    update_finicity_coverage(
        sorted(all_institutions.keys()),
        replace=args.replace_coverage,
        dry_run=args.dry_run or not complete,
    )

    if not args.coverage_only and not args.skip_providers:
        # Pruning compares existing tags against the markets this run saw, so it
        # is only safe once every page has been fetched.
        unmatched = update_bank_providers(all_institutions, args.dry_run,
                                          args.verbose, prune=complete)
        save_unmatched(unmatched, args.dry_run or not complete)

    if args.from_cache:
        pass
    elif complete:
        save_scraped_data(all_institutions, args.dry_run)
    else:
        print("\nSkipping scraped-data write (incomplete scrape)")

    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
