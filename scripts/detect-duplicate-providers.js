#!/usr/bin/env node

/**
 * Duplicate Provider Detection & Merging Script
 * 
 * This script detects duplicate providers based on normalized IDs
 * (e.g., "wells-fargo" vs "wellsfargo" are considered duplicates).
 * 
 * The oldest provider (based on git history) is kept, and coverage data
 * from newer duplicates is merged into it. Newer duplicates are deleted.
 * 
 * Usage:
 *   node scripts/detect-duplicate-providers.js              # Dry run (preview only)
 *   node scripts/detect-duplicate-providers.js --execute    # Actually merge & delete
 *   node scripts/detect-duplicate-providers.js --verbose    # Show detailed output
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// Help message
if (process.argv.includes('--help') || process.argv.includes('-h')) {
  console.log(`
Duplicate Provider Detection & Merging Script

USAGE:
  node scripts/detect-duplicate-providers.js [options]

OPTIONS:
  --execute     Apply changes (merge and delete duplicates)
                Without this flag, runs in dry-run mode (preview only)
  
  --verbose     Show detailed output including API aggregators and products
  
  --json        Output results as JSON (useful for programmatic use)
  
  --fuzzy       Enable fuzzy matching that strips country codes and legal suffixes
                This catches duplicates like "idbibank-in" vs "idbi-bank-ltd"
                which would be missed by exact matching
  
  --filter=ID   Only process duplicates matching the normalized ID
                Example: --filter=wellsfargo
  
  --ci          Exit with error code 1 if duplicates are found (for CI/pre-commit)
  
  --help, -h    Show this help message

EXAMPLES:
  # Preview all duplicates
  node scripts/detect-duplicate-providers.js

  # Preview with detailed info
  node scripts/detect-duplicate-providers.js --verbose

  # Find duplicates with fuzzy matching (catches more edge cases)
  node scripts/detect-duplicate-providers.js --fuzzy --verbose

  # Check only Wells Fargo duplicates
  node scripts/detect-duplicate-providers.js --filter=wellsfargo --verbose

  # Actually apply the changes
  node scripts/detect-duplicate-providers.js --execute

  # Apply changes with fuzzy matching
  node scripts/detect-duplicate-providers.js --fuzzy --execute

HOW IT WORKS:
  1. Normalizes provider IDs by removing hyphens, underscores, and spaces
  2. In --fuzzy mode, also strips:
     - Country code suffixes (e.g., -in, -ae, -uk)
     - Legal entity suffixes (e.g., -ltd, -limited, -inc, -bank)
     This catches duplicates like "idbibank-in" vs "idbi-bank-ltd"
  3. Groups providers with the same normalized ID as potential duplicates
  4. Determines which provider to keep based on:
     - Git creation date (oldest wins)
     - Completeness score (if same date)
  5. Merges coverage data (apiAggregators, apiProducts, countries, etc.)
     from deleted providers into the keeper
  6. Deletes the duplicate files
`);
  process.exit(0);
}

// Configuration
const PROVIDERS_DIR = path.join(__dirname, '..', 'data', 'account-providers');
const DRY_RUN = !process.argv.includes('--execute');
const VERBOSE = process.argv.includes('--verbose');
const JSON_OUTPUT = process.argv.includes('--json');
const CI_MODE = process.argv.includes('--ci');
const FUZZY_MODE = process.argv.includes('--fuzzy');
const FILTER = process.argv.find(arg => arg.startsWith('--filter='))?.split('=')[1] || null;

// Fields that should be merged (arrays are combined, objects are deep-merged)
const MERGE_FIELDS = [
  'apiAggregators',    // API aggregators like plaid, truelayer
  'apiProducts',       // API products offered
  'countries',         // Countries where the provider operates
  'compliance',        // Regulatory compliance info
  'collections',       // Collections like cma9
  'bankType',          // Bank types
  'mobileApps',        // Mobile app links
  'partnerships',      // Partnership info
  'integrations',      // Integrations
  'apiStandards',      // API standards supported
];

// Fields to take from the most complete record (not arrays)
const PREFER_NON_NULL_FIELDS = [
  'description',
  'legalName',
  'developerPortalUrl',
  'apiReferenceUrl',
  'twitter',
  'github',
  'crunchbase',
  'stockSymbol',
  'sandbox',
  'bic',
  'swiftCode',
  'ipoStatus',
  'wikipediaUrl',
  'investorRelationsUrl',
];

// ISO 3166-1 alpha-2 country codes (common ones used in provider IDs)
const COUNTRY_CODE_SUFFIXES = new Set([
  'ad', 'ae', 'af', 'ag', 'al', 'am', 'ao', 'ar', 'at', 'au', 'az',
  'ba', 'bb', 'bd', 'be', 'bf', 'bg', 'bh', 'bi', 'bj', 'bn', 'bo', 'br', 'bs', 'bt', 'bw', 'by', 'bz',
  'ca', 'cd', 'cf', 'cg', 'ch', 'ci', 'cl', 'cm', 'cn', 'co', 'cr', 'cu', 'cv', 'cy', 'cz',
  'de', 'dj', 'dk', 'dm', 'do', 'dz',
  'ec', 'ee', 'eg', 'er', 'es', 'et',
  'fi', 'fj', 'fr',
  'ga', 'gb', 'gd', 'ge', 'gh', 'gm', 'gn', 'gq', 'gr', 'gt', 'gw', 'gy',
  'hk', 'hn', 'hr', 'ht', 'hu',
  'id', 'ie', 'il', 'in', 'iq', 'ir', 'is', 'it',
  'jm', 'jo', 'jp',
  'ke', 'kg', 'kh', 'ki', 'km', 'kn', 'kp', 'kr', 'kw', 'kz',
  'la', 'lb', 'lc', 'li', 'lk', 'lr', 'ls', 'lt', 'lu', 'lv', 'ly',
  'ma', 'mc', 'md', 'me', 'mg', 'mk', 'ml', 'mm', 'mn', 'mo', 'mr', 'mt', 'mu', 'mv', 'mw', 'mx', 'my', 'mz',
  'na', 'ne', 'ng', 'ni', 'nl', 'no', 'np', 'nr', 'nz',
  'om',
  'pa', 'pe', 'pg', 'ph', 'pk', 'pl', 'pt', 'pw', 'py',
  'qa',
  'ro', 'rs', 'ru', 'rw',
  'sa', 'sb', 'sc', 'sd', 'se', 'sg', 'si', 'sk', 'sl', 'sm', 'sn', 'so', 'sr', 'ss', 'st', 'sv', 'sy', 'sz',
  'td', 'tg', 'th', 'tj', 'tl', 'tm', 'tn', 'to', 'tr', 'tt', 'tv', 'tw', 'tz',
  'ua', 'ug', 'uk', 'us', 'uy', 'uz',
  'va', 'vc', 've', 'vn', 'vu',
  'ws',
  'ye',
  'za', 'zm', 'zw'
]);

// Legal entity suffixes that can mask duplicates
const LEGAL_SUFFIXES = [
  'ltd', 'limited', 'inc', 'incorporated', 'corp', 'corporation',
  'plc', 'llc', 'llp', 'lp', 'gmbh', 'ag', 'sa', 'sas', 'sarl',
  'bv', 'nv', 'pty', 'pvt', 'private', 'public',
  'bank', 'banking', 'banque', 'banco', 'banca',
  'group', 'holding', 'holdings', 'international', 'intl',
  'financial', 'finance', 'services', 'trust', 'trustee'
];

/**
 * Normalize an ID for comparison
 * Removes hyphens, underscores, and spaces to find duplicates
 */
