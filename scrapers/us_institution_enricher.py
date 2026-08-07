#!/usr/bin/env python3
"""
US Institution Enricher

Turns a scraper's "unmatched institutions" file into real account providers by
resolving each name against authoritative US regulator data.

`schema.json` requires non-null `icon` and `websiteUrl`, which aggregator APIs
generally do not provide. Rather than guessing a domain per bank, this script
looks each institution up in the regulator's own registry and uses the website
that regulator publishes:

- Banks:          FDIC BankFind API      (NAME, CITY, STALP, WEBADDR, CERT)
- Credit unions:  NCUA quarterly Call Report data for identity, then the NCUA
                  Research-a-Credit-Union detail endpoint for the website

An institution is only created when the match is unambiguous. Where a name
carries a state hint ("1st National Bank (KS)"), that hint must AGREE with the
registry record -- a single candidate in the wrong state is rejected, not
accepted. Everything unresolved is reported, never guessed.

Repeatable: reference data and resolved websites are cached under
`scraped-data/reference/`, and the script is idempotent -- providers that
already exist are skipped, so re-running after a new scrape only adds what is
genuinely new.

Usage:
    python3 scrapers/us_institution_enricher.py --dry-run
    python3 scrapers/us_institution_enricher.py
"""

import argparse
import collections
import csv
import io
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from plaid_scraper import (
    ACCOUNT_PROVIDERS_PATH,
    get_existing_provider_ids,
    load_json,
    save_json,
    slugify,
)
from finicity_scraper import build_canonical_index, find_provider_match

BASE_PATH = Path(__file__).parent.parent
SCRAPED_DATA_PATH = BASE_PATH / "scraped-data"
REFERENCE_PATH = SCRAPED_DATA_PATH / "reference"
DEFAULT_UNMATCHED = SCRAPED_DATA_PATH / "finicity" / "finicity-unmatched.json"

FDIC_URL = (
    "https://api.fdic.gov/banks/institutions"
    "?filters=ACTIVE:1&fields=NAME,CITY,STALP,WEBADDR,CERT&limit=10000&format=json"
)
NCUA_ZIP_URL = "https://ncua.gov/files/publications/analysis/call-report-data-{quarter}.zip"
NCUA_DETAIL_URL = "https://mapping.ncua.gov/api/CreditUnionDetails/GetCreditUnionDetails/{charter}"

REQUEST_TIMEOUT = 180
NCUA_DETAIL_DELAY = 0.3
MAX_RETRIES = 4

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

STATES = set(
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS "
    "MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI "
    "WY PR VI GU AS MP".split()
)

# NCUA stores credit union names with the "credit union" part removed
# ("1ST COMMUNITY", not "1st Community Federal Credit Union"), so both sides are
# stripped before comparison.
CU_TAIL_RE = re.compile(r"\b(federal\s+credit\s+union|credit\s+union|fcu|fscu|cu)\b\s*$", re.I)
NOISE_RE = re.compile(r"\b(the|inc|incorporated|na|n a|company|co)\b", re.I)
PAREN_RE = re.compile(r"\([^)]*\)")


