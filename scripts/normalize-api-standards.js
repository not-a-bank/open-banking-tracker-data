#!/usr/bin/env node
// Normalize apiStandards values to the schema enum (case variants, aliases)
// and drop entries that are not API standards (auth protocols, regulations).
// Usage: node scripts/normalize-api-standards.js [--dry-run]
const fs = require('fs')
const path = require('path')

const DIR = path.join(__dirname, '../data/account-providers')
const ALIASES = {
  stet: 'STET',
  obie: 'OBIE',
  'open-banking-uk': 'OBIE',
  'BERLIN1.3': 'BERLIN',
  berlin: 'BERLIN',
  fdx: 'FDX',
  polishapi: 'POLISHAPI'
}
const ENUM = require('../schema.json').properties.apiStandards.items.enum
const dryRun = process.argv.includes('--dry-run')

let changed = 0
for (const file of fs.readdirSync(DIR).filter(f => f.endsWith('.json'))) {
  const filePath = path.join(DIR, file)
  const src = fs.readFileSync(filePath, 'utf8')
  const data = JSON.parse(src)
  if (!Array.isArray(data.apiStandards) || data.apiStandards.length === 0) continue

  const next = [...new Set(data.apiStandards.map(s => ALIASES[s] || s).filter(s => ENUM.includes(s)))]
  if (JSON.stringify(next) === JSON.stringify(data.apiStandards)) continue

  const dropped = data.apiStandards.filter(s => !ENUM.includes(ALIASES[s] || s))
  console.log(`${file}: ${JSON.stringify(data.apiStandards)} -> ${JSON.stringify(next)}${dropped.length ? ` (dropped ${dropped.join(', ')})` : ''}`)
  changed++
  if (dryRun) continue

  // Replace only the apiStandards array so the rest of the file keeps its formatting
  const out = src.replace(/^( *)"apiStandards": \[[\s\S]*?\]/m, (_, indent) => {
    if (next.length === 0) return `${indent}"apiStandards": []`
    const items = next.map(s => `${indent}  ${JSON.stringify(s)}`).join(',\n')
    return `${indent}"apiStandards": [\n${items}\n${indent}]`
  })
  fs.writeFileSync(filePath, out)
}
console.log(`${dryRun ? 'Would change' : 'Changed'} ${changed} file(s)`)
