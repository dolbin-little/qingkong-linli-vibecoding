"""Deterministic obstacle routing + VNS task assignment + real HiGHS MILP tours.

Coordinates: metres; clock: minutes; energy: Wh. See docs/ALGORITHMS.md.
"""
from functools import lru_cache
import heapq
import math
import random
import time
import numpy as np
from scipy.optimize import Bounds, LinearConstraint
from backend.solver import milp

PRODUCTS = {
    'powerbank': {'name': '共享充电宝', 'weight': .28, 'price': 2., 'unit': '元/小时', 'rental': True},
    'umbrella': {'name': '共享雨伞', 'weight': .35, 'price': 2., 'unit': '元/次', 'rental': True},
    'water': {'name': '瓶装饮用水', 'weight': .55, 'price': 2., 'unit': '元/瓶', 'rental': False},
    'firstaid': {'name': '便携急救包', 'weight': .20, 'price': 8., 'unit': '元/份', 'rental': False},
}
DEFAULT_ZONES = [
    {'id': 'Z01', 'name': '教学楼安全缓冲区', 'x': 390, 'y': 180, 'w': 120, 'h': 155},
    {'id': 'Z02', 'name': '居民楼安全缓冲区', 'x': 660, 'y': 365, 'w': 105, 'h': 130},
    {'id': 'Z03', 'name': '活动场地临时禁飞区', 'x': 220, 'y': 460, 'w': 130, 'h': 80},
]

def inside(p, r):
    return r['x'] <= p[0] <= r['x'] + r['w'] and r['y'] <= p[1] <= r['y'] + r['h']

def intersects(a, b, r):
    # Slab test, including boundaries; corners in the graph have a 2 m clearance.
    lo, hi = 0., 1.
    for dim, key, size in [(0, 'x', 'w'), (1, 'y', 'h')]:
        delta = b[dim] - a[dim]
        mn, mx = r[key], r[key] + r[size]
        if abs(delta) < 1e-10:
            if a[dim] < mn or a[dim] > mx:
                return False
        else:
            u, v = sorted(((mn - a[dim]) / delta, (mx - a[dim]) / delta))
            lo, hi = max(lo, u), min(hi, v)
            if lo > hi:
                return False
    return True

@lru_cache(maxsize=8192)
def _path(a, b, rectangles):
    zones = [dict(zip(('x', 'y', 'w', 'h'), r)) for r in rectangles]
    if any(inside(a, r) or inside(b, r) for r in zones):
        raise ValueError('起点或终点位于禁飞区内')
    nodes = [a, b]
    for r in zones:
        nodes += [(r['x'] - 2, r['y'] - 2), (r['x'] + r['w'] + 2, r['y'] - 2),
                  (r['x'] - 2, r['y'] + r['h'] + 2), (r['x'] + r['w'] + 2, r['y'] + r['h'] + 2)]
    nodes = [p for i, p in enumerate(nodes) if i < 2 or not any(inside(p, r) for r in zones)]
    adj = [[] for _ in nodes]
    for i, p in enumerate(nodes):
        for j in range(i):
            q = nodes[j]
            if not any(intersects(p, q, r) for r in zones):
                dist = math.dist(p, q)
                adj[i].append((j, dist)); adj[j].append((i, dist))
    costs, prev, queue = {0: 0}, {}, [(0, 0)]
    while queue:
        cost, i = heapq.heappop(queue)
        if cost > costs[i]:
            continue
        if i == 1:
            ids = [1]
            while ids[-1] != 0:
                ids.append(prev[ids[-1]])
            return cost, tuple(nodes[k] for k in reversed(ids))
        for j, d in adj[i]:
            if cost + d < costs.get(j, math.inf):
                costs[j] = cost + d; prev[j] = i
                heapq.heappush(queue, (cost + d, j))
    raise ValueError('禁飞区使目标不可达')

def path(a, b, zones):
    d, points = _path(tuple(a), tuple(b), tuple((r['x'], r['y'], r['w'], r['h']) for r in zones))
    return d, [list(p) for p in points]

def flight_energy(distance, payload, weather):
    speed = max(4., 10. - weather['wind'] * .3)
    seconds = distance / speed
    gross_w = 220 + 85 * payload + 2 * weather['wind'] ** 2
    solar_w = weather['irradiance'] * .12 * .20 * .90
    gross = gross_w * seconds / 3600
    solar = min(solar_w * seconds / 3600, gross * .3)
    return gross - solar, solar, seconds / 60

