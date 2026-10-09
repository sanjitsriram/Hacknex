const { parseLabReport } = require('./frontend/src/lib/parseLabReport');
const fs = require('fs');
const data = JSON.parse(fs.readFileSync('payload.json'));

const result = parseLabReport(data.parsing_run);
console.log(JSON.stringify(result, null, 2));
