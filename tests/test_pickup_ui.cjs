// Offline browser regression: requests are intercepted; no live database or server is used.
// Run with NODE_PATH pointing to a Node runtime that provides Playwright.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {spawnSync} = require('node:child_process');
const {chromium} = require('playwright');
const root = path.resolve(__dirname, '..');
const python = path.join(root, '.venv', 'Scripts', 'python.exe');
const fixture = spawnSync(python, ['-c', `import json; from backend.store import seed_state; from backend.simulation import metrics; from backend.planner import PRODUCTS; from backend.pickup import list_pickup_points; s=seed_state(); print(json.dumps({**s,'metrics':metrics(s),'products':PRODUCTS,'pickup_points':list_pickup_points(s['zones']),'user':{'role':'resident','username':'resident'}}))`], {cwd:root,encoding:'utf8'});
assert.equal(fixture.status, 0, fixture.stderr);
const state=JSON.parse(fixture.stdout), submitted=[];

(async()=>{
  let browser;
  try{
    try{browser=await chromium.launch({headless:true});}
    catch{browser=await chromium.launch({headless:true,channel:'msedge'});}
    const page=await browser.newPage({viewport:{width:1280,height:1000}});
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.route('**/*',async route=>{
      const url=new URL(route.request().url());
      if(url.pathname==='/api/state')return route.fulfill({json:state});
      if(url.pathname==='/api/orders'&&route.request().method()==='POST'){
        const body=route.request().postDataJSON();submitted.push(body);
        return route.fulfill({json:{id:'LH-QA',...body}});
      }
      const file=url.pathname==='/'?'frontend/index.html':url.pathname.startsWith('/assets/')?'frontend/'+url.pathname.slice(8):null;
      if(file)return route.fulfill({body:fs.readFileSync(path.join(root,file)),contentType:file.endsWith('.js')?'application/javascript':file.endsWith('.css')?'text/css':'text/html'});
      return route.fulfill({status:404,body:'Offline QA: unexpected request'});
    });
    // This origin is fully mocked above; no DNS lookup or live website is used.
    await page.goto('http://greenflight.test/#shop');
    await page.locator('[data-buy="powerbank"]').click();
    assert.equal(await page.locator('#submit-order').isDisabled(),true);
    assert.equal(await page.locator('#order-form [name="x"],#order-form [name="y"],#order-form [name="address"]').count(),0);
    assert.equal(await page.locator('#pickup-coordinates').count(),0);
    for(const point of state.pickup_points){
      await page.locator('#pickup-select').selectOption(point.id);
      assert.ok((await page.locator('#pickup-summary').textContent()).includes(point.name));
      assert.equal(await page.locator('#submit-order').isEnabled(),true);
    }
    await page.locator('#submit-order').click();
    await page.locator('#modal').waitFor({state:'hidden'});
    assert.equal(submitted[0].pickup_point_id,'P06');
    assert.equal(submitted[0].x,undefined);assert.equal(submitted[0].address,undefined);

    await page.locator('[data-buy="umbrella"]').click();
    assert.equal(await page.locator('#pickup-select').inputValue(),'');
    await page.locator('#pickup-select').selectOption('custom');
    await page.locator('#order-form [name="quantity"]').fill('2');
    const clickMap=async(x,y)=>{
      const point=await page.locator('#order-map').evaluate((svg,p)=>{
        const q=svg.createSVGPoint();q.x=p.x;q.y=p.y;
        const screen=q.matrixTransform(svg.getScreenCTM());return {x:screen.x,y:screen.y};
      },{x,y});
      await page.mouse.click(point.x,point.y);
    };
    await clickMap(420,230);
    assert.equal(await page.locator('#submit-order').isDisabled(),true);
    assert.ok((await page.locator('#pickup-error').textContent()).includes('禁飞区'));
    await clickMap(280,250);
    assert.equal(await page.locator('#submit-order').isEnabled(),true);
    assert.equal(await page.locator('#order-form [name="quantity"]').inputValue(),'2');
    await page.locator('#submit-order').click();
    await page.locator('#modal').waitFor({state:'hidden'});
    // Screen pixels are discrete; a single pixel spans about two map metres.
    assert.ok(Math.abs(submitted[1].x-280)<=3);assert.ok(Math.abs(submitted[1].y-250)<=3);
    assert.equal(submitted[1].address,`地图取件点（${submitted[1].x}, ${submitted[1].y}）`);
    assert.equal(submitted[1].quantity,2);

    await page.locator('[data-buy="powerbank"]').click();
    await page.locator('#pickup-map-panel summary').click();
    await page.locator('#order-map [data-pickup="P02"] circle').click();
    assert.equal(await page.locator('#pickup-select').inputValue(),'P02');
    await page.locator('#order-form [data-close]').click();

    state.user={role:'admin',username:'admin'};
    await page.goto('http://greenflight.test/#map');
    await page.locator('#network-map [data-pickup="P06"] circle').click();
    await page.locator('[data-action="new-order"]').click();
    assert.equal(await page.locator('#pickup-select').inputValue(),'P06');
    assert.ok((await page.locator('#pickup-coordinates').textContent()).includes('90'));
    const ids=await page.locator('[id]').evaluateAll(nodes=>nodes.map(n=>n.id));
    assert.equal(new Set(ids).size,ids.length,'Map and dialog SVG IDs must be unique');
    assert.deepEqual(errors,[]);
    console.log('PASS web: resident selection, six locations, custom map, no-fly rejection, quantities, map presets, admin map handoff, unique SVG IDs');
    await page.close();
  }finally{if(browser)await browser.close();}

  let mini,requests=[];
  vm.runInNewContext(fs.readFileSync(path.join(root,'miniprogram/pages/shop/index.js'),'utf8'),{
    Page:p=>mini=p,getApp:()=>({request:async(url,method,body)=>{
      if(url==='/state')return state;requests.push({url,body});return {id:'LH-MINI-QA'};
    }}),wx:{navigateTo:()=>{}}
  });
  mini.setData=data=>Object.assign(mini.data,data);
  await mini.load();mini.choose({currentTarget:{dataset:{id:'umbrella'}}});
  await mini.submit();assert.equal(requests.length,0);
  mini.choosePickup({detail:{value:'5'}});await mini.submit();
  assert.equal(requests[0].body.pickup_point_id,'P06');assert.equal(requests[0].body.x,undefined);
  mini.data.pickupPoints[0].available=false;mini.choosePickup({detail:{value:'0'}});
  await mini.submit();assert.equal(requests.length,1);
  console.log('PASS mini-program: location required, shared destination ID, unavailable location rejected');
})().catch(err=>{console.error(err);process.exitCode=1;});