def solve_tour(drone, station, orders, weather, zones, now):
    if not orders:
        return None
    load = sum(PRODUCTS[o['product']]['weight'] * o['quantity'] for o in orders)
    if load > drone['max_payload'] or len(orders) > 3:
        return None
    pts = [(station['x'], station['y'])] + [(o['x'], o['y']) for o in orders]
    n = len(pts)
    arcs = [(i, j) for i in range(n) for j in range(n) if i != j]
    ds, energies, durations, polylines = {}, {}, {}, {}
    try:
        for i, j in arcs:
            ds[i, j], polylines[i, j] = path(pts[i], pts[j], zones)
            energies[i, j], _, durations[i, j] = flight_energy(ds[i, j], load, weather)
    except ValueError:
        return None
    # x_ij binary, t_i continuous for customers; t_0 is excluded to allow return.
    m, total = len(arcs), len(arcs) + n - 1
    c = np.zeros(total)
    for k, arc in enumerate(arcs):
        c[k] = .45 * ds[arc] / 1000 + .35 * energies[arc] / 20
    c[m:] = .20 / (n - 1) / 3
    upper = np.ones(total)
    for i, o in enumerate(orders):
        upper[m + i] = o['deadline'] - now
        if upper[m + i] <= 0:
            return None
    rows, lb, ub = [], [], []
    def constraint(coeffs, low, high):
        row = np.zeros(total)
        for k, value in coeffs.items():
            row[k] = value
        rows.append(row); lb.append(low); ub.append(high)
    for i in range(n):
        constraint({k: 1 for k, (a, b) in enumerate(arcs) if a == i}, 1, 1)
        constraint({k: 1 for k, (a, b) in enumerate(arcs) if b == i}, 1, 1)
    big_m = 1000
    for k, (i, j) in enumerate(arcs):
        if j == 0:
            continue
        coeff = {m + j - 1: 1, k: -big_m}
        if i:
            coeff[m + i - 1] = -1
        # 0.2 min handling at every departure, including the initial loading.
        constraint(coeff, durations[i, j] + .2 - big_m, math.inf)
    # Conservative full payload energy bound + 0.8 Wh vertical/handling reserve.
    available = (drone['battery'] - 20) / 100 * drone['capacity_wh']
    constraint({k: energies[a] for k, a in enumerate(arcs)}, -math.inf, available - .8)
    result = milp(c, integrality=np.r_[np.ones(m), np.zeros(n - 1)],
                  bounds=Bounds(np.zeros(total), upper),
                  constraints=LinearConstraint(np.array(rows), lb, ub),
                  options={'time_limit': .6, 'mip_rel_gap': .005})
    if result.x is None:
        return None
    successors = {i: j for k, (i, j) in enumerate(arcs) if result.x[k] > .5}
    sequence, cursor = [], 0
    for _ in range(n):
        cursor = successors.get(cursor, 0)
        if cursor == 0:
            break
        if cursor in sequence:
            return None
        sequence.append(cursor)
    if len(sequence) != n - 1:
        return None
    current, elapsed, energy, solar, distance = 0, 0., .8, 0., 0.
    legs, arrivals = [], {}
    for nxt in sequence + [0]:
        dist = ds[current, nxt]
        en, pv, minutes = flight_energy(dist, load, weather)
        start = elapsed
        elapsed += .2 + minutes
        legs.append({'from': pts[current], 'to': pts[nxt], 'path': polylines[current, nxt],
                     'start': start, 'end': elapsed, 'energy': en, 'solar': pv,
                     'order_id': orders[nxt - 1]['id'] if nxt else None})
        energy += en; solar += pv; distance += dist
        if nxt:
            o = orders[nxt - 1]
            arrivals[o['id']] = round(elapsed, 4)
            if now + elapsed > o['deadline'] + 1e-5:
                return None
            if o.get('kind', 'delivery') != 'return':
                load -= PRODUCTS[o['product']]['weight'] * o['quantity']
        current = nxt
    score = .45 * distance / 1000 + .35 * energy / 20 + .20 * np.mean(list(arrivals.values())) / 3
    return {'drone_id': drone['id'], 'station_id': station['id'], 'orders': [orders[i - 1]['id'] for i in sequence],
            'legs': legs, 'arrivals': arrivals, 'distance_m': round(distance, 2), 'energy_wh': round(energy, 4),
            'solar_wh': round(solar, 4), 'duration_min': round(elapsed, 4), 'score': float(score),
            'solver': 'HiGHS MILP', 'solver_optimal': result.status == 0}

