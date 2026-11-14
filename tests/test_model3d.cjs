// Local offline browser QA; all requests are intercepted. Never opens the user's database.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..'),dir=path.join(root,'frontend/model3d');
const output=path.join(root,'output/三维模型精细版_20261023/交互预览');fs.mkdirSync(output,{recursive:true});
const sample=JSON.parse(fs.readFileSync(path.join(dir,'demo-state.json'),'utf8'));
const live={...structuredClone(sample),user:{username:'qa',role:'admin'}};
const types={'.html':'text/html; charset=utf-8','.js':'application/javascript','.mjs':'application/javascript','.json':'application/json','.css':'text/css','.glb':'model/gltf-binary'};
(async()=>{let browser;try{
  try{browser=await chromium.launch({headless:true,args:['--use-angle=swiftshader','--enable-unsafe-swiftshader']});}
  catch{browser=await chromium.launch({headless:true,channel:'msedge',args:['--use-angle=swiftshader','--enable-unsafe-swiftshader']});}
  const page=await browser.newPage({viewport:{width:1600,height:1120},deviceScaleFactor:1});
  const errors=[],mutations=[];let connected=false;
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async route=>{const u=new URL(route.request().url()),name=decodeURIComponent(u.pathname);
    if(name==='/api/state')return route.fulfill({status:connected?200:401,json:connected?live:{detail:'请先登录'}});
    if(name.startsWith('/api/')&&route.request().method()==='POST'){mutations.push({path:name,body:route.request().postDataJSON()});if(name==='/api/simulation')live.clock+=1;return route.fulfill({json:{ok:true}});}
    const file=name.startsWith('/assets/')?path.join(root,'frontend',name.slice(8)):null;
    if(file&&fs.existsSync(file)&&fs.statSync(file).isFile())return route.fulfill({body:fs.readFileSync(file),contentType:types[path.extname(file)]||'application/octet-stream'});
    return route.fulfill({status:404,body:'Local QA: missing file '+name});
  });
  await page.goto('http://greenflight.test/assets/model3d/index.html');
  await page.waitForFunction(()=>document.querySelector('canvas')&&document.querySelector('#connection').textContent.includes('独立演示'));
  await page.locator('#fallback').waitFor({state:'hidden'});
  await page.waitForTimeout(800);
  assert.equal(await page.locator('#model-title').textContent(),'太阳能辅助无人机');
  await page.screenshot({path:path.join(output,'01_太阳能辅助无人机.png'),fullPage:true});
  await page.locator('[data-preset="cutaway"]').click();await page.waitForTimeout(200);await page.screenshot({path:path.join(output,'02a_无人机内部透视.png'),fullPage:true});await page.locator('[data-preset="exploded"]').click();await page.locator('#explode').fill('80');await page.waitForTimeout(150);
  await page.screenshot({path:path.join(output,'02_无人机结构分解.png'),fullPage:true});
  await page.locator('[data-model="station"]').click();await page.waitForTimeout(300);
  await page.screenshot({path:path.join(output,'03_光伏共享站点.png'),fullPage:true});
  // Exercise real browser exports, including non-GLB geometry formats.
  for(const format of ['glb','obj','stl']){await page.locator('#export-format').selectOption(format);const promise=page.waitForEvent('download');await page.locator('#download').click();const download=await promise;const dest=path.join(output,'qa_export.'+format);await download.saveAs(dest);const bytes=fs.readFileSync(dest);assert.ok(bytes.length>5000);if(format==='glb')assert.equal(bytes.toString('utf8',0,4),'glTF');fs.unlinkSync(dest);}
  await page.locator('[data-model="community"]').click();await page.waitForTimeout(300);
  assert.equal(await page.locator('.model-label').count(),10);
  await page.locator('#demo-play').click();await page.waitForTimeout(1400);
  assert.ok((await page.locator('#readouts').textContent()).includes('0.'));
  await page.locator('#demo-play').click();
  assert.equal(mutations.length,0,'Offline playback must not write to backend');
  await page.screenshot({path:path.join(output,'04_社区配送场景.png'),fullPage:true});
  // The shipped GLB files must load with Three.js, retain hierarchy and have finite bounds.
  const validation=await page.evaluate(async()=>{const THREE=await import('./vendor/three/build/three.module.js');const {GLTFLoader}=await import('./vendor/three/examples/jsm/loaders/GLTFLoader.js');const loader=new GLTFLoader();const result=[];for(const name of ['太阳能辅助无人机','光伏共享站点','社区配送场景']){const g=await loader.loadAsync('./downloads/绿航智递_'+name+'.glb');const b=new THREE.Box3().setFromObject(g.scene);const count=[];g.scene.traverse(o=>{if(o.isMesh)count.push(o.name);});result.push({name,meshes:count.length,min:b.min.toArray(),max:b.max.toArray()});}return result;});
  for(const v of validation){assert.ok(v.meshes>40);assert.ok([...v.min,...v.max].every(Number.isFinite));}
  assert.ok(validation[2].min[0]>=-500.01&&validation[2].max[0]<=500.01);
  assert.ok(validation[2].min[2]>=-350.01&&validation[2].max[2]<=350.01);
  fs.writeFileSync(path.join(output,'模型加载验证.json'),JSON.stringify(validation,null,2));
  connected=true;await page.locator('#source').click();
  await page.waitForFunction(()=>document.querySelector('#connection').textContent.includes('平台仿真数据'));
  assert.equal(await page.locator('#dispatch').isEnabled(),true);
  await page.locator('#dispatch').click();await page.waitForFunction(()=>!document.querySelector('#dispatch').disabled);
  await page.locator('#advance').click();await page.waitForFunction(()=>!document.querySelector('#advance').disabled);
  assert.deepEqual(mutations.map(v=>v.path),['/api/dispatch','/api/simulation']);
  assert.equal(mutations[0].body.method,'vns');assert.equal(mutations[1].body.minutes,1);
  // New state/flight visibility cannot reset the user's camera; errors would be caught above.
  await page.setViewportSize({width:390,height:844});await page.locator('[data-model="drone"]').click();await page.waitForTimeout(200);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
  await page.screenshot({path:path.join(output,'05_手机适配.png'),fullPage:true});
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({status:'PASS',models:validation,offline_mutations:0,live_actions:mutations,mobile_overflow:false,browser_errors:errors},null,2));
}finally{await browser?.close();}})().catch(e=>{console.error(e);process.exit(1);});
