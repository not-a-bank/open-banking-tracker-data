#!/usr/bin/env node
// Clean up websiteUrl and DuckDuckGo favicon URLs on account providers:
// - websiteUrl: trim whitespace, add a missing https:// scheme, and null out
//   placeholder hosts (google.com, plaid.com) that are not the provider's site.
// - icon: DuckDuckGo favicons are derived from the websiteUrl host (as in #623).
//   When there is no websiteUrl the favicon host was guessed from the id slug
//   and almost never resolves, so set it to null instead.
// Usage: node scripts/fix-website-and-icon-urls.js [--dry-run]
const fs = require('fs')
const path = require('path')

const DIR = path.join(__dirname, '../data/account-providers')
const PLACEHOLDER_HOSTS = new Set(['google.com', 'plaid.com'])
const DDG_PREFIX = 'https://icons.duckduckgo.com/ip3/'
const dryRun = process.argv.includes('--dry-run')

function cleanWebsiteUrl (url) {
  if (typeof url !== 'string') return url
  let next = url.trim()
  if (!/^https?:\/\//i.test(next) && /^[a-z0-9-]+(\.[a-z0-9-]+)+(\/.*)?$/i.test(next)) next = `https://${next}`
  let host
  try { host = new URL(next).hostname } catch { return next }
  if (PLACEHOLDER_HOSTS.has(host.replace(/^www\./, ''))) return null
  return next
}

function ddgIcon (websiteUrl) {
  try { return `${DDG_PREFIX}${new URL(websiteUrl).hostname}.ico` } catch { return null }
}

// Replace a top-level string-or-null field in place so the rest of the file keeps its formatting
function setField (src, field, value) {
  const re = new RegExp(`^(  "${field}": )(null|"(?:[^"\\\\]|\\\\.)*")`, 'm')
  if (!re.test(src)) throw new Error(`field ${field} not found`)
  return src.replace(re, (_, prefix) => prefix + JSON.stringify(value))
}

const stats = { websiteFixed: 0, websitePlaceholder: 0, iconNulled: 0, iconRederived: 0 }
for (const file of fs.readdirSync(DIR).filter(f => f.endsWith('.json'))) {
  const filePath = path.join(DIR, file)
  let src = fs.readFileSync(filePath, 'utf8')
  const data = JSON.parse(src)
  const original = src

  const websiteUrl = cleanWebsiteUrl(data.websiteUrl)
  if (websiteUrl !== data.websiteUrl) {
    websiteUrl === null ? stats.websitePlaceholder++ : stats.websiteFixed++
    src = setField(src, 'websiteUrl', websiteUrl)
  }

  if (typeof data.icon === 'string' && data.icon.startsWith(DDG_PREFIX)) {
    const icon = websiteUrl ? ddgIcon(websiteUrl) : null
    if (icon !== data.icon) {
      icon === null ? stats.iconNulled++ : stats.iconRederived++
      src = setField(src, 'icon', icon)
    }
  }

  if (src !== original && !dryRun) {
    JSON.parse(src)
    fs.writeFileSync(filePath, src)
  }
}
console.log(dryRun ? 'Dry run:' : 'Applied:', stats)
