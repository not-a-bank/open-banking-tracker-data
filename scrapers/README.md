# Scrapers

This directory contains scrapers for updating API aggregator coverage and account provider data.

## Setup

Install Python dependencies:

```bash
pip install -r scrapers/requirements.txt
```

## Available Scrapers

### Plaid Scraper

Updates Plaid's market coverage and bank provider data.

```bash
npm run scrape:plaid
# or
python3 scrapers/plaid_scraper.py
```

**Features:**
- Updates market coverage in `data/api-aggregators/plaid.json`
- Fetches bank institutions from Plaid API (requires credentials)
- Creates/updates account provider entries with `plaid` in `apiAggregators`
- Saves institution ID mappings to `scrapers/plaid_institution_ids.json`

**Environment Variables:**

Sign up for a free Plaid account at https://dashboard.plaid.com/signup to get API credentials.

Create a `.env` file in the `scrapers/` directory:

```
PLAID_CLIENT_ID=your_client_id
PLAID_SECRET=your_secret
PLAID_ENV=production  # or sandbox
```

Without credentials, only country-level market coverage is updated. With credentials, bank-level data is fetched and providers are created/updated.

**Coverage:** US, CA, and 19 European countries (AT, BE, DE, DK, EE, ES, FI, FR, GB, IE, IT, LT, LV, NL, NO, PL, PT, SE)

---

### Flinks Scraper

Updates Flinks' market coverage and bank provider data by scraping their status page.

```bash
npm run scrape:flinks
# or
python3 scrapers/flinks_scraper.py
```

**Options:**
- `--coverage-only` - Only update market coverage (quick mode)
- `--dry-run` - Show what would be done without making changes

**Features:**
- Scrapes bank data from https://status.flinks.com/
- Updates market coverage in `data/api-aggregators/flinks.json`
- Creates/updates account provider entries with `flinks` in `apiAggregators`

**Coverage:** US, CA

---

### GoCardless Scraper

Updates GoCardless's market coverage and bank provider data by parsing their official coverage spreadsheet.

```bash
npm run scrape:gocardless
# or
python3 scrapers/gocardless_scraper.py
```

**Options:**
- `--csv-file PATH` - Path to CSV file (default: ~/Downloads/GoCardless Bank Account Data Coverage Overview - Coverage.csv)
- `--coverage-only` - Only update market coverage (skip provider updates)
- `--skip-providers` - Skip creating/updating account provider files
- `--dry-run` - Show what would be done without making changes

**Features:**
- Parses the official GoCardless coverage spreadsheet (2400+ institutions)
- Updates market coverage in `data/api-aggregators/gocardless.json`
- Creates/updates account provider entries with `gocardless` in `apiAggregators`
- Saves institution ID mappings to `scraped-data/gocardless/gocardless-institution-ids.json`

**Data Source:**

Download the CSV from the official GoCardless coverage spreadsheet:
https://docs.google.com/spreadsheets/d/1EZ5n7QDGaRIot5M86dwqd5UFSGEDTeTRzEq3D9uEDkM/

1. Open the spreadsheet
2. Go to File > Download > Comma-separated values (.csv)
3. Save to your Downloads folder (or specify path with `--csv-file`)

**Coverage:** AT, BE, BG, CY, CZ, DE, DK, EE, ES, FI, FR, GB, GR, HR, HU, IE, IS, IT, LI, LT, LU, LV, MT, NL, NO, PL, PT, RO, SE, SI, SK (31 European countries)

---

### Pluggy Scraper

Updates Pluggy's coverage data (Brazilian open finance).

```bash
python3 scrapers/pluggy_scraper.py
python3 scrapers/pluggy_scraper.py --update-providers
```

**Features:**
- Scrapes connector data from Pluggy documentation
- Supports both personal and business connectors
- Includes Open Finance regulated institutions

**Coverage:** Brazil, Mexico

---

### Akahu Scraper

Updates Akahu's coverage data (New Zealand open banking).

```bash
python3 scrapers/akahu_scraper.py
python3 scrapers/akahu_scraper.py --update-providers
```

**Features:**
- Scrapes integration data from Akahu developer docs
- Covers banks, investment platforms, and KiwiSaver providers
- Includes major NZ banks: ANZ, ASB, BNZ, Kiwibank, Westpac

**Coverage:** New Zealand

---

### Finverse Scraper

Updates Finverse's coverage data (Asia-Pacific open finance).

```bash
python3 scrapers/finverse_scraper.py
python3 scrapers/finverse_scraper.py --update-providers
```

**Features:**
- Scrapes bank coverage from Finverse website
- Covers 6 Asia-Pacific markets
- Includes major banks in each market

**Coverage:** Hong Kong, Singapore, Malaysia, Philippines, Vietnam, Indonesia

---

### SnapTrade Scraper

Updates SnapTrade's coverage data (investment/brokerage aggregator).

```bash
python3 scrapers/snaptrade_scraper.py
python3 scrapers/snaptrade_scraper.py --update-providers
```

**Features:**
- Fetches brokerage data from SnapTrade's public API
- Includes trading capability information
- Covers brokerages in US, Canada, Europe, Australia

**Coverage:** US, Canada, UK, Australia, and other markets

---

### Tink Scraper

Updates Tink's market coverage and bank provider data.

```bash
python3 scrapers/tink_scraper.py
```

**Options:**
- `--from-csvs DIR` - Parse from downloaded CSV files
- `--from-snapshots DIR` - Parse from browser snapshots
- `--coverage-only` - Only update market coverage
- `--skip-providers` - Skip updating account provider files

**Features:**
- Browser automation via Playwright to download CSV data per market
- Updates market coverage in `data/api-aggregators/tink.json`
- Creates/updates account provider entries with `tink` in `apiAggregators`

**Coverage:** 19 European countries

## Output

Each scraper updates:
1. The aggregator's JSON file in `data/api-aggregators/` with market coverage
2. Account provider files in `data/account-providers/` with the aggregator added to `apiAggregators`

## Adding New Scrapers

When creating a new scraper:
1. Add the Python script to `scrapers/`
2. Add any new dependencies to `scrapers/requirements.txt`
3. Add an npm script to `package.json`
4. Document the scraper in this README
