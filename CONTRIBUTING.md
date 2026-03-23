# Contributing to the Open Banking Tracker

We use [Github Flow](https://guides.github.com/introduction/flow/index.html), so all changes happen through pull requests. We actively welcome your pull requests.

1. Fork the repo and create your branch from `master`
2. Add or update the relevant data files
3. Ensure your data validates against the schema
4. Run the test suite
5. Open a pull request

## Adding an Account Provider (Bank / Financial Institution)

Add a file named `data/account-providers/<provider-id>.json`. Your data must follow the [account provider schema](https://github.com/apideck-io/open-banking-tracker-data/blob/master/schema.json).

If you're unsure about certain data points, leave them out or check with the company offering the service.

### Example

```json
{
  "id": "hsbc",
  "type": ["account"],
  "bankType": ["universal"],
  "name": "HSBC",
  "legalName": "HSBC Holdings plc",
  "ipoStatus": "public",
  "verified": false,
  "icon": "https://res.cloudinary.com/banq/image/upload/v1552239844/radar/icons/hsbc.svg",
  "websiteUrl": "https://www.hsbc.com/",
  "ownership": [],
  "stateOwned": false,
  "thirdPartyBankingLicense": null,
  "countryHQ": "GB",
  "countries": ["EU"],
  "compliance": [
    { "regulation": "PSD2", "status": "inProgress" },
    { "regulation": "OB", "status": "ready" },
    { "regulation": "GDPR", "status": "unknown" }
  ],
  "sandbox": {
    "status": "available",
    "sourceUrl": "https://www.businesswire.com/news/home/20190307005306/en/HSBC-Launches-PSD2-Developer-Portal-Expanded-APIs"
  },
  "developerPortalUrl": "https://developer.hsbc.com/",
  "apiProducts": [
    {
      "label": "Account Information",
      "type": "accountInformation",
      "categories": ["accounts"],
      "description": "Securely retrieve real-time Account Information for HSBC customers in your target market",
      "documentationUrl": "https://developer.hsbc.com/#/apiCatalogue/obie_accountInformation",
      "apiReferenceUrl": "https://developer.hsbc.com/#/login",
      "premium": false,
      "stage": "sandbox",
      "specification": "OBIE-AISP"
    },
    {
      "label": "Payment Initiation",
      "type": "paymentInitiation",
      "categories": ["payments"],
      "description": "Integrate secure payment Initiation in your application and launch your business potential.",
      "documentationUrl": "https://developer.hsbc.com/#/apiCatalogue/obie_paymentInitiation",
      "apiReferenceUrl": "https://developer.hsbc.com/#/login",
      "premium": false,
      "stage": "sandbox",
      "specification": "OBIE-PISP"
    }
  ],
  "apiStandards": ["STET", "OBIE"],
  "apiAggregators": ["klarna", "salt-edge", "token", "yolt", "openwrks"],
  "collections": ["cma9"],
  "webApplication": true,
  "mobileApps": [
    { "operatingSystem": "ios" },
    { "operatingSystem": "android" }
  ],
  "stockSymbol": "LON:HSBA"
}
```

## Adding an API Aggregator (Open Banking API Provider)

If you are an Open Banking API provider (like Plaid, Tink, GoCardless, etc.), follow these steps to add your platform to the tracker.

### 1. Create Your Aggregator File

Add a file named `data/api-aggregators/<your-id>.json`. Your `id` must be lowercase alphanumeric with hyphens only.

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
  "marketFocus": "Europe and North America"
}
```

Your data must follow the [API aggregator schema](https://github.com/apideck-io/open-banking-tracker-data/blob/master/api-aggregators-schema.json).

### 2. Declare Your Market Coverage

The `marketCoverage` field tells the tracker which countries you support. Without it, your listing has no geographic footprint.

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

### 3. Register Your ID in the Schema

Add your aggregator ID to the `apiAggregators` enum in [`schema.json`](https://github.com/apideck-io/open-banking-tracker-data/blob/master/schema.json). The enum is alphabetically sorted.

### 4. Tag the Banks You Cover

For every bank your platform supports, add your ID to that bank's `apiAggregators` array in `data/account-providers/<bank>.json`:

```json
{
  "apiAggregators": ["plaid", "tink", "your-company"]
}
```

This is **required**. Bank-level coverage is the core data that links aggregators to institutions in the tracker.

### 5. Build a Scraper to Keep Coverage in Sync

Coverage data goes stale fast — you add countries, onboard banks, sunset integrations. We strongly recommend building a scraper that keeps your listing and bank-level tags in sync with your actual coverage.

The `scrapers/` directory contains examples:

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

### Aggregator Checklist

- [ ] Created `data/api-aggregators/<your-id>.json` with all required fields
- [ ] Added `marketCoverage.live` with accurate ISO country codes
- [ ] Added your ID to the `apiAggregators` enum in `schema.json`
- [ ] Updated relevant bank files' `apiAggregators` arrays to include your ID
- [ ] Ran `npm run validate-aggregators` — passes
- [ ] Ran `npm run validate-links` — all URLs resolve
- [ ] (Recommended) Built a scraper to keep coverage in sync
- [ ] Opened a PR against `master`

## Validation

```bash
npm install
npm run validate-data        # validate everything
npm run validate-providers   # account providers only
npm run validate-aggregators # API aggregators only
npm run validate-links       # check all URLs resolve
```

## We Develop with Github

We use GitHub to host our data, code, to track issues and feature requests, as well as accept pull requests.

## Any contributions you make will be under the MIT License

In short, when you submit code changes, your submissions are understood to be under the same [MIT License](http://choosealicense.com/licenses/mit/) that covers the project.

## Report bugs using Github's [issues](https://github.com/apideck-io/open-banking-tracker-data/issues)

We use GitHub issues to track public bugs. Report a bug by [opening a new issue](https://github.com/apideck-io/open-banking-tracker-data/issues); it's that easy!

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

## References

This document was adapted from the open-source contribution guidelines for [Facebook's Draft](https://github.com/facebook/draft-js/blob/a9316a723f9e918afde44dea68b5f9f39b7d9b00/CONTRIBUTING.md).
