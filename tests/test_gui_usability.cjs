const {test}=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const M=require(path.resolve(__dirname,'../src/mic_50_90/gui_assets/model.js'));
test('criterion percentages preserve exact strict boundary decimals and old fraction meaning',()=>{
 assert.equal(typeof M.percentToFraction,'function');
 assert.equal(M.percentToFraction('5'),'0.05');
 assert.equal(M.fractionToPercent('0.05000000000000000001'),'5.000000000000000001');
 assert.equal(M.percentToFraction('5.000000000000000001'),'0.05000000000000000001');
 assert.equal(M.fractionToPercent('1/3'),'100/3');
 assert.equal(M.percentToFraction('100/3'),'1/3');
 assert.throws(()=>M.percentToFraction('101'),/100/);
 assert.throws(()=>M.percentToFraction('-1'),/100/);
 assert.equal(M.percentToFraction(''),null);
});
test('counts-only saved targets survive open/save without requiring quantiles',()=>{
 const p=M.importText('{"n":20,"panel":{"levels":[1,2]},"additional_counts":[{"n":20,"count":1,"threshold":1,"unit":"mg/L"}],"targets":[{"threshold":1,"decision_operator":"<","decision_fraction":0.05}]}');
 assert.deepEqual(M.targets(p),[{threshold:1,decision_operator:'<',decision_fraction:'0.05'}]);
 assert.equal(M.targets(M.importInput(M.save(p)))[0].decision_fraction,'0.05');
});
test('table preview handles quoted delimiters, multiline cells and Excel pasted TSV',()=>{
 assert.equal(typeof M.previewTable,'function');
 assert.deepEqual(M.previewTable('cohort_id,source\nA,"x,y"\nB,"line\none"\n','comma').cohorts,['A','B']);
 assert.equal(M.previewTable('cohort_id\tn\r\nA\t20\r\n','tab').rows,1);
 assert.throws(()=>M.previewTable('cohort_id,n\nA,20,extra','comma'),/row 2/i);
 assert.throws(()=>M.previewTable('cohort_id,n\nA,20','tab'),/delimiter|columns/i);
});
test('table documents and certificate source text survive save and reopen',()=>{
 const table={mode:'distribution',input_format:'tables',tables:{input:{text:'cohort_id,n\nA,20',delimiter:'comma'}},options:{}};
 assert.equal(M.importInput(M.save(table)).tables.input.text,table.tables.input.text);
 const raw='{"version":"1.0.0","certificates":[{"specification":{"n":20},"criteria":[{"decision_fraction":0.05000000000000000001}],"disclosures":[]}]}';
 const p=M.certificateInput(raw);
 assert.equal(p.certificate_json,raw);
 assert.equal(M.importText(JSON.stringify(M.save(p))).certificate_json,raw);
});
test('count relation preview never converts greater-or-equal blindly',()=>{
 assert.match(M.countPreview({relation:'<=',n:'20',count:'19',threshold:1}),/1.*strictly above/);
 assert.match(M.countPreview({relation:'>=',n:'20',count:'1',threshold:1}),/categor|boundar/i);
 assert.match(M.countPreview({relation:'<',n:'20',count:'1',threshold:1}),/categor|boundar/i);
});
