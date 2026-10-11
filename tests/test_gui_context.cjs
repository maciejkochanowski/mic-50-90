const test = require('node:test');
const assert = require('node:assert/strict');
const M = require('../src/mic_50_90/gui_assets/model.js');

test('blank sample context defaults to unknown without inferring iid', () => {
  const value = M.blank();
  assert.equal(value.config.sample_context.repeat_sampling, 'unknown');
  M.setSampleContext(value.config, {repeat_sampling:'no', host_species:'cattle'});
  assert.equal(value.config.iid, false);
});

test('editing sample context retains unknown source metadata through saved import', () => {
  const value = M.importInput({n:20, panel:{levels:[1,2]}, iid:false,
    sample_context:{repeat_sampling:'yes', specimen:'milk', source_note:{table:3}}});
  M.setSampleContext(value.config, {host_species:'cattle', specimen:'milk', repeat_sampling:'unknown', grouping_notes:'two farms', intended_population:'regional herds'});
  const roundtrip = M.importText(JSON.stringify(M.save(value)));
  assert.deepEqual(roundtrip.config.sample_context, {repeat_sampling:'unknown', specimen:'milk', source_note:{table:3}, host_species:'cattle', grouping_notes:'two farms', intended_population:'regional herds'});
  assert.equal(roundtrip.config.iid, false);
});

test('opening an older saved analysis does not insert metadata or threshold defaults', () => {
  const config = {n:20, panel:{levels:[1,2]}, iid:false, targets:[{threshold:1,unit:'mg/L'}]};
  const original = structuredClone(config);
  M.setSampleContext(config, {host_species:'', specimen:'', repeat_sampling:'unknown', grouping_notes:'', intended_population:''});
  M.setThresholdField(config.targets[0], 'threshold_kind', 'custom');
  M.setThresholdField(config.targets[0], 'threshold_source', '');
  assert.deepEqual(config, original);
});

test('threshold source context and decimal criteria survive save import', () => {
  const value = M.blank();
  value.config.targets = [{threshold:1,unit:'mg/L',decision_fraction:'0.050000000000001',source_extension:'retained'}];
  for (const [key, text] of Object.entries({threshold_kind:'clinical',threshold_source:'standard',threshold_version:'2026',threshold_applicability:'declared context'})) M.setThresholdField(value.config.targets[0],key,text);
  assert.deepEqual(M.importText(JSON.stringify(M.save(value))).config.targets, value.config.targets);
});

test('changing the question event clears incompatible boundaries but keeps the criterion', () => {
  const row = {threshold:1,unit:'mg/L',decision_operator:'<',decision_fraction:'0.050000000000001',threshold_kind:'clinical',threshold_source:'standard'};
  M.setTargetKind(row, 'category_range');
  assert.equal(row.threshold, undefined);
  assert.equal(row.threshold_kind, undefined);
  assert.equal(row.threshold_source, undefined);
  assert.equal(row.start_category, '');
  assert.equal(row.end_category, '');
  row.start_category='2';row.end_category='>4';
  const payload=M.blank();payload.config.targets=[row];
  assert.deepEqual(M.importText(JSON.stringify(M.save(payload))).config.targets,[row]);
  M.setTargetKind(row,'threshold');
  assert.equal(row.start_category,undefined);
  assert.equal(row.end_category,undefined);
  assert.equal(row.threshold,null);
  assert.equal(row.decision_fraction,'0.050000000000001');
});
