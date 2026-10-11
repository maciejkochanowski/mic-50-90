const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');
const {chromium}=require('playwright');
(async()=>{
 const [readyFile,pack,out,chrome]=process.argv.slice(2),ready=JSON.parse(fs.readFileSync(readyFile,'utf8'));
 const browser=await chromium.launch({headless:true,executablePath:chrome});
 const page=await browser.newPage({viewport:{width:1280,height:960},acceptDownloads:true});
 const records=[],errors=[];page.on('pageerror',e=>errors.push(String(e)));
 const open=async file=>{await page.locator('#input-file').setInputFiles(file);await page.waitForFunction(()=>document.querySelector('#input-file').value==='');};
 async function run(){if(await page.locator('#steps').isVisible())await page.locator('#steps button').nth(4).click();await page.locator('#validate').click();await page.locator('#validation').filter({hasText:'ready for calculation'}).waitFor();await page.locator('#run').click();await page.locator('#job-title').filter({hasText:'Your report is ready'}).waitFor({timeout:120000});}
 async function result(){const link=page.locator('#job-files a').filter({hasText:/^results.json$/});return (await page.request.get(await link.getAttribute('href'))).json();}
 async function fonts(node,selector){const cdp=await node.context().newCDPSession(node);await cdp.send('DOM.enable');await cdp.send('CSS.enable');const {root}=await cdp.send('DOM.getDocument');const {nodeId}=await cdp.send('DOM.querySelector',{nodeId:root.nodeId,selector});const x=await cdp.send('CSS.getPlatformFontsForNode',{nodeId});await cdp.detach();return x.fonts;}
 try{
  await page.goto(ready.url);await page.getByText('Local session ready',{exact:true}).waitFor();
  await page.evaluate(async()=>{await Promise.all([...document.fonts].map(f=>f.load()));const p=document.createElement('p');p.id='font-probe';p.textContent='MIC ≤ 4 μg/mL ≥ 1';document.querySelector('main').prepend(p);await document.fonts.ready;});
  const actual=await fonts(page,'#font-probe');assert(actual.every(f=>f.isCustomFont),JSON.stringify(actual));assert(actual.some(f=>/CMU/.test(f.familyName)));
  records.push({case:'desktop-font-glyphs',fonts:actual});
  await page.locator('#font-probe').screenshot({path:path.join(out,'font-glyphs.png')});await page.locator('#font-probe').evaluate(x=>x.remove());
  for(let i=0;i<3;i++){
   await open(path.join(out,`saved-${i}.json`));
   await page.locator('#previous-files').setInputFiles(['configuration','results'].map(n=>path.join(out,`saved-${i}`,'output',n+'.json')));
   await page.locator('#steps button').nth(2).click();await page.locator('#add-count').click();
   const row=page.locator('#counts .count-row').last();await row.locator('[data-count="threshold"]').fill('2');await row.locator('[data-count="count"]').fill('3');
   await run();const r=(await result()).cohorts[0];assert.equal(r.saved_count_update,true);assert.deepEqual(r.sample.categories.map(x=>x.count_lower),[12,5,3]);
   records.push({case:'saved-update-'+i,status:'passed',counts:r.sample.categories.map(x=>x.count_lower)});
  }
  // A changed original denominator must still be refused after loading a saved analysis.
  await open(path.join(out,'saved-0.json'));await page.locator('#previous-files').setInputFiles(['configuration','results'].map(n=>path.join(out,'saved-0','output',n+'.json')));
  await page.locator('#steps button').nth(0).click();await page.locator('#n').fill('21');await page.locator('#steps button').nth(4).click();await page.locator('#validate').click();await page.locator('#validation').filter({hasText:'Please correct'}).waitFor();records.push({case:'changed-denominator',status:'refused'});
  for(const kind of ['exact','range','percentage']){await open(path.join(out,'blanks-'+kind+'.json'));await run();const r=(await result()).cohorts[0];assert.equal(r.status,'ok');const c=r.sample.cdf[0];assert.deepEqual([c.count_lower,c.count_upper],kind==='range'?[11,13]:[12,12]);records.push({case:'optional-blanks-'+kind,status:'passed'});}
  const frame=page.frames().find(f=>f!==page.mainFrame());await frame.evaluate(()=>document.fonts.ready);
  const chart=frame.locator('.result-chart-block').first();
  for(const [kind,selector] of [['svg','[data-save-svg]'],['png','[data-save-png]']]){
   const download=page.waitForEvent('download');await chart.locator(selector).click();await(await download).saveAs(path.join(out,'exported-chart.'+kind));
  }
  const exported=fs.readFileSync(path.join(out,'exported-chart.svg'),'utf8');assert(exported.includes('data:font/woff;base64,'));
  const png=fs.readFileSync(path.join(out,'exported-chart.png'));assert.equal(png.subarray(1,4).toString(),'PNG');
  const offline=await browser.newPage();await offline.context().setOffline(true);await offline.goto(pathToFileURL(path.join(out,'exported-chart.svg')).href);await offline.evaluate(()=>document.fonts.ready);
  const chartFonts=[];for(let i=0;i<await offline.locator('text').count();i++){await offline.locator('text').nth(i).evaluate((x,j)=>x.id='chart-font-'+j,i);const ff=await fonts(offline,'#chart-font-'+i);assert(ff.length&&ff.every(f=>f.isCustomFont&&/DejaVu/.test(f.familyName)),JSON.stringify(ff));chartFonts.push(...ff);}await offline.screenshot({path:path.join(out,'offline-svg.png')});
  await offline.goto(pathToFileURL(path.join(pack,'output','ampicillin','report.html')).href);await offline.evaluate(()=>document.fonts.ready);
  const bodyFonts=await fonts(offline,'h1');assert(bodyFonts.every(f=>f.isCustomFont),JSON.stringify(bodyFonts));
  await offline.pdf({path:path.join(out,'offline-report.pdf'),format:'A4',printBackground:true});
  records.push({case:'offline-export',svg_fonts:chartFonts,html_fonts:bodyFonts,png_bytes:png.length});
  await open(path.join(pack,'windows','amikacin-certificate.json'));
  await page.locator('#run').click();await page.locator('#job-title').filter({hasText:'Your report is ready'}).waitFor({timeout:120000});
  const verificationFrame=await page.locator('#report-frame').elementHandle().then(e=>e.contentFrame());
  await verificationFrame.waitForURL(await page.locator('#report-frame').getAttribute('src'),{waitUntil:'load'});
  await verificationFrame.locator('h1').filter({hasText:'Report verification'}).waitFor({state:'attached'});await verificationFrame.evaluate(()=>document.fonts.ready);
  const originalInterpretation=await verificationFrame.locator('body > p').allTextContents();assert(originalInterpretation.some(t=>t.includes('Logical checking does not authenticate source records.')));
  await page.evaluate(()=>{window.print=()=>{window.__printed=true;const timer=window.setTimeout;window.setTimeout=(fn,delay,...args)=>delay===1000?0:timer(fn,delay,...args);};});
  await page.locator('#print-result').click();await page.waitForFunction(()=>window.__printed);await page.emulateMedia({media:'print'});
  assert.equal(await page.locator('#report-print-area body').count(),0);
  const head=page.locator('#report-print-area h1');assert(await head.isVisible());
  const interpretationParagraphs=await page.locator('#report-print-area main > p').evaluateAll(nodes=>nodes.map(n=>({text:n.textContent,display:getComputedStyle(n).display,height:n.getBoundingClientRect().height})));
  for(const text of originalInterpretation){const paragraph=interpretationParagraphs.find(p=>p.text===text);assert(paragraph&&paragraph.display!=='none'&&paragraph.height>0,'Interpretation paragraph must remain visible in print');}
  const flowLabels=await page.locator('#report-print-area .result-flow > span').evaluateAll(nodes=>nodes.map(n=>{const r=n.getBoundingClientRect();return{text:n.textContent,left:r.left,right:r.right,top:r.top,bottom:r.bottom};}));assert.equal(flowLabels.length,3);
  for(let i=1;i<flowLabels.length;i++){const a=flowLabels[i-1],b=flowLabels[i];assert((b.left-a.right>=8&&Math.abs(b.top-a.top)<1)||b.top-a.bottom>=4,'Printed progress labels must be visually separated');}
  const pre=await page.locator('#report-print-area pre').evaluate(x=>({height:x.clientHeight,scroll:x.scrollHeight,max:getComputedStyle(x).maxHeight,overflow:getComputedStyle(x).overflow}));assert.equal(pre.max,'none');assert.equal(pre.overflow,'visible');assert(pre.height>=pre.scroll-1);
  const headingText=await head.innerText();await page.pdf({path:path.join(out,'certificate-print.pdf'),format:'A4',printBackground:true});assert.equal(await page.locator('#report-print-area').count(),0);records.push({case:'certificate-print',visible_heading:headingText,interpretation_paragraphs:interpretationParagraphs,flow_labels:flowLabels,calculation_record:pre});
  assert.deepEqual(errors,[]);fs.writeFileSync(path.join(out,'ACCEPTANCE_BROWSER.json'),JSON.stringify({status:'passed',records,errors},null,2));
 }catch(e){await page.screenshot({path:path.join(out,'acceptance-error.png'),fullPage:true});console.error(await page.locator('#validation').innerText());throw e;}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});

