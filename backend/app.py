import asyncio
from contextlib import asynccontextmanager
import csv
import io
import json
import math
import random
import secrets
import time
from typing import Literal
from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from backend import store
from backend.planner import PRODUCTS, dispatch, inside
from backend.simulation import advance, apply_dispatch, event, metrics
from backend.energy import charging_plan
from backend.pickup import PICKUP_POINTS, list_pickup_points

@asynccontextmanager
async def lifespan(app):
    store.init_db()
    async def ticker():
        while True:
            await asyncio.sleep(1)
            try:
                def step():
                    if not store.read_state()['running']: return
                    with store.transaction() as s: advance(s, s['speed']/60)
                await asyncio.to_thread(step)
            except Exception as exc:
                with store.transaction() as s:
                    s['running'] = False
                    store.log(s, f'仿真暂停：{type(exc).__name__}', 'error')
    task = asyncio.create_task(ticker())
    yield
    task.cancel()

app = FastAPI(title='绿航智递 API', version='1.0.0', lifespan=lifespan,
              description='本地科研仿真平台。支付、地理、气象、飞行均为模拟。API 的硬件接入不下发飞控指令。')

@app.middleware('http')
async def headers(request, call_next):
    origin = request.headers.get('origin')
    if request.method not in ('GET', 'HEAD', 'OPTIONS') and origin:
        from urllib.parse import urlsplit
        if urlsplit(origin).netloc != request.headers.get('host'):
            return Response('Cross-origin mutation denied', status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['Cache-Control'] = 'no-store' if request.url.path.startswith('/api/') else 'no-cache'
    return response

def user(request: Request):
    token = request.cookies.get('gf_session', '')
    with store.connect() as db:
        row = db.execute('SELECT u.username,u.role FROM sessions s JOIN users u ON s.username=u.username WHERE s.token=? AND s.expires>?', (token, time.time())).fetchone()
    if not row: raise HTTPException(401, '请先登录')
    return dict(row)

def admin(u=Depends(user)):
    if u['role'] != 'admin': raise HTTPException(403, '需要管理员权限')
    return u

class Login(BaseModel):
    username: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=128)

attempts = {}
@app.post('/api/login')
def login(body: Login, response: Response, request: Request):
    key = request.client.host if request.client else 'local'
    now = time.time(); attempts[key] = [t for t in attempts.get(key, []) if now-t < 60]
    if len(attempts[key]) >= 12: raise HTTPException(429, '尝试过于频繁，请一分钟后再试')
    with store.connect() as db:
        row = db.execute('SELECT * FROM users WHERE username=?', (body.username,)).fetchone()
        if not row or not secrets.compare_digest(row['hash'], store.password_hash(body.password, row['salt'])):
            attempts[key].append(now); raise HTTPException(401, '账号或密码错误')
        token = secrets.token_urlsafe(32)
        db.execute('DELETE FROM sessions WHERE expires<?', (now,))
        db.execute('INSERT INTO sessions VALUES (?,?,?)', (token, row['username'], now+43200))
    response.set_cookie('gf_session', token, httponly=True, samesite='strict', max_age=43200)
    return {'username': row['username'], 'role': row['role']}

@app.post('/api/logout')
def logout(request: Request, response: Response):
    with store.connect() as db: db.execute('DELETE FROM sessions WHERE token=?', (request.cookies.get('gf_session', ''),))
    response.delete_cookie('gf_session'); return {'ok': True}

@app.get('/api/me')
def me(u=Depends(user)): return u

@app.get('/api/health')
def health(): return {'status': 'ok', 'mode': 'research', 'product':'sky-commons', 'version': '2.0.0'}

@app.get('/api/state')
def state(u=Depends(user)):
    s = store.read_state()
    if u['role'] != 'admin':
        s['orders'] = [o for o in s['orders'] if o['user_id'] == u['username']]
        owned = {o['id'] for o in s['orders']}
        s['flights'] = [{**f, 'orders': [i for i in f['orders'] if i in owned],
                        'legs': [{**leg, 'order_id': leg['order_id'] if leg['order_id'] in owned else None} for leg in f['legs']]}
                       for f in s['flights'] if owned.intersection(f['orders'])]
        s['dispatches'] = []; s['logs'] = []; s['experiments'] = []
        # Planning candidates contain other stations' operational details.
        s['flight_tasks'] = []
    return {**s, 'metrics': metrics(s), 'products': PRODUCTS, 'user': u,
            'pickup_points': list_pickup_points(s['zones'])}

