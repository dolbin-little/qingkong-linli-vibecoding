"""Fixed seeds, paired inputs, retained failures. Offline synthetic evaluation, not hardware proof."""
from pathlib import Path
import sys,time,json,math,hashlib,random,tempfile,html,platform,subprocess,statistics
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from autonomy.engine import FlightEngine
from autonomy.models import scene,Telemetry,norm,distance
from autonomy.simulator import Plant
from autonomy.planning import astar,safe_segment,energy_budget

SEEDS=[17,42,89]
DT=.05

class BenchAdapter:
    def __init__(self,plant,seed,fault=None):
        self.plant=plant;self.rng=random.Random(seed);self.fault=fault;self.clock=1000
        self.t=Telemetry(gps_fix=3,satellites=12,mode='GUIDED');self.acks=[];self.pending={};self.received=0;self.sent=0;self.payload_feedback={};self.detection=None
    def poll(self,now):
        self.clock=now;self.plant.step(DT);p=self.plant;fault=self.fault if p.age>=12 else None
        if fault=='link':return self.t
        for k in ('heartbeat_at','position_at','battery_at','gps_at'):setattr(self.t,k,now)
        self.t.gps_fix=1 if fault=='gps' else 3
        self.t.position=p.p[:];self.t.velocity=p.v[:];self.t.armed=p.armed
        self.t.mode='LAND' if p.mode==9 else 'GUIDED';self.t.battery=22 if fault=='battery' else p.battery
        if fault!='sensor':self.t.sensor_at=now;self.t.nearest=p.nearest()
        ob=p.obstacle()
        if ob and fault!='sensor':self.detection={**ob,'position':[v+self.rng.gauss(0,.12) for v in ob['position']],'at':now}
        else:self.detection=None
        self.payload_feedback={'released':p.payload_released,'at':now};self.received+=1
        return self.t
    def velocity(self,v):self.plant.target=list(v);self.plant.last_command=self.plant.age;self.sent+=1
    def land(self):self.plant.mode=9;self.plant.last_command=self.plant.age;self.sent+=1
    def arm(self):self.plant.armed=True;self.plant.last_command=self.plant.age;self.sent+=1
    def guided(self):self.plant.mode=4
    def release_payload(self):self.acks.append({'command':31002,'accepted':self.plant.release_payload(),'at':self.clock})

def segment_error(p,a,b):
    v=[y-x for x,y in zip(a,b)];w=[y-x for x,y in zip(a,p)];den=sum(x*x for x in v)
    u=max(0,min(1,sum(x*y for x,y in zip(v,w))/den)) if den else 0
    return distance(p,[x+u*y for x,y in zip(a,v)])

def experiment(name,seed,tracking=True,fault=None):
    s=scene(name,seed);s['clearance']=4.;s['goal'][2]=0;s['cruise_altitude']=12
    plant=Plant(s);adapter=BenchAdapter(plant,seed,fault)
    raw=astar(s['home'],s['goal'],s,simplify=False);route=astar(s['home'],s['goal'],s)
    with tempfile.TemporaryDirectory(prefix='bench-',dir=ROOT/'reports') as tmp:
        e=FlightEngine(tmp);e.s=s;e.adapter=adapter;e.tracking_enabled=tracking;e.route=route;e.index=1;e.started=1;e.phase='EXECUTING'
        plant.armed=True;errors=[];clearances=[];durations=[]
        for i in range(4800):
            start=time.perf_counter();e.tick(1000+i*DT);durations.append((time.perf_counter()-start)*1000)
            if len(e.route)>1:errors.append(min(segment_error(plant.p,a,b) for a,b in zip(e.route,e.route[1:])))
            if plant.armed and plant.p[2]>.5:clearances.append(plant.nearest())
            if e.phase in ('COMPLETED','STOPPED'):break
            if e.phase=='LINK_LOST' and plant.age>22:break
        expected='LINK_LOST' if fault=='link' else 'STOPPED' if fault else 'COMPLETED'
        return {'scenario':name,'seed':seed,'tracking':tracking,'fault_injected':fault,'phase':e.phase,'fault':e.fault,
                'expected_phase':expected,'expectation_met':e.phase==expected and not plant.collision,
                'completed':e.phase=='COMPLETED','collision':plant.collision,'delivery_confirmed':e.delivered,
                'elapsed_sim_s':round(plant.age,2),'distance_m':round(plant.distance,3),'plant_energy_wh':round(plant.energy_wh,4),
                'cross_track_rmse_m':round(math.sqrt(sum(x*x for x in errors)/len(errors)),4),
                'min_truth_clearance_m':round(min(clearances),3) if clearances else None,
                'interventions':e.stats['guard_interventions'],'replans':e.stats['replans'],
                'tick_compute_p95_ms':round(sorted(durations)[int(.95*(len(durations)-1))],3),
                'route_raw_m':energy_budget(raw)['distance_m'],'route_simplified_m':energy_budget(route)['distance_m'],
                'raw_points':len(raw),'simplified_points':len(route),
                'route_verified':all(safe_segment(a,b,s) for a,b in zip(route,route[1:])),
                'scene':s,'route':route,'raw_route':raw,'trace':e.trace,'events':list(reversed(e.events))}

