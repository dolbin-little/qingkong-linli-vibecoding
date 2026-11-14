import * as THREE from './vendor/three/build/three.module.js';
import {RoomEnvironment} from './vendor/three/examples/jsm/environments/RoomEnvironment.js';
import {OrbitControls} from './vendor/three/examples/jsm/controls/OrbitControls.js';
import {GLTFExporter} from './vendor/three/examples/jsm/exporters/GLTFExporter.js';
import {OBJExporter} from './vendor/three/examples/jsm/exporters/OBJExporter.js';
import {STLExporter} from './vendor/three/examples/jsm/exporters/STLExporter.js';
import {makeDrone,makeStation,makeCommunity,explodeModel,setCutaway,coords,COMPONENTS} from './models.mjs';
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const text=(s,v)=>$(s).textContent=v;
const clone=v=>structuredClone(v);
const titles={drone:'太阳能辅助无人机',station:'光伏共享站点',community:'社区配送场景'};
const descriptions={drone:'把光伏辅助补能、模块化电池与社区共享物品配送，整合到一架四旋翼概念机中。',station:'后侧光伏服务柜，前侧双起降平台。串联物品共享、能源补给与边缘协同。',community:'沿用平台坐标与计算航线，展示订单、取件点、站点、机队和禁飞区域。'};
let kind='drone',object,renderer,controls,camera,scene,liveState=null,demoBase=null,demoState=null,source='demo',demoTime=0,demoPlaying=false,busy=false;
let timer,lastPoll=0,refreshing=false,liveConnected=false,sceneSignature='',labelItems=[],pointerStart=null;
const stage=$('#stage'), labels=$('#labels');
function notify(message){text('#toast',message);$('#toast').hidden=false;clearTimeout(timer);timer=setTimeout(()=>$('#toast').hidden=true,4500);}
function state(){return source==='live'?liveState:demoState;}
function round(v,n=1){return Number(v||0).toFixed(n);}
function info(title,body){$('#component').replaceChildren();const b=document.createElement('b'),p=document.createElement('p');b.textContent=title;p.textContent=body;$('#component').append(b,p);}
function specs(entries){$('#specs').replaceChildren();for(const [label,value,unit] of entries){const dl=document.createElement('div'),dt=document.createElement('dt'),dd=document.createElement('dd'),sm=document.createElement('small');dt.textContent=label;dd.textContent=value;sm.textContent=unit;dd.append(sm);dl.append(dt,dd);$('#specs').append(dl);}}
function updatePanel(){
  text('#model-title',titles[kind]);text('#model-description',descriptions[kind]);text('#model-no',`${{drone:'01',station:'02',community:'03'}[kind]} / 03`);
  text('#view-caption',kind==='community'?'1000 × 700 m · 社区配送示意':kind==='drone'?'太阳能辅助四旋翼 · 概念设计':'光伏共享站点 · 概念设计');
  text('#scale-caption',kind==='community'?'站点 ×5 / 无人机 ×16 放大显示':'尺寸单位 m');
  $('#network-panel').hidden=kind!=='community';$('#explode-control').hidden=kind==='community';$('#zones-control').hidden=kind!=='community';$('#cutaway-control').hidden=kind==='community';$('#presets').hidden=kind==='community';text('#motion-label',kind==='community'?'飞行旋翼效果':'旋翼演示');
  if(kind==='drone')specs([['机载光伏','0.12','m²'],['电池假设','180','Wh'],['最大载重假设','1.8','kg'],['返航安全余量','20','%']]);
  if(kind==='station')specs([['站点光伏','3.0','m²'],['充电位','2','个'],['储能容量假设','1000','Wh'],['单口功率假设','100','W']]);
  if(kind==='community')specs([['示意范围','1000×700','m'],['共享站点',state()?.stations?.length||0,'个'],['公共取件点',state()?.pickup_points?.length||0,'个'],['展示飞行高度','40','m']]);
  $$('[data-model]').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.model===kind)));
  if(kind==='community')info(...COMPONENTS.network);else info('选择一个部件','点击模型，查看部件用途和平台中的对应参数。');
}
function dispose(o){o.traverse(m=>{m.geometry?.dispose();if(m.material){for(const a of (Array.isArray(m.material)?m.material:[m.material]))a.dispose();}});}
function signature(s){return JSON.stringify([s?.stations?.map(v=>[v.id,v.x,v.y,v.online]),s?.zones,s?.pickup_points,s?.orders?.map(o=>[o.id,o.x,o.y,o.status]),s?.flights?.map(f=>[f.drone_id,f.started,f.done,f.legs?.map(l=>l.path)])]);}
function build(preserveView=false){
  const previous=preserveView?{position:camera.position.clone(),target:controls.target.clone()}:null;
  if(object){scene.remove(object);dispose(object);}
  object=kind==='drone'?makeDrone():kind==='station'?makeStation():makeCommunity(state()||{});scene.add(object);
  if(kind!=='community'){explodeModel(object,Number($('#explode').value)/100);setCutaway(object,$('#cutaway').checked);}
  sceneSignature=signature(state());updatePanel();if(!previous)resetCamera();else{camera.position.copy(previous.position);controls.target.copy(previous.target);controls.update();}setLabels();syncCommunity();
}
function resetCamera(top=false){
  const views={drone:[[1.15,.87,1.48],[0,.015,0],.25,5],station:[[5.2,3.7,5.5],[0,1,.2],1.8,18],community:[[880,770,968],[0,-15,0],100,2200]};
  const [pos,target,min,max]=views[kind];camera.near=kind==='community'?.5:.01;camera.far=kind==='community'?6000:150;camera.updateProjectionMatrix();camera.up.set(0,1,0);camera.position.set(...(top?[target[0],kind==='community'?1000:kind==='station'?7:2.6,target[2]+.001]:pos));controls.target.set(...target);controls.minDistance=min;controls.maxDistance=max;controls.update();
  scene.getObjectByName('display-floor').visible=kind!=='community';scene.getObjectByName('studio-grid').visible=false;
  scene.background.set(kind==='community'?0xdfe8dd:0xe8ede1);scene.fog=null;const sun=scene.getObjectByName('studio-sun');const c=sun.shadow.camera;sun.castShadow=kind!=='community';c.left=c.bottom=-5;c.right=c.top=5;c.near=.1;c.far=120;c.updateProjectionMatrix();
}
function addLabel(label,pos,pickup=false){const el=document.createElement('div');el.className='model-label'+(pickup?' pickup':'');el.textContent=label;labels.append(el);labelItems.push({el,pos});}
function setLabels(){labels.replaceChildren();labelItems=[];
  if(kind==='community'){
    for(const s of state()?.stations||[])addLabel(s.name,new THREE.Vector3(...coords(s.x,s.y,24)));
    for(const p of state()?.pickup_points||[])addLabel(p.name,new THREE.Vector3(...coords(p.x,p.y,5)),true);
  }else if(kind==='drone'){
    addLabel('0.12 m² 机载光伏',new THREE.Vector3(0,.30,0));addLabel('底挂载荷舱',new THREE.Vector3(.25,-.12,.20));
  }else{addLabel('3 m² 光伏顶棚',new THREE.Vector3(0,2.5,-.75));addLabel('双起降补能位',new THREE.Vector3(.8,.55,1.5));}
}
function updateLabels(){labels.hidden=!$('#show-labels').checked;const w=stage.clientWidth,h=stage.clientHeight;for(const item of labelItems){const p=item.pos.clone();if(kind==='drone'&&item.el.textContent.includes('光伏'))p.y+=Number($('#explode').value)/100*.4;const v=p.project(camera);item.el.hidden=v.z< -1||v.z>1||Math.abs(v.x)>1||Math.abs(v.y)>1;item.el.style.left=`${(v.x+1)*w/2}px`;item.el.style.top=`${(-v.y+1)*h/2}px`;}}
function drawReadouts(){const s=state();if(!s)return;$('#readouts').replaceChildren();const entries=[['仿真时间',`T+${round(s.clock)} min`],['正在配送',`${s.drones.filter(d=>d.status==='flying').length} 架`],['待调度订单',`${s.orders.filter(o=>o.status==='pending').length} 单`],['正在补能',`${s.drones.filter(d=>d.status==='charging').length} 架`],['站点总储能',`${round(s.stations.reduce((v,x)=>v+x.storage_wh,0)/1000,2)} kWh`]];for(const [a,b] of entries){const div=document.createElement('div'),span=document.createElement('span'),strong=document.createElement('b');span.textContent=a;strong.textContent=b;div.append(span,strong);$('#readouts').append(div);}}
function syncCommunity(){if(kind!=='community'||!object)return;const s=state();if(!s)return;
  const drones=object.getObjectByName('drones');for(const node of drones.children){const d=s.drones.find(d=>d.id===node.name);if(!d)continue;node.position.set(...coords(d.x,d.y,d.status==='flying'?40:4.9));node.userData.entity.data=d;}
  for(const ring of object.getObjectByName('charge-markers').children){const d=s.drones.find(d=>d.id===ring.name);ring.visible=d?.status==='charging';if(d){ring.position.set(...coords(d.x,d.y,.5));ring.userData.entity.data=d;}}
  object.getObjectByName('zones').visible=$('#show-zones').checked;
  drawReadouts();
}
async function fetchState(){if(refreshing)return;refreshing=true;try{const r=await fetch('/api/state',{cache:'no-store'});if(!r.ok)throw Error(r.status===401?'登录平台后可同步实时仿真状态':'平台服务暂不可用');liveState=await r.json();liveConnected=true;text('#connection',source==='live'?'平台仿真已连接':'独立演示');if(source==='live'&&kind==='community'){if(sceneSignature!==signature(liveState))build(true);else syncCommunity();}return true;}catch(e){liveConnected=false;if(source==='live')text('#connection','连接中断 · 保留上次状态');return false;}finally{refreshing=false;updateSource();}}
function updateSource(){const live=source==='live',available=live&&liveConnected&&!!liveState?.user&&liveState.user.role==='admin';text('#source',live?'切换至独立演示':liveState?'切换至平台数据':'连接平台数据');$('#demo-play').hidden=live;$('#dispatch').hidden=!live;$('#advance').hidden=!live;$('#dispatch').disabled=!available||busy;$('#advance').disabled=!available||busy;text('#network-help',live?'读取现有平台状态。调度与推进按钮会更新平台订单和仿真时间；社区仅作三维示意。':'独立演示使用原 VNS–MILP 算法离线计算的示例航线，不修改平台订单。');text('#connection',live?(liveConnected?'平台仿真数据':liveState?'连接中断 · 保留上次状态':'等待平台登录'):'独立演示 · 不改平台数据');}
async function action(path,body){if(busy)return;busy=true;updateSource();try{const r=await fetch('/api'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(!r.ok){const err=await r.json();throw Error(typeof err.detail==='string'?err.detail:'操作失败');}await fetchState();notify(path==='/dispatch'?'平台调度完成，已同步计算航线':'平台仿真已推进 1 分钟');}catch(e){notify(e.message);}finally{busy=false;updateSource();}}
function interpolate(path,f){const lengths=[];let total=0;for(let i=1;i<path.length;i++){const d=Math.hypot(path[i][0]-path[i-1][0],path[i][1]-path[i-1][1]);lengths.push(d);total+=d;}let distance=total*f;for(let i=0;i<lengths.length;i++){if(distance<=lengths[i]){const a=distance/Math.max(lengths[i],.0001);return [path[i][0]+(path[i+1][0]-path[i][0])*a,path[i][1]+(path[i+1][1]-path[i][1])*a];}distance-=lengths[i];}return path.at(-1);}
function advanceDemo(dt){if(!demoPlaying||source!=='demo')return;demoTime+=dt*.17;demoState.clock=demoTime;let active=0;
  for(const f of demoState.flights){const d=demoState.drones.find(d=>d.id===f.drone_id),initial=demoBase.drones.find(d=>d.id===d.id);let spent=.8;
    for(const l of f.legs){const fraction=Math.min(1,Math.max(0,(demoTime-l.start)/Math.max(.001,l.end-l.start)));spent+=fraction*l.energy;if(demoTime>=l.start&&demoTime<=l.end)[d.x,d.y]=interpolate(l.path,fraction);if(l.order_id&&demoTime>=l.end){const o=demoState.orders.find(o=>o.id===l.order_id);if(o)o.status='delivered';}}
    d.battery=Math.max(0,initial.battery-spent/d.capacity_wh*100);
    if(demoTime>=f.duration_min){f.done=true;d.status='idle';const s=demoState.stations.find(s=>s.id===f.station_id);d.x=s.x;d.y=s.y;}else{d.status='flying';active++;}
  }
  if(!active){demoPlaying=false;text('#demo-play','重新播放配送演示');notify('示例航线已完成，点击可重播');}
  syncCommunity();
}
function showPicked(hit){let node=hit;while(node&&!node.userData.entity)node=node.parent;
  if(node?.userData.entity){const {type,data:d}=node.userData.entity;if(type==='station')info(d.name,`站点 ${d.id} · 储能 ${round(d.storage_wh,0)} / ${d.storage_capacity_wh} Wh · 光伏 ${d.pv_area} m² · ${d.chargers} 个充电位 · ${d.online?'在线':'暂停'}。`);if(type==='drone')info(d.id,`电量 ${round(d.battery)}% · ${({flying:'配送飞行中',idle:'待命',charging:'充电中',maintenance:'维护中'})[d.status]||d.status} · 最大载重 ${d.max_payload} kg · 电池 ${d.capacity_wh} Wh。`);if(type==='zone')info(d.name,'平台规划航线绕行的矩形禁飞区域；三维半透明柱体用于示意。');if(type==='pickup')info(d.name,`公共取件点 ${d.id} · 平面坐标 (${d.x}, ${d.y}) · ${d.available===false?'当前不可用':'可用'}。`);if(type==='order')info(d.id,`订单状态 ${d.status} · ${d.address}。`);return;}
  node=hit;while(node&&!node.userData.component)node=node.parent;if(node&&COMPONENTS[node.userData.component])info(...COMPONENTS[node.userData.component]);
}
async function exportModel(){const button=$('#download');button.disabled=true;try{const format=$('#export-format').value;const clean=kind==='drone'?makeDrone():kind==='station'?makeStation():makeCommunity(state()||{});clean.updateMatrixWorld(true);let result;if(format==='glb')result=await new GLTFExporter().parseAsync(clean,{binary:true,onlyVisible:true});else if(format==='obj')result=new OBJExporter().parse(clean);else result=new STLExporter().parse(clean,{binary:true});const blob=new Blob([result],{type:format==='glb'?'model/gltf-binary':'application/octet-stream'});save(blob,`晴空邻里_${titles[kind]}.${format}`);dispose(clean);notify('模型已导出（装配状态）');}catch(e){notify('导出失败：'+e.message);}finally{button.disabled=false;}}
function save(blob,name){const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);}
async function init(){
  demoBase=await fetch('./demo-state.json').then(r=>{if(!r.ok)throw Error('示例文件加载失败');return r.json();});demoState=clone(demoBase);
  scene=new THREE.Scene();scene.background=new THREE.Color(0xe8ede1);camera=new THREE.PerspectiveCamera(40,1,.01,150);
  try{renderer=new THREE.WebGLRenderer({antialias:true,preserveDrawingBuffer:true});}catch(e){$('#fallback').hidden=false;text('#connection','WebGL 不可用');return;}
  renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.05;renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;stage.append(renderer.domElement);
  controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;controls.maxPolarAngle=Math.PI*.49;
  const pmrem=new THREE.PMREMGenerator(renderer);const room=new RoomEnvironment();scene.environment=pmrem.fromScene(room,.04).texture;room.dispose();pmrem.dispose();scene.environmentIntensity=.65;
  scene.add(new THREE.HemisphereLight(0xffffff,0x657264,1.5));const sun=new THREE.DirectionalLight(0xfff9e7,3);sun.name='studio-sun';sun.position.set(10,18,12);sun.castShadow=true;sun.shadow.mapSize.set(2048,2048);sun.shadow.bias=-.00008;sun.shadow.normalBias=.001;sun.shadow.radius=4;scene.add(sun);
  const floor=new THREE.Mesh(new THREE.PlaneGeometry(50,50),new THREE.MeshStandardMaterial({color:0xe8ede1,roughness:.9}));floor.rotation.x=-Math.PI/2;floor.position.y=-.29;floor.name='display-floor';floor.receiveShadow=true;scene.add(floor);
  const grid=new THREE.GridHelper(15,30,0xb8c5a8,0xdce3d1);grid.position.y=-.285;grid.name='studio-grid';scene.add(grid);
  const resize=()=>{const w=stage.clientWidth,h=stage.clientHeight;renderer.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix();};new ResizeObserver(resize).observe(stage);resize();
  $$('[data-model]').forEach(b=>b.addEventListener('click',()=>{if(kind===b.dataset.model)return;kind=b.dataset.model;$('#explode').value=0;$('#cutaway').checked=false;build();}));
  $('#reset').onclick=()=>resetCamera();$('#top').onclick=()=>resetCamera(true);$('#explode').oninput=()=>explodeModel(object,Number($('#explode').value)/100);$('#cutaway').onchange=()=>setCutaway(object,$('#cutaway').checked);$$('[data-preset]').forEach(b=>b.onclick=()=>{const mode=b.dataset.preset;$('#explode').value=mode==='exploded'?90:0;$('#cutaway').checked=mode==='cutaway';explodeModel(object,Number($('#explode').value)/100);setCutaway(object,$('#cutaway').checked);resetCamera();if(mode==='exploded'){camera.position.multiplyScalar(1.3);controls.update();}});$('#show-zones').onchange=syncCommunity;$('#download').onclick=exportModel;
  $('#capture').onclick=()=>{renderer.render(scene,camera);renderer.domElement.toBlob(blob=>{if(blob)save(blob,`晴空邻里_${titles[kind]}_截图.png`);});};
  $('#dispatch').onclick=()=>action('/dispatch',{method:'vns'});$('#advance').onclick=()=>action('/simulation',{action:'advance',minutes:1});
  $('#source').onclick=async()=>{if(source==='live'){source='demo';demoPlaying=false;demoTime=0;demoState=clone(demoBase);}else{if(!await fetchState()){notify('请先启动并登录原平台，再连接平台数据。独立演示仍可使用。');return;}source='live';demoPlaying=false;}text('#demo-play','播放配送演示');updateSource();build();};
  $('#refresh').onclick=async()=>{if(source==='live'){if(await fetchState())notify('已同步平台状态');else notify('同步失败，请确认平台已启动并登录');}else{demoTime=0;demoPlaying=false;demoState=clone(demoBase);text('#demo-play','播放配送演示');build();notify('独立演示已复位');}};
  $('#demo-play').onclick=()=>{if(demoState.flights.every(f=>f.done)){demoTime=0;demoState=clone(demoBase);build();}demoPlaying=!demoPlaying;text('#demo-play',demoPlaying?'暂停配送演示':'继续配送演示');};
  const raycaster=new THREE.Raycaster();stage.onpointerdown=e=>pointerStart=[e.clientX,e.clientY];stage.onpointerup=e=>{if(!pointerStart||Math.hypot(e.clientX-pointerStart[0],e.clientY-pointerStart[1])>5)return;const r=stage.getBoundingClientRect();raycaster.setFromCamera(new THREE.Vector2((e.clientX-r.left)/r.width*2-1,-(e.clientY-r.top)/r.height*2+1),camera);const hits=raycaster.intersectObject(object,true);if(hits[0])showPicked(hits[0].object);};
  build();if(await fetchState()){source='live';updateSource();if(kind==='community')build();}
  let last=performance.now();renderer.setAnimationLoop(now=>{const dt=Math.min((now-last)/1000,.1);last=now;advanceDemo(dt);if($('#motion').checked)object.traverse(o=>{if(o.name==='propeller'&&(kind!=='community'||o.parent.parent.userData.entity?.data?.status==='flying'))o.rotation.y+=dt*18*(o.userData.spin||1);});controls.update();updateLabels();renderer.render(scene,camera);if(source==='live'&&kind==='community'&&now-lastPoll>4000){lastPoll=now;fetchState();}});
}
init().catch(e=>{text('#connection','加载失败');$('#fallback').hidden=false;$('#fallback').prepend(document.createTextNode(e.message+'。'));console.error(e);});
