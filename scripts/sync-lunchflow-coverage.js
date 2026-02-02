#!/usr/bin/env node
/**
 * Lunchflow Coverage Sync Script
 *
 * Lunchflow (https://www.lunchflow.app/) is an aggregator of aggregators,
 * inheriting coverage from multiple upstream providers:
 * - GoCardless (Europe)
 * - MX (US)
 * - Finicity/Mastercard (US)
 * - Pluggy (Brazil, Mexico)
 * - Akahu (New Zealand)
 * - Finverse (Asia-Pacific)
 * - SnapTrade (Investment accounts)
 *
 * This script:
 * 1. Reads market coverage from all upstream aggregators
 * 2. Combines them into Lunchflow's coverage
 * 3. Updates provider files that have upstream aggregators with 'lunchflow'
 *
 * Usage:
 *   node scripts/sync-lunchflow-coverage.js
 *   node scripts/sync-lunchflow-coverage.js --dry-run
 *   node scripts/sync-lunchflow-coverage.js --update-providers
 *   node scripts/sync-lunchflow-coverage.js --update-providers --dry-run
 */

const fs = require('fs');
const path = require('path');

// Paths
const BASE_PATH = path.join(__dirname, '..');
const AGGREGATORS_PATH = path.join(BASE_PATH, 'data', 'api-aggregators');
const PROVIDERS_PATH = path.join(BASE_PATH, 'data', 'account-providers');
const LUNCHFLOW_PATH = path.join(AGGREGATORS_PATH, 'lunchflow.json');

// Parse args
const args = process.argv.slice(2);
const DRY_RUN = args.includes('--dry-run');
const UPDATE_PROVIDERS = args.includes('--update-providers');

function loadJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

function saveJson(filePath, data) {
  fs.writeFileSync(filePath, JSON.stringify(data, null, 2) + '\n');
}

function getMarketCoverage(aggregatorId) {
  const filePath = path.join(AGGREGATORS_PATH, `${aggregatorId}.json`);

  if (!fs.existsSync(filePath)) {
    console.log(`  Warning: ${aggregatorId}.json not found`);
    return [];
  }

  const data = loadJson(filePath);
  const coverage = data.marketCoverage?.live || [];

  return coverage;
}

function syncLunchflowCoverage() {
  console.log('='.repeat(60));
  console.log('Lunchflow Coverage Sync');
  console.log('='.repeat(60));

  if (DRY_RUN) {
    console.log('\n[DRY RUN MODE - No changes will be saved]\n');
  }

  // Load lunchflow config
  const lunchflow = loadJson(LUNCHFLOW_PATH);
  const upstreamAggregators = lunchflow.upstreamAggregators || [];

  console.log(`\nUpstream aggregators: ${upstreamAggregators.join(', ')}`);

  // Collect all market coverage from upstream
  const allCountries = new Set();
  const coverageByAggregator = {};

  console.log('\nCollecting market coverage:');

  for (const aggregatorId of upstreamAggregators) {
    const countries = getMarketCoverage(aggregatorId);
    coverageByAggregator[aggregatorId] = countries;

    for (const country of countries) {
      allCountries.add(country);
    }

    console.log(`  ${aggregatorId}: ${countries.length} countries (${countries.slice(0, 5).join(', ')}${countries.length > 5 ? '...' : ''})`);
  }

  // Sort countries alphabetically
  const combinedCoverage = Array.from(allCountries).sort();

  console.log(`\nCombined coverage: ${combinedCoverage.length} countries`);
  console.log(`  ${combinedCoverage.join(', ')}`);

  // Update lunchflow.json
  lunchflow.marketCoverage = { live: combinedCoverage };
  lunchflow.lastUpdated = new Date().toISOString();
  lunchflow.coverage = {
    total: combinedCoverage.length,
    byUpstream: {}
  };

  for (const [agg, countries] of Object.entries(coverageByAggregator)) {
    lunchflow.coverage.byUpstream[agg] = countries.length;
  }

  if (!DRY_RUN) {
    saveJson(LUNCHFLOW_PATH, lunchflow);
    console.log(`\nUpdated: ${LUNCHFLOW_PATH}`);
  } else {
    console.log(`\n[DRY RUN] Would update: ${LUNCHFLOW_PATH}`);
  }

  // Optionally update provider files
  if (UPDATE_PROVIDERS) {
    console.log('\n' + '-'.repeat(60));
    console.log('Updating provider files...');
    console.log('-'.repeat(60));

    const providerFiles = fs.readdirSync(PROVIDERS_PATH)
      .filter(f => f.endsWith('.json'));

    let updated = 0;
    let skipped = 0;
    let alreadyHas = 0;

    for (const file of providerFiles) {
      const filePath = path.join(PROVIDERS_PATH, file);

      try {
        const provider = loadJson(filePath);
        const aggregators = provider.apiAggregators || [];

        // Check if provider has any upstream aggregator
        const hasUpstream = aggregators.some(agg => upstreamAggregators.includes(agg));

        if (hasUpstream) {
          if (aggregators.includes('lunchflow')) {
            alreadyHas++;
          } else {
            // Add lunchflow
            aggregators.push('lunchflow');
            aggregators.sort();
            provider.apiAggregators = aggregators;

            if (!DRY_RUN) {
              saveJson(filePath, provider);
            }

            updated++;

            if (updated <= 10) {
              console.log(`  ${DRY_RUN ? '[DRY RUN] Would update' : 'Updated'}: ${file}`);
            }
          }
        } else {
          skipped++;
        }
      } catch (err) {
        console.log(`  Error processing ${file}: ${err.message}`);
      }
    }

    if (updated > 10) {
      console.log(`  ... and ${updated - 10} more`);
    }

    console.log(`\nProvider stats:`);
    console.log(`  Updated: ${updated}`);
    console.log(`  Already had lunchflow: ${alreadyHas}`);
    console.log(`  No upstream aggregator: ${skipped}`);
  }

  console.log('\nDone!');
}

// Run
syncLunchflowCoverage();
