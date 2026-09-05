const {chromium,webkit}=await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawn} from 'node:child_process';
import {tmpdir} from 'node:os';
import {createServer} from 'node:http';
// Exercise the real Next server action against a local-only API double. No
// credentials or production writes: browser -> server action -> HTTP -> UI.
let apiMode='success', writes=0;
const snapshots=new Map();
const api=createServer(async(req,res)=>{
 const id=req.url.split('/students/')[1]?.split('/')[0];
 if(!id){res.writeHead(404).end();return;}
 let snapshot=snapshots.get(id) ?? {revision:0,state:{product_id:'book',books:{book:{current_piece_id:'1',completed:false,pieces:{}}}}};
 if(req.method==='PATCH'){
  let raw=''; for await(const chunk of req) raw+=chunk;
  const command=JSON.parse(raw); writes++;
  await new Promise(resolve=>setTimeout(resolve,600));
  if(apiMode==='conflict'){res.writeHead(409,{'Content-Type':'application/json'}).end(JSON.stringify({detail:'Ce suivi a été modifié par un autre professeur.'}));return;}
  snapshot=structuredClone(snapshot);snapshot.revision++;
  if(command.action==='CORRECT') snapshot.state.books.book.current_piece_id=command.piece_id;
  if(command.action==='COMPLETE_PIECE'){
   snapshot.state.books.book.pieces[snapshot.state.books.book.current_piece_id]={status:'COMPLETED'};
   snapshot.state.books.book.current_piece_id=command.piece_id;
  }
  snapshots.set(id,snapshot);
 }
 res.writeHead(200,{'Content-Type':'application/json'}).end(JSON.stringify(snapshot));
});
await new Promise(resolve=>api.listen(0,'127.0.0.1',resolve));
const frontend=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const fixture=path.join(frontend,'app/mobile-qa/page.tsx');
assert(!fs.existsSync(fixture),'Refusing to overwrite an existing page');
fs.mkdirSync(path.dirname(fixture),{recursive:true});
fs.copyFileSync(path.join(frontend,'tests/fixtures/teacher-mobile-page.tsx'),fixture);
const server=spawn(process.execPath,[path.join(frontend,'node_modules/next/dist/bin/next'),'dev','-p','3019'],{cwd:frontend,stdio:'ignore',env:{...process.env,BACKEND_INTERNAL_URL:`http://127.0.0.1:${api.address().port}`}});
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
  await page.context().addCookies([{name:'portal_access_token',value:'local-qa-only',url:'http://localhost:3019'}]);
  snapshots.clear(); writes=0; apiMode='success';
  await page.getByRole('button',{name:'Continuer ce morceau',exact:true}).click();
  await page.locator('section[aria-busy="true"]').waitFor();
  await page.getByRole('button',{name:'Élève suivant',exact:true}).click();
  assert.equal(await page.getByRole('combobox',{name:'Élève affiché'}).inputValue(),'11111111-1111-4111-8111-111111111111');
  await page.getByText('Enregistré ✓',{exact:true}).waitFor();
  assert.equal(writes,1,'One action must produce one write');
  await page.getByRole('button',{name:'Terminé → suivant',exact:true}).click();
  await page.locator('fieldset:visible select').selectOption('2');
  await page.getByRole('button',{name:'Enregistrer',exact:true}).click();
  await page.getByText('Enregistré ✓',{exact:true}).waitFor();
  assert.equal(await page.locator('fieldset:visible').count(),0);
  await page.getByText('1 morceau terminé sur 3',{exact:true}).waitFor();
  await page.getByText('Partition et morceaux déjà travaillés',{exact:true}).click();
  await page.getByRole('button',{name:'Changer la partition ou le morceau',exact:true}).click();
  await page.locator('fieldset:visible select').nth(1).selectOption('0');
  apiMode='conflict';
  await page.getByRole('button',{name:'Enregistrer',exact:true}).click();
  await page.getByRole('alert').filter({hasText:'autre professeur'}).waitFor();
  assert.equal(await page.locator('fieldset:visible select').nth(1).inputValue(),'0');
  await page.getByRole('button',{name:'Annuler',exact:true}).click();
  apiMode='success';
  await page.context().clearCookies();
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
} finally { await browser?.close(); server.kill('SIGTERM'); api.close(); fs.unlinkSync(fixture); }
