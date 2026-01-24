/**
 * Script to check if JSON filenames match their internal 'id' field
 * 
 * This script scans all JSON files in the data directory and reports
 * any files where the filename (without .json extension) differs from
 * the 'id' field inside the JSON file.
 * 
 * Usage: node scripts/check-filename-id-mismatch.js
 */

const fs = require('fs');
const path = require('path');

// Directory containing the data files
const DATA_DIR = path.join(__dirname, '..', 'data');

/**
 * Recursively get all JSON files in a directory
 * @param {string} dir - Directory to scan
 * @returns {string[]} - Array of file paths
 */
function getJsonFiles(dir) {
  let results = [];
  
  // Read all items in the directory
  const items = fs.readdirSync(dir);
  
  for (const item of items) {
    const fullPath = path.join(dir, item);
    const stat = fs.statSync(fullPath);
    
    if (stat.isDirectory()) {
      // Recursively scan subdirectories
      results = results.concat(getJsonFiles(fullPath));
    } else if (item.endsWith('.json')) {
      // Add JSON files to results
      results.push(fullPath);
    }
  }
  
  return results;
}

/**
 * Check if a file's name matches its internal ID
 * @param {string} filePath - Path to the JSON file
 * @returns {object|null} - Mismatch info or null if they match
 */
function checkFilenameIdMismatch(filePath) {
  try {
    // Read and parse the JSON file
    const content = fs.readFileSync(filePath, 'utf8');
    const data = JSON.parse(content);
    
    // Get the filename without the .json extension
    const filename = path.basename(filePath, '.json');
    
    // Get the ID from the JSON content
    const id = data.id;
    
    // If there's no ID field, skip this file
    if (!id) {
      return null;
    }
    
    // Compare filename with ID
    if (filename !== id) {
      return {
        filePath: filePath,
        relativePath: path.relative(DATA_DIR, filePath),
        filename: filename,
        id: id
      };
    }
    
    return null;
  } catch (error) {
    console.error(`Error reading file ${filePath}: ${error.message}`);
    return null;
  }
}

/**
 * Main function to run the check
 */
function main() {
  console.log('Checking for filename/ID mismatches...\n');
  console.log(`Scanning directory: ${DATA_DIR}\n`);
  
  // Get all JSON files
  const files = getJsonFiles(DATA_DIR);
  console.log(`Found ${files.length} JSON files to check.\n`);
  
  // Check each file for mismatches
  const mismatches = [];
  
  for (const file of files) {
    const mismatch = checkFilenameIdMismatch(file);
    if (mismatch) {
      mismatches.push(mismatch);
    }
  }
  
  // Report results
  if (mismatches.length === 0) {
    console.log('✅ All filenames match their IDs!');
  } else {
    console.log(`❌ Found ${mismatches.length} mismatch(es):\n`);
    console.log('─'.repeat(80));
    
    for (const mismatch of mismatches) {
      console.log(`File: ${mismatch.relativePath}`);
      console.log(`  Filename: "${mismatch.filename}"`);
      console.log(`  ID:       "${mismatch.id}"`);
      console.log('─'.repeat(80));
    }
    
    // Summary table
    console.log('\nSummary:');
    console.log('┌─────────────────────────────────────────┬─────────────────────────────────────────┐');
    console.log('│ Filename                                │ ID in file                              │');
    console.log('├─────────────────────────────────────────┼─────────────────────────────────────────┤');
    
    for (const mismatch of mismatches) {
      const filename = mismatch.filename.padEnd(39).substring(0, 39);
      const id = mismatch.id.padEnd(39).substring(0, 39);
      console.log(`│ ${filename} │ ${id} │`);
    }
    
    console.log('└─────────────────────────────────────────┴─────────────────────────────────────────┘');
    
    // Exit with error code if mismatches found
    process.exit(1);
  }
}

// Run the script
main();
