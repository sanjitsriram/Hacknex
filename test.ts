import { parseLabReport } from './frontend/src/lib/parseLabReport';
import fs from 'fs';
const data = JSON.parse(fs.readFileSync('payload.json', 'utf8'));

const result = parseLabReport(data.parsing_run);
console.log(JSON.stringify(result, null, 2));
