const test = require('node:test');
const assert = require('node:assert/strict');
const M = require('../src/mic_50_90/gui_assets/model.js');

test('new forms suggest a grouping width, imported analyses preserve opt-in', () => {
  assert.equal(M.blank().options.population_precision_pp, 10);
  const config = {n:20, unit:'mg/L', iid:true, panel:{levels:[1,2]}};
  const bare = M.importInput(config);
  assert.equal(bare.options.population_precision_pp, undefined);
  assert.equal(M.importInput({inputs:[config]}).options.population_precision_pp, undefined);
  for (const width of [null, 12.5]) {
    const imported = M.importInput({inputs:[config], population_precision_pp:width});
    assert.equal(imported.options.population_precision_pp, width);
    assert.equal(M.importInput(M.save(imported)).options.population_precision_pp, width);
  }
});

function savedInput(kind) {
  const config = {n:20, unit:'mg/L', panel:{levels:[1,2]},
    additional_counts:[{threshold:1, count:8, n:20, unit:'mg/L'}],
    source_extension:{table:'A', annotation:'unchanged'}};
  if (kind !== 'absent-targets') config.targets = [];
  if (kind === 'implicit-target-scale') {
    Object.assign(config.additional_counts[0], {relation:'>', source:''});
    config.targets.push({threshold:1, unit:'mg/L', decision_operator:'<=',
      decision_fraction:'0.4000000000000000001'});
  }
  return M.importInput(config);
}

for (const kind of ['absent-targets', 'implicit-count-defaults', 'implicit-target-scale']) {
  test(`unchanged collection preserves saved ${kind}`, () => {
    const payload = savedInput(kind), original = M.clone(payload.config);
    // These are the defaults displayed by the real form's controls.
    for (const row of M.targets(payload)) {
      M.setThresholdField(row, 'target_scale', row.target_scale || 'recorded');
      M.setThresholdField(row, 'threshold_kind', row.threshold_kind || 'custom');
      M.setThresholdField(row, 'threshold_source', row.threshold_source ?? '');
    }
    for (const row of payload.config.additional_counts) {
      M.setCountField(row, 'relation', row.relation || '>');
      M.setCountField(row, 'source_scale', row.source_scale ?? '');
      M.setCountField(row, 'source', row.source ?? '');
    }
    assert.deepEqual(payload.config, original);
    assert.deepEqual(M.importText(JSON.stringify(M.save(payload))).config, {
      ...original, n:'20', additional_counts:original.additional_counts.map(row => ({...row, n:'20', count:'8'})),
    });
  });
}

test('adding a target explicitly creates the previously absent collection', () => {
  const payload = savedInput('absent-targets');
  assert.deepEqual(M.targets(payload), []);
  assert.equal('targets' in payload.config, false);
  M.targets(payload, true).push({threshold:2, unit:'mg/L'});
  assert.deepEqual(payload.config.targets, [{threshold:2, unit:'mg/L'}]);
});

test('explicit edits record displayed defaults and later non-default values', () => {
  const count = {threshold:1, count:8, n:20, unit:'mg/L'};
  M.setCountField(count, 'relation', '>', true);
  M.setCountField(count, 'source', '', true);
  assert.equal(count.relation, '>');
  assert.equal(count.source, '');
  M.setCountField(count, 'relation', '<=', true);
  M.setCountField(count, 'source', 'Laboratory record A', true);
  assert.equal(count.relation, '<=');
  assert.equal(count.source, 'Laboratory record A');
  const target = {threshold:1, unit:'mg/L'};
  M.setThresholdField(target, 'target_scale', 'recorded', true);
  M.setThresholdField(target, 'threshold_kind', 'custom', true);
  assert.equal(target.target_scale, 'recorded');
  assert.equal(target.threshold_kind, 'custom');
  M.setThresholdField(target, 'target_scale', 'interval', true);
  assert.equal(target.target_scale, 'interval');
});

test('collection retains absent and existing blank optional count fields', () => {
  const row = {threshold:1, count:8, n:20, unit:'mg/L', decimal_places:''};
  const original = M.clone(row);
  M.setCountField(row, 'count_min', null);
  M.setCountField(row, 'percentage', '');
  M.setCountField(row, 'decimal_places', null);
  assert.deepEqual(row, original);
});

test('the count editor selects supplied information instead of unused blank fields', () => {
  assert.equal(typeof M.countType, 'function', 'The editor needs a shared count representation selector.');
  assert.equal(M.countType({count:0, count_min:'', count_max:null, percentage:''}), 'exact');
  assert.equal(M.countType({count:'', count_min:7, count_max:9, percentage:null}), 'range');
  assert.equal(M.countType({count:null, count_min:'', count_max:'', percentage:'40'}), 'percentage');
  assert.equal(M.countType({count_min:null, count_max:null}), 'range');
  assert.equal(M.countType({percentage:'', decimal_places:null}), 'percentage');
});

test('the count preview uses a supplied range when the exact field is blank', () => {
  assert.match(M.countPreview({threshold:1, source_scale:'recorded', n:20,
    count:'', count_min:7, count_max:9}, {levels:[1,2]}), /7 to 9 of 20/);
});
