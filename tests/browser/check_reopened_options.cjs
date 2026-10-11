/* Run against an actual local GUI, with Playwright available in NODE_PATH. */
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const {chromium}=require('playwright');

(async()=>{
  const [readyFile,out,chrome]=process.argv.slice(2);
  const ready=JSON.parse(fs.readFileSync(readyFile,'utf8'));
  fs.mkdirSync(out,{recursive:true});
  const browser=await chromium.launch({headless:true,...(chrome?{executablePath:chrome}:{})});
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const cases=[];
  try {
    await page.goto(ready.url);
    await page.getByText('Local session ready',{exact:true}).waitFor();
    const config={cohort_id:'Reopened sample',n:20,unit:'mg/L',iid:true,
      confidence_level:.95,panel:{levels:[1,2]},
      additional_counts:[{threshold:1,count:8,n:20,unit:'mg/L'}]};
    for(const [name,extra,expected] of [
      ['missing',{},''],['disabled',{population_precision_pp:null},''],
      ['enabled',{population_precision_pp:12.5},'12.5']]) {
      const input={inputs:[config],population_method:'bonferroni',...extra};
      await page.locator('#input-file').setInputFiles({name:name+'.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(input))});
      await page.waitForFunction(()=>document.querySelector('#input-file').value==='');
      await page.locator('#steps button').nth(3).click();
      await page.locator('#inference-details').evaluate(x=>x.open=true);
      const value=await page.locator('#population-precision').inputValue();
      cases.push({name,expected,actual:value});
      assert.equal(value,expected,'Import must preserve whether population grouping was requested: '+name);
      const download=page.waitForEvent('download');await page.locator('#save-input').click();
      const target=path.join(out,name+'-saved.json');await(await download).saveAs(target);
      const saved=JSON.parse(fs.readFileSync(target,'utf8')).payload;
      assert.equal(saved.options.population_precision_pp,expected===''?null:Number(expected));
      assert.equal(saved.config.n,'20'); // The form preserves integers as exact decimal strings.
      assert.equal(saved.config.iid,true);
    }
    await page.locator('#steps button').nth(4).click();
    await page.locator('#validate').click();
    await page.locator('#validation').filter({hasText:'ready for calculation'}).waitFor();
    await page.locator('#run').click();
    await page.locator('#job-title').filter({hasText:'Your report is ready'}).waitFor({timeout:120000});
    const downloads=page.locator('details').filter({has:page.locator('#job-files')});
    if(!await downloads.evaluate(x=>x.open))await downloads.locator('summary').click();
    const [report]=await Promise.all([page.waitForEvent('download'),page.locator('#job-files a[download="report.html"]').click()]);
    await report.saveAs(path.join(out,'report.html'));
    assert(fs.readFileSync(path.join(out,'report.html'),'utf8').includes('Reopened sample'));
    assert.deepEqual(errors,[]);
    await page.screenshot({path:path.join(out,'reopened-options.png')});
    fs.writeFileSync(path.join(out,'REOPENED_OPTIONS.json'),JSON.stringify({status:'passed',cases,errors},null,2));
  } catch(e) {
    fs.writeFileSync(path.join(out,'REOPENED_OPTIONS.json'),JSON.stringify({status:'failed',cases,error:e.message},null,2));
    await page.screenshot({path:path.join(out,'reopened-options-error.png')});throw e;
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