def http_get(url: str, data: Optional[bytes] = None, timeout: int = REQUEST_TIMEOUT) -> Optional[bytes]:
    """GET (or POST when data is given) with retries."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"

    delay = 3
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            request = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except Exception as e:  # noqa: BLE001 - network errors are retryable
            if attempt == MAX_RETRIES:
                print(f"  Error fetching {url}: {e}")
                return None
            time.sleep(delay)
            delay *= 2
    return None


# --------------------------------------------------------------------------
# Name normalisation and matching
# --------------------------------------------------------------------------

def state_hint(name: str) -> Optional[str]:
    """
    Pull a US state code out of a display name.

    "Arsenal Credit Union (MO)"  -> "MO"
    "1st National Bank(Lebanon, OH)" -> "OH"
    "Commonwealth One FCU, VA"   -> "VA"
    """
    candidates: list[str] = []
    parenthetical = re.search(r"\(([^)]*)\)\s*$", name)
    if parenthetical:
        candidates += re.findall(r"\b([A-Z]{2})\b", parenthetical.group(1).upper())
    trailing = re.search(r",\s*([A-Za-z]{2})\s*$", name)
    if trailing:
        candidates.append(trailing.group(1).upper())

    for candidate in candidates:
        if candidate in STATES:
            return candidate
    return None


def normalize_name(name: str, drop_credit_union: bool = False) -> str:
    """Reduce a name to a comparable form."""
    text = PAREN_RE.sub(" ", name.lower())
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = NOISE_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()

    if drop_credit_union:
        previous = None
        while previous != text:
            previous = text
            text = CU_TAIL_RE.sub("", text).strip()
    return text


def normalize_website(raw: Optional[str]) -> Optional[str]:
    """
    Turn a registry website value into a schema-valid URL.

    Registry values are inconsistent: "www.ergobank.com",
    "http://www.PORTAGECOUNTYBANK.COM", "WWW.BANKWITH1ST.COM".
    """
    if not raw:
        return None
    value = raw.strip()
    if not value or value.lower() in {"n/a", "na", "none", "null"}:
        return None

    if not re.match(r"^https?://", value, re.I):
        value = f"https://{value}"

    parsed = urllib.parse.urlsplit(value)
    host = (parsed.netloc or "").lower().strip()
    if not host or "." not in host:
        return None
    # Reject anything that is not a plausible hostname.
    if not re.match(r"^[a-z0-9.\-]+$", host):
        return None

    path = parsed.path.rstrip("/")
    return f"https://{host}{path}" if path else f"https://{host}/"


def website_host(url: str) -> str:
    return urllib.parse.urlsplit(url).netloc.lower().removeprefix("www.")


# --------------------------------------------------------------------------
# Reference data
# --------------------------------------------------------------------------

def load_fdic(refresh: bool = False) -> list[dict]:
    """Active FDIC-insured banks with a published website."""
    REFERENCE_PATH.mkdir(parents=True, exist_ok=True)
    cache = REFERENCE_PATH / "fdic-institutions.json"

    if cache.exists() and not refresh:
        payload = load_json(cache)
    else:
        print("Fetching FDIC BankFind institutions...")
        raw = http_get(FDIC_URL)
        if raw is None:
            print("  FDIC fetch failed; continuing without bank reference data")
            return []
        payload = json.loads(raw)
        save_json(cache, payload)
        print(f"  Cached FDIC data to {cache}")

    banks = []
    for row in payload.get("data", []):
        record = row.get("data", {})
        website = normalize_website(record.get("WEBADDR"))
        if not website:
            continue
        banks.append({
            "kind": "bank",
            "name": (record.get("NAME") or "").strip(),
            "state": (record.get("STALP") or "").strip().upper(),
            "city": (record.get("CITY") or "").strip(),
            "website": website,
            "source": "FDIC",
            "source_id": record.get("CERT"),
        })
    print(f"  FDIC: {len(banks)} active banks with a website")
    return banks


def load_ncua(refresh: bool = False) -> list[dict]:
    """Active federally insured credit unions (identity only; website resolved later)."""
    REFERENCE_PATH.mkdir(parents=True, exist_ok=True)
    cache = REFERENCE_PATH / "ncua-credit-unions.json"

    if cache.exists() and not refresh:
        credit_unions = load_json(cache)
        print(f"  NCUA: {len(credit_unions)} credit unions (cached)")
        return credit_unions

    print("Fetching NCUA call report data...")
    raw = None
    now = datetime.now()
    # Walk back through recent quarters until one downloads. NCUA names these
    # files by quarter END month (03, 06, 09, 12), and the most recent quarter
    # is not published until well after it closes.
    quarters = []
    year, month = now.year, ((now.month - 1) // 3 + 1) * 3
    for _ in range(6):
        quarters.append(f"{year}-{month:02d}")
        month -= 3
        if month < 1:
            month += 12
            year -= 1

    for quarter in quarters:
        raw = http_get(NCUA_ZIP_URL.format(quarter=quarter))
        if raw and raw[:2] == b"PK":
            print(f"  Using quarter {quarter}")
            break
        raw = None

    if raw is None:
        print("  NCUA fetch failed; continuing without credit union reference data")
        return []

    credit_unions = []
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        name = next((n for n in archive.namelist() if n.upper().endswith("FOICU.TXT")), None)
        if not name:
            print("  FOICU.txt not found in NCUA archive")
            return []
        text = archive.read(name).decode("latin-1")

    for row in csv.DictReader(io.StringIO(text)):
        charter = (row.get("CU_NUMBER") or "").strip()
        cu_name = (row.get("CU_NAME") or "").strip()
        if not charter or not cu_name:
            continue
        credit_unions.append({
            "kind": "credit-union",
            "name": cu_name,
            "state": (row.get("STATE") or "").strip().upper(),
            "city": (row.get("CITY") or "").strip(),
            "website": None,
            "source": "NCUA",
            "source_id": charter,
        })

    save_json(cache, credit_unions)
    print(f"  NCUA: {len(credit_unions)} credit unions cached to {cache}")
    return credit_unions


def load_website_cache() -> dict:
    path = REFERENCE_PATH / "ncua-websites.json"
    return load_json(path) if path.exists() else {}


def save_website_cache(cache: dict) -> None:
    REFERENCE_PATH.mkdir(parents=True, exist_ok=True)
    save_json(REFERENCE_PATH / "ncua-websites.json", cache)


def resolve_credit_union_website(charter: str, cache: dict) -> Optional[str]:
    """Look up a credit union's website, caching both hits and misses."""
    if charter in cache:
        return cache[charter]

    raw = http_get(NCUA_DETAIL_URL.format(charter=charter), timeout=60)
    website = None
    if raw:
        try:
            website = normalize_website(json.loads(raw).get("creditUnionWebsite"))
        except Exception:  # noqa: BLE001 - a bad payload is just a miss
            website = None

    cache[charter] = website
    time.sleep(NCUA_DETAIL_DELAY)
    return website