function normalizeId(id) {
  return id.toLowerCase().replace(/[-_\s]/g, '');
}

/**
 * Aggressively normalize an ID by stripping country codes and legal suffixes
 * This is used for fuzzy matching to catch duplicates like "idbibank-in" vs "idbi-bank-ltd"
 */
function fuzzyNormalizeId(id) {
  let normalized = id.toLowerCase();
  
  // Remove hyphens, underscores, spaces
  normalized = normalized.replace(/[-_\s]/g, '');
  
  // Strip country code suffix if present at the end (e.g., "idbibankin" -> "idbibank")
  for (const cc of COUNTRY_CODE_SUFFIXES) {
    if (normalized.endsWith(cc) && normalized.length > cc.length + 3) {
      // Make sure we're not stripping part of the actual name
      normalized = normalized.slice(0, -cc.length);
      break;
    }
  }
  
  // Strip legal suffixes (e.g., "idbibankltd" -> "idbibank")
  for (const suffix of LEGAL_SUFFIXES) {
    if (normalized.endsWith(suffix) && normalized.length > suffix.length + 3) {
      normalized = normalized.slice(0, -suffix.length);
      break;
    }
  }
  
  return normalized;
}

/**
 * Get the git creation date of a file
 * Returns null if file is not tracked in git
 */
