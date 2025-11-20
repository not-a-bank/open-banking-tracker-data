# Quick Reference: Validate Individual Files

## Quick Start

### Validate a single file:
```bash
npm run validate-file -- data/account-providers/220bank.json
```

### See detailed errors:
```bash
npm run validate-file -- data/account-providers/220bank.json --verbose
```

### Validate an API aggregator:
```bash
npm run validate-file -- data/api-aggregators/plaid.json
```

### Get help:
```bash
npm run validate-file -- --help
```

## Output Examples

### ✅ Valid File
```
✅ File is VALID
```

### ❌ Invalid File (Compact)
```
❌ File has ERRORS:

  • .apiReferenceUrl: should match pattern "^(https?|http?)://"
  • .type: should be array

Run with --verbose for detailed errors
```

### ❌ Invalid File (Verbose)
```
❌ File has ERRORS:

Error 1:
  Location: .apiReferenceUrl
  Type: pattern
  Message: should match pattern "^(https?|http?)://"
```

## Command Options

| Option | Usage | Example |
|--------|-------|---------|
| `--verbose` or `-v` | Show detailed errors | `npm run validate-file -- file.json --verbose` |
| `--type <type>` | Specify schema (provider/aggregator/auto) | `npm run validate-file -- file.json --type aggregator` |
| `--help` or `-h` | Show help | `npm run validate-file -- --help` |

## Exit Codes

- `0`: File is valid ✅
- `1`: File has validation errors ❌
- `2`: File not found or cannot be read
- `3`: Invalid arguments

Use in shell scripts:
```bash
npm run validate-file -- file.json && echo "Valid" || echo "Invalid"
```

## Common Use Cases

### Validate while editing:
```bash
npm run validate-file -- data/account-providers/220bank.json
```

### Understand what's wrong:
```bash
npm run validate-file -- data/account-providers/220bank.json --verbose
```

### Check multiple files:
```bash
for file in data/account-providers/*.json; do
  npm run validate-file -- "$file" || echo "Invalid: $file"
done
```

### Use in CI/CD:
```bash
npm run validate-file -- "$FILE_PATH" || exit 1
```

## Tips

✓ **Auto-detection**: Type is detected from file path (account-providers/ = provider, api-aggregators/ = aggregator)

✓ **Always use --verbose**: When debugging errors, verbose mode shows full context

✓ **Relative or absolute paths**: Both work fine

✓ **Exit codes**: Useful for scripts and CI/CD pipelines

✓ **Error messages**: Show exact location (e.g., `.apiReferenceUrl`) and what's wrong

## Alternative Methods

### Direct Node execution:
```bash
node scripts/validate-file.js data/account-providers/220bank.json
```

### Direct execution (after chmod +x):
```bash
./scripts/validate-file.js data/account-providers/220bank.json
```

## Script Location

`scripts/validate-file.js` - Full CLI validator with help and options

## For More Information

```bash
npm run validate-file -- --help
```