def build_reference_index(records: list[dict]) -> dict[str, list[dict]]:
    index: dict[str, list[dict]] = collections.defaultdict(list)
    for record in records:
        drop = record["kind"] == "credit-union"
        index[normalize_name(record["name"], drop_credit_union=drop)].append(record)
    return index


def match_institution(name: str, bank_index: dict, cu_index: dict) -> Optional[dict]:
    """
    Resolve a display name to exactly one registry record, or None.

    A state hint must AGREE with the candidate. Accepting a lone candidate in a
    contradicting state is how "1st National Bank (KS)" ends up pointing at an
    Ohio bank's website.
    """
    hint = state_hint(name)

    for index, drop in ((bank_index, False), (cu_index, True)):
        candidates = index.get(normalize_name(name, drop_credit_union=drop), [])
        if not candidates:
            continue
        if hint:
            candidates = [c for c in candidates if c["state"] == hint]
        if len(candidates) == 1:
            return candidates[0]
    return None


# --------------------------------------------------------------------------
# Provider creation
# --------------------------------------------------------------------------

def build_provider(provider_id: str, display_name: str, record: dict,
                   aggregator: str) -> dict:
    website = record["website"]
    host = urllib.parse.urlsplit(website).netloc.lower()
    bank_type = "credit-union" if record["kind"] == "credit-union" else "retail"

    return {
        "id": provider_id,
        "type": ["account"],
        "bankType": [bank_type],
        "name": display_name,
        # FDIC publishes a full legal name; NCUA stores an upper-case name with
        # the "credit union" part stripped ("ADVANCIAL"), which is worse than
        # recording nothing.
        "legalName": record["name"] if record["kind"] == "bank" else None,
        "verified": False,
        "status": "live",
        "icon": f"https://icons.duckduckgo.com/ip3/{host}.ico",
        "websiteUrl": website,
        "countryHQ": "US",
        "countries": ["US"],
        "webApplication": True,
        "mobileApps": [],
        "compliance": [],
        "developerPortalUrl": None,
        "apiStandards": [],
        "apiProducts": [],
        "apiAggregators": [aggregator],
        "ownership": [],
        "stateOwned": False,
        "stockSymbol": None,
    }


