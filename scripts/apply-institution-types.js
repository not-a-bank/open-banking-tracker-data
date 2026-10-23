#!/usr/bin/env node
// Apply institution-type classifications to account providers that still carry
// the bulk-import defaults (type ["account"], bankType ["retail"]).
//
// Input: a JSON map { <provider id>: { class, confidence, source } } where class is
// one of the keys of CLASS_MAP below. Classes from keyword rules are applied as-is;
// model classifications are applied only at high/medium confidence.
//
// Also normalizes malformed `type` values (a bare string, character-split arrays,
// values outside the schema enum).
//
// Usage: node scripts/apply-institution-types.js <classifications.json> [--dry-run]
const fs = require('fs')
const path = require('path')

const DIR = path.join(__dirname, '../data/account-providers')
const TYPE_ENUM = require('../schema.json').properties.type.items.enum
const CLASS_MAP = {
  bank: { type: ['account'] }, // keep bankType as is
  credit_union: { type: ['account'], bankType: ['credit-union'] },
  central_bank: { type: ['account'], bankType: ['central'] },
  development_bank: { type: ['account'], bankType: ['development'] },
  payment_emoney: { type: ['account'], bankType: [] },
  investment: { type: ['investment'], bankType: [] },
  brokerage: { type: ['brokerage'], bankType: [] },
  insurance: { type: ['other'], bankType: [] },
  non_financial: { type: ['other'], bankType: [] },
  public_body: { type: ['other'], bankType: [] }
}

const [input] = process.argv.slice(2).filter(a => !a.startsWith('--'))
const dryRun = process.argv.includes('--dry-run')
const classes = input ? JSON.parse(fs.readFileSync(input, 'utf8')) : {}

const same = (a, b) => JSON.stringify(a) === JSON.stringify(b)
const isImportDefault = d => same(d.type, ['account']) && same(d.bankType, ['retail']) &&
  !d.verified && !d.developerPortalUrl && !(d.apiProducts || []).length

function normalizeType (type) {
  const list = Array.isArray(type) ? type : [type]
  const valid = list.filter(t => TYPE_ENUM.includes(t))
  // character-split remnants like ["a","c","c","o","u","n","t"]
  if (list.some(t => typeof t === 'string' && t.length === 1) && !valid.includes('account')) valid.push('account')
  return [...new Set(valid.length ? valid : ['account'])]
}

// Replace a top-level array field in place so the rest of the file keeps its formatting
function setArray (src, field, values) {
  const re = new RegExp(`^( *)"${field}": (\\[[\\s\\S]*?\\]|"[^"]*")`, 'm')
  if (!re.test(src)) throw new Error(`field ${field} not found`)
  return src.replace(re, (_, indent) => {
    if (!values.length) return `${indent}"${field}": []`
    return `${indent}"${field}": [\n${values.map(v => `${indent}  ${JSON.stringify(v)}`).join(',\n')}\n${indent}]`
  })
}

const stats = { typeNormalized: 0, applied: {}, skippedLowConfidence: 0, skippedNotDefault: 0 }
for (const file of fs.readdirSync(DIR).filter(f => f.endsWith('.json'))) {
  const filePath = path.join(DIR, file)
  const original = fs.readFileSync(filePath, 'utf8')
  const data = JSON.parse(original)
  let src = original

  const type = normalizeType(data.type)
  if (!same(type, data.type)) {
    src = setArray(src, 'type', type)
    data.type = type
    stats.typeNormalized++
  }

  const c = classes[data.id]
  if (c && CLASS_MAP[c.class]) {
    if (c.source === 'model' && !['high', 'medium'].includes(c.confidence)) {
      stats.skippedLowConfidence++
    } else if (!isImportDefault(data)) {
      stats.skippedNotDefault++
    } else {
      const next = CLASS_MAP[c.class]
      if (!same(next.type, data.type)) src = setArray(src, 'type', next.type)
      if (next.bankType && !same(next.bankType, data.bankType)) src = setArray(src, 'bankType', next.bankType)
      stats.applied[c.class] = (stats.applied[c.class] || 0) + 1
    }
  }

  if (src !== original && !dryRun) {
    JSON.parse(src)
    fs.writeFileSync(filePath, src)
  }
}
console.log(dryRun ? 'Dry run:' : 'Applied:', stats)
