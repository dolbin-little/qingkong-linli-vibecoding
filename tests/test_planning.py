import copy
import math
import pytest
from backend.store import seed_state
from backend.planner import dispatch, solve_tour, path, intersects, PRODUCTS
from backend.energy import charging_plan
from backend.simulation import apply_dispatch, advance
from backend.avoidance import dwa
from backend.mqtt_bridge import validate
from backend.forecast import predict_irradiance

def test_visibility_path_avoids_rectangle():
    zones=[{'x':4,'y':-2,'w':2,'h':4}]
    distance, pts=path((0,0),(10,0),zones)
    assert distance>10
    assert all(not intersects(a,b,zones[0]) for a,b in zip(pts,pts[1:]))

def test_path_rejects_endpoint_in_zone():
    with pytest.raises(ValueError):path((5,0),(10,0),[{'x':4,'y':-2,'w':2,'h':4}])

def test_dispatch_unique_feasible_and_deterministic():
    s=seed_state();result=dispatch(s);again=dispatch(s)
    ids=[i for r in result['routes'] for i in r['orders']]
    assert len(ids)==len(set(ids))==6
    assert result['score']==again['score']
    assert all(a>=b-1e-8 for a,b in zip(result['history'],result['history'][1:]))
    for r in result['routes']:
        d=next(d for d in s['drones'] if d['id']==r['drone_id'])
        assert d['battery']-r['energy_wh']/d['capacity_wh']*100>=20
        assert sum(PRODUCTS[o['product']]['weight']*o['quantity'] for o in s['orders'] if o['id'] in r['orders'])<=d['max_payload']
        assert all(t<=next(o['deadline'] for o in s['orders'] if o['id']==i) for i,t in r['arrivals'].items())
        assert all(not intersects(a,b,z) for l in r['legs'] for a,b in zip(l['path'],l['path'][1:]) for z in s['zones'])
        assert r['legs'][0]['from']==r['legs'][-1]['to']

def test_zero_inventory_prevents_dispatch():
    s=seed_state()
    for st in s['stations']:st['inventory']={p:0 for p in PRODUCTS}
    assert not dispatch(s)['routes']

def test_low_battery_prevents_dispatch():
    s=seed_state()
    for d in s['drones']:d['battery']=20
    assert not dispatch(s)['routes']

def test_weather_safety_blocks_departures():
    s=seed_state();s['weather']['wind']=12
    assert not dispatch(s)['routes']

def test_expired_orders_not_scheduled():
    s=seed_state();s['clock']=7
    assert not dispatch(s)['routes']

def test_oversized_payload_infeasible():
    s=seed_state();o=copy.deepcopy(s['orders'][0]);o.update(product='water',quantity=8)
    assert solve_tour(s['drones'][0],s['stations'][0],[o],s['weather'],s['zones'],0) is None

def test_mpc_charger_capacity_and_energy_causality():
    s=seed_state();s['weather']['irradiance']=0
    for st in s['stations']:st['storage_wh']=3;st['chargers']=1
    plan=charging_plan(s)
    for p in plan['plans']:
        assert sum(sum(a['schedule_wh'])/.92 for a in p['actions'])<=3.001
        for t in range(6):assert sum(a['schedule_wh'][t]>.001 for a in p['actions'])<=1

def test_no_sun_no_storage_no_charging():
    s=seed_state();s['weather']['irradiance']=0
    for st in s['stations']:st['storage_wh']=0
    assert all(p['allocated_wh']==0 for p in charging_plan(s)['plans'])

def test_simulation_completes_flights_and_preserves_stock():
    s=seed_state();start=sum(sum(st['inventory'].values()) for st in s['stations'])
    apply_dispatch(s)
    assert sum(sum(st['inventory'].values()) for st in s['stations'])==start-6
    for _ in range(5):advance(s,1)
    assert all(o['status']=='delivered' for o in s['orders'])
    assert all(f['done'] for f in s['flights'])
    assert all(0<=d['battery']<=100 for d in s['drones'])
    assert all(0<=st['storage_wh']<=st['storage_capacity_wh'] for st in s['stations'])

def test_dwa_avoids_obstacle_and_has_bounds():
    r=dwa((0,0,0,1,0),(10,0),[(2,0,.8)])
    if r['safe']:
        assert all(math.hypot(x-2,y)>.8+.8 for x,y,_ in r['trajectory'])
        assert 0<=r['speed']<=1.3 and abs(r['yaw_rate'])<=.36+1e-8
    else:assert r['speed']==0

def test_mqtt_validation():
    assert validate({'device_id':'LH-001','battery':50,'x':2,'y':3})['battery']==50
    with pytest.raises(ValueError):validate({'device_id':'x','battery':200,'x':0,'y':0})
    with pytest.raises(ValueError):validate({'device_id':'x','battery':float('nan'),'x':0,'y':0})

def test_forecast_is_bounded_and_fallback_explicit():
    values,label=predict_irradiance(700)
    assert len(values)==6 and all(0<=v<=1200 for v in values)
    assert '基线' in label

def test_aco_is_actual_feasible_assignment():
    s=seed_state();r=dispatch(s,method='aco',seed=19)
    assert r['routes'] and len(r['history'])==5
    assert len({i for route in r['routes'] for i in route['orders']})==6

def test_batch_limit_reports_all_deferred_orders():
    s=seed_state();s['orders']=[{**s['orders'][0],'id':str(i)} for i in range(27)]
    r=dispatch(s,iterations=1)
    assigned={i for route in r['routes'] for i in route['orders']}
    assert len(assigned)+len(r['unassigned'])==27

def test_vns_does_not_worsen_its_feasible_seed():
    s=seed_state();baseline=dispatch(s,'greedy');r=dispatch(s,'vns')
    assert r['score']<=baseline['score']+1e-6

