'use strict';

const Promise = require('bluebird')
const fs = require('fs')
const readFile = Promise.promisify(fs.readFile)
const { getFiles, getFile } = require('./utils')
const Ajv = require('ajv')
const ajv = Ajv({ allErrors: true })
ajv.addMetaSchema(require('ajv/lib/refs/json-schema-draft-06.json'))
var validate = ajv.compile(require('../schema.json'))
var validData = true

function asyncFunction(file, cb) {
  getFile(file)
    .then(e => {
      const valid = validate(JSON.parse(e))
      if (!valid) {
        console.log(file + ': ')
        console.log(validate.errors)
        validData = false
      }
      cb()
    })
    .catch(e => console.error(e))
}

let requests = getFiles('data').map((fileName) => {
  return new Promise((resolve) => { 
    asyncFunction(fileName, resolve)
    const ext = fileName.split('.').pop();
    if (ext !== 'json') {
      throw `"${ext}" must be saved with a JSON extension`
    }
  });
})

Promise.all(requests).then(() => {
  validData ? console.log('All data is valid') : process.exitCode = 1
})