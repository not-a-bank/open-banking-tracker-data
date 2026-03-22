#!/usr/bin/env node

'use strict'

/**
 * HTTP link checker for provider and aggregator JSON.
 * Default: retailWebLoginUrl + commercialWebLoginUrl only (fast, targets SEO login fields).
 * --full: additional whitelisted URL fields (website, docs, icons, MCP URLs, etc.).
 */

const fs = require('fs')
const path = require('path')
const https = require('https')
const http = require('http')

const DEFAULT_TIMEOUT_MS = 15000
const DEFAULT_CONCURRENCY = 12
const MAX_REDIRECTS = 8

const UA_BOT = 'Mozilla/5.0 (compatible; OpenBankingTracker-LinkValidator/1.0; +https://github.com/not-a-bank/open-banking-tracker-data)'
const UA_BROWSER =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'

const LOGIN_KEYS = new Set(['retailWebLoginUrl', 'commercialWebLoginUrl'])

/** Keys checked when --full is passed (any nesting depth; parent key must match). */
const FULL_LINK_KEYS = new Set([
  ...LOGIN_KEYS,
  'icon',
  'websiteUrl',
  'developerPortalUrl',
  'developerCommunityUrl',
  'openBankProjectUrl',
  'apiReferenceUrl',
  'investorRelationsUrl',
  'wikipediaUrl',
  'storeUrl',
  'sourceUrl',
  'caseStudyUrl',
  'documentationUrl',
  'statusUrl',
  'institutionStatusUrl',
  'githubUrl',
  'shareholderIconUrl',
  'apiAccessRequestUrl',
  'apiChangelogUrl',
  'apiMarketplaceUrl',
  'serverUrl',
  'repositoryUrl',
  'smitheryUrl',
  'iconUrl',
  'website'
])

function getFilesRecursive (dir) {
  let fileList = []
  let files
  try {
    files = fs.readdirSync(dir)
  } catch (e) {
    return fileList
  }
  for (let i = 0; i < files.length; i++) {
    const name = path.join(dir, files[i])
    const stat = fs.statSync(name)
    if (stat.isDirectory()) {
      fileList = fileList.concat(getFilesRecursive(name))
    } else if (files[i].endsWith('.json') && files[i] !== '.DS_Store') {
      fileList.push(name)
    }
  }
  return fileList
}

function getProviderFiles () {
  const dataDir = path.join(__dirname, '../data')
  const dirs = [
    path.join(dataDir, 'account-providers'),
    path.join(dataDir, 'third-party-providers')
  ]
  let out = []
  for (const dir of dirs) {
    out = out.concat(getFilesRecursive(dir))
  }
  return out
}

function getAggregatorFiles () {
  return getFilesRecursive(path.join(__dirname, '../data/api-aggregators'))
}

/**
 * @param {string} url
 * @param {object} opts
 * @param {string} opts.method 'HEAD' | 'GET'
 * @param {number} opts.redirectsLeft
 * @param {string} [opts.userAgent]
 * @returns {Promise<{ ok: boolean, status: number, finalUrl: string, error?: string }>}
 */
function requestOnce (url, opts) {
  const method = opts.method || 'HEAD'
  const redirectsLeft = opts.redirectsLeft ?? MAX_REDIRECTS
  const timeoutMs = opts.timeoutMs || DEFAULT_TIMEOUT_MS
  const userAgent = opts.userAgent || UA_BOT

  return new Promise((resolve) => {
    let parsed
    try {
      parsed = new URL(url)
    } catch (e) {
      resolve({ ok: false, status: 0, finalUrl: url, error: 'Invalid URL' })
      return
    }

    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      resolve({ ok: false, status: 0, finalUrl: url, error: 'Unsupported protocol' })
      return
    }

    const client = parsed.protocol === 'https:' ? https : http
    const req = client.request(
      {
        method,
        hostname: parsed.hostname,
        port: parsed.port || undefined,
        path: parsed.pathname + parsed.search,
        timeout: timeoutMs,
        headers: {
          'User-Agent': userAgent,
          Accept: method === 'GET' ? 'text/html,application/xhtml+xml,*/*;q=0.8' : '*/*',
          'Accept-Language': 'en-US,en;q=0.9'
        }
      },
      (res) => {
        if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location && redirectsLeft > 0) {
          let nextUrl
          try {
            nextUrl = new URL(res.headers.location, url).href
          } catch (e) {
            resolve({ ok: false, status: res.statusCode, finalUrl: url, error: 'Bad redirect location' })
            return
          }
          res.resume()
          requestOnce(nextUrl, {
            method,
            redirectsLeft: redirectsLeft - 1,
            timeoutMs,
            userAgent
          }).then(resolve)
          return
        }

        const ok = res.statusCode >= 200 && res.statusCode < 400
        res.resume()
        resolve({ ok, status: res.statusCode || 0, finalUrl: url })
      }
    )

    req.on('error', (err) => {
      resolve({ ok: false, status: 0, finalUrl: url, error: err.message })
    })
    req.on('timeout', () => {
      req.destroy()
      resolve({ ok: false, status: 0, finalUrl: url, error: 'Request timeout' })
    })
    req.end()
  })
}

