from autonomy.engine import FlightEngine
from autonomy.models import Telemetry
from autonomy.planning import astar

class Adapter:
    def __init__(self,armed=True,battery=95):
        self.t=Telemetry(position=[20.,10.,12.],battery=battery,armed=armed,heartbeat_at=1000,position_at=1000,sensor_at=1000,battery_at=1000,gps_at=1000,gps_fix=3,satellites=12,nearest=100,mode='GUIDED');self.acks=[];self.pending={};self.received=1;self.sent=0;self.velocities=[];self.arms=0;self.lands=0
    def poll(self,now):return self.t
    def velocity(self,v):self.velocities.append(v)
    def land(self):self.lands+=1
    def arm(self):self.arms+=1

def test_low_battery_return_still_sends_control(tmp_path):
    e=FlightEngine(tmp_path);e.adapter=Adapter(battery=22);e.route=astar(e.adapter.t.position,e.s['home'],e.s);e.index=1;e.returning=True;e.phase='RETURNING';e.started=1;e.tick(1000)
    assert e.phase=='RETURNING' and e.adapter.velocities and any(abs(v)>0 for v in e.adapter.velocities[-1])
    assert e.adapter.lands==0

def test_autopilot_unexpected_disarm_requires_ground_confirmation(tmp_path):
    e=FlightEngine(tmp_path);e.adapter=Adapter(armed=False);e.phase='RETURNING';e.started=1;e.tick(1000)
    assert e.phase=='LANDING' and e.fault=='AUTOPILOT_DISARMED'
    e.adapter.t.position[2]=0;e.tick(1000.1)
    assert e.phase=='STOPPED'

def test_mode_confirmation_timeout_cancels_pending_arm(tmp_path):
    e=FlightEngine(tmp_path);e.adapter=Adapter(armed=False);e.adapter.t.mode='STABILIZE';e.phase='ARMING';e.pending_arm=True;e.arm_requested_at=994;e.tick(1000)
    assert e.phase=='READY' and not e.pending_arm and not e.adapter.arms

def test_protective_hold_cancels_queued_arm(tmp_path):
    e=FlightEngine(tmp_path);e.adapter=Adapter(armed=False);e.phase='ARMING';e.pending_arm=True;e.action('hold');e.tick(1000)
    assert not e.pending_arm and e.adapter.arms==0

def test_invalid_reconnection_keeps_existing_adapter(tmp_path):
    import pytest
    (tmp_path/'config').mkdir();(tmp_path/'config/project.json').write_text('{}')
    e=FlightEngine(tmp_path);old=Adapter(armed=False);e.adapter=old;e.phase='CONNECTED'
    with pytest.raises(ValueError):e.action('connect',{'endpoint':'udpout:127.0.0.1:0'})
    assert e.adapter is old and e.simulation and e.phase=='CONNECTED'
