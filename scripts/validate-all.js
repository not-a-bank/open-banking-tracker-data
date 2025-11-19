'use strict'

const Promise = require('bluebird')
const fs = require('fs')
const path = require('path')
const { getFile, getFiles } = require('./utils')
const Ajv = require('ajv')

// Initialize AJV with draft-06 support
const ajv = Ajv({ allErrors: true })
ajv.addMetaSchema(require('ajv/lib/refs/json-schema-draft-06.json'))

// Compile validators for both schemas
const providerSchema = require('../schema.json')
const aggregatorSchema = require('../api-aggregators-schema.json')
const validateProvider = ajv.compile(providerSchema)
const validateAggregator = ajv.compile(aggregatorSchema)

let validData = true
let providerCount = 0
let aggregatorCount = 0
let providerErrors = 0
let aggregatorErrors = 0

/**
 * Validates a single provider file
 * @param {string} file - Path to the provider file
 * @param {function} cb - Callback function
 */
function validateProviderFile (file, cb) {
  getFile(file)
    .then(e => {
      try {
        const json = JSON.parse(e)
        const valid = validateProvider(json)
        
        if (!valid) {
          console.log(`  ❌ ${file}`)
          validData = false
          providerErrors++
        } else {
          providerCount++
        }
        cb()
      } catch (e) {
        validData = false
        console.error(`  ❌ Failed parsing: ${file}`)
        providerErrors++
        process.exitCode = 1
        cb()
      }
    })
    .catch(e => {
      validData = false
      console.error(`  ❌ Failed reading: ${file}`)
      providerErrors++
      process.exitCode = 1
      cb()
    })
}

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
          console.log(`  ❌ ${file}`)
          validData = false
          aggregatorErrors++
        } else {
          aggregatorCount++
        }
        cb()
      } catch (e) {
        validData = false
        console.error(`  ❌ Failed parsing: ${file}`)
        aggregatorErrors++
        process.exitCode = 1
        cb()
      }
    })
    .catch(e => {
      validData = false
      console.error(`  ❌ Failed reading: ${file}`)
      aggregatorErrors++
      process.exitCode = 1
      cb()
    })
}

/**
 * Gets all files from a directory recursively
 */
function getFilesRecursive (dir) {
  let fileList = []
  const files = fs.readdirSync(dir)
  
  for (let i in files) {
    if (!files.hasOwnProperty(i)) continue
    const name = path.join(dir, files[i])
    const stat = fs.statSync(name)
    
    if (stat.isDirectory()) {
      // Recursively get files from subdirectories
      fileList = fileList.concat(getFilesRecursive(name))
    } else if (files[i].endsWith('.json') && files[i] !== '.DS_Store') {
      fileList.push(name)
    }
  }
  
  return fileList
}

/**
 * Gets all API aggregator files from the data/api-aggregators directory
 */
function getAggregatorFiles () {
  const dir = path.join(__dirname, '../data/api-aggregators')
  try {
    return getFilesRecursive(dir)
  } catch (err) {
    console.log('  ⚠️  No API aggregators directory found')
    return []
  }
}

/**
 * Gets all provider files (account-providers and third-party-providers)
 */
function getProviderFiles () {
  const dataDir = path.join(__dirname, '../data')
  const providerDirs = [
    path.join(dataDir, 'account-providers'),
    path.join(dataDir, 'third-party-providers')
  ]
  
  let files = []
  for (const dir of providerDirs) {
    try {
      files = files.concat(getFilesRecursive(dir))
    } catch (err) {
      // Directory might not exist
    }
  }
  
  return files
}

// Main validation logic
console.log('\n🔍 Validating all data...\n')

// Validate Account Providers
console.log('📋 Account Providers:')
const providerFiles = getProviderFiles()

// Create validation request arrays
let allRequests = []

if (providerFiles.length === 0) {
  console.log('  ⚠️  No provider files found')
} else {
  const providerRequests = providerFiles.map((fileName) => {
    return new Promise((resolve) => {
      validateProviderFile(fileName, resolve)
    })
  })
  allRequests = allRequests.concat(providerRequests)
}

// Validate API Aggregators
console.log('\n🔗 API Aggregators:')
const aggregatorFiles = getAggregatorFiles()

if (aggregatorFiles.length === 0) {
  console.log('  ⚠️  No API aggregators found')
} else {
  const aggregatorRequests = aggregatorFiles.map((fileName) => {
    return new Promise((resolve) => {
      validateAggregatorFile(fileName, resolve)
    })
  })
  allRequests = allRequests.concat(aggregatorRequests)
}

Promise.all(allRequests).then(() => {
  console.log(`\n${'='.repeat(60)}`)
  console.log('📊 Validation Summary:')
  console.log(`${'='.repeat(60)}`)
  console.log(`📋 Account Providers:   ${providerCount} valid, ${providerErrors} errors`)
  console.log(`🔗 API Aggregators:     ${aggregatorCount} valid, ${aggregatorErrors} errors`)
  console.log(`${'='.repeat(60)}`)
  
  if (validData) {
    console.log('\n✅ All data is valid!\n')
  } else {
    console.log('\n❌ Some data has validation errors\n')
    process.exitCode = 1
  }
})

