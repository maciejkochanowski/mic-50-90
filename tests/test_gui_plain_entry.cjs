const test=require('node:test');
const assert=require('node:assert/strict');
const M=require('../src/mic_50_90/gui_assets/model.js');

test('blank entry explains the two essential missing sample fields',()=>{
  const issues=M.stepIssues(M.blank(),0);
  assert.deepEqual(issues.map(x=>x.id),['n','unit']);
  assert.match(issues[0].message,/same organism and antimicrobial/);
});
test('a missing panel gives a source-finding instruction',()=>{
  const p=M.blank();p.config.n=67;p.config.unit='mg/L';
  assert.match(M.stepIssues(p,1)[0].message,/Methods|laboratory/);
});
test('unknown MIC convention cannot be quietly filled in',()=>{
  const p=M.blank();p.config.summaries.quantiles=[{probability:.5,category:'1'}];
  const before=JSON.stringify(p);
  assert.match(M.stepIssues(p,2)[0].message,/MIC50/);
  assert.equal(JSON.stringify(p),before);
});
test('counts alone need no MIC quantile convention',()=>{
  const p=M.blank();p.config.n=67;p.config.additional_counts=[{threshold:.25,count:59,n:67,relation:'<='}];
  assert.deepEqual(M.stepIssues(p,2),[]);
});
test('zero count is present, while a missing histogram cell is not zero',()=>{
  const p=M.blank();p.mode='reporting-audit';p.config.n=10;
  p.histogram=[{category:'1',count:10},{category:'2',count:null}];p.rank_convention='ceiling';
  assert.match(M.stepIssues(p,2)[0].message,/including zeros/);
  p.histogram[1].count=0;
  assert.deepEqual(M.stepIssues(p,2),[]);
});
test('histogram totals use the original sample size',()=>{
  const p=M.blank();p.mode='reporting-audit';p.config.n=67;p.histogram=[{count:59},{count:9}];p.rank_convention='ceiling';
  assert.match(M.stepIssues(p,2)[0].message,/68.*67/);
});
test('plain distribution requires no optional criterion or inference layer',()=>{
  assert.deepEqual(M.stepIssues(M.blank(),3),[]);
});
test('laboratory comparison explains why it needs a concentration',()=>{
  const p=M.blank();p.mode='reporting-audit';
  assert.match(M.stepIssues(p,3)[0].message,/concentration/);
});
