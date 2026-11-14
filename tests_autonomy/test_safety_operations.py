import time
import pytest
from autonomy.engine import FlightEngine
from autonomy.safety_status import LoopTiming
from test_engine_regressions import Adapter

def engine(tmp_path):
    e=FlightEngine(tmp_path);e.adapter=Adapter();e.phase='EXECUTING';e.started=1
    return e

def test_readonly_external_never_sends_protective_motion(tmp_path):
    e=engine(tmp_path);e.simulation=False;e.adapter.t.gps_fix=1
    e.tick(1000)
    assert e.adapter.lands==0 and not e.adapter.velocities and not e.adapter.arms
    assert e.snapshot(1000)['safety_status']['title']=='外部飞控只读监控'

def test_landing_cannot_be_replaced_by_stale_sensor_hold(tmp_path):
    e=engine(tmp_path);e.phase='LANDING';e.adapter.t.sensor_at=0;e.tick(1000)
    assert e.phase=='LANDING' and not e.adapter.velocities

def test_link_loss_waits_for_fresh_ground_evidence(tmp_path):
    e=engine(tmp_path);e.adapter.t.heartbeat_at=990;e.tick(1000)
    assert e.phase=='LINK_LOST' and e.adapter.lands==1
    e.adapter.t.armed=False;e.tick(1000.1)
    assert e.phase=='LINK_LOST'
    e.adapter.t.heartbeat_at=e.adapter.t.position_at=1000.2;e.adapter.t.position[2]=0
    e.tick(1000.2)
    assert e.phase=='STOPPED' and not e.delivered

def test_unarmed_aloft_is_not_ground_confirmation(tmp_path):
    e=engine(tmp_path);e.adapter.t.armed=False;e.tick(1000)
    assert e.phase=='LANDING'
    e.adapter.t.position[2]=0;e.tick(1000.1)
    assert e.phase=='STOPPED'

def test_manual_lease_expiry_zeros_and_latches(tmp_path):
    e=engine(tmp_path);e.phase='MANUAL';e.manual_v=[1,0,0];e.lease='desktop';e.lease_at=970
    e.tick(1000)
    assert e.fault=='CONTROL_LEASE_EXPIRED' and e.phase=='HOLD'
    assert e.adapter.velocities[-1]==[0,0,0]

def test_release_manual_lease_immediately_holds(tmp_path):
    e=engine(tmp_path);e.phase='MANUAL';e.take_lease('desktop')
    e.action('release',owner='desktop')
    assert e.phase=='HOLD' and e.fault=='CONTROL_LEASE_EXPIRED'

def test_manual_takeover_requires_owner_and_resets_old_velocity(tmp_path):
    e=engine(tmp_path)
    with pytest.raises(ValueError):e.action('manual',owner='web')
    e.take_lease('web');e.manual_v=[1,0,0];e.action('manual',owner='web')
    assert e.phase=='MANUAL' and e.manual_v==[0,0,0]

def test_manual_resume_requires_healthy_telemetry_and_owner(tmp_path):
    e=engine(tmp_path);e.phase='MANUAL';e.manual=True;e.take_lease('web')
    now=time.monotonic()
    for k in ('heartbeat_at','position_at','sensor_at','battery_at','gps_at'):setattr(e.adapter.t,k,now)
    e.action('start',owner='web')
    assert e.phase=='EXECUTING' and not e.manual

def test_autonomous_task_does_not_depend_on_ui_lease(tmp_path):
    e=engine(tmp_path);e.route=[[20,10,12],[22,10,12]];e.index=1;e.lease=None
    e.tick(1000)
    assert e.phase=='EXECUTING' and not e.fault

def test_timing_only_latches_after_three_consecutive_misses():
    t=LoopTiming();assert not t.observe(1000)
    assert not t.observe(1000.05)
    assert not t.observe(1000.25)
    assert not t.observe(1000.45)
    assert t.observe(1000.65)
    assert not t.observe(1000.7)
    assert t.dump()['deadline_misses']==3 and t.dump()['consecutive_misses']==0

def test_no_safe_return_lands_instead_of_sending_old_route(tmp_path):
    e=engine(tmp_path);e.s['home']=[35,30,0]
    e.protect('BATTERY_RESERVE','RTL')
    assert e.fault=='RETURN_ROUTE_BLOCKED' and e.phase=='LANDING' and e.adapter.lands==1

def test_stale_telemetry_cancels_delayed_arm_request(tmp_path):
    e=engine(tmp_path);e.adapter.t.armed=False;e.adapter.t.position[2]=0
    e.phase='ARMING';e.pending_arm=True;e.arm_requested_at=1000
    e.adapter.t.position_at=998;e.tick(1000)
    assert not e.pending_arm and e.adapter.arms==0 and e.phase=='READY'
