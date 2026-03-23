# [Open Banking Tracker](https://www.openbankingtracker.com/)

<img src="https://github.com/apideck-io/open-banking-tracker-data/blob/master/images/screenshot.png">

This repository holds all the providers displayed in the tracker.

[Open Banking Tracker](https://www.openbankingtracker.com/) shows whether large institutions, such as Deutsche Bank, HSBC, Citi, and many more, have the correct infrastructure in place to be adequately prepared for the upcoming change in the regulatory environment as we will be tracking over 30 data points per organization (Sandboxes, AIS, PIS, APIs, Data breaches, iOS, and Android usage, etc.). In regards to PSD2 and Open Banking, registered financial institutions are required to have developer sandboxes (area for developers to test their programs) and relevant APIs in place to promote transparency and freedom of data.

Our goal, through this project, is to bring more transparency throughout the industry as well as empower developers and customers to choose the right partner to help support their growth. We will encourage that by sharing insights and reports in the future based on the analytics we generate.

## How to Contribute

### Adding an Account Provider (Bank / Financial Institution)

See the [contribution guidelines](https://github.com/apideck-io/open-banking-tracker-data/blob/master/CONTRIBUTING.md) for how to add a bank or financial institution.

### Adding an API Aggregator (Open Banking API Provider)

If you are an Open Banking API provider (like Plaid, Tink, GoCardless, etc.), follow these steps to add your platform to the tracker.

#### 1. Create Your Aggregator File

Create `data/api-aggregators/<your-id>.json` with your profile:

```json
{
  "id": "your-company",
  "label": "Your Company",
  "website": "https://yourcompany.com/",
  "iconUrl": "https://res.cloudinary.com/apideck/icons/your-company",
  "developerPortalUrl": "https://docs.yourcompany.com/",
  "countryHQ": "US",
  "verified": false,
  "description": "One-line description of what your platform does and where",
  "marketFocus": "Europe and North America",
  "marketCoverage": {
    "live": ["DE", "FR", "GB", "NL", "US"]
  }
}
```

Your `id` must be lowercase alphanumeric with hyphens only.

#### 2. Declare Your Market Coverage

The `marketCoverage` field is how the tracker knows which countries you support. Without it, your listing has no geographic footprint.

```json
{
  "marketCoverage": {
    "live": ["US", "GB", "DE", "FR", "NL"],
    "upcoming": ["AU", "BR"]
  }
}
```

- Use **ISO 3166-1 alpha-2** country codes (e.g., `US`, `GB`, `DE`)
- `live` — countries where your integration is production-ready
- `upcoming` — countries you're actively working on

#### 3. Register Your ID in the Schema

Add your aggregator ID to the `apiAggregators` enum in [`schema.json`](https://github.com/apideck-io/open-banking-tracker-data/blob/master/schema.json) so that bank records can reference you. The enum is alphabetically sorted.

#### 4. Tag the Banks You Cover

For every bank your platform supports, add your ID to that bank's `apiAggregators` array in `data/account-providers/<bank>.json`:

```json
{
  "apiAggregators": ["plaid", "tink", "your-company"]
}
```

This is **required** — it is the core data that links aggregators to banks in the tracker.

#### 5. Build a Scraper to Keep Coverage in Sync

Coverage data goes stale fast. We strongly recommend building a scraper that keeps your listing and bank-level tags in sync with your actual coverage.

The `scrapers/` directory contains examples you can reference:

| Scraper | Source |
|---|---|
| `plaid_scraper.py` | Plaid API + docs |
| `gocardless_scraper.py` | GoCardless institution list |
| `flinks_scraper.py` | Flinks coverage page |

Your scraper should:

1. **Fetch your live country list** from your API or docs and update `marketCoverage` in your aggregator JSON
2. **Fetch your supported institutions** and update each bank's `apiAggregators` array to include your ID
3. **Match institutions to provider files** using BIC/SWIFT codes (most reliable), filename slugs, or a manual mapping file

Register it in `package.json`:

```json
{
  "scripts": {
    "scrape:yourcompany": "python3 scrapers/yourcompany_scraper.py"
  }
}
```

Run your scraper before each PR and on a monthly cadence at minimum.

#### Checklist

- [ ] Created `data/api-aggregators/<your-id>.json` with all required fields
- [ ] Added `marketCoverage.live` with accurate ISO country codes
- [ ] Added your ID to the `apiAggregators` enum in `schema.json`
- [ ] Updated relevant bank files' `apiAggregators` arrays to include your ID
- [ ] Ran `npm run validate-aggregators` — passes
- [ ] Ran `npm run validate-links` — all URLs resolve
- [ ] (Recommended) Built a scraper to keep coverage in sync
- [ ] Opened a PR against `master`

## Format

We use JSON Schema to validate the data and to maintain a high level of data quality. Please find the schemas at:
- [Account Provider & Third-Party Schema](https://github.com/apideck-io/open-banking-tracker-data/blob/master/schema.json)
- [API Aggregator Schema](https://github.com/apideck-io/open-banking-tracker-data/blob/master/api-aggregators-schema.json)

## Data Validation

All data is automatically validated to ensure quality and consistency. We have comprehensive validation at three levels:

### Local Validation (Before Commit)

Validate all data locally before pushing:

```bash
npm install
npm run validate-data
```

This validates both account providers and API aggregators against their schemas.

### Specific Type Validation

Validate a specific data type:

```bash
# Validate account and third-party providers only
npm run validate-providers

# Validate API aggregators only
npm run validate-aggregators
```

### Available npm Scripts

```json
{
  "validate-data": "Validate all data files (providers + aggregators)",
  "validate-providers": "Validate account and third-party providers only",
  "validate-aggregators": "Validate API aggregators only"
}
```

## Removal

We only show publicly available data and try to verify as much data as possible.
If you want to be removed from the tracker, send in a pull request with the reason stated.

## License

Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0). Please see the [license file](https://github.com/apideck-io/open-banking-tracker-data/blob/master/LICENSE.md) for more information.

Commercial licenses available on request [contact us](mailto:hello@apideck.com)

## About

Made in Belgium 🇧🇪 Europe 🇪🇺

The Open Banking Tracker is created by [Apideck](https://www.apideck.com/).

## Disclaimer

We do our best to ensure that the data we provide is complete, accurate and useful. However, because we do not verify all the data, and because the processing required to make the data useful is complex, we cannot be liable for omissions or inaccuracies.

## Links

* [Open Banking Tracker](https://www.openbankingtracker.com/)
* [Apideck](https://www.apideck.com/)