@app.get('/api/pickup-points')
def pickup_points(u=Depends(user)):
    return list_pickup_points(store.read_state()['zones'])

class OrderInput(BaseModel):
    product: Literal['powerbank', 'umbrella', 'water', 'firstaid']
    quantity: int = Field(default=1, ge=1, le=3)
    pickup_point_id: str | None = Field(default=None, min_length=1, max_length=20)
    x: float | None = Field(default=None, ge=20, le=980, allow_inf_nan=False)
    y: float | None = Field(default=None, ge=20, le=680, allow_inf_nan=False)
    address: str | None = Field(default=None, min_length=2, max_length=100)
    priority: int = Field(default=1, ge=1, le=3)
    deadline_minutes: int = Field(default=6, ge=3, le=30)

@app.post('/api/orders')
def create_order(body: OrderInput, u=Depends(user)):
    data = body.model_dump(exclude={'deadline_minutes'})
    if body.pickup_point_id is not None:
        point = next((p for p in PICKUP_POINTS if p['id'] == body.pickup_point_id), None)
        if point is None: raise HTTPException(422, '取件点不存在，请重新选择')
        data.update(x=point['x'], y=point['y'], address=point['name'])
    elif body.x is None or body.y is None or not body.address or len(body.address.strip()) < 2:
        raise HTTPException(422, '请选择公共取件点，或在地图上选择位置')
    else:
        data['address'] = body.address.strip()
    with store.transaction() as s:
        if any(inside((data['x'], data['y']), z) for z in s['zones']): raise HTTPException(422, '取件点位于禁飞区，请选择其他位置')
        if sum(o['status'] in ('pending', 'flying') for o in s['orders']) >= 100: raise HTTPException(409, '待处理订单过多，请先完成配送')
        oid = f"LH-{s['next_order']}"; s['next_order'] += 1
        o = {**data, 'id': oid, 'user_id': u['username'],
             'created': s['clock'], 'deadline': s['clock']+body.deadline_minutes, 'status': 'pending',
             'kind': 'delivery', 'payment': 'simulated_paid', 'amount': PRODUCTS[body.product]['price']*body.quantity+1.5,
             'station_id': None, 'drone_id': None, 'delivered_at': None, 'returned_at': None, 'source': 'user', 'events': []}
        event(s, o, '模拟支付完成，订单进入调度队列'); s['orders'].insert(0, o)
        store.log(s, f'{oid} 新订单 · {PRODUCTS[body.product]["name"]}', 'order')
        if s['settings']['auto_dispatch']: apply_dispatch(s)
    return o

def find_order(s, oid, u):
    o = next((o for o in s['orders'] if o['id'] == oid), None)
    if o is None: raise HTTPException(404, '订单不存在')
    if u['role'] != 'admin' and o['user_id'] != u['username']: raise HTTPException(403, '无权操作此订单')
    return o

@app.post('/api/orders/{oid}/cancel')
def cancel(oid: str, u=Depends(user)):
    with store.transaction() as s:
        o = find_order(s, oid, u)
        if o['status'] != 'pending' or o['kind'] == 'return': raise HTTPException(409, '仅待调度的配送订单可以取消')
        o['status'] = 'cancelled'; o['payment'] = 'simulated_refunded'; event(s, o, '已取消，模拟退款完成')
    return {'ok': True}

