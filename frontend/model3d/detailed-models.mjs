import * as T from './vendor/three/build/three.module.js';
import {RoundedBoxGeometry} from './vendor/three/examples/jsm/geometries/RoundedBoxGeometry.js';

// All geometry is authored in metres. PCB / cell / fastener layouts are engineering concepts,
// not fabrication drawings, selected commercial components, or measured hardware.
const C={white:0xe8eceb,green:0x133d36,teal:0x218779,lime:0xb4da8a,carbon:0x202a2c,black:0x111a1e,metal:0xa6b1b5,copper:0xc4884c,pcb:0x1a6258,blue:0x102c48,gold:0xc3a56b};
const materials=new Map();
function mat(key,color,metal=.1,rough=.45){if(!materials.has(key))materials.set(key,new T.MeshStandardMaterial({name:key,color,metalness:metal,roughness:rough}));return materials.get(key);}
const M={white:()=>mat('Ceramic_white_shell',C.white,.22,.27),green:()=>mat('Deep_forest_anodised',C.green,.5,.28),teal:()=>mat('Teal_anodised',C.teal,.5,.28),carbon:()=>mat('Carbon_composite',C.carbon,.35,.39),black:()=>mat('Black_polymer',C.black,.1,.6),metal:()=>mat('Brushed_aluminium',C.metal,.78,.26),copper:()=>mat('Copper_winding',C.copper,.75,.25),gold:()=>mat('Gold_contact',C.gold,.8,.24),pcb:()=>mat('FR4_green_PCB',C.pcb,.12,.52),blue:()=>mat('Monocrystalline_PV',C.blue,.48,.2),lime:()=>mat('Service_lime',C.lime,.15,.4)};
function group(p,name){const g=new T.Group();g.name=name;p.add(g);return g;}
function part(p,key){const g=group(p,key);g.userData={component:key,home:[0,0,0]};return g;}
function add(p,name,g,m,pos=[0,0,0]){const o=new T.Mesh(g,m);o.name=name;o.position.set(...pos);o.castShadow=true;o.receiveShadow=true;p.add(o);return o;}
function box(p,n,size,pos,m=M.white(),radius=0){return add(p,n,radius?new RoundedBoxGeometry(...size,2,radius):new T.BoxGeometry(...size),m,pos);}
function cyl(p,n,r,h,pos,m=M.metal(),r2=r,segments=24){return add(p,n,new T.CylinderGeometry(r,r2,h,segments),m,pos);}
function tube(p,n,a,b,r,m=M.carbon()){const v=new T.Vector3(...a),w=new T.Vector3(...b),delta=w.clone().sub(v);const o=cyl(p,n,r,delta.length(),v.clone().add(w).multiplyScalar(.5).toArray(),m);o.quaternion.setFromUnitVectors(new T.Vector3(0,1,0),delta.normalize());return o;}
function cable(p,n,pts,r=.002,color=0xc38a48){const curve=new T.CatmullRomCurve3(pts.map(v=>new T.Vector3(...v)));return add(p,n,new T.TubeGeometry(curve,24,r,6,false),mat('Wire_'+color,color,.2,.5));}
function screw(p,x,y,z,r=.0045){cyl(p,'Hex_socket_fastener',r,r*.5,[x,y,z],M.metal(),r,6);box(p,'Fastener_recess',[r*.9,.0005,r*.24],[x,y+r*.26,z],M.black());}
function gridScrews(p,w,d,y,r=.004){for(const x of [-w/2,w/2])for(const z of [-d/2,d/2])screw(p,x,y,z,r);}
function ring(p,n,r,t,pos,m=M.metal()){const o=add(p,n,new T.TorusGeometry(r,t,8,48),m,pos);o.rotation.x=Math.PI/2;return o;}
function finnedBox(p,n,size,pos){const g=group(p,n);g.position.set(...pos);box(g,n+'_base',size,[0,0,0],M.metal(),size[1]*.15);for(let i=0;i<9;i++)box(g,'Cooling_fin',[size[0]*.85,size[1]*.6,.0015],[0,size[1]*.65,-size[2]*.4+i*size[2]*.1],M.metal());return g;}
function board(p,n,w,d,pos,detail=true){
  const g=group(p,n);g.position.set(...pos);box(g,'FR4_board',[w,.002,d],[0,0,0],M.pcb(),.001);
  gridScrews(g,w*.88,d*.82,.002,Math.min(w*.025,.003));
  const chip=Math.min(w,d)*.33;box(g,'Processor_package',[chip,.006,chip],[0,.0045,0],M.black(),.001);
  for(let i=0;i<8;i++)for(const side of [-1,1]){box(g,'IC_gullwing_pin',[.002,.001,.006],[-chip*.4+i*chip*.115,.0025,side*(chip/2+.002)],M.metal());box(g,'IC_gullwing_pin',[.006,.001,.002],[side*(chip/2+.002),.0025,-chip*.4+i*chip*.115],M.metal());}
  for(let i=0;i<6;i++)for(const side of [-1,1]){const x=-w*.36+i*w*.14;box(g,'SMD_resistor',[.005,.002,.0025],[x,.002,side*d*.34],M.black());for(const dz of [-1,1])box(g,'SMD_terminal',[.001,.0022,.0026],[x+dz*.002,.002,side*d*.34],M.metal());}
  for(let i=0;i<4;i++){cyl(g,'Capacitor_can',.0035,.007,[-w*.32+i*w*.21,.005,d*.26],M.metal());box(g,'JST_connector',[.009,.006,.007],[-w*.32+i*w*.21,.004,-d*.43],M.white());}
  if(detail){for(let i=0;i<12;i++){const z=-d*.35+i*d*.062;box(g,'Copper_trace',[w*.15,.0002,.0004],[w*.33,.0012,z],M.gold());box(g,'Copper_trace',[.0004,.0002,d*.2],[-w*.27+i*w*.048,.0012,-d*.28],M.gold());}}
  return g;
}
function photovoltaic(p,w,d,y,z=0){
  const g=group(p,'PV_laminated_assembly');g.position.set(0,y,z);box(g,'PV_aluminium_frame',[w,.012,d],[0,0,0],M.metal(),.004);box(g,'PV_backplane',[w-.012,.005,d-.012],[0,.008,0],M.black(),.002);
  const cols=8,rows=6,dx=(w-.024)/cols,dz=(d-.024)/rows;
  for(let i=0;i<cols;i++)for(let j=0;j<rows;j++){
    const x=-w/2+.012+dx*(i+.5),z0=-d/2+.012+dz*(j+.5);
    box(g,'Mono_Si_cell',[dx-.002,.0015,dz-.002],[x,.0115,z0],M.blue(),Math.min(.003,dx*.05));
    for(const k of [-1,0,1])box(g,'PV_busbar',[.00045,.0002,dz-.003],[x+k*dx*.28,.0124,z0],M.metal());
  }
  return g;
}
function propeller(p,x,z,spin){const g=group(p,'propeller');g.position.set(x,.146,z);g.userData.spin=spin;
  for(const sign of [-1,1]){const positions=[],indices=[];const steps=18;
    for(let i=0;i<=steps;i++){const t=i/steps,r=.018+.132*t,width=.009*Math.sin(Math.PI*(t*.8+.1))+.002,sweep=.022*t*t;for(const side of [-1,1])positions.push(sign*r,.005*(1-t)+side*.002*(1-t),sign*sweep+side*width);}
    for(let i=0;i<steps;i++){const a=i*2;indices.push(a,a+1,a+2,a+1,a+3,a+2);}
    const geometry=new T.BufferGeometry();geometry.setAttribute('position',new T.Float32BufferAttribute(positions,3));geometry.setIndex(indices);geometry.computeVertexNormals();const m=M.carbon().clone();m.side=T.DoubleSide;add(g,'Twisted_aerofoil_blade',geometry,m);
  }
  cyl(g,'Propeller_hub',.016,.018,[0,.004,0],M.metal());screw(g,0,.015,0,.005);return g;
}
export function makeDetailedDrone(){
  const root=new T.Group();root.name='GreenFlight_D2_solar_assisted_quadrotor';root.userData={units:'metres',concept:true,version:'2.0',pv_area_m2:.12,battery_Wh:180,payload_kg:1.8};
  const frame=part(root,'frame'),shell=part(root,'shell'),solar=part(root,'solar'),motors=part(root,'motors'),electronics=part(root,'electronics'),battery=part(root,'battery'),cargo=part(root,'cargo'),gear=part(root,'gear');
  box(frame,'CNC_lower_frame',[.355,.022,.24],[0,.035,0],M.carbon(),.018);box(frame,'Vibration_isolation_deck',[.30,.013,.20],[0,.086,0],M.green(),.015);
  for(const x of [-.13,.13])for(const z of [-.08,.08]){cyl(frame,'Silicone_damper',.009,.025,[x,.061,z],M.teal());screw(frame,x,.1,z);}
  const canopy=box(shell,'Removable_upper_fairing',[.365,.075,.245],[0,.136,0],M.white(),.035);canopy.userData.shell=true;
  box(shell,'Canopy_edge_seal',[.37,.008,.25],[0,.103,0],M.green(),.015).userData.shell=true;
  for(const x of [-.165,.165])for(let j=0;j<6;j++)box(shell,'Side_vent_louvre',[.004,.012,.014],[x,.13,-.05+j*.02],M.carbon());
  for(const x of [-.1,.1])for(const z of [-.09,.09])screw(shell,x,.176,z,.0035);
  const lens=mat('Optical_lens',0x0e3142,.65,.1);const front=cyl(frame,'Downward_positioning_camera',.013,.015,[0,.045,.12],lens);front.rotation.x=Math.PI/2;ring(frame,'Camera_bezel',.014,.002,[0,.045,.13],M.metal()).rotation.x=0;
  for(const x of [-1,1])for(const z of [-1,1]){
    const end=[x*.39,.061,z*.39],start=[x*.13,.052,z*.085];tube(frame,'Carbon_fibre_boom',start,end,.016,M.carbon());
    for(const t of [.28,.77]){const a=start.map((v,i)=>v+(end[i]-v)*t);const o=cyl(frame,'Arm_clamp',.019,.026,a,M.metal());o.quaternion.setFromUnitVectors(new T.Vector3(0,1,0),new T.Vector3(...end).sub(new T.Vector3(...start)).normalize());}
    const esc=board(electronics,'ESC_module',.047,.023,[x*.275,.073,z*.25],false);esc.rotation.y=-x*z*Math.PI/4;
    cable(electronics,'Motor_power_harness',[[x*.13,.056,z*.09],[x*.25,.053,z*.24],[x*.39,.075,z*.39]],.002,x<0?0x9d4640:0xa8a18b);
    const motor=group(motors,'Brushless_motor');motor.position.set(...end);cyl(motor,'Motor_mount',.044,.012,[0,0,0],M.green());cyl(motor,'Stator',.030,.038,[0,.026,0],M.carbon());cyl(motor,'Rotor_bell',.034,.012,[0,.051,0],M.metal());
    for(let j=0;j<12;j++){const a=j*Math.PI/6;cyl(motor,'Copper_coil',.0035,.022,[Math.cos(a)*.024,.028,Math.sin(a)*.024],M.copper(),.0035,10);box(motor,'Rotor_vent',[.006,.014,.004],[Math.cos(a)*.032,.041,Math.sin(a)*.032],M.black()).rotation.y=-a;}
    for(const dx of [-.018,.018])screw(motor,dx,.059,0,.003);
    propeller(motors,x*.39,z*.39,x*z);
    const led=mat(x<0?'Red_navigation_LED':'Green_navigation_LED',x<0?0xd86550:0x8bcf81,.2,.22);led.emissive=new T.Color(x<0?0x582018:0x1d4229);cyl(frame,'Navigation_light',.006,.006,[x*.315,.081,z*.31],led);
  }
  const fc=board(electronics,'Flight_controller_IMU_board',.125,.085,[0,.105,.005]);box(fc,'IMU_shield',[.025,.007,.02],[.033,.007,0],M.metal(),.001);
  const mppt=board(electronics,'MPPT_concept_power_board',.08,.05,[0,.078,-.065],false);cyl(mppt,'Power_inductor',.008,.009,[.023,.007,0],M.carbon());
  cable(electronics,'PV_to_MPPT',[[.10,.22,-.08],[.14,.17,-.09],[.08,.09,-.08],[0,.085,-.07]],.002,0x355b85);
  cable(electronics,'Battery_bus',[[0,-.02,-.07],[.12,.025,-.1],[.10,.07,-.04]],.003,0xb45144);
  for(const x of [-.13,.13])for(const z of [-.09,.09])cyl(solar,'PV_standoff',.004,.055,[x,.19,z],M.metal());photovoltaic(solar,.4,.3,.221);
  box(solar,'PV_junction_box',[.035,.009,.026],[0,.205,-.09],M.black(),.003);
  const batteryBase=box(battery,'Quick_release_battery_tray',[.235,.013,.135],[0,-.056,0],M.carbon(),.01);
  box(battery,'Battery_enclosure',[.224,.068,.122],[0,-.016,0],M.green(),.012).userData.shell=true;
  for(let i=0;i<6;i++)for(let j=0;j<2;j++){const x=-.075+i*.03,z=-.025+j*.05;cyl(battery,'Cell_concept_12_cell_layout',.0105,.057,[x,-.017,z],mat('Cell_wrapper',0x4a7383,.35,.3));cyl(battery,'Cell_terminal',.0075,.001,[x,.012,z],M.metal());}
  box(battery,'Battery_latch',[.055,.022,.022],[0,-.012,.071],M.gold(),.005);box(battery,'Gold_power_connector',[.03,.018,.012],[0,-.01,-.071],M.gold(),.002);
  const case0=box(cargo,'Payload_protective_case',[.275,.14,.215],[0,-.143,0],M.white(),.024);case0.userData.shell=true;
  box(cargo,'Payload_seal',[.28,.009,.22],[0,-.079,0],M.teal(),.012);box(cargo,'Payload_lower_bumper',[.245,.014,.19],[0,-.212,0],M.carbon(),.009);
  for(const x of [-.105,.105]){box(cargo,'Over_centre_latch',[.023,.035,.015],[x,-.113,.111],M.metal(),.004);screw(cargo,x,-.071,.07,.003);}
  box(cargo,'Payload_inner_parcel',[.17,.07,.125],[0,-.14,0],mat('Parcel_cardboard',0xbc9a71,.05,.8),.008);
  for(const x of [-.207,.207]){for(const z of [-.155,.155]){tube(gear,'Landing_strut',[x*.73,.024,z],[x,-.264,z*.9],.008,M.carbon());ring(gear,'Strut_collar',.009,.002,[x*.85,-.08,z*.98]);}tube(gear,'Landing_skid',[x,-.264,-.215],[x,-.264,.215],.010,M.metal());for(const z of [-.185,.185])box(gear,'Elastomer_landing_pad',[.035,.018,.053],[x,-.274,z],M.black(),.007);}
  return root;
}