function getGitCreationDate(filePath) {
  try {
    const result = execSync(
      `git log --diff-filter=A --format='%aI' -- "${filePath}"`,
      { encoding: 'utf8', cwd: path.dirname(filePath), stdio: ['pipe', 'pipe', 'pipe'] }
    ).trim();

    if (result) {
      // Take only the first line (oldest commit) in case of multiple results
      const firstDate = result.split('\n')[0].trim();
      const date = new Date(firstDate);
      // Validate the date is valid
      if (!isNaN(date.getTime())) {
        return date;
      }
    }
  } catch (e) {
    // File not tracked in git yet
  }
  return null;
}

/**
 * Get file modification time as fallback for git date
 */
function getFileMTime(filePath) {
  try {
    const stats = fs.statSync(filePath);
    return stats.mtime;
  } catch (e) {
    return new Date();
  }
}

/**
 * Get the creation date of a provider file
 * Uses git history first, falls back to file mtime
 */
function getProviderAge(filePath) {
  const gitDate = getGitCreationDate(filePath);
  if (gitDate) {
    return { date: gitDate, source: 'git' };
  }
  return { date: getFileMTime(filePath), source: 'mtime' };
}

/**
 * Read and parse a provider JSON file
 */
function readProvider(filePath) {
  try {
    const content = fs.readFileSync(filePath, 'utf8');
    return JSON.parse(content);
  } catch (e) {
    console.error(`Error reading ${filePath}:`, e.message);
    return null;
  }
}

/**
 * Write provider JSON file
 */
function writeProvider(filePath, data) {
  const content = JSON.stringify(data, null, 2) + '\n';
  fs.writeFileSync(filePath, content, 'utf8');
}

/**
 * Merge two arrays, keeping unique values
 * For arrays of objects, uses JSON stringify for comparison
 */
function mergeArrays(arr1, arr2) {
  if (!arr1 && !arr2) return [];
  if (!arr1) return arr2 || [];
  if (!arr2) return arr1 || [];
  
  // Ensure both are arrays
  const a1 = Array.isArray(arr1) ? arr1 : [arr1];
  const a2 = Array.isArray(arr2) ? arr2 : [arr2];
  
  const result = [...a1];
  const existingStrings = new Set(a1.map(item => 
    typeof item === 'object' ? JSON.stringify(item) : item
  ));
  
  for (const item of a2) {
    const itemString = typeof item === 'object' ? JSON.stringify(item) : item;
    if (!existingStrings.has(itemString)) {
      result.push(item);
      existingStrings.add(itemString);
    }
  }
  
  return result;
}

/**
 * Merge coverage data from source into target
 * Target is the older provider that we're keeping
 */
function mergeCoverage(target, source) {
  const merged = { ...target };
  let changesMade = [];
  
  // Merge array fields
  for (const field of MERGE_FIELDS) {
    if (source[field] && Array.isArray(source[field]) && source[field].length > 0) {
      const originalLength = merged[field] ? merged[field].length : 0;
      merged[field] = mergeArrays(merged[field], source[field]);
      
      if (merged[field].length > originalLength) {
        changesMade.push(`${field}: added ${merged[field].length - originalLength} items`);
      }
    }
  }
  
  // Take non-null values for scalar fields
  for (const field of PREFER_NON_NULL_FIELDS) {
    if (!merged[field] && source[field]) {
      merged[field] = source[field];
      changesMade.push(`${field}: inherited value`);
    }
  }
  
  return { merged, changesMade };
}

/**
 * Calculate a "completeness score" for a provider
 * Higher score means more data
 */
function calculateCompleteness(provider) {
  let score = 0;
  
  for (const field of MERGE_FIELDS) {
    if (provider[field] && Array.isArray(provider[field])) {
      score += provider[field].length;
    }
  }
  
  for (const field of PREFER_NON_NULL_FIELDS) {
    if (provider[field]) {
      score += 1;
    }
  }
  
  // Extra points for important fields
  if (provider.apiProducts && provider.apiProducts.length > 0) score += 5;
  if (provider.developerPortalUrl) score += 2;
  if (provider.description) score += 2;
  
  return score;
}

