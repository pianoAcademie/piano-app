const {chromium,webkit}=await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawn} from 'node:child_process';
import {tmpdir} from 'node:os';
const frontend=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const fixture=path.join(frontend,'app/mobile-qa/page.tsx');
assert(!fs.existsSync(fixture),'Refusing to overwrite an existing page');
fs.mkdirSync(path.dirname(fixture),{recursive:true});
fs.copyFileSync(path.join(frontend,'tests/fixtures/teacher-mobile-page.tsx'),fixture);
const server=spawn(process.execPath,[path.join(frontend,'node_modules/next/dist/bin/next'),'dev','-p','3019'],{cwd:frontend,stdio:'ignore'});
const artifacts=process.env.QA_ARTIFACT_DIR || tmpdir();
let browser;
try {
 for(let i=0;i<60;i++) {try {if((await fetch('http://localhost:3019/mobile-qa')).ok) break;}catch {} await new Promise(r=>setTimeout(r,500));}
 assert.equal(server.exitCode,null,'The fixture server failed to start; verify port 3019 is free');
 browser=process.env.QA_WEBKIT ? await webkit.launch() : await chromium.launch({...(process.env.CHROME_EXECUTABLE ? {executablePath:process.env.CHROME_EXECUTABLE} : {}),headless:true});
 for(const width of [320,393,768]) {
  const page=await browser.newPage({viewport:{width,height:852},isMobile:true,hasTouch:true});
  // Local HTTP fixture only: WebKit otherwise upgrades localhost assets to HTTPS.
  await page.route('**/mobile-qa*', async route => {
    if (route.request().resourceType() !== 'document') return route.continue();
    const response=await route.fetch(); const headers=response.headers();
    if(headers['content-security-policy']) headers['content-security-policy']=headers['content-security-policy'].replace('upgrade-insecure-requests','');
    await route.fulfill({response,headers});
  });
  await page.goto('http://localhost:3019/mobile-qa');
  await page.getByRole('button',{name:'Élève suivant',exact:true}).click();
  assert((await page.getByRole('combobox',{name:'Élève affiché',exact:true}).boundingBox()).height>=44);
  await page.getByRole('button',{name:'Choisir le morceau travaillé',exact:true}).click();
  await page.locator('fieldset select').nth(1).selectOption('2');
  page.once('dialog',dialog=>dialog.accept());
  await page.getByRole('button',{name:'Présent',exact:true}).click();
  assert.equal(await page.locator('fieldset:visible').count(),1);
  await page.getByRole('button',{name:'Élève précédent',exact:true}).click();
  assert.equal(await page.locator('.teacher-attendance-row-card:visible').count(),1);
  await page.getByRole('button',{name:'Élève suivant',exact:true}).click();
  assert.equal(await page.locator('fieldset select:visible').nth(1).inputValue(),'2');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  assert.equal(await page.locator('.teacher-course-tools').getAttribute('open'),null);
  if(width===393) await page.screenshot({path:path.join(artifacts,'piano-mobile-full-editor.png'),fullPage:true});
  page.once('dialog',dialog=>dialog.dismiss());
  await page.getByRole('link',{name:'Fermer',exact:true}).click();
  assert.equal(await page.getByRole('dialog').count(),1);
  await page.getByRole('button',{name:'Annuler',exact:true}).click();
  await page.getByRole('button',{name:'Choisir le morceau travaillé',exact:true}).click();
  await page.getByRole('button',{name:'Enregistrer',exact:true}).click();
  await page.getByRole('alert').waitFor();
  assert.equal(await page.locator('fieldset:visible').count(),1);
  await page.getByRole('button',{name:'Annuler',exact:true}).click();
  await page.getByRole('button',{name:'Élève précédent',exact:true}).click();
  if(width===393) await page.screenshot({path:path.join(artifacts,'piano-mobile-full-presences.png'),fullPage:true});
  await page.setViewportSize({width,height:430});
  const close=await page.getByRole('link',{name:'Fermer',exact:true}).boundingBox();
  assert(close.y>=0 && close.y+close.height<=430);
  await page.getByRole('link',{name:'Retour au planning',exact:true}).click();
  await page.waitForURL('**closed=1');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.setViewportSize({width,height:852});
  if(width===393) await page.screenshot({path:path.join(artifacts,'piano-mobile-planning.png'),fullPage:true});
  await page.goto('http://localhost:3019/mobile-qa');
  await page.getByRole('link',{name:'Fermer',exact:true}).click();
  await page.waitForURL('**closed=1');
  await page.close();
  console.log(`PASS ${width}px: full dialog, student navigation, retained draft, failed save, guarded close, reduced viewport, planning overflow`);
 }
} finally { await browser?.close(); server.kill('SIGTERM'); fs.unlinkSync(fixture); }
