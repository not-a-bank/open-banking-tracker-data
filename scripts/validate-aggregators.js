'use strict'

const Promise = require('bluebird')
const fs = require('fs')
const path = require('path')
const { getFile } = require('./utils')
const Ajv = require('ajv')

// Initialize AJV with draft-06 support
const ajv = Ajv({ allErrors: true })
ajv.addMetaSchema(require('ajv/lib/refs/json-schema-draft-06.json'))

// Compile validators for both schemas
const aggregatorSchema = require('../api-aggregators-schema.json')
const validateAggregator = ajv.compile(aggregatorSchema)

let validData = true
let successCount = 0
let errorCount = 0

/**
 * Validates a single API aggregator file
 * @param {string} file - Path to the aggregator file
 * @param {function} cb - Callback function
 */
function validateAggregatorFile (file, cb) {
  getFile(file)
    .then(e => {
      try {
        const json = JSON.parse(e)
        const valid = validateAggregator(json)
        
        if (!valid) {
          console.log(`\n❌ ${file}:`)
          console.log(validateAggregator.errors)
          validData = false
          errorCount++
        } else {
          console.log(`✓ ${file}`)
          successCount++
        }
        cb()
      } catch (e) {
        validData = false
        console.error(`\n❌ Failed parsing: ${file}`)
        console.error(e.message)
        errorCount++
        process.exitCode = 1
        cb()
      }
    })
    .catch(e => {
      validData = false
      console.error(`\n❌ Failed reading: ${file}`)
      console.error(e.message)
      errorCount++
      process.exitCode = 1
      cb()
    })
}

/**
 * Gets all API aggregator files from the data/api-aggregators directory
 */
function getAggregatorFiles () {
  const dir = path.join(__dirname, '../data/api-aggregators')
  try {
    const files = fs.readdirSync(dir)
    return files
      .filter(file => file.endsWith('.json'))
      .map(file => path.join('data/api-aggregators', file))
  } catch (err) {
    console.error(`Failed to read aggregators directory: ${err.message}`)
    process.exitCode = 1
    return []
  }
}

// Main validation logic
console.log('🔍 Validating API Aggregators...\n')

const aggregatorFiles = getAggregatorFiles()

if (aggregatorFiles.length === 0) {
  console.log('⚠️  No API aggregator files found')
  process.exit(0)
}

const requests = aggregatorFiles.map((fileName) => {
  return new Promise((resolve) => {
    validateAggregatorFile(fileName, resolve)
  })
})

Promise.all(requests).then(() => {
  console.log(`\n${'='.repeat(50)}`)
  console.log(`Total: ${aggregatorFiles.length} files`)
  console.log(`✓ Valid: ${successCount}`)
  console.log(`✗ Invalid: ${errorCount}`)
  console.log(`${'='.repeat(50)}`)
  
  if (validData) {
    console.log('\n✅ All API aggregators are valid!')
  } else {
    console.log('\n❌ Some API aggregators have validation errors')
    process.exitCode = 1
  }
})

