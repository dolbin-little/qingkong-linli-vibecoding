"""Rolling-horizon charging MILP (6 x 10 min slots), solar + finite storage.
Only first action is executed before the next replan. No implicit grid energy.
"""
import math
import numpy as np
from scipy.optimize import Bounds, LinearConstraint
from backend.solver import milp

def charging_plan(state):
    from backend.forecast import predict_irradiance
    irradiation, forecast_model = predict_irradiance(state['weather']['irradiance'], state.get('irradiance_history'))
    plans = []
    for station in state['stations']:
        drones = [d for d in state['drones'] if d['station_id'] == station['id'] and d['status'] in ('idle', 'charging') and d['battery'] < 95]
        forecast = [round(value * station['pv_area'] * .20, 1) for value in irradiation]
        if not drones or not station['online']:
            plans.append({'station_id': station['id'], 'forecast_w': forecast, 'actions': [], 'solver': '无需充电', 'allocated_wh': 0})
            continue
        n, h = len(drones), 6
        # x_dt binary charger occupation, e_dt delivered Wh, storage_t continuous.
        size = 2 * n * h + h
        c = np.zeros(size); upper = np.ones(size)
        upper[n*h:2*n*h] = 100 / 6 * .92
        upper[2*n*h:] = station['storage_capacity_wh']
        rows, low, high = [], [], []
        def add(co, lo, hi):
            row = np.zeros(size)
            for k, v in co.items(): row[k] = v
            rows.append(row); low.append(lo); high.append(hi)
        for d, drone in enumerate(drones):
            for t in range(h):
                ix, en = d*h+t, n*h+d*h+t
                c[ix] = .01
                c[en] = -(1 + (100-drone['battery']) / 100) * (.96 ** t)
                add({en: 1, ix: -100/6*.92}, -math.inf, 0)
            add({n*h+d*h+t: 1 for t in range(h)}, 0, (95-drone['battery'])/100*drone['capacity_wh'])
        for t in range(h):
            add({d*h+t: 1 for d in range(n)}, 0, station['chargers'])
            # storage can curtail PV, never borrow future supply.
            co = {2*n*h+t: 1, **{n*h+d*h+t: 1/.92 for d in range(n)}}
            if t: co[2*n*h+t-1] = -1
            supply = forecast[t]/6 + (station['storage_wh'] if t == 0 else 0)
            add(co, -math.inf, supply)
        result = milp(c, integrality=np.r_[np.ones(n*h), np.zeros(n*h+h)],
                      bounds=Bounds(np.zeros(size), upper), constraints=LinearConstraint(rows, low, high),
                      options={'time_limit': 1.})
        actions = []
        if result.x is not None:
            for d, drone in enumerate(drones):
                schedule = [round(float(max(0, result.x[n*h+d*h+t])), 4) for t in range(h)]
                actions.append({'drone_id': drone['id'], 'schedule_wh': schedule,
                                'charge_now': schedule[0] > .01, 'battery': drone['battery']})
        plans.append({'station_id': station['id'], 'forecast_w': forecast, 'actions': actions,
                      'solver': 'HiGHS MPC-MILP' if result.x is not None else '不可行',
                      'allocated_wh': round(sum(sum(a['schedule_wh']) for a in actions), 2)})
    return {'horizon_minutes': 60, 'step_minutes': 10, 'plans': plans, 'forecast_model': forecast_model, 'source': '模拟光照预测，非实测天气'}