@app.post('/api/orders/{oid}/return')
def return_order(oid: str, u=Depends(user)):
    with store.transaction() as s:
        o = find_order(s, oid, u)
        if o['status'] != 'delivered' or o['kind'] != 'delivery' or not PRODUCTS[o['product']]['rental']:
            raise HTTPException(409, '只有已送达的共享物品可以申请归还')
        rid = f"LH-{s['next_order']}"; s['next_order'] += 1
        ret = {**o, 'id': rid, 'original_id': oid, 'kind': 'return', 'status': 'pending',
               'created': s['clock'], 'deadline': s['clock']+15, 'delivered_at': None, 'returned_at': None,
               'drone_id': None, 'flight_task_id': None, 'amount': 0, 'events': [], 'payment': 'not_required'}
        o['status'] = 'return_requested'; event(s, o, f'已申请无人机上门回收 · {rid}')
        event(s, ret, '回收任务已创建'); s['orders'].insert(0, ret)
        if s['settings']['auto_dispatch']: apply_dispatch(s)
    return ret

class DispatchInput(BaseModel):
    method: Literal['vns', 'greedy', 'dqn', 'aco'] = 'vns'

@app.post('/api/dispatch')
def schedule(body: DispatchInput, u=Depends(admin)):
    with store.transaction() as s: result = apply_dispatch(s, body.method)
    return result

class Control(BaseModel):
    action: Literal['start', 'pause', 'advance', 'cloud', 'auto']
    value: bool = True
    minutes: float = Field(default=1, ge=.1, le=30, allow_inf_nan=False)
    speed: int = Field(default=6, ge=1, le=30)

@app.post('/api/simulation')
def control(body: Control, u=Depends(admin)):
    with store.transaction() as s:
        if body.action == 'start': s['running'] = True; s['speed'] = body.speed
        if body.action == 'pause': s['running'] = False
        if body.action == 'advance':
            left = body.minutes
            while left > 1e-8:
                step = min(left, 1.); advance(s, step); left -= step
        if body.action == 'cloud':
            s['cloud_online'] = body.value; store.log(s, '云连接恢复' if body.value else '模拟云断连，启用本地站点调度', 'network')
        if body.action == 'auto': s['settings']['auto_dispatch'] = body.value
    return {'ok': True}

class WeatherInput(BaseModel):
    label: str = Field(default='自定义天气', max_length=20)
    irradiance: float = Field(ge=0, le=1200, allow_inf_nan=False)
    wind: float = Field(ge=0, le=25, allow_inf_nan=False)
    rain: float = Field(ge=0, le=50, allow_inf_nan=False)
    temperature: float = Field(default=23, ge=-20, le=50, allow_inf_nan=False)

@app.post('/api/weather')
def weather(body: WeatherInput, u=Depends(admin)):
    with store.transaction() as s:
        if any(not f['done'] for f in s['flights']) or any(t['phase'] not in ('COMPLETED','CANCELLED','RECOVERED') for t in s.get('flight_tasks',[])): raise HTTPException(409, '请等待当前航班返站后切换天气；本版本不模拟空中突变飞控')
        s['weather'] = body.model_dump(); store.log(s, f'天气切换：{body.label}，后续任务使用新能耗参数', 'weather')
        if s['settings']['auto_dispatch']: apply_dispatch(s)
    return {'ok': True}

class StationInput(BaseModel):
    online: bool | None = None
    product: Literal['powerbank', 'umbrella', 'water', 'firstaid'] | None = None
    add_stock: int = Field(default=0, ge=0, le=100)

@app.patch('/api/stations/{sid}')
def update_station(sid: str, body: StationInput, u=Depends(admin)):
    with store.transaction() as s:
        st = next((x for x in s['stations'] if x['id'] == sid), None)
        if not st: raise HTTPException(404, '站点不存在')
        if body.online is False and (any(not f['done'] and f['station_id'] == sid for f in s['flights']) or any(t['station_id'] == sid and t['phase'] not in ('COMPLETED','CANCELLED','RECOVERED') for t in s.get('flight_tasks', []))): raise HTTPException(409, '有任务预占或航班待返站，不能停用')
        if body.online is not None: st['online'] = body.online
        if body.product: st['inventory'][body.product] += body.add_stock
        store.log(s, f"{st['name']} 配置已更新", 'station')
    return st

class DroneInput(BaseModel):
    status: Literal['idle', 'maintenance']