def svg_route(row):
    def points(route):return ' '.join(f'{p[0]*4+20:.1f},{340-p[1]*4:.1f}' for p in route)
    circles=''.join(f'<circle cx="{o["x"]*4+20}" cy="{340-o["y"]*4}" r="{o["r"]*4}" fill="#d9e3da"/><text x="{o["x"]*4+10}" y="{340-o["y"]*4}" font-size="12">{o["id"]}</text>' for o in row['scene']['obstacles'])
    return f'<svg viewBox="0 0 440 370" role="img" aria-label="航线与轨迹叠加">{circles}<polyline points="{points(row["raw_route"])}" fill="none" stroke="#ba9b68" stroke-width="2" stroke-dasharray="4 4"/><polyline points="{points(row["route"])}" fill="none" stroke="#7787b5" stroke-width="2"/><polyline points="{points([x["p"] for x in row["trace"]])}" fill="none" stroke="#207c6b" stroke-width="2"/></svg>'

def chart(rows,key,label,unit):
    maxv=max([r[key] or 0 for r in rows]+[.001]);items=[]
    for i,r in enumerate(rows):
        y=30+i*25;v=r[key] or 0;color='#277c6a' if r['tracking'] else '#bd9a61'
        items.append(f'<text x="0" y="{y+12}" font-size="11">{r["scenario"]}/{r["seed"]}/{"跟踪" if r["tracking"] else "基线"}</text><rect x="170" y="{y}" width="{v/maxv*220:.1f}" height="14" fill="{color}"/><text x="{180+v/maxv*220:.1f}" y="{y+12}" font-size="11">{v}</text>')
    return f'<h3>{label}（{unit}）</h3><svg viewBox="0 0 470 {len(rows)*25+45}" role="img" aria-label="{label}">{"".join(items)}</svg>'

