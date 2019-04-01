# Adding a provider to the Open Banking Tracker

We use [Github Flow](https://guides.github.com/introduction/flow/index.html), so all code changes happen through pull requests
are the best way to propose changes to the codebase (we use [Github Flow](https://guides.github.com/introduction/flow/index.html)). We actively welcome your pull requests:

- Fork the repo and create your branch with the name of the provider you want to add from `master`.
- Add a file with the provider name to the data folder.
- Make sure your data follows the following [schema](https://github.com/apideck-io/open-banking-tracker-data/blob/master/schema.json). Please look into the following [example](https://github.com/apideck-io/open-banking-tracker-data/blob/master/example.json) for more info
- If you're unsure about certain data points leave them out or check with the company offering the service.
- Ensure the test suite passes.
- Issue that pull request!

## Example

```
{
  "id": "hsbc",
  "type": ["account"],
  "bankType": ["universal"],
  "name": "HSBC",
  "legalName": "HSBC Holdings plc",
  "ipoStatus": "public",
  "verified": false,
  "iconUrl": "https://res.cloudinary.com/banq/image/upload/v1552239844/radar/icons/hsbc.svg",
  "website": "https://www.hsbc.com/",
  "ownership": [],
  "stateOwned": false,
  "countryHQ": "GB",
  "countries": ["EU"],
  "compliance": [
    { 
      "regulation": "PSD2",
      "status": "inProgress"
    },
    { 
      "regulation": "OB",
      "status": "ready"
    },
    {
      "regulation": "GDPR",
      "status": "unknown"
    }
  ],
  "sandbox": {
    "status": "available",
    "sourceUrl": "https://www.businesswire.com/news/home/20190307005306/en/HSBC-Launches-PSD2-Developer-Portal-Expanded-APIs"
  },
  "developerPortalUrl": "https://developer.hsbc.com/",
  "apiAccess": "verifiedTpp",
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
      "description": "Integrate secure payment Initiation in your application and launch your business potential.",
      "categories": ["payments"],
      "documentationUrl": "https://developer.hsbc.com/#/apiCatalogue/obie_paymentInitiation",
      "apiReferenceUrl": "https://developer.hsbc.com/#/login",
      "premium": false,
      "stage": "sandbox",
      "specification": "OBIE-PISP"
    },
    {
      "label": "Funds Confirmation",
      "type": "fundsConfirmation",
      "categories": ["payments"],
      "description": "Receive a confirmation of available funds to cover a proposed transaction amount.",
      "documentationUrl": "https://developer.hsbc.com/#/apiCatalogue/obie_fundsConfirmation",
      "apiReferenceUrl": "https://developer.hsbc.com/#/login",
      "premium": false,
      "stage": "sandbox",
      "specification": "OBIE-CBPII"
    },
    {
      "label": "Account Information",
      "type": "accountInformation",
      "categories": ["accounts"],
      "description": "Securely retrieve real-time Account Information for HSBC customers in your target market",
      "documentationUrl": "https://developer.hsbc.com/#/apiCatalogue/obie_accountInformation",
      "apiReferenceUrl": "https://developer.hsbc.com/#/login",
      "premium": false,
      "stage": "sandbox",
      "specification": "STET-AISP"
    },
    {
      "label": "Payment Initiation",
      "type": "paymentInitiation",
      "description": "Integrate secure payment Initiation in your application and launch your business potential.",
      "categories": ["payments"],
      "documentationUrl": "https://developer.hsbc.com/#/apiCatalogue/obie_paymentInitiation",
      "apiReferenceUrl": "https://developer.hsbc.com/#/login",
      "premium": false,
      "stage": "sandbox",
      "specification": "STET-PISP"
    },
    {
      "label": "Funds Confirmation",
      "type": "fundsConfirmation",
      "categories": ["payments"],
      "description": "Receive a confirmation of available funds to cover a proposed transaction amount.",
      "documentationUrl": "https://developer.hsbc.com/#/apiCatalogue/obie_fundsConfirmation",
      "apiReferenceUrl": "https://developer.hsbc.com/#/login",
      "premium": false,
      "stage": "sandbox",
      "specification": "STET-CBPII"
    },
    {
      "label": "ATM Locator",
      "type": "atmLocator",
      "categories": ["locators"],
      "description": "Get the locations of all our ATMs.",
      "documentationUrl": "https://developer.hsbc.com/#/apiCatalogue/open_atmLocator",
      "apiReferenceUrl": "https://developer.hsbc.com/#/login",
      "premium": false,
      "stage": "live",
      "countries": ["UK"]
    },
    {
      "label": "Branch Locator",
      "type": "branchLocator",
      "categories": ["locators"],
      "description": "Get the location of and facilities at our branches.",
      "documentationUrl": "https://developer.hsbc.com/#/apiCatalogue/open_branchLocator",
      "apiReferenceUrl": "https://developer.hsbc.com/#/login",
      "premium": false,
      "stage": "live",
      "countries": ["UK"]
    },
    {
      "label": "Product Finder",
      "type": "productFinder",
      "categories": ["products"],
      "description": "Current accounts, SME lending products and commercial credit cards.",
      "documentationUrl": "https://developer.hsbc.com/#/apiCatalogue/open_productFinder",
      "apiReferenceUrl": "https://developer.hsbc.com/#/login",
      "premium": false,
      "stage": "live",
      "countries": ["UK"]
    }
  ],
  "apiStandards": [
    "STET",
    "OBIE"
  ],
  "webApplication": true,
  "mobileApps": [
    {
      "operatingSystem": "ios"
    },
    {
      "operatingSystem": "android"
    }
  ],
"stockSymbol": "LON:HSBA",
 "investorRelationsUrl": "https://www.hsbc.com/investors/",
 "financialReports": [
   {
     "label": "Q4 2018",
     "date": "2019-02-19",
     "url": "https://res.cloudinary.com/banq/image/upload/v1552641665/Financial%20Data/HSBC-annual-report-and-accounts-2018.pdf"
   }
 ],
 "twitter": "hsbc",
 "crunchbase": "hsbc",
 "github": null,
 "fca": "001b000000MfELyAAN",
 "articles": []
}
```

## We Develop with Github

We use github to host our data, code, to track issues and feature requests, as well as accept pull requests.

## Any contributions you make will be under the MIT License

In short, when you submit code changes, your submissions are understood to be under the same [MIT License](http://choosealicense.com/licenses/mit/) that covers the project. 

## Report bugs using Github's [issues](https://github.com/apideck-io/open-banking-tracker-data/issues)

We use GitHub issues to track public bugs. Report a bug by [opening a new issue](https://github.com/apideck-io/open-banking-tracker-data/issues); it's that easy!

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

## References

This document was adapted from the open-source contribution guidelines for [Facebook's Draft](https://github.com/facebook/draft-js/blob/a9316a723f9e918afde44dea68b5f9f39b7d9b00/CONTRIBUTING.md).
