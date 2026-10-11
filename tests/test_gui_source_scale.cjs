const test=require('node:test');
const assert=require('node:assert/strict');
const M=require('../src/mic_50_90/gui_assets/model.js');

test('new counts state their recorded scale without changing reopened inputs',()=>{
  assert.equal(M.newCount('20','mg/L').source_scale,'recorded');
  const raw=M.blank();raw.config.additional_counts=[{threshold:2,count:10,n:20,unit:'mg/L',relation:'<='}];
  assert.equal(M.importInput(raw).config.additional_counts[0].source_scale,undefined);
});
test('recorded preview shows the exact selected category labels',()=>{
  const row={threshold:2,relation:'>=',source_scale:'recorded',count:10,n:20};
  const text=M.countPreview(row,{levels:[1,2,4]});
  assert.match(text,/2, 4, >4/);assert.match(text,/10 of 20/);
  assert.match(M.countPreview({...row,source_scale:'interval'},{levels:[1,2,4]}),/measurement interval/i);
});

test('a panel with implicit recorded values has the same count preview',()=>{
  const panel={categories:[{label:'a',lower_bound:null,upper_bound:1},
    {label:'b',lower_bound:1,upper_bound:2},{label:'c',lower_bound:2,upper_bound:null}]};
  const text=M.countPreview({source_scale:'recorded',threshold:1,relation:'>',count:10,n:20},panel);
  assert.match(text,/categories b, c/);
});

test('collecting an untouched optional count field preserves a saved update',()=>{
  const row={threshold:2,relation:'>',count:4,n:20,unit:'mg/L',source:'original row'};
  const before=JSON.stringify(row);
  M.setCountField(row,'source_scale','');
  assert.equal(JSON.stringify(row),before);
  M.setCountField(row,'source_scale','recorded');
  assert.equal(row.source_scale,'recorded');
});