def render(report):
    rows=report['results'];normal=[r for r in rows if not r['fault_injected']];fails=[r for r in rows if not r['expectation_met']]
    official=ROOT/'reports/official-sitl-acceptance.json'
    sitl=json.loads(official.read_text(encoding='utf8')) if official.exists() else None
    status=('通过' if sitl['passed'] else '未通过') if sitl else '尚未运行'
    sitl_lines=''.join(f'<li>{html.escape(c["name"])}：{"通过" if c["passed"] else "未通过"}</li>' for c in (sitl or {}).get('checks',[]))
    cases=''.join(f'<article><h3>{r["scenario"]} / seed {r["seed"]} / {"启用跟踪" if r["tracking"] else "关闭跟踪"}</h3>{svg_route(r)}<p>{r["phase"]} · {r["fault"] or "无保护触发"} · 耗时 {r["elapsed_sim_s"]}s</p></article>' for r in rows if r['seed']==42)
    notes=''.join(f'<p>{r["scenario"]}/{r["seed"]}/{r["tracking"]}：{r["phase"]}，{r["fault"] or "超时或未满足预期"}，碰撞={r["collision"]}</p>' for r in fails) or '<p>全部测试达到预先定义的预期。</p>'
    body=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>晴空邻里 · 可复现验证</title><style>
    body{{margin:0;background:#f4f5ef;color:#203e36;font:16px 'Microsoft YaHei',sans-serif}}main{{max-width:1260px;margin:auto;padding:42px}}h1{{font-size:36px}}.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:22px}}article,section{{background:white;padding:24px;margin:18px 0;border-radius:12px}}svg{{width:100%;max-height:620px}}.muted{{color:#66786d;line-height:1.8}}summary{{cursor:pointer}}pre{{white-space:pre-wrap;word-break:break-all}}@media(max-width:800px){{.grid{{grid-template-columns:1fr}}}}</style><main>
    <p>晴空邻里 / 固定场景测试 / {report['created']}</p><h1>让每一次改进都有可复验的依据</h1>
    <p class="muted">{len(rows)} 次离线合成闭环 · {sum(r['completed'] for r in normal)}/{len(normal)} 正常场景完成 · {sum(r['collision'] for r in rows)} 次模型碰撞 · {len(fails)} 个未达预期案例。所有结果保留，不删除失败场景。</p>
    <section><h2>官方 ArduCopter SITL：{status}</h2><p>使用本项目 MAVLink 适配器与速度外环驱动官方飞控软件。与下方自建动力学模型评测分开计数。</p><details><summary>展开验收项目</summary><ul>{sitl_lines}</ul><p>{html.escape((sitl or {}).get('error',''))}</p></details><p class="muted">未验证实物卸货、真实传感器、硬件急停及实机飞行。官方仿真中的地面停留不代表货物投放成功。</p></section>
    <section><h2>相同种子下比较，保留完整失败原因</h2><p>种子 {SEEDS}；控制步长0.05秒；单次最多240模拟秒。绿色启用α–β跟踪，金色关闭跟踪，其他参数相同。保护落地与正常完成分开统计。</p></section>
    <div class="grid"><article>{chart(normal,'distance_m','实际轨迹长度','m')}</article><article>{chart(normal,'cross_track_rmse_m','到当前规划航线的距离均方根','m')}</article></div>
    <section><h2>网格航线简化</h2><p>同一场景起终点与净空约束。原始网格长度 {rows[0]['route_raw_m']}m → 简化后 {rows[0]['route_simplified_m']}m；航点 {rows[0]['raw_points']} → {rows[0]['simplified_points']}。两条路线均复核，数据来自当前固定场景，不能代表所有地图。</p></section>
    <h2>轨迹叠加与故障案例</h2><p>金色虚线：原始网格；蓝线：简化航线；绿线：实际模拟轨迹。圆形为建筑俯视，模型保留高度。</p><div class="grid">{cases}</div>
    <section><h2>未达预期的案例</h2>{notes}</section>
    <section><h2>复现条件与证据边界</h2><p class="muted">离线评测使用简化速度滞后、风扰和电池模型；能耗未实测标定。计算P95是本机离线计算耗时，并非真实飞行控制周期。轨迹误差相对当前规划路径计算。当前数据属于固定合成回归集，不是独立实地验证集，不用于声称临床、工业或航空安全认证。</p><details><summary>代码与参数指纹</summary><pre>{html.escape(json.dumps(report['provenance'],ensure_ascii=False,indent=2))}</pre></details></section></main></html>'''
    (ROOT/'reports/evaluation.html').write_text(body,encoding='utf8')

def run():
    (ROOT/'reports').mkdir(exist_ok=True)
    rows=[]
    for name in ('neighborhood','wind','crossing'):
        for seed in SEEDS:
            for tracking in (False,True):
                row=experiment(name,seed,tracking);rows.append(row)
                print(name,seed,tracking,row['phase'],row['fault'],flush=True)
    for fault in ('sensor','gps','link','battery'):
        row=experiment('neighborhood',42,True,fault);rows.append(row);print('fault',fault,row['phase'],row['fault'],flush=True)
    sources=['autonomy/engine.py','autonomy/planning.py','autonomy/safety.py','autonomy/safety_status.py','autonomy/simulator.py','autonomy/perception.py','tools/benchmark.py']
    provenance={'python':platform.python_version(),'seeds':SEEDS,'dt_s':DT,'max_steps':4800,'generated_at':time.strftime('%Y-%m-%d %H:%M:%S'),
                'git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                'source_sha256':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in sources}}
    report={'suite':'fixed-synthetic-benchmark-v1','created':provenance['generated_at'],'provenance':provenance,'results':rows}
    (ROOT/'reports/fixed-benchmark.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');render(report)
    print('REPORT',ROOT/'reports/evaluation.html',flush=True)

if __name__=='__main__':run()
