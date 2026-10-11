const test = require('node:test');
const assert = require('node:assert/strict');
const M = require('../src/mic_50_90/gui_assets/model.js');
test('suppressed counts convert exactly without treating blanks as zero',()=>{
  let r={n:50}; M.setSuppressedCount(r,'<','5');
  assert.equal(r.count_min,'0'); assert.equal(r.count_max,'4');
  assert.match(r.source_information.original_text,/<5/);
  r={n:50}; M.setSuppressedCount(r,'>=','5');
  assert.equal(r.count_min,'5'); assert.equal(r.count_max,'50');
  assert.throws(()=>M.setSuppressedCount({n:50},'<',''));
  assert.throws(()=>M.setSuppressedCount({n:50},'<','0'));
  assert.throws(()=>M.setSuppressedCount({n:50},'>=','51'));
});
test('measurement scale survives saved forms',()=>{
  const p=M.blank();p.config.targets=[{threshold:2,target_scale:'interval'}];
  assert.equal(M.importInput(M.save(p)).config.targets[0].target_scale,'interval');
});