/**
 * HEAD first; on 405/501 retry GET (some hosts disallow HEAD).
 * On 401/403 retry GET with a browser User-Agent (many banks use WAF / bot blocks).
 */
async function checkUrl (url, timeoutMs) {
  const t = timeoutMs || DEFAULT_TIMEOUT_MS
  let r = await requestOnce(url, { method: 'HEAD', timeoutMs: t })
  if (!r.ok && (r.status === 405 || r.status === 501)) {
    r = await requestOnce(url, { method: 'GET', timeoutMs: t })
  }
  if (!r.ok && (r.status === 401 || r.status === 403)) {
    r = await requestOnce(url, { method: 'GET', timeoutMs: t, userAgent: UA_BROWSER })
  }
  if (!r.ok && (r.status === 502 || r.status === 503 || r.status === 504)) {
    await new Promise((res) => setTimeout(res, 2000))
    r = await requestOnce(url, { method: 'GET', timeoutMs: t, userAgent: UA_BROWSER })
  }
  return r
}

function walkForLinks (node, keyName, keySet, acc, filePath, idHint) {
  if (node === null || node === undefined) return

  if (typeof node === 'string' && keySet.has(keyName)) {
    if (/^https?:\/\//i.test(node)) {
      acc.push({
        url: node,
        field: keyName,
        file: filePath,
        id: idHint
      })
    }
    return
  }

  if (Array.isArray(node)) {
    for (let i = 0; i < node.length; i++) {
      // Reset key context so nested objects expose real field names (e.g. documentationUrl in apiProducts[])
      walkForLinks(node[i], '', keySet, acc, filePath, idHint)
    }
    return
  }

  if (typeof node === 'object') {
    const id = node.id != null ? node.id : idHint
    for (const k of Object.keys(node)) {
      walkForLinks(node[k], k, keySet, acc, filePath, id)
    }
  }
}

function extractLinks (json, filePath, keySet) {
  const acc = []
  const idHint = json && json.id != null ? json.id : path.basename(filePath, '.json')
  walkForLinks(json, '', keySet, acc, filePath, idHint)
  return acc
}

async function runPool (tasks, concurrency, worker) {
  let i = 0
  const results = []
  async function workerLoop () {
    while (i < tasks.length) {
      const idx = i++
      results[idx] = await worker(tasks[idx], idx)
    }
  }
  const runners = []
  const n = Math.min(concurrency, Math.max(1, tasks.length))
  for (let w = 0; w < n; w++) runners.push(workerLoop())
  await Promise.all(runners)
  return results
}

function parseArgs () {
  const argv = process.argv.slice(2)
  const out = {
    full: false,
    aggregators: false,
    providers: true,
    strict: false,
    allow403: false,
    concurrency: DEFAULT_CONCURRENCY,
    timeout: DEFAULT_TIMEOUT_MS,
    files: [],
    help: false
  }

  for (let a = 0; a < argv.length; a++) {
    const t = argv[a]
    if (t === '--help' || t === '-h') out.help = true
    else if (t === '--full') out.full = true
    else if (t === '--aggregators') out.aggregators = true
    else if (t === '--no-providers') out.providers = false
    else if (t === '--strict') out.strict = true
    else if (t === '--allow-403') out.allow403 = true
    else if (t === '--concurrency') out.concurrency = Math.max(1, parseInt(argv[++a], 10) || DEFAULT_CONCURRENCY)
    else if (t === '--timeout') out.timeout = Math.max(1000, parseInt(argv[++a], 10) || DEFAULT_TIMEOUT_MS)
    else if (!t.startsWith('-')) out.files.push(path.resolve(t))
  }

  return out
}

