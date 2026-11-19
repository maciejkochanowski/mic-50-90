const {test}=require('node:test');
const assert=require('node:assert/strict');
const M=require('../src/mic_50_90/gui_assets/model.js');
for (const version of ['1.0.0','1.0.1','1.0.2','1.0.3']) {
 test(`certificate ${version} remains readable after patch upgrade`,()=>{
  const raw=JSON.stringify({version,certificates:[{specification:{n:20},criteria:[{decision_fraction:'0.05'}],disclosures:[]}]});
  const imported=M.certificateInput(raw);
  assert.equal(imported.certificate_json,raw);
  assert.equal(M.importText(JSON.stringify(M.save(imported))).certificate_json,raw);
 });
}
test('unknown certificate producer remains refused',()=>{
 const raw=JSON.stringify({version:'9.9.9',certificates:[{specification:{n:20},criteria:[],disclosures:[]}]});
 assert.throws(()=>M.certificateInput(raw),/MIC-50-90 reporting_certificates/);
});
