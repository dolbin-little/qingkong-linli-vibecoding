import math
from backend.planner import dispatch, PRODUCTS
from backend.energy import charging_plan
from backend.store import log

def event(state, order, message):
    order['events'].append({'at': round(state['clock'], 3), 'text': message})

def apply_dispatch(state, method=None):
    method = method or state['settings']['algorithm']
    result = dispatch(state, method)
    drones = {d['id']: d for d in state['drones']}
    stations = {s['id']: s for s in state['stations']}
    orders = {o['id']: o for o in state['orders']}
    for route in result['routes']:
        drone = drones[route['drone_id']]
        for oid in route['orders']:
            order = orders[oid]
            if order.get('kind') != 'return':
                stations[route['station_id']]['inventory'][order['product']] -= order['quantity']
            order.update(status='flying', station_id=route['station_id'], drone_id=drone['id'],
                         eta=state['clock'] + route['arrivals'][oid])
            event(state, order, f"{drone['id']} 已分配 · {method.upper()} 调度 · 含返航电量检查")
        drone['status'] = 'flying'
        state['flights'].append({**route, 'started': state['clock'], 'initial_battery': drone['battery'],
                                 'done': False, 'id': f"F{state['revision']}-{drone['id']}"})
    state['dispatches'].insert(0, {**result, 'at': state['clock']})
    state['dispatches'] = state['dispatches'][:30]
    controller = '云端' if state['cloud_online'] else '站点边缘接管（仿真）'
    log(state, f"{controller} · {method.upper()} 完成，派出 {len(result['routes'])} 架，待分配 {len(result['unassigned'])} 单", 'dispatch')
    return result

def interpolate(points, ratio):
    lengths = [math.dist(a, b) for a, b in zip(points, points[1:])]
    target = sum(lengths) * min(1, max(0, ratio))
    for i, length in enumerate(lengths):
        if target <= length:
            f = target / max(length, 1e-9)
            return [points[i][k] + f * (points[i+1][k] - points[i][k]) for k in (0, 1)]
        target -= length
    return points[-1]

def advance(state, minutes):
    start = state['clock']
    state['clock'] += minutes
    if int(start/10) != int(state['clock']/10):
        state.setdefault('irradiance_history', []).append(state['weather']['irradiance'])
        state['irradiance_history'] = state['irradiance_history'][-24:]
    drones = {d['id']: d for d in state['drones']}
    orders = {o['id']: o for o in state['orders']}
    stations = {s['id']: s for s in state['stations']}
    for flight in state['flights']:
        if flight['done']:
            continue
        drone = drones[flight['drone_id']]
        elapsed = state['clock'] - flight['started']
        spent = .8
        for leg in flight['legs']:
            fraction = min(1., max(0., (elapsed-leg['start']) / max(.001, leg['end']-leg['start'])))
            spent += fraction * leg['energy']
            if leg['start'] <= elapsed <= leg['end']:
                drone['x'], drone['y'] = interpolate(leg['path'], fraction)
            oid = leg['order_id']
            if oid and elapsed >= leg['end'] and orders[oid]['status'] == 'flying':
                o = orders[oid]
                o['delivered_at'] = flight['started'] + leg['end']
                o['status'] = 'returning' if o.get('kind') == 'return' else 'delivered'
                event(state, o, '已收取归还物品，返站中' if o.get('kind') == 'return' else '物品已送达公共取件点（仿真）')
                log(state, f"{oid} {'取件完成' if o.get('kind') == 'return' else '配送完成'}", 'order')
        drone['battery'] = max(0, flight['initial_battery'] - spent / drone['capacity_wh'] * 100)
        if elapsed >= flight['duration_min']:
            station = stations[flight['station_id']]
            drone.update(x=station['x'], y=station['y'], status='idle')
            drone['flight_minutes'] += flight['duration_min']; drone['distance_m'] += flight['distance_m']
            flight['done'] = True
            for oid in flight['orders']:
                o = orders[oid]
                if o.get('kind') == 'return':
                    o['status'] = 'completed'; o['returned_at'] = state['clock']
                    station['inventory'][o['product']] += o['quantity']
                    original = orders[o['original_id']]
                    original['status'] = 'returned'; original['returned_at'] = state['clock']
                    hours = max(1, math.ceil((state['clock'] - original['delivered_at']) / 60))
                    original['settled_amount'] = round((hours if o['product'] == 'powerbank' else 1) * PRODUCTS[o['product']]['price'] * o['quantity'] + 1.5, 2)
                    event(state, original, f"归还入库完成 · 模拟结算 ¥{original['settled_amount']:.2f}")
            log(state, f"{drone['id']} 已返站，剩余电量 {drone['battery']:.1f}%", 'flight')
    # Charge only drones that were available at interval start (avoid charging an entire interval after landing).
    busy_before = {f['drone_id'] for f in state['flights'] if f['started'] + f['duration_min'] > start and f['started'] <= start}
    energy_state = {**state, 'drones': [{**d, 'status': 'flying'} if d['id'] in busy_before else d for d in state['drones']]}
    plan = charging_plan(energy_state)
    solar_total, delivered_total = 0., 0.
    for p in plan['plans']:
        station = stations[p['station_id']]
        produced = state['weather']['irradiance'] * station['pv_area'] * .2 * minutes / 60 if station['online'] else 0
        available = station['storage_wh'] + produced
        consumed = 0.
        for a in p['actions']:
            drone = drones[a['drone_id']]
            requested = a['schedule_wh'][0] * min(minutes / 10, 1)
            delivered = min(requested, max(0, available-consumed) * .92, (100-drone['battery'])/100*drone['capacity_wh'])
            drone['battery'] += delivered / drone['capacity_wh'] * 100
            drone['status'] = 'charging' if delivered > .001 and drone['battery'] < 95 else 'idle'
            consumed += delivered / .92; delivered_total += delivered
        station['storage_wh'] = min(station['storage_capacity_wh'], max(0, available-consumed))
        solar_total += produced
    state['energy_log'].append({'at': state['clock'], 'pv_wh': solar_total, 'charged_wh': delivered_total})
    state['energy_log'] = state['energy_log'][-2000:]
    if state['settings']['auto_dispatch'] and any(o['status'] == 'pending' for o in state['orders']):
        apply_dispatch(state)

def metrics(state):
    delivered = [o for o in state['orders'] if o.get('kind') != 'return' and o.get('delivered_at') is not None]
    times = [o['delivered_at'] - o['created'] for o in delivered]
    flights = [f for f in state['flights'] if f['done']]
    energy = sum(f['energy_wh'] for f in flights)
    # Explicit illustrative unit economics; not a real cost assertion.
    cost = len(flights)*1.1 + energy/1000*.65 + sum(f['duration_min'] for f in flights)*.08
    return {'orders': len([o for o in state['orders'] if o.get('kind') != 'return']), 'delivered': len(delivered),
            'pending': sum(o['status'] == 'pending' for o in state['orders']),
            'flying': sum(d['status'] == 'flying' for d in state['drones']),
            'available': sum(d['status'] == 'idle' for d in state['drones']),
            'avg_minutes': round(sum(times)/len(times), 2) if times else None,
            'on_time_pct': round(sum(o['delivered_at'] <= o['deadline'] for o in delivered)/len(delivered)*100, 1) if delivered else None,
            'energy_wh': round(energy, 2), 'distance_km': round(sum(f['distance_m'] for f in flights)/1000, 2),
            'solar_wh': round(sum(x['pv_wh'] for x in state['energy_log']), 2),
            'cost_per_order': round(cost / sum(len(f['orders']) for f in flights), 2) if flights else None}
