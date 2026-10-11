const assert = require('node:assert/strict');
const path = require('node:path');
const {test} = require('node:test');
const modelPath = path.resolve(__dirname, '../src/mic_50_90/gui_assets/model.js');
let M;
try { M = require(modelPath); } catch (error) { if (error.code !== 'MODULE_NOT_FOUND') throw error; }
test('a fresh input has no guessed panel, quantiles, rank convention or iid declaration', () => {
  assert.ok(M, 'The guided input model is not implemented');
  const p = M.blank();
  assert.deepEqual(p.config.panel, {});
  assert.equal(p.config.iid, false);
  assert.deepEqual(p.config.summaries.quantiles, []);
});
test('saving and reopening retains advanced analysis settings without mutation', () => {
  assert.ok(M);
  const raw = {n:20, unit:'mg/L', panel:{levels:[1,2]}, custom:{evidence:'abc'}, reporting_envelope:{variants:[{id:'other'}]}};
  const p = M.importInput(raw);
  p.config.n = 25;
  assert.equal(raw.n,20);
  assert.deepEqual(M.importInput(M.save(p)),p);
  assert.deepEqual(p.config.custom,{evidence:'abc'});
  assert.deepEqual(p.config.reporting_envelope,raw.reporting_envelope);
});
test('output configuration imports only a single cohort and retains computation options', () => {
  assert.ok(M);
  const p=M.importInput({inputs:[{n:20,unit:'mg/L',panel:{levels:[1,2]}}],population_method:'joint-exact',precision_pp:10,population_time_limit:3});
  assert.equal(p.options.population_method,'joint-exact');
  assert.equal(p.options.precision_pp,10);
  assert.throws(()=>M.importInput({inputs:[{n:20},{n:30}]}),/one cohort/);
});
test('changing one quantile retains arbitrary other probabilities and clears conflicting rank representations', () => {
  assert.ok(M);
  const config={summaries:{quantiles:[{probability:.5,category:'1',rank:10,source:'reported'},{probability:.75,category:'2',rank:15}]}};
  M.setQuantile(config,.5,{category:'<=1',convention:'ceiling'});
  assert.deepEqual(config.summaries.quantiles,[{probability:.5,category:'<=1',convention:'ceiling',source:'reported'},{probability:.75,category:'2',rank:15}]);
  M.setQuantile(config,.5,null);
  assert.equal(config.summaries.quantiles[0].probability,.75);
});
test('exact counts at or below a threshold are complemented without guessing endpoint conventions', () => {
  assert.ok(M);
  assert.equal(M.exactCount(67,59,'<='),8);
  assert.equal(M.exactCount(67,8,'>'),8);
  assert.throws(()=>M.exactCount(67,59,'>='),/strictly above/);
  assert.throws(()=>M.exactCount(67,59.2,'<='),/integer/);
});
test('panel preview preserves explicit categories and accurately describes shorthand censoring', () => {
  assert.ok(M);
  assert.deepEqual(M.panelLabels({levels:[1,2]}),['<=1','2','>2']);
  assert.deepEqual(M.panelLabels({levels:[1,2],left_censored:false,right_censored:false}),['1','2']);
  assert.deepEqual(M.panelLabels({categories:[{label:'low'},{label:'high'}]}),['low','high']);
});
test('render data do not stringify absent scientific input into numbers', () => {
  assert.ok(M);
  assert.equal(M.number(''),null);
  assert.throws(()=>M.number('abc'),/finite/);
  assert.throws(()=>M.number('Infinity'),/finite/);
  assert.equal(M.number('0'),0);
});
test('import preserves exact counts and criterion decimals without JavaScript rounding',()=>{
  assert.equal(typeof M.parseJSON,'function');
  const p=M.parseJSON('{"n":2.0000000000000001,"targets":[{"decision_fraction":0.1000000000000000001}],"panel":{"levels":[0.5,1]},"label":"example 123"}');
  assert.equal(p.n,'2.0000000000000001');
  assert.equal(p.targets[0].decision_fraction,'0.1000000000000000001');
  assert.deepEqual(p.panel.levels,[.5,1]);
  assert.equal(p.label,'example 123');
  assert.throws(()=>M.parseJSON('{"panel":{"levels":[0.1000000000000000001]}}'),/precision/);
});
test('exact integer input and complements never truncate fractional or unsafe values',()=>{
  assert.equal(typeof M.integer,'function');
  assert.equal(M.integer('20'),'20');
  assert.throws(()=>M.integer('20.000000000000001'),/integer/);
  assert.equal(M.exactCount('7133','5407','<='),'1726');
  assert.throws(()=>M.integer('9007199254740992'),/supported/);
});
test('quantile editing recognises exact probability strings from saved engine configurations',()=>{
 const config={summaries:{quantiles:[{probability:'0.5',category:'<=1',convention:'ceiling'},{probability:'0.9',category:'2',convention:'ceiling'}]}};
 M.setQuantile(config,.5,{category:'<=1',rank:'10'});
 assert.equal(config.summaries.quantiles.length,2);
 assert.equal(config.summaries.quantiles[0].probability,'0.5');
 assert.equal(config.summaries.quantiles[0].rank,'10');
});
test('concentration-series labels match the engine twelve-significant-digit formatting',()=>{
 assert.deepEqual(M.panelLabels({levels:[1e-7,.123456789123456]}),['<=1e-07','0.123456789123','>0.123456789123']);
});
test('opaque calibration records and user metadata retain ordinary numeric types',()=>{
 const p=M.parseJSON('{"n":20,"custom":{"n":20,"count":2},"wasserstein_calibration_manifest":{"n":20,"count":2},"calibration_context":{"n":20},"additional_counts":[{"n":20,"count":2}]}');
 assert.equal(p.n,'20');assert.equal(p.custom.n,20);assert.equal(p.custom.count,2);
 assert.equal(p.wasserstein_calibration_manifest.n,20);assert.equal(p.calibration_context.n,20);
 assert.equal(p.additional_counts[0].count,'2');
});
test('calibrated imports retain original JSON text for hash-preserving local transport',()=>{
 assert.equal(typeof M.importText,'function');
 const text='{"n":20,"panel":{"levels":[1,2]},"reference_distribution":[0.0,0.5,0.5],"wasserstein_calibration_manifest":{"level":0.75},"calibration_context":{"vectors":[[0.0,1.0,1.0]]}}';
 const p=M.importText(text);assert.equal(p.calibration_input_text,text);
 assert.equal(M.importText(JSON.stringify(M.save(p))).calibration_input_text,text);
});
