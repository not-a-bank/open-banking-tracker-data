#!/usr/bin/env node
// Validate a list of changed data files in one process: JSON schema plus the
// filename/id check. Used by .github/workflows/validate-data.yml.
//
// Reads paths from a file (one per line) rather than argv, so PRs touching tens of
// thousands of files don't hit argument-length limits, and compiles each schema once.
//
// Usage: node scripts/validate-changed.js --files-from changed-files.txt
'use strict'

const fs = require('fs')
const path = require('path')
const { getSchema, detectType } = require('./validate-file')

const Ajv = require('ajv')
const ajv = new Ajv({ allErrors: true })
ajv.addMetaSchema(require('ajv/lib/refs/json-schema-draft-06.json'))

const listArg = process.argv.indexOf('--files-from')
if (listArg === -1 || !process.argv[listArg + 1]) {
  console.error('Usage: node scripts/validate-changed.js --files-from <file>')
  process.exit(3)
}
const files = fs.readFileSync(process.argv[listArg + 1], 'utf8').split('\n').map(f => f.trim()).filter(Boolean)

const validators = {}
const validatorFor = type => (validators[type] = validators[type] || ajv.compile(getSchema(type)))

let failed = 0
let checked = 0
for (const file of files) {
  if (!fs.existsSync(file)) continue
  checked++
  const errors = []
  let data
  try {
    data = JSON.parse(fs.readFileSync(file, 'utf8'))
  } catch (error) {
    errors.push(`invalid JSON: ${error.message}`)
  }
  if (data) {
    const validate = validatorFor(detectType(path.resolve(file)))
    if (!validate(data)) validate.errors.forEach(e => errors.push(`${e.dataPath || 'root'}: ${e.message}`))
    const filename = path.basename(file, '.json')
    if (data.id && data.id !== filename) errors.push(`filename/id mismatch (filename: ${filename}, id: ${data.id})`)
  }
  if (errors.length) {
    failed++
    console.log(`❌ ${file}`)
    errors.forEach(e => console.log(`  • ${e}`))
  }
}

console.log(`\nChecked ${checked} file(s): ${checked - failed} valid, ${failed} with errors`)
if (failed) {
  console.log(`::error::${failed} changed file(s) failed validation. Run \`node scripts/validate-file.js <file> --verbose\` locally for details.`)
  process.exit(1)
}
