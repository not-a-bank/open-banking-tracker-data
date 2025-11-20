#!/usr/bin/env node

'use strict'

const Ajv = require('ajv')
const fs = require('fs')
const path = require('path')

// Initialize AJV with draft-06 support
const ajv = new Ajv({ allErrors: true })
ajv.addMetaSchema(require('ajv/lib/refs/json-schema-draft-06.json'))

// Parse command line arguments
function parseArgs() {
  const args = process.argv.slice(2)
  
  if (args.length === 0 || args.includes('--help') || args.includes('-h')) {
    showHelp()
    process.exit(0)
  }
  
  const filePath = args[0]
  const verbose = args.includes('--verbose') || args.includes('-v')
  const type = args.includes('--type') 
    ? args[args.indexOf('--type') + 1]
    : null
  
  return { filePath, verbose, type }
}

// Display help text
function showHelp() {
  console.log(`
╔════════════════════════════════════════════════════════════════╗
║           File Validator - CLI Tool                           ║
╚════════════════════════════════════════════════════════════════╝

USAGE:
  validate-file <filepath> [options]

ARGUMENTS:
  <filepath>              Path to the JSON file to validate

OPTIONS:
  --type <type>         Specify schema type:
                        - provider (default for account-providers/)
                        - aggregator (for api-aggregators/)
                        - auto (auto-detect based on path)
  
  --verbose, -v         Show detailed error messages
  
  --help, -h            Display this help message

EXAMPLES:
  # Validate an account provider
  validate-file data/account-providers/220bank.json
  
  # Validate with verbose output
  validate-file data/account-providers/220bank.json --verbose
  
  # Validate an API aggregator
  validate-file data/api-aggregators/plaid.json --type aggregator
  
  # Auto-detect type from file path
  validate-file data/account-providers/220bank.json --type auto

OUTPUT:
  ✅ File is VALID
  ❌ File has ERRORS (with detailed error list)

EXIT CODES:
  0  File is valid
  1  File has validation errors
  2  File not found or cannot be read
  3  Invalid arguments
`)
}

// Detect file type from path
function detectType(filePath) {
  if (filePath.includes('api-aggregators')) {
    return 'aggregator'
  }
  if (filePath.includes('account-providers') || filePath.includes('third-party-providers')) {
    return 'provider'
  }
  return 'provider' // default
}

// Get schema based on type
function getSchema(type) {
  const schemaDir = path.join(__dirname, '..')
  
  if (type === 'aggregator') {
    return require(path.join(schemaDir, 'api-aggregators-schema.json'))
  }
  
  // Default: provider schema
  return require(path.join(schemaDir, 'schema.json'))
}

// Validate file
function validateFile(filePath, schema, verbose) {
  try {
    // Read and parse file
    const fileContent = fs.readFileSync(filePath, 'utf8')
    const data = JSON.parse(fileContent)
    
    // Compile and run validation
    const validate = ajv.compile(schema)
    const valid = validate(data)
    
    if (valid) {
      console.log('✅ File is VALID')
      return true
    } else {
      console.log('❌ File has ERRORS:\n')
      
      if (verbose) {
        // Detailed output
        validate.errors.forEach((error, index) => {
          console.log(`Error ${index + 1}:`)
          console.log(`  Location: ${error.dataPath || 'root'}`)
          console.log(`  Type: ${error.keyword}`)
          console.log(`  Message: ${error.message}`)
          if (error.params) {
            console.log(`  Details:`, JSON.stringify(error.params, null, 2))
          }
          console.log()
        })
      } else {
        // Compact output
        validate.errors.forEach((error) => {
          const location = error.dataPath || 'root'
          console.log(`  • ${location}: ${error.message}`)
        })
        console.log(`\nRun with --verbose for detailed errors`)
      }
      
      return false
    }
  } catch (error) {
    if (error instanceof SyntaxError) {
      console.error(`❌ Invalid JSON: ${error.message}`)
    } else if (error.code === 'ENOENT') {
      console.error(`❌ File not found: ${filePath}`)
    } else {
      console.error(`❌ Error: ${error.message}`)
    }
    return null
  }
}

// Format output
function formatOutput(filePath, isValid, fileType) {
  console.log()
  console.log('─'.repeat(60))
  console.log(`File: ${filePath}`)
  console.log(`Type: ${fileType}`)
  console.log(`Status: ${isValid ? '✅ VALID' : '❌ INVALID'}`)
  console.log('─'.repeat(60))
}

// Main function
function main() {
  const { filePath, verbose, type } = parseArgs()
  
  // Resolve file path
  const resolvedPath = path.resolve(filePath)
  
  // Detect or validate type
  let fileType = type === 'auto' ? detectType(resolvedPath) : type || detectType(resolvedPath)
  
  // Get schema
  let schema
  try {
    schema = getSchema(fileType)
  } catch (error) {
    console.error(`❌ Error loading schema: ${error.message}`)
    process.exit(3)
  }
  
  // Validate
  const isValid = validateFile(resolvedPath, schema, verbose)
  
  if (isValid === null) {
    process.exit(2)
  }
  
  if (!isValid) {
    process.exit(1)
  }
  
  process.exit(0)
}

// Run if this is the main module
if (require.main === module) {
  main()
}

module.exports = { validateFile, getSchema, detectType }

