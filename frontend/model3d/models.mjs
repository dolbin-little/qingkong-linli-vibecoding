import * as THREE from './vendor/three/build/three.module.js';
import {makeDetailedDrone,makeDetailedStation} from './detailed-models.mjs';
export {setCutaway} from './detailed-models.mjs';

export const MODEL_VERSION = '2.0.0';
export const COMPONENTS = {
  solar: ['机载光伏板', '0.40 × 0.30 m，合计 0.12 m²；布置在四个旋翼盘之间。按平台 20% 效率、90% 转换系数计算，720 W/m² 时约 15.55 W，仅作辅助补能。'],
  shell: ['可拆卸流线型外壳', '倒角外罩、通风百叶、减振安装和紧固件的概念布局；透视开关可查看内部模块。'],
  electronics: ['飞控与电源电子系统', '独立飞控板、IMU 屏蔽罩、四路 ESC、MPPT 概念功率管理板与电源线束。板级几何用于说明连接关系，不是可制造电路图。'],
  controller: ['站点边缘控制与供电', '网关板、MPPT 散热模块与两路充电母线的概念布局。平台为 FastAPI/SQLite 后端、VNS–MILP 调度与 LSTM/MPC 能源管理。'],
  frame: ['机架与飞控舱', '四旋翼 X 形概念机架；中央舱容纳飞控、定位与通信模块。展示结构关系，尚未做强度、气动与电磁兼容验证。'],
  motors: ['动力与旋翼', '四组电机及双叶桨，旋翼半径 0.15 m、轴心间距 0.78 m。旋转动画只表达工作状态，不模拟推力。'],
  battery: ['可更换电池', '平台容量假设 180 Wh，返航后由站点充电。调度检查返航能量并保留 20% 安全余量；外观尺寸不代表已验证的电芯方案。'],
  cargo: ['配送载荷舱', '底挂物品舱，支持展示充电宝、雨伞、饮水与急救用品配送。平台最大载重假设 1.8 kg；尚未验证样机承载能力。'],
  gear: ['起落架', '双侧支撑和缓冲脚垫，为底部载荷留出空间。尺寸为外观设计值。'],
  roof: ['站点光伏顶棚', '光伏面板 2.0 × 1.5 m，共 3 m²；720 W/m²、20% 效率下理论功率 432 W。顶棚位于柜体后方，起降区位于前方。'],
  pads: ['双起降与补能位', '两个独立停靠位置，对应平台每站 2 个充电位。充电接触、定位和无人机自主着陆接口为概念表达。'],
  cabinet: ['共享物品柜', '四类储物格对应平台库存：共享充电宝、共享雨伞、瓶装饮水与便携急救包；显示面板用于表达取件与库存服务。'],
  storage: ['站点储能与控制舱', '平台每站储能上限 1000 Wh；充电模型单口 100 W、效率 92%。能源中心通过 60 分钟 MPC 时域分配资源。'],
  network: ['社区配送网络', '与原平台统一采用 1000 × 700 m 平面坐标。建筑为示意体块；站点、无人机符号有意放大，飞行展示高度为 40 m，不代表获批空域。'],
};
const palette = { green: 0x204d3d, lime: 0xc7df8f, white: 0xf1f2e8, dark: 0x182b2b, metal: 0x87978c, blue: 0x193c68, gold: 0xc99b47 };
export function material(color, metalness=.15, roughness=.55) { return new THREE.MeshStandardMaterial({color, metalness, roughness}); }
export function mesh(geometry, mat, parent, name, pos=[0,0,0]) {
  const o = new THREE.Mesh(geometry, mat); o.name=name; o.position.set(...pos); o.castShadow=true; o.receiveShadow=true; parent.add(o); return o;
}
function box(p,n,size,pos,color) { return mesh(new THREE.BoxGeometry(...size),material(color),p,n,pos); }
function cylinder(p,n,r,h,pos,color,r2=r) { return mesh(new THREE.CylinderGeometry(r,r2,h,24),material(color,.35),p,n,pos); }
function component(parent,key,pos=[0,0,0]) { const g=new THREE.Group(); g.name=key; g.userData.component=key; g.position.set(...pos); g.userData.home=pos; parent.add(g); return g; }
function bar(p,n,a,b,r,color) {const va=new THREE.Vector3(...a),vb=new THREE.Vector3(...b),d=vb.clone().sub(va);const m=cylinder(p,n,r,d.length(),va.clone().add(vb).multiplyScalar(.5).toArray(),color);m.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),d.normalize());return m;}
function panel(p,w,d,pos,name) {
  const g=new THREE.Group();g.name=name;g.position.set(...pos);p.add(g);
  box(g,'铝合金边框',[w,.018,d],[0,0,0],palette.metal);
  box(g,'光伏有效面',[w-.012,.008,d-.012],[0,.013,0],palette.blue);
  for(let i=1;i<8;i++)box(g,'电池片纵栅',[.001,.001,d-.02],[-w/2+w*i/8,.018,0],0x7195b7);
  for(let j=1;j<5;j++)box(g,'电池片横栅',[w-.02,.001,.001],[0,.018,-d/2+d*j/5],0x7195b7);
  return g;
}
function makeSimpleDrone() {
  const root=new THREE.Group();root.name='GreenFlight_solar_assisted_quadcopter';root.userData={units:'metres',concept:true,pv_area_m2:.12,battery_Wh:180,payload_kg:1.8};
  const frame=component(root,'frame');
  box(frame,'飞控主舱',[.38,.085,.26],[0,.09,0],palette.white);
  box(frame,'中层安装板',[.43,.018,.28],[0,.035,0],palette.green);
  for(const x of [-1,1])for(const z of [-1,1]) {
    bar(frame,'碳纤维机臂',[x*.12,.05,z*.09],[x*.39,.05,z*.39],.018,palette.dark);
    cylinder(frame,'电机座',.046,.014,[x*.39,.067,z*.39],palette.green);
    cylinder(frame,'状态灯',.012,.01,[x*.28,.075,z*.28],x<0?0xed8a68:0xaed76b);
  }
  cylinder(frame,'GNSS 天线',.025,.025,[0,.17,-.105],palette.white);
  const solar=component(root,'solar');panel(solar,.4,.3,[0,.215,0],'0.12m2 光伏组件');
  for(const x of [-.13,.13])bar(solar,'顶板支架',[x,.13,0],[x,.205,0],.008,palette.metal);
  const motors=component(root,'motors');
  for(const x of [-1,1])for(const z of [-1,1]) {
    cylinder(motors,'无刷电机',.032,.048,[x*.39,.1,z*.39],palette.dark);
    const rotor=new THREE.Group();rotor.name='propeller';rotor.position.set(x*.39,.136,z*.39);rotor.userData.spin=x*z;motors.add(rotor);
    const blade=box(rotor,'双叶桨',[.30,.007,.022],[0,0,0],palette.dark);blade.rotation.y=x*z*.3;
    cylinder(rotor,'桨毂',.014,.013,[0,.005,0],palette.metal);
  }
  const battery=component(root,'battery');box(battery,'180Wh 电池概念外壳',[.29,.06,.16],[0,-.025,0],palette.green);
  box(battery,'电池拉手',[.06,.015,.018],[0,-.02,.09],palette.gold);
  const cargo=component(root,'cargo');box(cargo,'轻量配送舱',[.28,.13,.22],[0,-.13,0],palette.white);
  box(cargo,'载荷舱盖',[.285,.015,.225],[0,-.058,0],palette.lime);
  box(cargo,'舱门扣',[.045,.025,.012],[0,-.12,.116],palette.green);
  const gear=component(root,'gear');
  for(const x of [-.22,.22]) {
    for(const z of [-.16,.16])bar(gear,'起落支撑',[x*.7,.02,z],[x,-.26,z],.009,palette.metal);
    bar(gear,'滑橇',[x,-.26,-.23],[x,-.26,.23],.012,palette.dark);
    for(const z of [-.2,.2])box(gear,'缓冲脚垫',[.055,.018,.065],[x,-.27,z],palette.green);
  }
  return root;
}
function makeSimpleStation() {
  const root=new THREE.Group();root.name='GreenFlight_shared_solar_station';root.userData={units:'metres',concept:true,pv_area_m2:3,chargers:2,storage_capacity_Wh:1000};
  const cabinet=component(root,'cabinet');
  box(cabinet,'站点基座',[3.4,.12,3.4],[0,.06,.25],0xb5bfa8);
  box(cabinet,'服务柜主体',[1.8,1.55,.6],[0,.9,-.8],palette.white);
  const colors=[palette.green,0x9fba78,0xa2b9b1,0xd6cda9];
  for(let i=0;i<4;i++){const x=-.66+i*.44;box(cabinet,['充电宝格','雨伞格','饮水格','急救用品格'][i],[.41,1.1,.025],[x,.95,-.485],colors[i]);box(cabinet,'柜门拉手',[.025,.16,.03],[x+.13,.92,-.463],palette.white);}
  box(cabinet,'信息显示屏',[.42,.24,.025],[0,1.57,-.47],palette.dark);
  const roof=component(root,'roof');
  for(const x of [-.91,.91])for(const z of [-1.36,-.11])cylinder(roof,'顶棚支柱',.028,2.14,[x,1.19,z],palette.green);
  panel(roof,2,1.5,[0,2.3,-.75],'3m2 顶棚光伏');
  box(roof,'顶棚前沿',[2.04,.08,.04],[0,2.27,.015],palette.green);
  const pads=component(root,'pads');
  for(const x of [-.88,.88]){
    box(pads,'独立起降平台',[1.42,.12,1.4],[x,.23,1.08],palette.green);
    cylinder(pads,'降落靶面',.55,.008,[x,.295,1.08],palette.lime);
    box(pads,'H 标左',[.055,.008,.4],[x-.13,.303,1.08],palette.white);box(pads,'H 标右',[.055,.008,.4],[x+.13,.303,1.08],palette.white);box(pads,'H 标横',[.3,.008,.055],[x,.303,1.08],palette.white);
    for(const dx of [-.25,.25])box(pads,'充电接触带',[.04,.009,.5],[x+dx,.305,1.08],palette.gold);
  }
  const storage=component(root,'storage');box(storage,'储能及边缘控制柜',[.46,.75,.58],[1.2,.51,-.8],palette.green);
  for(let i=0;i<5;i++)box(storage,'散热格栅',[.24,.012,.012],[1.2,.46+i*.06,-.501],palette.metal);
  cylinder(storage,'运行指示灯',.025,.015,[1.2,.91,-.8],palette.lime);
  return root;
}
export const BUILDINGS=[[70,65,60,38],[145,68,62,37],[235,80,80,40],[335,65,60,38],[560,65,90,35],[730,50,48,38],[880,80,65,45],[50,225,50,70],[210,280,72,48],[320,360,65,45],[540,270,56,60],[840,240,80,40],[810,405,65,50],[80,465,65,35],[430,470,65,45],[440,620,80,35],[580,565,45,65],[710,580,45,55],[875,510,50,38]];
export function coords(x,y,height=0) {return [x-500,height,y-350];}
export function makeCommunity(state) {
  const root=new THREE.Group();root.name='GreenFlight_community_1000x700m';root.userData={units:'metres',concept:true,station_display_scale:5,drone_display_scale:16,display_altitude_m:40};
  const city=component(root,'network');
  box(city,'社区地块',[1000,2,700],[0,-1,0],0xd7e1cd);
  // River follows the original two-dimensional map; roads above it read as bridges.
  const riverCurves=[new THREE.CubicBezierCurve3(new THREE.Vector3(...coords(-20,425)),new THREE.Vector3(...coords(220,385)),new THREE.Vector3(...coords(205,380)),new THREE.Vector3(...coords(380,410))),new THREE.CubicBezierCurve3(new THREE.Vector3(...coords(380,410)),new THREE.Vector3(...coords(555,440)),new THREE.Vector3(...coords(680,620)),new THREE.Vector3(...coords(1040,490)))];
  const riverPoints=riverCurves.flatMap((c,i)=>c.getPoints(45).slice(i?1:0)).filter(p=>p.x>=-500&&p.x<=500),riverVertices=[];
  for(let i=0;i<riverPoints.length-1;i++){const a=riverPoints[i],b=riverPoints[i+1],normal=new THREE.Vector3(-(b.z-a.z),0,b.x-a.x).normalize().multiplyScalar(28);const corners=[a.clone().add(normal),a.clone().sub(normal),b.clone().add(normal),b.clone().sub(normal)];for(const j of [0,2,1,1,2,3])riverVertices.push(Math.max(-500,Math.min(500,corners[j].x)),.025,Math.max(-350,Math.min(350,corners[j].z)));}
  const riverGeometry=new THREE.BufferGeometry();riverGeometry.setAttribute('position',new THREE.Float32BufferAttribute(riverVertices,3));riverGeometry.computeVertexNormals();mesh(riverGeometry,material(0x9ebfc0),city,'清溪河道');
  for(const y of [140,350,560])box(city,'社区横向道路',[1000,.12,24],coords(500,y,.08),0xf5f3e8);
  for(const x of [180,370,630,790])box(city,'社区纵向道路',[24,.14,700],coords(x,350,.09),0xf5f3e8);
  BUILDINGS.forEach(([x,y,w,d],i)=>{const h=12+(i%5)*5;box(city,'建筑示意_'+i,[w,h,d],coords(x+w/2,y+d/2,h/2),[0xc1cdbb,0xb7c8bb,0xe3e4d7][i%3]);box(city,'建筑屋顶_'+i,[w+1,.7,d+1],coords(x+w/2,y+d/2,h+.35),0xa1b59e);});
  const windowMatrices=[];const transform=new THREE.Object3D();
  BUILDINGS.forEach(([x,y,w,d],i)=>{const height=12+(i%5)*5;
    for(let floor=1;floor<height/4;floor++)for(let col=0;col<Math.floor(w/8);col++)for(const edge of [0,1]){transform.position.set(...coords(x+5+col*8,y+(edge?d+.05:-.05),floor*4));transform.scale.set(3.5,1.8,.08);transform.rotation.set(0,0,0);transform.updateMatrix();windowMatrices.push(transform.matrix.clone());}
    for(const xx of [x+.15,x+w-.15])for(let floor=1;floor<height/4;floor++)for(let col=0;col<Math.floor(d/8);col++){transform.position.set(...coords(xx,y+5+col*8,floor*4));transform.scale.set(.08,1.8,3.5);transform.updateMatrix();windowMatrices.push(transform.matrix.clone());}
    box(city,'屋顶设备机房',[w*.25,2.5,d*.24],coords(x+w*.68,y+d*.65,height+1.6),0x7d928a);
    for(let k=0;k<3;k++)box(city,'屋顶空调外机',[4,1.5,2.2],coords(x+8+k*6,y+8,height+1.5),0xd3d8d4);
    box(city,'建筑入口雨棚',[9,.6,4],coords(x+w/2,y+d+2,3),0x668a7c);
  });
  const windows=new THREE.InstancedMesh(new THREE.BoxGeometry(1,1,1),material(0x66868c,.35,.2),windowMatrices.length);windows.name='建筑窗格立面';windowMatrices.forEach((m,i)=>windows.setMatrixAt(i,m));city.add(windows);
  for(const y of [140,350,560])for(let x=20;x<990;x+=22)box(city,'道路中心虚线',[10,.02,.65],coords(x,y,.19),0xc2c8b9);
  for(const x of [180,370,630,790])for(const y of [140,350,560])for(let n=0;n<6;n++)box(city,'斑马线',[1.9,.03,14],coords(x-7+n*2.8,y-24,.2),0xffffff);
  for(let i=0;i<14;i++){const x=25+(i*67)%940,y=[125,365,545][i%3];box(city,'路侧车辆',[9,3.2,4.5],coords(x,y,1.8),[0x46776e,0xb7bdb7,0xd8d6be][i%3]);box(city,'车辆车窗',[4.5,1,4.6],coords(x,y,3.2),0x607d80);}
  for(const x of [175,625,795])for(const y of [200,430,630]){cylinder(city,'路灯立柱',.5,12,coords(x,y,6),0x6c7f72);box(city,'路灯灯臂',[4,.5,.5],coords(x+1.5,y,12),0x7f9186);box(city,'路灯灯具',[2,.4,1.1],coords(x+3,y,11.8),0xf4e3ae);}
  for(const [x,y,r] of [[555,210,40],[885,640,44],[85,620,30]])cylinder(city,'社区绿地',r,.3,coords(x,y,.2),0xadc58c);
  for(let i=0;i<35;i++){const x=30+(i*127)%940,y=22+(i*79)%650; if(BUILDINGS.some(([bx,by,w,d])=>x>bx-5&&x<bx+w+5&&y>by-5&&y<by+d+5))continue; cylinder(city,'树干',1,5,coords(x,y,2.5),0x80765b);mesh(new THREE.SphereGeometry(5,10,8),material(0x779d70),city,'树冠',coords(x,y,7));}
  const zones=new THREE.Group();zones.name='zones';root.add(zones);
  for(const z of state.zones||[]){const m=material(0xc99b47);m.transparent=true;m.opacity=.2;m.depthWrite=false;const o=mesh(new THREE.BoxGeometry(z.w,60,z.h),m,zones,z.name||'禁飞区域',coords(z.x+z.w/2,z.y+z.h/2,30));o.userData.entity={type:'zone',data:z};o.castShadow=false;const e=new THREE.LineSegments(new THREE.EdgesGeometry(o.geometry),new THREE.LineBasicMaterial({color:0xad7938}));e.position.copy(o.position);zones.add(e);}
  for(const z of state.zones||[]){for(const h of [1,60]){for(const yy of [z.y,z.y+z.h])bar(zones,'禁飞边界实体',[...coords(z.x,yy,h)],[...coords(z.x+z.w,yy,h)],.65,0xb78636);for(const xx of [z.x,z.x+z.w])bar(zones,'禁飞边界实体',[...coords(xx,z.y,h)],[...coords(xx,z.y+z.h,h)],.65,0xb78636);}for(const xx of [z.x,z.x+z.w])for(const yy of [z.y,z.y+z.h])bar(zones,'禁飞边界立柱',coords(xx,yy,1),coords(xx,yy,60),.65,0xb78636);}
  const stations=new THREE.Group();stations.name='stations';root.add(stations);
  for(const s of state.stations||[]){const o=makeSimpleStation();o.scale.setScalar(5);o.position.set(...coords(s.x,s.y,.3));o.name=s.id;o.userData.entity={type:'station',data:s};stations.add(o);}
  const pickups=new THREE.Group();pickups.name='pickups';root.add(pickups);
  for(const p of state.pickup_points||[]){const o=cylinder(pickups,p.name,6,1,coords(p.x,p.y,.6),p.available===false?0x969f9a:0x538aa4);o.userData.entity={type:'pickup',data:p};}
  const routes=new THREE.Group();routes.name='routes';root.add(routes);
  for(const f of (state.flights||[]).filter(f=>!f.done))for(const l of f.legs||[]){const points=(l.path||[]).map(([x,y])=>new THREE.Vector3(...coords(x,y,40)));if(points.length<2)continue;const line=new THREE.Line(new THREE.BufferGeometry().setFromPoints(points),new THREE.LineBasicMaterial({color:0x327d64}));line.name=f.drone_id+'_route';routes.add(line);}
  for(const f of (state.flights||[]).filter(f=>!f.done))for(const l of f.legs||[])for(let i=1;i<(l.path||[]).length;i++){const a=l.path[i-1],b=l.path[i];bar(routes,f.drone_id+'_route_solid',coords(...a,40),coords(...b,40),1.2,0x21745a);}
  const drones=new THREE.Group();drones.name='drones';root.add(drones);
  for(const d of state.drones||[]){const o=makeSimpleDrone();o.scale.setScalar(16);o.position.set(...coords(d.x,d.y,d.status==='flying'?40:4.9));o.name=d.id;o.userData.entity={type:'drone',data:d};drones.add(o);}
  const chargeMarkers=new THREE.Group();chargeMarkers.name='charge-markers';root.add(chargeMarkers);
  for(const d of state.drones||[]){const o=mesh(new THREE.TorusGeometry(9,.6,6,28),material(0x77ad57),chargeMarkers,d.id,coords(d.x,d.y,.5));o.rotation.x=-Math.PI/2;o.visible=d.status==='charging';o.userData.entity={type:'drone',data:d};}
  const orders=new THREE.Group();orders.name='orders';root.add(orders);
  for(const d of (state.orders||[]).filter(o=>['pending','flying','return_requested'].includes(o.status))){const o=mesh(new THREE.ConeGeometry(5,12,16),material(palette.gold),orders,d.id,coords(d.x,d.y,8));o.userData.entity={type:'order',data:d};}
  return root;
}

export function explodeModel(root,amount) {
  const offsets={shell:[0,.26,0],electronics:[0,.12,0],controller:[.65,.3,0],solar:[0,.52,0],frame:[0,.13,0],motors:[0,.24,0],battery:[0,-.22,0],cargo:[0,-.45,0],gear:[.25,-.2,0],roof:[0,1.1,0],cabinet:[0,0,0],pads:[0,0,1],storage:[.75,0,0]};
  for(const g of root.children){if(g.userData.home&&offsets[g.name])g.position.fromArray(g.userData.home).addScaledVector(new THREE.Vector3(...offsets[g.name]),amount);}
}

export function makeDrone(){return makeDetailedDrone();}
export function makeStation(){return makeDetailedStation();}