def display_name_for(institution: dict, record: dict) -> str:
    """
    Pick the better-looking of the two available names.

    FDIC names are properly cased and complete ("Adams Bank & Trust"), so they
    win. NCUA names are upper case with the "credit union" part stripped
    ("1ST COMMUNITY"), so the aggregator's own display name is kept there.
    """
    if record["kind"] == "bank":
        return PAREN_RE.sub("", record["name"]).strip() or institution["name"]
    return institution["name"]


def squash_id(provider_id: str) -> str:
    """
    Match `normalizeId` in scripts/detect-duplicate-providers.js.

    The repo treats IDs as duplicates when they differ only by separators
    ("first-state-bank" vs "firststate-bank"), and the pre-commit hook rejects
    the commit. Creating one of those is a guaranteed broken commit, so the
    enricher applies the same rule up front.
    """
    return re.sub(r"[-_\s]", "", provider_id.lower())


def build_squash_index(existing_ids: set[str]) -> dict[str, str]:
    index: dict[str, str] = {}
    for provider_id in existing_ids:
        index.setdefault(squash_id(provider_id), provider_id)
    return index


def build_domain_index() -> dict[str, str]:
    """Map website host -> existing provider ID, to catch same-bank-different-name."""
    index: dict[str, str] = {}
    for path in ACCOUNT_PROVIDERS_PATH.glob("*.json"):
        try:
            provider = load_json(path)
        except Exception:  # noqa: BLE001 - skip unreadable files
            continue
        url = provider.get("websiteUrl")
        if not isinstance(url, str) or not url.startswith("http"):
            continue
        host = website_host(url)
        if host:
            index.setdefault(host, path.stem)
    return index


