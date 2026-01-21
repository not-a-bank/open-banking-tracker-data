#!/usr/bin/env node

'use strict'

const fs = require('fs')
const path = require('path')
const https = require('https')
const http = require('http')

// Environment variable to control strict mode (fail on missing icons)
const STRICT_MODE = process.env.STRICT_ICON_CHECK === 'true'

/**
 * Check if a URL exists by making a HEAD request
 * @param {string} url - The URL to check
 * @returns {Promise<{exists: boolean, status: number, error?: string}>}
 */
function checkUrlExists(url) {
  return new Promise((resolve) => {
    try {
      const urlObj = new URL(url)
      const client = urlObj.protocol === 'https:' ? https : http
      
      const req = client.request(
        {
          method: 'HEAD',
          hostname: urlObj.hostname,
          port: urlObj.port,
          path: urlObj.pathname + urlObj.search,
          timeout: 10000,
          headers: {
            'User-Agent': 'Mozilla/5.0 (compatible; IconValidator/1.0)'
          }
        },
        (res) => {
          // Follow redirects (3xx status codes)
          if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
            checkUrlExists(res.headers.location).then(resolve)
            return
          }
          
          resolve({
            exists: res.statusCode >= 200 && res.statusCode < 400,
            status: res.statusCode
          })
        }
      )
      
      req.on('error', (error) => {
        resolve({
          exists: false,
          status: 0,
          error: error.message
        })
      })
      
      req.on('timeout', () => {
        req.destroy()
        resolve({
          exists: false,
          status: 0,
          error: 'Request timeout'
        })
      })
      
      req.end()
    } catch (error) {
      resolve({
        exists: false,
        status: 0,
        error: error.message
      })
    }
  })
}

/**
 * Validate icons in a JSON file
 * @param {string} filePath - Path to the JSON file
 * @returns {Promise<{valid: boolean, errors: string[]}>}
 */
async function validateFileIcons(filePath) {
  const errors = []
  
  try {
    const content = fs.readFileSync(filePath, 'utf8')
    const data = JSON.parse(content)
    
    // Check main icon field
    if (data.icon) {
      console.log(`  Checking icon: ${data.icon}`)
      const result = await checkUrlExists(data.icon)
      
      if (!result.exists) {
        const errorMsg = result.error 
          ? `Icon URL not accessible: ${data.icon} (${result.error})`
          : `Icon URL not accessible: ${data.icon} (HTTP ${result.status})`
        errors.push(errorMsg)
      }
    } else {
      errors.push('Missing required "icon" field')
    }
    
    return {
      valid: errors.length === 0,
      errors
    }
  } catch (error) {
    if (error instanceof SyntaxError) {
      return { valid: false, errors: [`Invalid JSON: ${error.message}`] }
    }
    if (error.code === 'ENOENT') {
      return { valid: false, errors: [`File not found: ${filePath}`] }
    }
    return { valid: false, errors: [error.message] }
  }
}

/**
 * Main function
 */
async function main() {
  const args = process.argv.slice(2)
  
  const strictFlag = args.includes('--strict')
  const isStrict = STRICT_MODE || strictFlag
  
  if (args.length === 0 || args.includes('--help') || args.includes('-h')) {
    console.log(`
Usage: validate-icons.js <file1> [file2] [file3] ...

Validates that icon URLs in JSON files are accessible.

Options:
  --strict      Fail with exit code 1 if any icons are invalid
                (also enabled via STRICT_ICON_CHECK=true env var)
  --help, -h    Show this help message

Examples:
  validate-icons.js data/account-providers/griffin.json
  validate-icons.js data/account-providers/*.json
  validate-icons.js --strict data/account-providers/griffin.json
`)
    process.exit(0)
  }
  
  console.log('🔍 Validating icon URLs...\n')
  
  let hasErrors = false
  
  for (const filePath of args) {
    // Skip flags
    if (filePath.startsWith('-')) continue
    
    const resolvedPath = path.resolve(filePath)
    const fileName = path.basename(filePath)
    
    // Check if file exists first
    if (!fs.existsSync(resolvedPath)) {
      console.log(`📄 ${fileName}`)
      console.log(`   ⚠️ File does not exist, skipping\n`)
      continue
    }
    
    console.log(`📄 ${fileName}`)
    
    const result = await validateFileIcons(resolvedPath)
    
    if (result.valid) {
      console.log(`   ✅ Icon is valid\n`)
    } else {
      hasErrors = true
      console.log(`   ❌ Icon validation failed:`)
      result.errors.forEach(err => console.log(`      - ${err}`))
      console.log()
    }
  }
  
  if (hasErrors) {
    if (isStrict) {
      console.log('❌ Some icon validations failed! (strict mode)')
      process.exit(1)
    } else {
      console.log('⚠️  Some icon validations failed (warning only)')
      console.log('   Run with --strict or STRICT_ICON_CHECK=true to enforce')
      process.exit(0)
    }
  } else {
    console.log('✅ All icon validations passed!')
    process.exit(0)
  }
}

main()
