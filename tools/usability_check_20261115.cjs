const {chromium}=require('playwright');
const fs=require('fs');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
 const context=await browser.newContext({viewport:{width:1500,height:1000}}),page=await context.newPage(),errors=[],checks=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:19051/');await page.locator('#password').fill('GreenFlight2026!');await page.locator('#login-form button').click();
 await page.waitForFunction(()=>!document.querySelector('#login').open);
 await page.waitForFunction(()=>document.querySelector('#rail-status').textContent!=='独立飞行服务待连接');
 if((await page.locator('#phase').textContent())==='尚未连接'){if(await page.locator('#battery').textContent()!=='电量待回传')throw Error('Missing telemetry shown as zero battery');checks.push('missing telemetry placeholder');}
 for(const kind of ['manual','intro']){
  const a=page.locator(`a[href="/help/${kind}"]`);if(!await a.isVisible())throw Error('Missing '+kind);
  const response=await context.request.get('http://127.0.0.1:19051/help/'+kind);if(!response.ok())throw Error('Help response');checks.push(kind+' entry and document');
 }
 const downloaded=page.waitForEvent('download');await page.locator('#export').click();const download=await downloaded;
 const record=JSON.parse(fs.readFileSync(await download.path(),'utf8'));if(record.trace_scope!=='full_retained_window')throw Error('Wrong export scope');checks.push('browser full-window export');
 for(const name of ['perception','planning','safety','edge','testing','sources','flight'])await page.locator(`[data-page="${name}"]`).click();
 checks.push('seven flight pages');await page.screenshot({path:'reports/usability-20261115.png',fullPage:false});
 await page.goto('http://127.0.0.1:19051/community');await page.locator('[data-action="advance"]').waitFor();
 if(!await page.getByText('社区业务仿真（不快进独立飞控）').isVisible())throw Error('Missing simulation boundary');
 checks.push('community simulation explanation');if(!await page.locator('a[href="/help/manual"]').isVisible())throw Error('Community help');checks.push('community help entry');
 if(errors.length)throw Error(errors.join(';'));checks.push('no script errors');
 fs.writeFileSync('reports/usability-check-20261115.json',JSON.stringify({date:'2026-11-15',passed:true,checks,errors},null,2));console.log('PASS',checks.length);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
