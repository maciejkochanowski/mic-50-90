// Print complete local reports with all details visible and no network requests.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { pathToFileURL } = require('url');
const { chromium } = require('playwright');
async function main() {
  const [chrome, ...files] = process.argv.slice(2);
  if (!chrome || !files.length) throw new Error('Usage: node tools/print_reports.cjs CHROME REPORT.html [...]');
  const browser = await chromium.launch({executablePath: chrome, headless: true});
  const records=[];
  try {
    for (const name of files) {
      const file=path.resolve(name), target=file.replace(/\.html$/i,'.pdf');
      if(target===file) throw new Error('Expected an HTML report');
      const page=await browser.newPage();
      await page.route(/^https?:\/\//, route=>route.abort());
      await page.goto(pathToFileURL(file).href);
      await page.evaluate(async()=>{
        await document.fonts.ready;
        for(const item of document.querySelectorAll('details')) item.open=true;
      });
      await page.emulateMedia({media:'print'});
      await page.pdf({path:target,format:'A4',printBackground:true,
        margin:{top:'12mm',bottom:'12mm',left:'12mm',right:'12mm'}});
      records.push({html:file,pdf:target,
        html_sha256:crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex'),
        pdf_sha256:crypto.createHash('sha256').update(fs.readFileSync(target)).digest('hex'),
        expanded_details:await page.locator('details[open]').count(),offline:true});
      await page.close();
    }
  } finally { await browser.close(); }
  process.stdout.write(JSON.stringify({status:'passed',records},null,2)+'\n');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