async function main () {
  const args = parseArgs()
  if (args.help || (args.files.length === 0 && !args.providers && !args.aggregators)) {
    console.log(`
Usage: node scripts/validate-links.js [options] [file.json ...]

Checks that HTTP(S) URLs in JSON data respond successfully (2xx/3xx → final 2xx).

Options:
  (default)     Scan all account-providers + third-party-providers for login URLs only
                (${[...LOGIN_KEYS].join(', ')}).

  --full        Also check other whitelisted link fields (websiteUrl, icon, docs, MCP URLs, …).
  --aggregators Include data/api-aggregators (useful with --full).
  --no-providers Skip provider directories when using explicit paths or --aggregators-only flow.

  --strict      Exit with code 1 if any link fails (default: warn only, exit 0).
  --allow-403   Treat HTTP 403 as OK (many bank sites block automated clients; use with care).
  --concurrency N   Parallel requests (default: ${DEFAULT_CONCURRENCY}).
  --timeout MS      Per-request timeout (default: ${DEFAULT_TIMEOUT_MS}).

  file.json ... Only validate these files (implies you manage the list yourself).

Examples:
  npm run validate-links
  npm run validate-links -- --full --aggregators --strict
  node scripts/validate-links.js --strict data/account-providers/allica-bank.json
`)
    process.exit(args.help ? 0 : 1)
  }

  const keySet = args.full ? FULL_LINK_KEYS : LOGIN_KEYS

  let files = [...args.files]
  if (args.files.length === 0) {
    if (args.providers) files = files.concat(getProviderFiles())
    if (args.aggregators) files = files.concat(getAggregatorFiles())
  }

  if (files.length === 0) {
    console.error('No JSON files to scan.')
    process.exit(1)
  }

  /** @type {{ url: string, field: string, file: string, id: string }[]} */
  const tasks = []
  let readErrors = 0

  for (const filePath of files) {
    let raw
    try {
      raw = fs.readFileSync(filePath, 'utf8')
    } catch (e) {
      readErrors++
      console.error(`❌ Read error: ${filePath} (${e.message})`)
      continue
    }

    if (!args.full) {
      const hasLogin =
        raw.includes('"retailWebLoginUrl"') || raw.includes('"commercialWebLoginUrl"')
      if (!hasLogin) continue
    }

    let json
    try {
      json = JSON.parse(raw)
    } catch (e) {
      readErrors++
      console.error(`❌ JSON parse: ${filePath} (${e.message})`)
      continue
    }

    const links = extractLinks(json, filePath, keySet)
    for (const L of links) {
      tasks.push(L)
    }
  }

  console.log(`\n🔗 Link validation (${args.full ? 'full' : 'login-only'} fields, ${tasks.length} URLs, concurrency ${args.concurrency})\n`)

  if (tasks.length === 0) {
    console.log('No URLs to check in scope.')
    process.exit(readErrors > 0 ? 1 : 0)
  }

  const failures = []
  const forbiddenSkips = []

  await runPool(tasks, args.concurrency, async (task) => {
    const r = await checkUrl(task.url, args.timeout)
    const rel = path.relative(path.join(__dirname, '..'), task.file)
    const ok = r.ok || (args.allow403 && r.status === 403)
    if (ok) {
      process.stdout.write(r.ok ? '.' : 'F')
      if (!r.ok && r.status === 403) {
        forbiddenSkips.push({ ...task, rel, status: r.status, finalUrl: r.finalUrl })
      }
    } else {
      process.stdout.write('x')
      failures.push({
        ...task,
        rel,
        status: r.status,
        error: r.error || null,
        finalUrl: r.finalUrl
      })
    }
  })

  console.log('\n')

  if (forbiddenSkips.length) {
    console.log(`\n⚠️  HTTP 403 (allowed via --allow-403; page may still work in a browser): ${forbiddenSkips.length}\n`)
    for (const f of forbiddenSkips) {
      console.log(`  • ${f.rel} (${f.id})  ${f.field}\n    ${f.url}\n`)
    }
  }

  if (failures.length) {
    console.log(`❌ Failed: ${failures.length} / ${tasks.length}\n`)
    for (const f of failures) {
      console.log(`  • ${f.rel} (${f.id})  ${f.field}`)
      console.log(`    ${f.url}`)
      console.log(`    → HTTP ${f.status}${f.error ? ` (${f.error})` : ''}\n`)
    }
  } else if (!forbiddenSkips.length) {
    console.log(`✅ All ${tasks.length} URLs responded successfully.\n`)
  } else {
    console.log(`✅ No hard failures (${forbiddenSkips.length} URL(s) skipped as 403 only).\n`)
  }

  if (readErrors > 0) {
    console.log(`⚠️  ${readErrors} file read/parse error(s).\n`)
  }

  const broken = failures.length > 0 || readErrors > 0
  if (args.strict && broken) {
    process.exit(1)
  }
  process.exit(0)
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
