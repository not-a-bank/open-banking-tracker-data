#!/usr/bin/env node
// Fill in websiteUrl for providers that have none, from a reviewed map
// { <provider id>: <url> }, and derive the DuckDuckGo favicon from the new host
// (same rule as scripts/fix-website-and-icon-urls.js). Records that already have a
// websiteUrl are never touched.
// Usage: node scripts/apply-website-urls.js <websites.json> [--dry-run]
const fs = require('fs')
const path = require('path')

const DIR = path.join(__dirname, '../data/account-providers')
const DDG_PREFIX = 'https://icons.duckduckgo.com/ip3/'
const [input] = process.argv.slice(2).filter(a => !a.startsWith('--'))
const dryRun = process.argv.includes('--dry-run')
const websites = JSON.parse(fs.readFileSync(input, 'utf8'))

// Replace a top-level string-or-null field in place so the rest of the file keeps its formatting
function setField (src, field, value) {
  const re = new RegExp(`^(  "${field}": )(null|"(?:[^"\\\\]|\\\\.)*")`, 'm')
  if (!re.test(src)) throw new Error(`field ${field} not found`)
  return src.replace(re, (_, prefix) => prefix + JSON.stringify(value))
}

const stats = { applied: 0, iconSet: 0, skippedHasWebsite: 0, missing: 0 }
for (const [id, url] of Object.entries(websites)) {
  const filePath = path.join(DIR, `${id}.json`)
  if (!fs.existsSync(filePath)) { stats.missing++; continue }
  let src = fs.readFileSync(filePath, 'utf8')
  const data = JSON.parse(src)
  if (data.websiteUrl !== null) { stats.skippedHasWebsite++; continue }

  src = setField(src, 'websiteUrl', url)
  stats.applied++
  if (data.icon === null || (typeof data.icon === 'string' && data.icon.startsWith(DDG_PREFIX))) {
    src = setField(src, 'icon', `${DDG_PREFIX}${new URL(url).hostname}.ico`)
    stats.iconSet++
  }
  if (!dryRun) {
    JSON.parse(src)
    fs.writeFileSync(filePath, src)
  }
}
console.log(dryRun ? 'Dry run:' : 'Applied:', stats)
