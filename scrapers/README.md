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
