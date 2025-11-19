# [Open Banking Tracker](https://www.openbankingtracker.com/) 

<img src="https://github.com/apideck-io/open-banking-tracker-data/blob/master/images/screenshot.png">

This repository holds all the providers displayed in the tracker. 

[Open Banking Tracker](https://www.openbankingtracker.com/) shows whether large institutions, such as Deutsche Bank, HSBC, Citi, and many more, have the correct infrastructure in place to be adequately prepared for the upcoming change in the regulatory environment as we will be tracking over 30 data points per organization (Sandboxes, AIS, PIS, APIs, Data breaches, iOS, and Android usage, etc.). In regards to PSD2 and Open Banking, registered financial institutions are required to have developer sandboxes (area for developers to test their programs) and relevant APIs in place to promote transparency and freedom of data.

Our goal, through this project, is to bring more transparency throughout the industry as well as empower developers and customers to choose the right partner to help support their growth. We will encourage that by sharing insights and reports in the future based on the analytics we generate.

## [How to add a service?](https://github.com/apideck-io/open-banking-tracker-data/blob/master/CONTRIBUTING.md)

You can add a service by following the [contribution guidelines](https://github.com/apideck-io/open-banking-tracker-data/blob/master/CONTRIBUTING.md).

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
