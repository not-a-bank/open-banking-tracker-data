#!/usr/bin/env python3
"""
YAXI Coverage Scraper

This script updates YAXI's bank providers.

Sources:
- https://docs.yaxi.tech/getting-started.html
"""

import json
import subprocess
from pathlib import Path
from urllib.request import urlopen, Request

from plaid_scraper import load_json, save_json, slugify

BASE_PATH = Path(__file__).parent.parent
ACCOUNT_PROVIDERS_PATH = BASE_PATH / "data" / "account-providers"
CONNECTION_IDS_PATH = Path(__file__).parent / "yaxi_connection_ids.json"

REQUEST_TIMEOUT = 30

def create_account_provider(connection: dict) -> dict:
    name = connection["displayName"]
    bank_id = slugify(name)
    countries = connection["countries"]

    provider = {
        "id": bank_id,
        "type": ["account"],
        "bankType": ["retail"],
        "name": name,
        "legalName": None,
        "verified": False,
        "status": "live",
        "icon": None,
        "websiteUrl": None,
        "countryHQ": None,
        "countries": countries,
        "webApplication": True,
        "mobileApps": [],
        "compliance": [],
        "developerPortalUrl": None,
        "apiStandards": [],
        "apiProducts": [],
        "apiAggregators": ["yaxi"],
        "ownership": [],
        "stateOwned": False,
        "stockSymbol": None
    }

    return provider


def add_to_existing_provider(provider_path: Path) -> bool:
    provider = load_json(provider_path)

    aggregators = provider.get("apiAggregators", [])
    if aggregators is None:
        aggregators = []

    if "yaxi" not in aggregators:
        aggregators.append("yaxi")
        aggregators.sort()
        provider["apiAggregators"] = aggregators
        save_json(provider_path, provider)
        return True

    return False


def update_bank_providers() -> None:
    """Fetch bank data from YAXI API and create/update account providers."""
    print("\n=== Updating Bank Providers ===\n")

    print("Fetching connections from YAXI API...")
    try:
        with urlopen(
            Request(
                url="https://api.yaxi.tech/search",
                headers={"Content-Type": "application/json"},
                data=b'{"filters": [{"term": ""}], "ibanDetection": false}',
            ),
            timeout=REQUEST_TIMEOUT,
        ) as f:
            connections = json.loads(f.read())
    except Exception as e:
        print(f"  Warning: API request failed: {e}")
        return

    print(f"Processing {len(connections)} connections...")

    existing_ids = set()
    for json_file in ACCOUNT_PROVIDERS_PATH.glob("*.json"):
        existing_ids.add(json_file.stem)
    print(f"Found {len(existing_ids)} existing account providers")

    if CONNECTION_IDS_PATH.exists():
        with open(CONNECTION_IDS_PATH, "r", encoding="utf-8") as f:
            id_mappings = json.load(f)
    else:
        id_mappings = {}

    new_count = 0
    updated_count = 0
    skipped_count = 0

    for connection in connections:
        name = connection["displayName"]

        bank_id = slugify(name)

        provider_path = ACCOUNT_PROVIDERS_PATH / f"{bank_id}.json"

        if bank_id in existing_ids:
            if add_to_existing_provider(provider_path):
                updated_count += 1
                if bank_id != bank_id:
                    print(f"  Updated: {name} -> {bank_id}.json (added yaxi)")
                else:
                    print(f"  Updated: {name} (added yaxi)")
            else:
                skipped_count += 1
        else:
            provider = create_account_provider(connection)
            save_json(provider_path, provider)
            existing_ids.add(bank_id)
            new_count += 1
            print(f"  Created: {name} ({bank_id}.json)")
        id_mappings[bank_id] = connection["id"]

    with open(CONNECTION_IDS_PATH, "w", encoding="utf-8") as f:
        json.dump(id_mappings, f, indent=2)
        f.write("\n")
    print(f"Saved {len(id_mappings)} YAXI connection ID mappings")

    print(f"\nSummary: {new_count} new, {updated_count} updated, {skipped_count} already had yaxi")

def main():
    """Main entry point."""
    print("=" * 60)
    print("YAXI Coverage Scraper")
    print("=" * 60)

    update_bank_providers()

    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)


if __name__ == "__main__":
    main()