def dispatch(state, method='vns', iterations=25, seed=42):
    started = time.perf_counter()
    weather, now = state['weather'], state['clock']
    all_orders = sorted([o for o in state['orders'] if o['status'] == 'pending'],
                        key=lambda o: (-o['priority'], o['deadline'], o['id']))
    orders = all_orders[:24]
    deferred = [o['id'] for o in all_orders[24:]]
    drones = [d for d in state['drones'] if d['status'] in ('idle', 'charging') and d['battery'] > 22]
    stations = {s['id']: s for s in state['stations'] if s['online']}
    drones = [d for d in drones if d['station_id'] in stations]
    empty = {'routes': [], 'unassigned': [o['id'] for o in orders] + deferred, 'history': [], 'method': method,
             'elapsed_ms': 0, 'score': 0, 'reason': ''}
    if weather['wind'] > 10 or weather['rain'] > 5:
        return {**empty, 'reason': '天气超过仿真安全阈值，暂停新航班'}
    if not orders or not drones:
        return {**empty, 'reason': '没有待调度订单或可用无人机'}
    cache = {}
    def evaluate(assign):
        counts, routes, penalty = {}, [], 0.
        for o, d in zip(orders, assign):
            if d < 0:
                penalty += 100 * o['priority']; continue
            if o.get('kind') == 'return':
                if drones[d]['station_id'] != o['station_id']:
                    return math.inf, []
                continue
            key = (drones[d]['station_id'], o['product'])
            counts[key] = counts.get(key, 0) + o['quantity']
        if any(q > stations[s]['inventory'][p] for (s, p), q in counts.items()):
            return math.inf, []
        for idx, drone in enumerate(drones):
            group = [o for o, d in zip(orders, assign) if d == idx]
            if not group:
                continue
            key = idx, tuple(sorted(o['id'] for o in group))
            if key not in cache:
                cache[key] = solve_tour(drone, stations[drone['station_id']], group, weather, state['zones'], now)
            route = cache[key]
            if route is None:
                return math.inf, []
            routes.append(route)
        return penalty + sum(r['score'] for r in routes), routes
    assign = [-1] * len(orders)
    for i, o in enumerate(orders):
        candidates = []
        for d, drone in enumerate(drones):
            proposal = assign.copy(); proposal[i] = d
            score, routes = evaluate(proposal)
            if math.isfinite(score):
                candidates.append((score, d, routes))
        if candidates:
            if method in ('greedy', 'vns', 'aco'):
                _, d, _ = min(candidates, key=lambda x: math.dist((o['x'], o['y']), (stations[drones[x[1]]['station_id']]['x'], stations[drones[x[1]]['station_id']]['y'])))
            elif method == 'dqn':
                from backend.learning import rank_candidates
                d = rank_candidates(candidates, drones, len(orders) - i)
            else:
                _, d, _ = min(candidates, key=lambda x: x[0])
            assign[i] = d
    best_score, best_routes = evaluate(assign)
    history = [round(best_score, 5)]
    rng = random.Random(seed)
    best = assign.copy()
    if method == 'aco':
        pheromone = np.ones((len(orders), len(drones)))
        for _ in range(4):
            for ant in range(4):
                trial = [-1] * len(orders)
                for i in range(len(orders)):
                    choices = []
                    for d in range(len(drones)):
                        proposal = trial.copy(); proposal[i] = d
                        score, _ = evaluate(proposal)
                        if math.isfinite(score): choices.append((d, score))
                    if choices:
                        floor = min(score for _, score in choices)
                        weights = [pheromone[i, d] / (1 + score - floor)**2 for d, score in choices]
                        trial[i] = rng.choices([d for d, _ in choices], weights=weights, k=1)[0]
                score, routes = evaluate(trial)
                if score < best_score:
                    best, best_score, best_routes = trial, score, routes
            pheromone *= .8
            for i, d in enumerate(best):
                if d >= 0: pheromone[i, d] += 1 / (1 + best_score)
            history.append(round(best_score, 5))
    if method == 'vns':
        # Three neighbourhoods: relocate, exchange, and two-order shaking.
        for it in range(iterations):
            trial = best.copy()
            i = rng.randrange(len(orders))
            if it % 3 == 1 and len(orders) > 1:
                j = rng.randrange(len(orders)); trial[i], trial[j] = trial[j], trial[i]
            else:
                trial[i] = rng.randrange(-1, len(drones))
                if it % 3 == 2 and len(orders) > 1:
                    trial[rng.randrange(len(orders))] = rng.randrange(len(drones))
            score, routes = evaluate(trial)
            if score < best_score - 1e-8:
                best, best_score, best_routes = trial, score, routes
            # Best-improvement local search around one task. Every candidate tour
            # is re-solved by MILP, and cache keys include its entire task set.
            for destination in range(len(drones)):
                local = best.copy(); local[i] = destination
                score, routes = evaluate(local)
                if score < best_score - 1e-8:
                    best, best_score, best_routes = local, score, routes
            if it % 3 == 1:
                for j in rng.sample(range(len(orders)), min(4, len(orders))):
                    local = best.copy(); local[i], local[j] = local[j], local[i]
                    score, routes = evaluate(local)
                    if score < best_score - 1e-8:
                        best, best_score, best_routes = local, score, routes
            history.append(round(best_score, 5))
    assigned = {oid for r in best_routes for oid in r['orders']}
    return {'routes': best_routes, 'unassigned': [o['id'] for o in orders if o['id'] not in assigned] + deferred,
            'history': history, 'method': method, 'elapsed_ms': round((time.perf_counter() - started) * 1000, 1),
            'score': round(best_score, 5), 'reason': '未分配订单可能受库存、时间窗、载重、电量或任务上限限制',
            'milp_subproblems': len(cache), 'seed': seed}