@app.patch('/api/drones/{did}')
def update_drone(did: str, body: DroneInput, u=Depends(admin)):
    with store.transaction() as s:
        d = next((x for x in s['drones'] if x['id'] == did), None)
        if not d: raise HTTPException(404, '无人机不存在')
        if d['status'] in ('flying','flight_active','flight_reserved','recovery_required'): raise HTTPException(409, '任务占用或待核对的飞机不能切换维护状态，请先处理飞行任务')
        d['status'] = body.status; store.log(s, f'{did} 状态变更为 {body.status}', 'device')
    return d

class ZoneInput(BaseModel):
    name: str = Field(min_length=2, max_length=40)
    x: float = Field(ge=5, le=900, allow_inf_nan=False)
    y: float = Field(ge=5, le=600, allow_inf_nan=False)
    w: float = Field(ge=10, le=200, allow_inf_nan=False)
    h: float = Field(ge=10, le=200, allow_inf_nan=False)

@app.post('/api/zones')
def add_zone(body: ZoneInput, u=Depends(admin)):
    with store.transaction() as s:
        if len(s['zones']) >= 10: raise HTTPException(409, '最多 10 个禁飞区域')
        if any(not f['done'] for f in s['flights']) or any(t['phase'] not in ('COMPLETED','CANCELLED','RECOVERED') for t in s.get('flight_tasks',[])): raise HTTPException(409, '请等待所有航班返站后编辑禁飞区')
        z = body.model_dump()
        if z['x']+z['w']>995 or z['y']+z['h']>695: raise HTTPException(422, '区域超出地图')
        if any(inside((p['x'],p['y']), z) for p in s['stations']+s['orders'] if p.get('status') not in ('cancelled', 'returned', 'completed')):
            raise HTTPException(409, '区域覆盖站点或订单取件点')
        z['id'] = 'Z'+secrets.token_hex(3); s['zones'].append(z); store.log(s, f'新增禁飞区：{z["name"]}', 'map')
    return z

@app.delete('/api/zones/{zid}')
def delete_zone(zid: str, u=Depends(admin)):
    with store.transaction() as s:
        if any(not f['done'] for f in s['flights']) or any(t['phase'] not in ('COMPLETED','CANCELLED','RECOVERED') for t in s.get('flight_tasks',[])): raise HTTPException(409, '请等待所有航班返站')
        s['zones'] = [z for z in s['zones'] if z['id'] != zid]
    return {'ok': True}

@app.get('/api/energy')
def energy(u=Depends(admin)): return charging_plan(store.read_state())

class ScenarioInput(BaseModel):
    count: int = Field(default=8, ge=1, le=24)
    seed: int = Field(default=42, ge=0, le=99999)

def generate(s, count, seed):
    rng = random.Random(seed)
    for i in range(count):
        for _ in range(100):
            x, y = rng.randint(40, 960), rng.randint(40, 660)
            if not any(inside((x,y), z) for z in s['zones']): break
        product = rng.choice(list(PRODUCTS))
        oid = f"LH-{s['next_order']}"; s['next_order'] += 1
        s['orders'].insert(0, {'id': oid, 'user_id': 'resident', 'product': product, 'quantity': 1,
                             'x': x, 'y': y, 'address': f'仿真取件点 {x},{y}', 'priority': rng.choice([1,1,2,3]),
                             'created': s['clock'], 'deadline': s['clock']+8, 'status': 'pending', 'kind': 'delivery',
                             'payment': 'simulated_paid', 'amount': PRODUCTS[product]['price']+1.5,
                             'station_id': None, 'drone_id': None, 'delivered_at': None, 'returned_at': None,
                             'source': 'generated', 'events': [{'at': s['clock'], 'text': f'随机种子 {seed} 生成的仿真订单'}]})

@app.post('/api/scenarios')
def scenario(body: ScenarioInput, u=Depends(admin)):
    with store.transaction() as s:
        if sum(o['status'] == 'pending' for o in s['orders']) + body.count > 100: raise HTTPException(409, '待调度订单已达上限')
        generate(s, body.count, body.seed); store.log(s, f'生成 {body.count} 笔仿真订单 · seed={body.seed}', 'scenario')
    return {'ok': True}