def main():
    parser = argparse.ArgumentParser(
        description="Create account providers for unmatched institutions using FDIC/NCUA data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scrapers/us_institution_enricher.py --dry-run
  python3 scrapers/us_institution_enricher.py --limit 50 --verbose
  python3 scrapers/us_institution_enricher.py --refresh-reference
""",
    )
    parser.add_argument("--unmatched-file", type=Path, default=DEFAULT_UNMATCHED,
                        help=f"Unmatched institutions JSON (default: {DEFAULT_UNMATCHED})")
    parser.add_argument("--aggregator", default="finicity",
                        help="Aggregator ID to record on created providers (default: finicity)")
    parser.add_argument("--refresh-reference", action="store_true",
                        help="Re-download FDIC/NCUA reference data instead of using the cache")
    parser.add_argument("--limit", type=int, help="Process only the first N institutions")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be created without writing files")
    parser.add_argument("--verbose", action="store_true", help="Log every decision")
    args = parser.parse_args()

    print("=" * 60)
    print("US Institution Enricher")
    print("=" * 60)
    if args.dry_run:
        print("\n*** DRY RUN - no files will be written ***")

    if not args.unmatched_file.exists():
        print(f"\nError: {args.unmatched_file} not found.")
        print("Run the aggregator's scraper first to generate it.")
        return 1

    institutions = load_json(args.unmatched_file).get("institutions", [])
    if args.limit:
        institutions = institutions[:args.limit]
    print(f"\nLoaded {len(institutions)} unmatched institutions")

    print("\n=== Reference Data ===\n")
    banks = load_fdic(args.refresh_reference)
    credit_unions = load_ncua(args.refresh_reference)
    if not banks and not credit_unions:
        print("\nNo reference data available. Aborting without changes.")
        return 1

    bank_index = build_reference_index(banks)
    cu_index = build_reference_index(credit_unions)

    print("\n=== Matching ===\n")
    existing_ids = get_existing_provider_ids()
    canonical_index = build_canonical_index(existing_ids)
    domain_index = build_domain_index()
    squash_index = build_squash_index(existing_ids)
    website_cache = load_website_cache()
    print(f"Indexed {len(existing_ids)} providers ({len(domain_index)} with a website)")

    created: list[tuple[str, str, str]] = []
    stats = collections.Counter()
    unresolved: list[dict] = []
    batch_slugs: set[str] = set()
    batch_hosts: set[str] = set()

    try:
        for institution in institutions:
            name = institution["name"]
            record = match_institution(name, bank_index, cu_index)

            if record is None:
                stats["no_registry_match"] += 1
                unresolved.append({"name": name, "reason": "no unambiguous registry match"})
                continue

            if record["kind"] == "credit-union" and not record["website"]:
                record = dict(record)
                record["website"] = resolve_credit_union_website(record["source_id"], website_cache)

            if not record["website"]:
                stats["no_website"] += 1
                unresolved.append({"name": name, "reason": "registry has no website"})
                continue

            display_name = display_name_for(institution, record)
            provider_id = slugify(display_name)
            if not provider_id:
                stats["bad_slug"] += 1
                continue

            existing = (find_provider_match(provider_id, ["US"], existing_ids, canonical_index)
                        or squash_index.get(squash_id(provider_id)))
            if existing:
                stats["already_exists"] += 1
                unresolved.append({
                    "name": name,
                    "reason": f"collides with existing provider {existing}",
                })
                if args.verbose:
                    print(f"  Exists:  {display_name} -> {existing}.json")
                continue

            host = website_host(record["website"])
            if host in domain_index:
                stats["duplicate_domain"] += 1
                if args.verbose:
                    print(f"  Dup URL: {display_name} -> {domain_index[host]}.json ({host})")
                continue
            if provider_id in batch_slugs or host in batch_hosts:
                stats["duplicate_in_batch"] += 1
                continue

            provider = build_provider(provider_id, display_name, record, args.aggregator)
            if not args.dry_run:
                save_json(ACCOUNT_PROVIDERS_PATH / f"{provider_id}.json", provider)

            existing_ids.add(provider_id)
            canonical_index.setdefault(provider_id, provider_id)
            squash_index.setdefault(squash_id(provider_id), provider_id)
            batch_slugs.add(provider_id)
            batch_hosts.add(host)
            domain_index[host] = provider_id
            created.append((provider_id, display_name, record["source"]))
            stats[f"created_{record['kind']}"] += 1
            if args.verbose:
                print(f"  Created: {display_name} ({provider_id}.json) <- {record['source']}")
    finally:
        # Always persisted, including on --dry-run: this is a gitignored lookup
        # cache under scraped-data/, not repo data, and saving it means a dry
        # run followed by a real run does not repeat ~700 NCUA requests.
        save_website_cache(website_cache)

    prefix = "[dry-run] " if args.dry_run else ""
    print("\n=== Summary ===\n")
    print(f"  {prefix}{stats['created_bank']} banks created (FDIC)")
    print(f"  {prefix}{stats['created_credit-union']} credit unions created (NCUA)")
    print(f"  {stats['already_exists']} already exist as providers")
    print(f"  {stats['duplicate_domain']} skipped: website already used by another provider")
    print(f"  {stats['duplicate_in_batch']} skipped: duplicate within this batch")
    print(f"  {stats['no_website']} skipped: registry has no website")
    print(f"  {stats['no_registry_match']} skipped: no unambiguous registry match")
    print(f"\n  {len(created)} providers {'would be' if args.dry_run else ''} created in total")

    if not args.dry_run and unresolved:
        report = args.unmatched_file.parent / "still-unresolved.json"
        save_json(report, {
            "note": (
                "Institutions that could not be resolved to an FDIC or NCUA record with a "
                "published website. These need manual research; nothing here was guessed."
            ),
            "generated_at": datetime.now().isoformat(),
            "count": len(unresolved),
            "institutions": unresolved,
        })
        print(f"  Wrote {len(unresolved)} unresolved institutions to {report}")

    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
