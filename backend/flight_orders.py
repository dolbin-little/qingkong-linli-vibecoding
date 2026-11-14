"""Durable business ledger for the single independent simulated aircraft.

The flight worker owns reconciliation, so closing the browser/web server cannot
stop order updates. SQLite BEGIN IMMEDIATE serializes it with legacy dispatch.
Inventory means AVAILABLE stock: reserve once, consume on release feedback,
restore only on preflight cancellation or explicit recovery confirmation.
"""
import copy
import math
import time
from backend import store
from backend.planner import PRODUCTS, inside
from autonomy.models import scene
from autonomy.planning import astar, energy_budget

LANDING_POINTS = {'P01': [24., 16., 0.], 'P02': [52., 15., 0.],
                  'P03': [87., 32., 0.], 'P04': [38., 68., 0.],
                  'P05': [78., 70., 0.], 'P06': [12., 40., 0.]}
STATION_POINTS = {'S01': [10., 10., 0.], 'S02': [90., 10., 0.],
                  'S03': [10., 70., 0.], 'S04': [90., 70., 0.]}
TERMINAL = {'COMPLETED', 'CANCELLED', 'RECOVERED'}


def note(state, order, text):
    order['events'].append({'at': state['clock'], 'wall_time': time.time(), 'text': text})