@app.post('/api/experiments')
def experiment(body: ScenarioInput, u=Depends(admin)):
    from copy import deepcopy
    base = store.seed_state(); base['orders'] = []; generate(base, body.count, body.seed)
    rows = []
    for method in ('greedy', 'vns', 'dqn'):
        result = dispatch(deepcopy(base), method, seed=body.seed)
        arrivals = [a for r in result['routes'] for a in r['arrivals'].values()]
        rows.append({'method': method, 'assigned': len(arrivals), 'total': body.count,
                     'distance_m': round(sum(r['distance_m'] for r in result['routes']), 2),
                     'energy_wh': round(sum(r['energy_wh'] for r in result['routes']), 2),
                     'avg_minutes': round(sum(arrivals)/len(arrivals), 3) if arrivals else None,
                     'elapsed_ms': result['elapsed_ms'], 'score': result['score'], 'history': result['history']})
    report = {'seed': body.seed, 'count': body.count, 'results': rows, 'source': '独立合成场景，同数据、同约束、未修改运营订单', 'created': time.time()}
    with store.transaction() as s:
        s['experiments'].insert(0, report); s['experiments'] = s['experiments'][:20]
    return report

@app.get('/api/learning')
def learning(u=Depends(admin)):
    from backend.learning import model_info
    info = model_info()
    forecast_report = store.ROOT/'data'/'forecast-training.json'
    if forecast_report.exists(): info['forecast'] = json.loads(forecast_report.read_text(encoding='utf-8'))
    return info

class RegisterInput(BaseModel):
    username: str = Field(min_length=3, max_length=30, pattern=r'^[a-zA-Z0-9_]+$')
    password: str = Field(min_length=10, max_length=128)

@app.post('/api/register')
def register(body: RegisterInput):
    with store.LOCK, store.connect() as db:
        if db.execute('SELECT 1 FROM users WHERE username=?', (body.username,)).fetchone():
            raise HTTPException(409, '账号已存在')
        if db.execute('SELECT count(*) FROM users').fetchone()[0] >= 100:
            raise HTTPException(409, '本地演示账号数量已达上限')
        salt = secrets.token_hex(16)
        db.execute('INSERT INTO users VALUES (?,?,?,?)', (body.username, salt, store.password_hash(body.password, salt), 'resident'))
    return {'username': body.username, 'role': 'resident'}

@app.get('/api/export/orders')
def export(u=Depends(admin)):
    s = store.read_state(); output = io.StringIO(newline='')
    fields = ['id','product','quantity','address','status','kind','created','deadline','delivered_at','drone_id','station_id','amount','source']
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction='ignore'); writer.writeheader()
    for o in s['orders']:
        row = dict(o)
        for key in fields:
            if isinstance(row.get(key), str) and row[key].startswith(('=', '+', '-', '@')): row[key] = "'"+row[key]
        writer.writerow(row)
    return Response('\ufeff'+output.getvalue(), media_type='text/csv; charset=utf-8', headers={'Content-Disposition': 'attachment; filename="greenflight-orders.csv"'})

@app.get('/api/export/experiments')
def export_experiments(u=Depends(admin)):
    return Response(json.dumps(store.read_state()['experiments'], ensure_ascii=False, indent=2), media_type='application/json', headers={'Content-Disposition': 'attachment; filename="greenflight-experiments.json"'})

class ResetInput(BaseModel):
    confirmation: Literal['RESET_DEMO']

@app.post('/api/reset')
def reset(body: ResetInput, u=Depends(admin)):
    with store.transaction() as s:
        if any(t['phase'] not in ('COMPLETED','CANCELLED','RECOVERED') for t in s.get('flight_tasks',[])):
            raise HTTPException(409,'有关联飞行任务未结束，禁止重置订单与库存')
        backup = store.ROOT/'data'/f'backup-{int(time.time())}.json'
        backup.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding='utf-8')
        s.clear(); s.update(store.seed_state())
    return {'ok': True, 'backup': backup.name}

@app.get('/')
def index(): return FileResponse(store.ROOT/'frontend'/'sky.html')

app.mount('/assets', StaticFiles(directory=store.ROOT/'frontend'), name='assets')
