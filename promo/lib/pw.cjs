// Playwright from the global install, so the studio needs no npm install.
module.exports = require(require('child_process').execSync('npm root -g').toString().trim() + '/playwright');
