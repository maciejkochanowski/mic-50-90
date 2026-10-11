const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');
const {chromium}=require('playwright');
(async()=>{
 const [readyFile,pack,out,chrome]=process.argv.slice(2),ready=JSON.parse(fs.readFileSync(readyFile,'utf8'));
 const browser=await chromium.launch({headless:true,executablePath:chrome});
 const page=await browser.newPage({viewport:{width:1060,height:940},deviceScaleFactor:1.5,acceptDownloads:true,locale:'en-US'});
 const errors=[],messages=[],record={};page.on('pageerror',e=>errors.push(String(e)));
 page.on('console',msg=>{if(msg.type()==='error')messages.push(msg.text().replace(/token=[^\s&]+/g,'token=REDACTED'));});
 async function shot(name,loc){await page.evaluate(()=>document.fonts.ready);await loc.scrollIntoViewIfNeeded();await loc.screenshot({path:path.join(out,name+'.png')});}
 async function files(stage){
  const links=await page.locator('#job-files a').evaluateAll(xs=>xs.map(x=>({name:x.download||x.textContent.trim(),url:x.href})));
  const dir=path.join(out,'windows-'+stage);fs.mkdirSync(dir,{recursive:true});
  for(const x of links){if(!/\.(json|csv)$/.test(x.name))continue;const res=await page.request.get(x.url);assert(res.ok());fs.writeFileSync(path.join(dir,path.basename(x.name)),await res.body());}
  const downloads=page.locator('details').filter({has:page.locator('#job-files')});
  if(!await downloads.evaluate(x=>x.open))await downloads.locator('summary').click();
  const [reportDownload]=await Promise.all([
    page.waitForEvent('download',{timeout:10000}),
    page.locator('#job-files a[download="report.html"]').click()
  ]);
  await reportDownload.saveAs(path.join(dir,'report.html'));
  record[stage]=JSON.parse(fs.readFileSync(path.join(dir,'results.json'),'utf8'));
 }
 async function run(stage){
  await page.locator('#steps button').nth(4).click();await page.locator('#validate').click();await page.locator('#validation').filter({hasText:'ready for calculation'}).waitFor();
  await page.locator('#run').click();await page.locator('#job-title').filter({hasText:'Your report is ready'}).waitFor({timeout:150000});
  await page.frameLocator('#report-frame').locator('body').waitFor({state:'attached'});await files(stage);
 }
 try{
  await page.goto(ready.url);await page.getByText('Local session ready',{exact:true}).waitFor();
  await page.locator('#input-file').setInputFiles(path.join(pack,'windows/guide-ampicillin-before.json'));
  await page.waitForFunction(()=>document.querySelector('#input-file').value==='');
  for(let i=0;i<4;i++){
   await page.locator('#steps button').nth(i).click();
   if(i===0)await page.locator('#sample-notes').evaluate(x=>x.open=true);
   if(i===3){await page.locator('#question-details').evaluate(x=>x.open=true);await page.locator('#inference-details').evaluate(x=>x.open=true);assert.equal(await page.locator('#population-precision').inputValue(),'');}
   await shot('form-'+i,page.locator(`.step-panel[data-panel="${i}"]`));
   const parts=i===0?[['sample-fields','.step-panel[data-panel="0"] > .fields']]:i===1?[['panel-fields','#levels-editor']]:i===2?[['quantile-fields','#quantiles'],['range-fields','#range-details']]:[['question-fields','#question-details'],['population-fields','#population-options > .fields'],['numerical-fields','#joint-options']];
   for(const [n,selector] of parts)await shot(n,page.locator(selector).first());
  }
  record.form={n:await page.locator('#n').inputValue(),confidence:await page.locator('#confidence').inputValue(),method:await page.locator('#population-method').inputValue(),iid:await page.locator('#iid').isChecked(),time:await page.locator('#time-limit').inputValue(),tolerance:await page.locator('#tolerance').inputValue(),criterion:await page.locator('[data-target="decision_fraction"]').count()};
  const saved=page.waitForEvent('download');await page.locator('#save-input').click();await(await saved).saveAs(path.join(out,'windows-input-before.json'));
  await run('before');
  await page.screenshot({path:path.join(out,'windows-before.png'),fullPage:false});
  await page.locator('#add-result-count').click();await page.locator('#notice').filter({hasText:'The original input is restored'}).waitFor();
  await page.locator('#counts .count-row').first().waitFor();
  const row=page.locator('#counts .count-row').last();
  record.count_controls=await row.locator('input,select,textarea').evaluateAll(xs=>xs.map(x=>({tag:x.tagName,key:x.getAttribute('data-count'),value:x.value,options:x.options?[...x.options].map(o=>o.value):undefined})));
  fs.writeFileSync(path.join(out,'COUNT_CONTROLS.json'),JSON.stringify(record.count_controls,null,2));
  await row.locator('[data-count="threshold"]').fill('0.25');await row.locator('[data-count="relation"]').selectOption('<=');await row.locator('[data-count="count"]').fill('59');
  const source=row.locator('[data-count="source"]');if(await source.count())await source.fill('Table 1: 59 susceptible at the source-defined breakpoint <=0.25; no intermediate isolate');
  await shot('added-count',row);
  await page.locator('#steps button').nth(3).click();
  await page.locator('#inference-details').evaluate(x=>x.open=true);
  assert.equal(await page.locator('#population-precision').inputValue(),'');
  const savedAfter=page.waitForEvent('download');await page.locator('#save-input').click();await(await savedAfter).saveAs(path.join(out,'windows-input-after.json'));
  await run('after');assert.equal(record.after.cohorts[0].saved_count_update,true);
  for(const zoom of [1.25,1.5]){await page.evaluate(z=>document.documentElement.style.zoom=String(z),zoom);await page.screenshot({path:path.join(out,'windows-after-'+Math.round(zoom*100)+'.png')});}await page.evaluate(()=>document.documentElement.style.zoom='1');
  const reportFrame=await page.locator('#report-frame').elementHandle().then(e=>e.contentFrame());await reportFrame.evaluate(()=>document.fonts.ready);
  await page.screenshot({path:path.join(out,'windows-after.png'),fullPage:false});
  const offline=await browser.newPage({viewport:{width:960,height:900},deviceScaleFactor:1.5});await offline.context().setOffline(true);
  for(const stage of ['before','after']){
   await offline.goto(pathToFileURL(path.join(out,'windows-'+stage+'/report.html')).href);await offline.evaluate(()=>document.fonts.ready);
   await offline.pdf({path:path.join(out,'windows-'+stage+'/report.pdf'),format:'A4',printBackground:true});
   await offline.screenshot({path:path.join(out,'report-'+stage+'.png'),fullPage:true});
   const sections=await offline.locator('h1,h2,h3,h4,summary').allTextContents();fs.writeFileSync(path.join(out,'REPORT_'+stage+'.json'),JSON.stringify(sections,null,2));
   const charts=offline.locator('.result-chart-block');
   await offline.locator('details').evaluateAll(xs=>xs.forEach(x=>x.open=true));
   for(let i=0;i<Math.min(await charts.count(),4);i++)await charts.nth(i).screenshot({path:path.join(out,stage+'-chart-'+i+'.png')});
   await offline.locator('details').evaluateAll(xs=>xs.forEach(x=>x.open=true));
   const checked=offline.locator('details').filter({has:offline.locator('summary').filter({hasText:'How this result was checked'})}).last();
   if(await checked.count())await checked.screenshot({path:path.join(out,stage+'-checked.png')});
  }
  const chart=offline.locator('.result-chart-block').first();
  for(const ext of ['svg','png']){const download=offline.waitForEvent('download');await chart.locator('[data-save-'+ext+']').click();await(await download).saveAs(path.join(out,'chart.'+ext));}
  assert.deepEqual(errors,[]);record.errors=errors;record.status='passed';record.browser=await browser.version();
  fs.writeFileSync(path.join(out,'WINDOWS_RUN.json'),JSON.stringify(record,null,2));
  console.log(JSON.stringify({status:'passed',stages:Object.keys(record).filter(x=>['before','after'].includes(x)),form:record.form}));
 }catch(e){await page.screenshot({path:path.join(out,'capture-error.png'),fullPage:true});fs.writeFileSync(path.join(out,'BROWSER_FAILURE.json'),JSON.stringify({errors,messages,notice:await page.locator('#notice').textContent()},null,2));throw e;}
 finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