/**
 * Main function to detect and handle duplicates
 */
function detectDuplicates() {
  if (!JSON_OUTPUT) {
    const modeStr = FUZZY_MODE ? ' (fuzzy mode - stripping country/legal suffixes)' : '';
    console.log(`🔍 Scanning for duplicate providers${modeStr}...\n`);
  }
  
  // Read all provider files
  const files = fs.readdirSync(PROVIDERS_DIR)
    .filter(f => f.endsWith('.json'));
  
  if (!JSON_OUTPUT) {
    console.log(`Found ${files.length} provider files.\n`);
  }
  
  // Group by normalized ID (using fuzzy or exact normalization)
  const groups = new Map();
  const normalizeFn = FUZZY_MODE ? fuzzyNormalizeId : normalizeId;
  
  for (const file of files) {
    const filePath = path.join(PROVIDERS_DIR, file);
    const id = file.replace('.json', '');
    const normalizedId = normalizeFn(id);
    
    if (!groups.has(normalizedId)) {
      groups.set(normalizedId, []);
    }
    groups.get(normalizedId).push({ file, filePath, id, originalNormalized: normalizeId(id) });
  }
  
  // Find groups with more than one provider (duplicates)
  let duplicateGroups = [];
  for (const [normalizedId, providers] of groups) {
    if (providers.length > 1) {
      duplicateGroups.push({ normalizedId, providers });
    }
  }
  
  // Apply filter if specified
  if (FILTER) {
    const normalizedFilter = normalizeId(FILTER);
    duplicateGroups = duplicateGroups.filter(g => g.normalizedId === normalizedFilter);
    if (!JSON_OUTPUT && duplicateGroups.length === 0) {
      console.log(`No duplicates found matching filter "${FILTER}" (normalized: "${normalizedFilter}")`);
      return [];
    }
  }
  
  if (duplicateGroups.length === 0) {
    if (!JSON_OUTPUT) {
      console.log('✅ No duplicates found!');
    } else {
      console.log(JSON.stringify({ duplicates: [], summary: { groups: 0, toDelete: 0, toKeep: 0 } }, null, 2));
    }
    return [];
  }
  
  if (!JSON_OUTPUT) {
    console.log(`Found ${duplicateGroups.length} potential duplicate group(s):\n`);
  }
  
  // Process each duplicate group
  const results = [];
  
  for (const group of duplicateGroups) {
    if (!JSON_OUTPUT) {
      console.log(`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`);
      console.log(`📁 Normalized ID: "${group.normalizedId}"`);
      console.log(`   Found ${group.providers.length} providers:\n`);
    }
    
    // Get age and data for each provider
    const providersWithData = group.providers.map(p => {
      const data = readProvider(p.filePath);
      const age = getProviderAge(p.filePath);
      const completeness = data ? calculateCompleteness(data) : 0;
      
      return { ...p, data, age, completeness };
    }).filter(p => p.data !== null);
    
    if (providersWithData.length < 2) {
      if (!JSON_OUTPUT) {
        console.log('   ⚠️  Could not read all provider files, skipping.\n');
      }
      continue;
    }
    
    // Sort by age (oldest first), then by completeness (highest first)
    providersWithData.sort((a, b) => {
      const ageDiff = a.age.date.getTime() - b.age.date.getTime();
      if (ageDiff !== 0) return ageDiff;
      return b.completeness - a.completeness;
    });
    
    // Print info about each provider
    if (!JSON_OUTPUT) {
      for (let i = 0; i < providersWithData.length; i++) {
        const p = providersWithData[i];
        const isKeep = i === 0;
        const marker = isKeep ? '✓ KEEP' : '✗ DELETE';
        const dateStr = p.age.date.toISOString().split('T')[0];
        
        console.log(`   ${marker}: ${p.file}`);
        console.log(`      ID: "${p.id}"`);
        console.log(`      Name: "${p.data.name}"`);
        if (p.data.countryHQ) {
          console.log(`      Country HQ: ${p.data.countryHQ}`);
        }
        console.log(`      Created: ${dateStr} (${p.age.source})`);
        console.log(`      Completeness score: ${p.completeness}`);
        
        if (VERBOSE) {
          const aggregators = p.data.apiAggregators || [];
          const products = p.data.apiProducts || [];
          console.log(`      API Aggregators: [${aggregators.join(', ')}]`);
          console.log(`      API Products: ${products.length}`);
          if (FUZZY_MODE) {
            console.log(`      Exact normalized: "${p.originalNormalized || normalizeId(p.id)}"`);
            console.log(`      Fuzzy normalized: "${fuzzyNormalizeId(p.id)}"`);
          }
        }
        console.log('');
      }
    }
    
    // The first one (oldest) is kept, rest are merged into it
    const keeper = providersWithData[0];
    const toDelete = providersWithData.slice(1);
    
    // Warn if fuzzy mode found matches with different country HQs
    if (FUZZY_MODE && !JSON_OUTPUT) {
      const countries = new Set(providersWithData.map(p => p.data.countryHQ).filter(Boolean));
      if (countries.size > 1) {
        console.log(`   ⚠️  WARNING: These providers have different country HQs: [${[...countries].join(', ')}]`);
        console.log(`      They may be legitimate regional entities. Review carefully before merging.\n`);
      }
    }
    
    let finalData = keeper.data;
    let allChanges = [];
    
    // Merge data from all duplicates
    for (const dup of toDelete) {
      const { merged, changesMade } = mergeCoverage(finalData, dup.data);
      finalData = merged;
      
      if (changesMade.length > 0) {
        allChanges.push({ from: dup.file, changes: changesMade });
      }
    }
    
    // Report merge changes
    if (!JSON_OUTPUT && allChanges.length > 0) {
      console.log('   📋 Merging coverage data:');
      for (const change of allChanges) {
        console.log(`      From ${change.from}:`);
        for (const c of change.changes) {
          console.log(`         - ${c}`);
        }
      }
      console.log('');
    }
    
    results.push({
      normalizedId: group.normalizedId,
      keeper: {
        file: keeper.file,
        id: keeper.id,
        name: keeper.data.name,
        created: keeper.age.date.toISOString(),
        completeness: keeper.completeness,
      },
      toDelete: toDelete.map(d => ({
        file: d.file,
        id: d.id,
        name: d.data.name,
        created: d.age.date.toISOString(),
        completeness: d.completeness,
      })),
      changes: allChanges,
    });
    
    // Execute if not dry run
    if (!DRY_RUN) {
      // Write merged data to keeper
      if (allChanges.length > 0) {
        writeProvider(keeper.filePath, finalData);
        if (!JSON_OUTPUT) {
          console.log(`   ✅ Updated ${keeper.file} with merged data.`);
        }
      }
      
      // Delete duplicates
      for (const dup of toDelete) {
        fs.unlinkSync(dup.filePath);
        if (!JSON_OUTPUT) {
          console.log(`   🗑️  Deleted ${dup.file}`);
        }
      }
      if (!JSON_OUTPUT) {
        console.log('');
      }
    }
  }
  
  // Summary
  const summary = {
    groups: results.length,
    toDelete: results.reduce((sum, r) => sum + r.toDelete.length, 0),
    toKeep: results.length,
    dryRun: DRY_RUN,
  };
  
  if (JSON_OUTPUT) {
    console.log(JSON.stringify({ duplicates: results, summary }, null, 2));
  } else {
    console.log('\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    console.log('📊 SUMMARY');
    console.log(`   Duplicate groups found: ${summary.groups}`);
    console.log(`   Files to delete: ${summary.toDelete}`);
    console.log(`   Files to keep: ${summary.toKeep}`);
    
    if (DRY_RUN) {
      console.log('\n⚠️  DRY RUN - No changes made.');
      console.log('   Run with --execute flag to apply changes:');
      console.log('   node scripts/detect-duplicate-providers.js --execute\n');
    } else {
      console.log('\n✅ All changes applied successfully.\n');
    }
  }
  
  // In CI mode, exit with error if duplicates found
  if (CI_MODE && results.length > 0) {
    if (!JSON_OUTPUT) {
      console.log('💡 TIP: Run "npm run fix-duplicates" to automatically merge and remove duplicates.\n');
    }
    process.exit(1);
  }
  
  return results;
}

// Run the script
detectDuplicates();