function screen(p,w,h,pos){box(p,'Touch_screen_bezel',[w+.05,h+.05,.015],pos,M.carbon(),.012);box(p,'Touch_screen_glass',[w,h,.004],[pos[0],pos[1],pos[2]+.009],mat('Screen_glass',0x133d43,.5,.16),.005);for(let i=0;i<4;i++)box(p,'Interface_row',[w*.75,h*.07,.002],[pos[0],pos[1]+h*.25-i*h*.15,pos[2]+.013],M.teal(),.003);}
export function makeDetailedStation(){
  const root=new T.Group();root.name='GreenFlight_S2_shared_solar_station';root.userData={units:'metres',concept:true,version:'2.0',pv_area_m2:3,chargers:2,storage_capacity_Wh:1000};
  const cabinet=part(root,'cabinet'),roof=part(root,'roof'),pads=part(root,'pads'),storage=part(root,'storage'),controller=part(root,'controller');
  box(cabinet,'Foundation_plinth',[3.5,.12,3.65],[0,.06,.22],mat('Architectural_concrete',0xb7bdb4,.1,.87),.035);
  box(cabinet,'Folded_aluminium_cabinet',[1.87,1.55,.62],[0,.91,-.83],M.white(),.045).userData.shell=true;
  box(cabinet,'Green_service_header',[1.9,.21,.65],[0,1.785,-.83],M.green(),.035);
  for(let i=0;i<4;i++){const x=-.675+i*.45;box(cabinet,['Powerbank_door','Umbrella_door','Water_door','Firstaid_door'][i],[.425,1.16,.028],[x,.92,-.501],i%2?M.white():M.teal(),.014).userData.shell=true;box(cabinet,'Recessed_handle',[.032,.18,.012],[x+.145,1,-.48],M.carbon(),.009);cyl(cabinet,'Door_lock',.012,.01,[x+.145,.82,-.473],M.metal()).rotation.x=Math.PI/2;
    for(const h of [.48,1.37])box(cabinet,'Stainless_hinge',[.018,.07,.025],[x-.188,h,-.477],M.metal(),.003);
    for(const y of [.46,.76,1.06,1.36])box(cabinet,'Internal_shelf',[.38,.012,.46],[x,y,-.8],M.metal(),.002);
    for(let j=0;j<3;j++){const yy=.50+j*.3;if(i===0)for(const k of [-.09,.09])box(cabinet,'Shared_powerbank',[.065,.12,.022],[x+k,yy+.06,-.69],M.white(),.007);if(i===1)for(const k of [-.09,0,.09])cyl(cabinet,'Folded_shared_umbrella',.025,.23,[x+k,yy+.115,-.7],M.green());if(i===2)for(const k of [-.09,0,.09]){cyl(cabinet,'Bottle_body',.032,.18,[x+k,yy+.09,-.7],mat('Bottle_pale_blue',0xb5d8db,.15,.2));cyl(cabinet,'Bottle_cap',.018,.025,[x+k,yy+.19,-.7],M.teal());}if(i===3)box(cabinet,'Firstaid_pack',[.22,.13,.11],[x,yy+.065,-.74],M.white(),.01);}
  }
  screen(cabinet,.29,.13,[0,1.79,-.496]);
  for(const x of [-.96,.96])for(const z of [-1.41,-.08]){
    box(roof,'Aluminium_column',[.055,2.1,.055],[x,1.19,z],M.green(),.006);box(roof,'Column_base_plate',[.12,.018,.12],[x,.14,z],M.metal(),.005);for(const dx of [-.04,.04])for(const dz of [-.04,.04])screw(roof,x+dx,.152,z+dz,.007);
  }
  box(roof,'Canopy_crossbeam',[2.10,.06,.06],[0,2.23,-.75],M.green(),.008);photovoltaic(roof,2,1.5,2.29,-.75);
  box(roof,'Rainwater_gutter',[2.05,.04,.06],[0,2.26,.035],M.metal(),.008);
  cable(roof,'Roof_PV_DC_harness',[[.4,2.28,-1.4],[.94,2.24,-1.4],[.94,.45,-1.4],[1.2,.4,-1.1]],.012,0x3b4c50);
  for(const x of [-.9,.9]){
    const g=group(pads,'Precision_docking_platform');g.position.set(x,0,1.1);
    box(g,'Charging_pad_base',[1.46,.12,1.47],[0,.22,0],M.green(),.045);box(g,'Replaceable_landing_surface',[1.34,.012,1.34],[0,.287,0],M.carbon(),.035);
    ring(g,'Landing_guidance_ring',.49,.012,[0,.303,0],M.lime());
    for(const dx of [-.13,.13])box(g,'Landing_H_marker',[.055,.004,.39],[dx,.303,0],M.white(),.003);box(g,'Landing_H_crossbar',[.29,.004,.055],[0,.303,0],M.white(),.003);
    for(const dx of [-.22,.22]){box(g,'Conductive_charge_rail',[.045,.012,.51],[dx,.311,0],M.gold(),.008);for(const zz of [-.18,.18])cyl(g,'Spring_loaded_contact',.012,.014,[dx,.323,zz],M.gold());}
    for(const dx of [-.57,.57])for(const dz of [-.57,.57]){screw(g,dx,.302,dz,.009);box(g,'Pad_alignment_LED',[.065,.008,.065],[dx,.305,dz],M.teal(),.015);}
  }
  box(storage,'Energy_edge_cabinet',[.52,1.05,.67],[1.22,.66,-.83],M.green(),.035).userData.shell=true;
  box(storage,'Power_module_backplate',[.46,.93,.015],[1.22,.65,-1.15],M.metal(),.005);
  for(let i=0;i<4;i++)box(storage,'Storage_module_concept',[.35,.13,.32],[1.22,.34+i*.16,-.84],M.black(),.014);
  finnedBox(controller,'Station_MPPT_heatsink',[.15,.06,.18],[1.22,.99,-.84]);
  board(controller,'Edge_gateway_board',.18,.14,[1.22,.88,-.76]);
  for(let i=0;i<10;i++)box(storage,'Cabinet_vent',[.26,.009,.013],[1.22,.4+i*.032,-.487],M.black(),.003);
  screen(storage,.22,.1,[1.22,1.05,-.486]);
  for(const x of [.99,1.45])for(const y of [.22,1.1]){const s=cyl(storage,'Access_panel_screw',.007,.004,[x,y,-.48],M.metal(),.007,6);s.rotation.x=Math.PI/2;}
  cable(controller,'Charge_rail_bus_A',[[1.22,.24,-.65],[1.15,.16,.2],[-.9,.16,1.1]],.012,0xb68350);
  cable(controller,'Charge_rail_bus_B',[[1.22,.28,-.65],[1.35,.16,.2],[.9,.16,1.1]],.012,0x426479);
  return root;
}

export function setCutaway(root,enabled){root.traverse(o=>{if(!o.isMesh||!o.userData.shell)return;if(!o.userData.originalMaterial)o.userData.originalMaterial=o.material;if(enabled){if(!o.userData.cutawayMaterial){const m=o.userData.originalMaterial.clone();m.transparent=true;m.opacity=.12;m.depthWrite=false;m.side=T.DoubleSide;o.userData.cutawayMaterial=m;}o.material=o.userData.cutawayMaterial;}else o.material=o.userData.originalMaterial;});}
