import math,json,copy,time
from pathlib import Path
import pytest
from autonomy.models import scene,Telemetry,SCENARIOS,distance,norm
from autonomy.planning import astar,safe_segment,safe_point,PositionController,energy_budget
from autonomy.safety import SafetyGuard
from autonomy.perception import Tracker
from autonomy.research import AuditChain,offload,ResidualMonitor

@pytest.mark.parametrize('name',list(SCENARIOS))
def test_route_corridors(name):
    s=scene(name);s['clearance']=4;p=astar(s['home'],s['goal'],s)
    assert p[0]==s['home'] and p[-1]==s['goal']
    assert all(safe_segment(a,b,s) for a,b in zip(p,p[1:]))
    assert 0<energy_budget(p)['solar_wh']<energy_budget(p)['gross_wh']

@pytest.mark.parametrize('goal',[[200,40,12],[35,30,12],[10,10,40],[float('nan'),30,12],[10,10,-1]])
def test_invalid_missions(goal):
    s=scene()
    with pytest.raises(ValueError):astar(s['home'],goal,s)

def telemetry():return Telemetry(position=[10.,10.,12.],heartbeat_at=1000,position_at=1000,sensor_at=1000,battery_at=1000,gps_at=1000,gps_fix=3,satellites=12,nearest=100)

@pytest.mark.parametrize('field,value,expected',[('battery_at',996,'BATTERY_STALE'),('gps_at',997,'GPS_STALE'),('satellites',255,'POSITION_QUALITY'),('battery',float('nan'),'INVALID_BATTERY'),('battery',12,'BATTERY_CRITICAL'),('battery',24,'BATTERY_RESERVE'),('heartbeat_at',990,'LINK_LOSS'),('position_at',998,'POSITION_STALE'),('sensor_at',998,'PERCEPTION_STALE'),('gps_fix',1,'POSITION_QUALITY'),('satellites',3,'POSITION_QUALITY'),('position',[120,10,12],'GEOFENCE'),('position',[float('nan'),10,12],'INVALID_STATE'),('sensor_at',1001,'INVALID_TIMESTAMP'),('nearest',1,'OBSTACLE_NEAR')])
def test_fault_responses(field,value,expected):
    t=telemetry();setattr(t,field,value);reason,action=SafetyGuard().check(t,scene(),1000)
    assert reason==expected and action in ('HOLD','LAND','RTL')

def test_preflight_requires_battery_reserve():
    t=telemetry();t.battery=40;assert SafetyGuard().preflight(t,scene(),1000)[0] is False

def test_command_lookahead_and_nonfinite():
    t=telemetry();g=SafetyGuard();s=scene()
    assert g.check(t,s,1000,[float('nan'),0,0])[0]=='INVALID_COMMAND'
    t.position=[98.,10.,12.];assert g.check(t,s,1000,[2.,0,0])[0]=='CORRIDOR_LIMIT'

def test_controller_limit_and_convergence():
    c=PositionController();p=[10.,10.,12.];v=[0.,0.,0.];target=[20.,20.,15.];last=[0.,0.,0.]
    for _ in range(500):
        v=c.step(p,v,target,.05)
        assert max(abs(a-b) for a,b in zip(v,last))<=.091
        assert norm(v)<=3.6
        p=[x+y*.05 for x,y in zip(p,v)];last=v[:]
    assert distance(p,target)<.1

def test_tracker_rejects_bad_then_expires():
    t=Tracker()
    with pytest.raises(ValueError):t.ingest([{'id':'a','position':[float('nan'),0,0]}],10)
    assert not t.tracks
    t.ingest([{'id':'a','position':[4,0,12],'radius':1}],10)
    assert t.risk([0,0,12],[1,0,0],10)<4
    t.prune(12);assert not t.tracks

def test_tracker_velocity_updates():
    t=Tracker();t.ingest([{'id':'a','position':[1,0,12]}],1);t.ingest([{'id':'a','position':[2,0,12]}],1.2)
    assert t.tracks['a']['velocity'][0]>0

def test_hash_chain_tampering(tmp_path):
    p=tmp_path/'chain';a=AuditChain(p);a.append('arm',{'ok':True});a.append('land',{'ok':True});assert a.verify(p)
    text=p.read_text(encoding='utf-8').replace('"arm"','"bad"');p.write_text(text,encoding='utf-8');assert not a.verify(p)
    with pytest.raises(ValueError):AuditChain(p)

@pytest.mark.parametrize('cloud',[True,False])
def test_critical_tasks_stay_onboard(cloud):
    r=offload(priority=3,cloud=cloud,deadline_ms=70);assert r['selected']=='机载';assert all(not n['feasible'] for n in r['options'] if n['node']!='机载')

def test_deadline_rejection_and_input():
    assert offload(deadline_ms=.01)['selected']=='拒绝非关键任务'
    with pytest.raises(ValueError):offload(cycles=-1)

def test_monitor_warmup_and_anomaly():
    m=ResidualMonitor()
    for _ in range(20):m.score([.1,.9,.05])
    assert m.score([.1,.9,.05])['status']=='正常范围'
    assert m.score([3.,.2,2.])['status']=='异常线索'

def test_return_path_with_energy():
    s=scene();p=astar(s['goal'],s['home'],s)
    assert p[-1]==s['home'] and energy_budget(p)['estimated_wh']>0

@pytest.mark.parametrize('reverse',[False,True])
def test_safe_nongrid_endpoint_does_not_round_into_building(reverse):
    s=scene();s['clearance']=4;a=[21.1,29.1,12.];b=s['goal']
    assert safe_point(a,s) and not safe_point([22,30,12],s)
    p=astar(b,a,s) if reverse else astar(a,b,s)
    assert all(safe_segment(x,y,s) for x,y in zip(p,p[1:]))

def test_software_guard_never_forces_motor_cut():
    from autonomy.mavlink_adapter import MAVLinkAdapter
    a=object.__new__(MAVLinkAdapter);a.t=telemetry();a.t.armed=True
    with pytest.raises(ValueError):a.disarm()

def test_local_simulator_udp_stays_on_loopback():
    from autonomy.mavlink_adapter import EphemeralUDP
    link=EphemeralUDP('udpout:127.0.0.1:18651')
    try:assert link.port.getsockname()[0]=='127.0.0.1'
    finally:link.close()
