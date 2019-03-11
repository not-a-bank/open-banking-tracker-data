const Promise = require('bluebird')
const fs = require('fs')
const readFile = Promise.promisify(fs.readFile)

module.exports.getFiles = (dir) => {
  var fileList = [];

  var files = fs.readdirSync(dir);
  for(var i in files){
      if (!files.hasOwnProperty(i)) continue;
      var name = dir + '/' + files[i];
      if (!fs.statSync(name).isDirectory()){
        fileList.push(name);
      }
  }
  return fileList;
}

module.exports.getFile = (path) => {
  const file = readFile(path, 'utf8')
  return file
}