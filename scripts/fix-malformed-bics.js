#!/usr/bin/env node

'use strict'

const fs = require('fs')
const path = require('path')

// BIC/SWIFT code pattern: 4 letters (bank) + 2 letters (country) + 2 alphanumeric (location) + optional 3 alphanumeric (branch)
const BIC_PATTERN = /^[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?$/

const dataDir = path.join(__dirname, '..', 'data', 'account-providers')

function isValidBic(bic) {
  if (!bic || typeof bic !== 'string') return false
  return BIC_PATTERN.test(bic)
}

function processFiles(dryRun = false) {
  const files = fs.readdirSync(dataDir).filter(f => f.endsWith('.json'))
  const malformedFiles = []

  for (const file of files) {
    const filePath = path.join(dataDir, file)
    try {
      const content = fs.readFileSync(filePath, 'utf8')
      const data = JSON.parse(content)

      if (data.bic !== undefined && data.bic !== null) {
        if (!isValidBic(data.bic)) {
          malformedFiles.push({ file, bic: data.bic })

          if (!dryRun) {
            data.bic = null
            fs.writeFileSync(filePath, JSON.stringify(data, null, 2) + '\n')
          }
        }
      }
    } catch (e) {
      console.error(`Error processing ${file}: ${e.message}`)
    }
  }

  return malformedFiles
}

// Main
const args = process.argv.slice(2)
const dryRun = args.includes('--dry-run')

console.log(dryRun ? 'DRY RUN - No files will be modified\n' : 'Fixing malformed BICs...\n')

const malformed = processFiles(dryRun)

if (malformed.length === 0) {
  console.log('No malformed BICs found.')
} else {
  console.log(`Found ${malformed.length} malformed BIC(s):\n`)
  malformed.forEach(({ file, bic }) => {
    console.log(`  ${file}: "${bic}"`)
  })

  if (!dryRun) {
    console.log(`\nFixed ${malformed.length} file(s) - set malformed BICs to null`)
  }
}