class FlightOrders:
    def __init__(self):
        store.init_db()
        self.last_signature = None

    def recover_after_restart(self):
        """Never silently release stock/aircraft after an unknown process exit."""
        with store.transaction() as s:
            for task in s.setdefault('flight_tasks', []):
                if task['phase'] not in TERMINAL:
                    task.update(phase='INTERRUPTED', reason='飞行服务重启，执行状态未知，需核对货物与飞机', updated_at=time.time())
                    order = next(o for o in s['orders'] if o['id'] == task['order_id'])
                    if not task.get('delivered'): order['status'] = 'flight_exception'
                    note(s, order, task['reason'])

    def list(self):
        s = store.read_state()
        return {'orders': [o for o in s['orders'] if o['status'] == 'pending' and o.get('kind') == 'delivery'],
                'tasks': list(reversed(s.get('flight_tasks', []))),
                'mapping': {'kind': 'named_simulation_sites', 'landing_points': LANDING_POINTS,
                            'station_points': STATION_POINTS,
                            'note': '社区站点/取件点与局部测试场有明确对应；坐标为研究场景，不是实际地理导航。'}}

    def preview(self, order_id, seed=42):
        return self._plan(store.read_state(), order_id, seed)

    def _plan(self, state, order_id, seed):
        order = next((o for o in state['orders'] if o['id'] == order_id), None)
        if not order: raise ValueError('订单不存在，请刷新订单列表')
        if order['status'] != 'pending' or order.get('kind') != 'delivery':
            raise ValueError('仅待调度的配送订单可载入；已执行订单不会重复发货')
        if any(inside((order['x'], order['y']), z) for z in state['zones']):
            raise ValueError('订单取件点已进入社区禁飞区，请调整后重试')
        if order.get('pickup_point_id') not in LANDING_POINTS:
            raise ValueError('当前飞行联调仅支持六个已配置公共取件点；地图自选点请先配置着陆场映射')
        if state['weather']['wind'] > 10 or state['weather']['rain'] > 5:
            raise ValueError('社区气象条件不满足本版任务起飞要求')
        weight = PRODUCTS[order['product']]['weight'] * order['quantity']
        candidates = []
        for station in state['stations']:
            item = {'station_id': station['id'], 'station_name': station['name'], 'eligible': False}
            candidates.append(item)
            if not station['online']:
                item['reason'] = '站点暂停服务'; continue
            if station['inventory'].get(order['product'], 0) < order['quantity']:
                item['reason'] = '可用库存不足'; continue
            aircraft = [d for d in state['drones'] if d['station_id'] == station['id']
                        and d['status'] in ('idle', 'charging') and d['max_payload'] >= weight
                        and d['battery'] >= 45]
            if not aircraft:
                item['reason'] = '没有满足电量、载荷与状态条件的无人机'; continue
            sc = scene('neighborhood', seed); sc['clearance'] = 4.
            sc['home'] = STATION_POINTS[station['id']][:]
            sc['goal'] = LANDING_POINTS[order['pickup_point_id']][:]; sc['cruise_altitude'] = 12.
            try:
                route = astar(sc['home'], sc['goal'], sc, altitude=12.)
                back = astar(sc['goal'], sc['home'], sc, altitude=12.)
            except ValueError as exc:
                item['reason'] = str(exc); continue
            outbound = energy_budget(route, payload=weight, wind=state['weather']['wind'])
            inbound = energy_budget(back, payload=0., wind=state['weather']['wind'])
            energy = round(outbound['estimated_wh'] + inbound['estimated_wh'], 3)
            aircraft = [d for d in aircraft if (d['battery']-25)/100*d['capacity_wh'] >= energy]
            if not aircraft:
                item['reason'] = '任务与返航预算超过可用电量'; continue
            drone = max(aircraft, key=lambda d: d['battery'])
            item.update(eligible=True, reason='库存、载荷、电量与起降走廊检查通过', drone_id=drone['id'],
                        battery=drone['battery'], roundtrip_m=round(outbound['distance_m']+inbound['distance_m'], 2),
                        estimated_wh=energy, scene=sc, route=route)
        feasible = [c for c in candidates if c['eligible']]
        if not feasible: raise ValueError('无法安排任务：' + '；'.join(c['station_name']+'：'+c['reason'] for c in candidates))
        best = min(feasible, key=lambda c: (c['estimated_wh'], c['roundtrip_m'], c['station_id']))
        return {'order_id': order_id, 'product': PRODUCTS[order['product']]['name'], 'quantity': order['quantity'],
                'address': order['address'], 'weight_kg': round(weight, 3), 'selected': best,
                'candidates': candidates, 'basis': '可行站点中选择参数化往返耗能较低方案；并非VNS全局最优或实机续航保证',
                'coordinate_note': '公共取件点映射至局部模拟着陆场；非实地经纬度。'}

    def reserve(self, order_id, run_id, seed=42):
        with store.transaction() as s:
            tasks = s.setdefault('flight_tasks', [])
            active = next((t for t in tasks if t['phase'] not in TERMINAL), None)
            if active: raise ValueError('单飞行器通道已被任务 '+active['run_id']+' 占用，请完成或核对恢复后再载入')
            plan = self._plan(s, order_id, seed); selected = plan['selected']
            o = next(o for o in s['orders'] if o['id'] == order_id)
            st = next(x for x in s['stations'] if x['id'] == selected['station_id'])
            drone = next(x for x in s['drones'] if x['id'] == selected['drone_id'])
            st['inventory'][o['product']] -= o['quantity']; drone['status'] = 'flight_reserved'
            o.update(status='flight_reserved', station_id=st['id'], drone_id=drone['id'], flight_task_id=run_id)
            task = {'run_id': run_id, 'order_id': order_id, 'station_id': st['id'], 'drone_id': drone['id'],
                    'phase': 'READY', 'delivered': False, 'stock': 'reserved', 'created_at': time.time(),
                    'updated_at': time.time(), 'plan': plan, 'reason': '任务已预占库存与运力，等待飞前检查', 'history': []}
            tasks.append(task); note(s, o, f'任务 {run_id} 已准备：{st["name"]} / {drone["id"]}；库存已预占')
        return copy.deepcopy(task)

    def sync(self, snap):
        if not snap.get('order_id') or not snap.get('run_id'): return
        signature = (snap['run_id'], snap['phase'], snap['delivered'], snap.get('fault'), snap.get('lease'))
        if signature == self.last_signature: return
        with store.transaction() as s:
            task = next((t for t in s.get('flight_tasks', []) if t['run_id'] == snap['run_id']), None)
            if not task or task['phase'] in TERMINAL: return
            o = next(o for o in s['orders'] if o['id'] == task['order_id'])
            drone = next(d for d in s['drones'] if d['id'] == task['drone_id'])
            phase = snap['phase']; old_phase = task['phase']
            task.update(phase=phase, reason=snap['reason'], updated_at=time.time(), fault=snap.get('fault'),
                        owner=snap.get('lease'), delivered=bool(snap['delivered']))
            task['history'].append({'time': time.time(), 'phase': phase, 'reason': snap['reason'], 'owner': snap.get('lease')})
            task['history'] = task['history'][-200:]
            if snap['delivered'] and task['stock'] == 'reserved':
                task['stock'] = 'consumed'; o.update(status='delivered', delivered_at=s['clock'], delivered_wall_at=time.time())
                o['flight_elapsed_minutes'] = round((time.time()-task['created_at'])/60, 3)
                note(s, o, '模拟交付双反馈确认，物品已交付；飞机返航状态单独记录')
            elif not snap['delivered']:
                o['status'] = 'flight_exception' if phase in ('STOPPED', 'HOLD', 'LANDING') or snap.get('fault') else ('flight_reserved' if phase == 'READY' else 'flight_active')
            if phase == 'COMPLETED':
                drone.update(status='idle', battery=(snap.get('telemetry') or {}).get('battery', drone['battery']))
                note(s, o, '飞行任务已返站落地，运力释放；订单交付与返航均已确认')
            elif phase == 'STOPPED':
                drone['status'] = 'recovery_required'
                note(s, o, '飞行已停止，资源保留待核对：'+snap['reason'])
            elif phase not in ('READY',): drone['status'] = 'flight_active'
            if old_phase != phase: note(s, o, '飞行阶段：'+phase+' · '+snap['reason'])
        self.last_signature = signature

    def release(self, run_id, recovered=False, note_text=''):
        with store.transaction() as s:
            task = next((t for t in s.get('flight_tasks', []) if t['run_id'] == run_id), None)
            if not task: raise ValueError('飞行任务不存在')
            if task['phase'] in TERMINAL: return copy.deepcopy(task)
            if not recovered and task['phase'] != 'READY': raise ValueError('只有未解锁的准备任务可以取消预占')
            if recovered and task['phase'] not in ('STOPPED', 'INTERRUPTED'):
                raise ValueError('仅落地停止或服务中断的任务可人工核对恢复')
            if recovered and len(note_text.strip()) < 6: raise ValueError('请填写不少于6字的飞机返站及货物核对说明')
            o = next(o for o in s['orders'] if o['id'] == task['order_id'])
            st = next(st for st in s['stations'] if st['id'] == task['station_id'])
            drone = next(d for d in s['drones'] if d['id'] == task['drone_id'])
            if task['stock'] == 'reserved':
                st['inventory'][o['product']] += o['quantity']; task['stock'] = 'restored'
                o.update(status='pending', station_id=None, drone_id=None, flight_task_id=None)
            # Actual battery may be unknown after interruption: require maintenance
            # release by the operator, never turn an unknown aircraft into idle.
            drone['status'] = 'maintenance' if recovered else 'idle'
            task.update(phase='RECOVERED' if recovered else 'CANCELLED', updated_at=time.time(),
                        reason=note_text if recovered else '起飞前取消，库存与运力已释放')
            note(s, o, task['reason'] + ('；飞机转维护待检查' if recovered else ''))
            return copy.deepcopy(task)
