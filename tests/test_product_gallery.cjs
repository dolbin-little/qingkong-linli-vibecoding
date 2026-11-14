const {chromium}=require('playwright');
const {pathToFileURL}=require('node:url');
const path=require('node:path');
const fs=require('node:fs');
const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),base=path.join(root,'frontend/model3d');
const out=path.join(root,'output/三维模型精细版_20261023/交互预览');
(async()=>{let browser;try{
  try{browser=await chromium.launch({headless:true});}catch{browser=await chromium.launch({headless:true,channel:'msedge'});}
  const page=await browser.newPage({viewport:{width:1600,height:1150}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(pathToFileURL(path.join(base,'design.html')).href);
  await page.waitForFunction(()=>document.querySelector('#hero-image').complete&&document.querySelector('#hero-image').naturalWidth===3840);
  assert.equal(await page.locator('#thumbs button').count(),6);
  for(let i=0;i<6;i++){
    await page.locator('#thumbs button').nth(i).click();
    await page.waitForFunction(()=>document.querySelector('#hero-image').complete&&document.querySelector('#hero-image').naturalWidth===3840);
    assert.ok((await page.locator('#counter').textContent()).startsWith(`${i+1} / 6`));
    const png=await page.locator('#png-link').getAttribute('href'),svg=await page.locator('#svg-link').getAttribute('href');
    assert.ok(fs.existsSync(path.join(base,png)));assert.ok(fs.existsSync(path.join(base,svg)));
  }
  await page.locator('#thumbs button').nth(1).click();await page.waitForFunction(()=>document.querySelector('#hero-image').complete);
  await page.screenshot({path:path.join(out,'06_产品设计图册_电脑.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:path.join(out,'07_产品设计图册_手机.png'),fullPage:true});
  assert.deepEqual(errors,[]);
  // A direct file open has a specific instruction, instead of a misleading WebGL error.
  await page.goto(pathToFileURL(path.join(base,'index.html')).href);
  await page.waitForFunction(()=>!document.querySelector('#fallback').hidden&&document.querySelector('#fallback').textContent.includes('本地 HTTP 服务'));
  console.log('PASS gallery: direct file open, six slides, PNG/SVG links, mobile width; direct 3D file-open guidance.');
}finally{await browser?.close();}})().catch(e=>{console.error(e);process.exit(1);});
