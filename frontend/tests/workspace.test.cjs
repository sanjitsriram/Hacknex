const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const code = ts.transpileModule(fs.readFileSync('src/lib/data.ts', 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
const mod = { exports: {} };
new Function('exports', 'module', code)(mod.exports, mod);
const { validateFile, updateRegionText, parseSavedState, regions, baseText, defaultPreferences } = mod.exports;
test('upload boundaries and supported MIME types', () => {
  for (const type of ['image/png', 'image/jpeg', 'image/webp', 'application/pdf']) assert.equal(validateFile({name:'source',type,size:20*1024*1024}), null);
  for (const file of [{type:'image/png',size:0},{type:'image/png',size:20*1024*1024+1},{type:'image/svg+xml',size:5},{type:'application/octet-stream',size:5}]) assert.ok(validateFile({name:'source',...file}));
});
test('region decisions update the intended line, including duplicate illegibility markers', () => {
  let text = updateRegionText(baseText, regions[0], '4.8', '[illegible]');
  text = updateRegionText(text, regions[1], 'Harris', '[illegible]');
  text = updateRegionText(text, regions[1], '[illegible]', 'Harvis');
  assert.ok(text.includes('north wall measures [illegible] metres.'));
  assert.ok(text.includes('Mr. Harvis on Friday.'));
});
test('manual text conflicts never change an unrelated occurrence', () => {
  assert.equal(updateRegionText('4.8\nCompletely edited text.', regions[0], '4.8', '4.3'), null);
  assert.equal(updateRegionText(regions[0].line + '\n' + regions[0].line, regions[0], '4.8', '4.3'), null);
});
test('malformed storage is rejected and invalid audit entries are ignored', () => {
  assert.throws(() => parseSavedState('{broken'));
  assert.throws(() => parseSavedState(JSON.stringify({text:'text',preferences:{reviewer:''},corrections:{},events:[]})));
  const result = parseSavedState(JSON.stringify({text:baseText,preferences:defaultPreferences,corrections:{r1:'4.8',r2:55},events:[null,{}],reviewed:true}));
  assert.equal(result.reviewed,false); assert.deepEqual(result.events,[]); assert.deepEqual(result.corrections,{r1:'4.8'});
});
test('api module exports and document mapping contract', () => {
  const apiCode = ts.transpileModule(fs.readFileSync('src/lib/api.ts', 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  const apiMod = { exports: {} };
  new Function('exports', 'module', apiCode)(apiMod.exports, apiMod);
  assert.ok(apiMod.exports.API_BASE);
  assert.equal(typeof apiMod.exports.fetchDocumentsFromApi, 'function');
  assert.equal(typeof apiMod.exports.uploadDocumentToApi, 'function');
  assert.equal(typeof apiMod.exports.recognizeRegionApi, 'function');
  assert.equal(typeof apiMod.exports.scheduleDocumentRecognitionApi, 'function');
  assert.equal(typeof apiMod.exports.getJobStatusApi, 'function');
  assert.equal(typeof apiMod.exports.fetchDocumentRegionsApi, 'function');
  assert.equal(typeof apiMod.exports.fetchDocumentJobsApi, 'function');
});
