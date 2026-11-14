from tools.benchmark import experiment
from autonomy.models import scene
from autonomy.planning import astar,safe_segment,energy_budget

def test_simplification_shortens_route_without_removing_clearance_checks():
    s=scene();s['clearance']=4;s['goal'][2]=0
    raw=astar(s['home'],s['goal'],s,simplify=False)
    compact=astar(s['home'],s['goal'],s)
    assert len(compact)<len(raw)
    assert energy_budget(compact)['distance_m']<=energy_budget(raw)['distance_m']
    assert all(safe_segment(a,b,s) for a,b in zip(compact,compact[1:]))

def test_fixed_input_reproduces_flight_metrics():
    a=experiment('neighborhood',42,False)
    b=experiment('neighborhood',42,False)
    for key in ('phase','distance_m','plant_energy_wh','cross_track_rmse_m','elapsed_sim_s'):
        assert a[key]==b[key]
    assert a['completed'] and not a['collision']

def test_lost_link_is_not_counted_as_success_or_confirmed_landing():
    r=experiment('neighborhood',42,True,'link')
    assert r['expectation_met'] and r['phase']=='LINK_LOST'
    assert not r['completed'] and not r['delivery_confirmed']
