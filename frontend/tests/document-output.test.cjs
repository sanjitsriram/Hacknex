const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const code = ts.transpileModule(fs.readFileSync('src/lib/document-output.ts', 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
const mod = { exports: {} };
new Function('exports', 'module', code)(mod.exports, mod);
const { documentOutput } = mod.exports;
test('JSON preserves all pages, provider metadata and raw content without mutation', () => {
  const run = { id: 'run-1', provider_id: 'provider', model_version: '1.6', input_sha256: 'hash', markdown_text: 'தமிழ்', pages: [{ markdown_text: 'one', blocks: [{ content: '<script>raw</script>', bounding_box: { x: 2, y: 3, w: 4, h: 5 } }] }, { markdown_text: 'two', blocks: [] }] };
  const before = JSON.stringify(run);
  const result = JSON.parse(documentOutput(run, 'json'));
  assert.deepEqual(result.parsing_run, run);
  assert.equal(result.review_status, 'unverified');
  assert.equal(JSON.stringify(run), before);
  assert.equal(documentOutput(run, 'markdown'), 'தமிழ்');
});
test('Markdown fallback includes every page without invented text', () => {
  assert.equal(documentOutput({ markdown_text: '', pages: [{ markdown_text: 'one' }, { markdown_text: 'two' }] }, 'markdown'), 'one\n\ntwo');
});
