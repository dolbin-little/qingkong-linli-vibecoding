from types import SimpleNamespace

import pytest

from autonomy.engine import FlightEngine
from autonomy.mavlink_adapter import MAVLinkAdapter
from autonomy.models import Telemetry,scene,norm
from autonomy.planning import astar
from autonomy.simulator import Plant

class Adapter:
    def __init__(self):
        self.t=Telemetry(position=[86.,65.,0.],heartbeat_at=1000,position_at=1000,sensor_at=1000,battery_at=1000,gps_at=1000,gps_fix=3,satellites=12,nearest=80,mode='LAND');self.acks=[];self.pending={};self.received=1;self.sent=0;self.releases=0;self.arms=0;self.guides=0;self.payload_feedback={}
    def poll(self,now):
        for name in ('heartbeat_at','position_at','sensor_at','battery_at','gps_at'):setattr(self.t,name,now)
        return self.t
    def velocity(self,v):pass
    def land(self):pass
    def guided(self):self.guides+=1;self.t.mode='GUIDED'
    def arm(self):self.arms+=1
    def release_payload(self):self.releases+=1

def setup(tmp_path,phase='DELIVERY_LANDING'):
    e=FlightEngine(tmp_path);e.adapter=Adapter();e.s['goal']=[86.,65.,0.];e.s['cruise_altitude']=12;e.phase=phase;e.delivery_at=1000;e.delivery_release_at=1000;e.started=1;e.delivery_status='LANDING';return e

def test_arrival_never_marks_delivery_in_cruise_air(tmp_path):
    e=setup(tmp_path,'EXECUTING');e.adapter.t.armed=True;e.adapter.t.position[2]=12;e.route=[];e.index=0;e.tick(1000)
    assert e.phase=='DELIVERY_LANDING' and not e.delivered and not e.adapter.releases

def test_release_only_after_disarmed_at_delivery_ground(tmp_path):
    e=setup(tmp_path);e.adapter.t.armed=True;e.adapter.t.position[2]=1;e.tick(1000)
    assert e.adapter.releases==0
    e.adapter.t.armed=False;e.adapter.t.position[2]=0;e.tick(1001)
    assert e.phase=='DELIVERY_RELEASING' and e.adapter.releases==1 and not e.delivered

def test_release_ack_alone_is_insufficient(tmp_path):
    e=setup(tmp_path,'DELIVERY_RELEASING');e.adapter.acks=[{'command':31002,'accepted':True,'at':1000}];e.tick(1004)
    assert not e.delivered and not e.adapter.arms and e.phase=='DELIVERY_RELEASING'


@pytest.mark.parametrize("request_at", [1000.0, 2**32 / 1000 - 2])
def test_previous_delivery_feedback_arriving_after_new_request_is_ignored(tmp_path, request_at):
    engine = setup(tmp_path, "DELIVERY_RELEASING")
    engine.delivery_release_at = request_at
    engine.adapter.acks = [{"command": 31002, "accepted": True, "at": request_at}]
    decoder = MAVLinkAdapter.__new__(MAVLinkAdapter)
    decoder.endpoint = "udpout:127.0.0.1:18751"
    decoder.sys = 1
    decoder.pending = {}
    decoder.received = 0
    decoder.t = engine.adapter.t

    def receive_feedback(sent_at, received_at):
        message = SimpleNamespace(
            get_type=lambda: "NAMED_VALUE_FLOAT",
            get_srcSystem=lambda: 1,
            name="PAYLOAD",
            value=1.0,
            time_boot_ms=int(sent_at * 1000) % 2**32,
        )
        messages = iter((message, None))
        decoder.link = SimpleNamespace(recv_match=lambda **_: next(messages))
        decoder.last_gcs = received_at
        decoder.poll(received_at)
        engine.adapter.payload_feedback = decoder.payload_feedback
        engine.tick(received_at)

    receive_feedback(request_at - 1, request_at + 4)
    assert engine.phase == "DELIVERY_RELEASING"
    assert not engine.delivered and not engine.returning and not engine.adapter.arms

    receive_feedback(request_at + 4.25, request_at + 4.5)
    assert engine.delivered and engine.phase == "DEPARTURE_ARMING"


def test_payload_feedback_without_ack_times_out_grounded(tmp_path):
    e=setup(tmp_path,'DELIVERY_RELEASING');e.adapter.payload_feedback={'released':True,'at':1011};e.tick(1011)
    assert not e.delivered and e.phase=='STOPPED' and e.fault=='PAYLOAD_CONFIRM_TIMEOUT' and not e.adapter.arms

def test_dual_confirmation_then_preflight_before_takeoff(tmp_path):
    e=setup(tmp_path,'DELIVERY_RELEASING');e.adapter.acks=[{'command':31002,'accepted':True,'at':1000}];e.adapter.payload_feedback={'released':True,'at':1002};e.tick(1002)
    assert not e.delivered and not e.adapter.guides
    e.adapter.payload_feedback['at']=1004;e.tick(1004)
    assert e.delivered and e.phase=='DEPARTURE_ARMING' and e.adapter.guides==1 and e.adapter.arms==0
    e.tick(1004.1);assert e.adapter.arms==1

def test_payload_rejection_does_not_return_or_report_success(tmp_path):
    e=setup(tmp_path,'DELIVERY_RELEASING');e.adapter.acks=[{'command':31002,'accepted':False,'at':1000}];e.tick(1001)
    assert not e.delivered and e.phase=='STOPPED' and e.fault=='PAYLOAD_RELEASE_REJECTED' and not e.returning

def test_simulated_latch_checks_ground_location_and_arm_state():
    s=scene();p=Plant(s);p.p=[86.,65.,12.];assert not p.release_payload()
    p.p[2]=0;p.armed=True;assert not p.release_payload()
    p.armed=False;p.p=[10,10,0];assert not p.release_payload()
    p.p=[86,65,0];p.injected='payload';assert not p.release_payload()
    p.injected=None;assert p.release_payload() and p.payload_released

def test_task_history_cannot_show_previous_delivery_confirmation(tmp_path):
    e=setup(tmp_path);e.run_id='old';e.event('DELIVERY_CONFIRMED');e.run_id='new';e.event('MISSION_LOADED')
    assert [x['name'] for x in e.snapshot(1000)['events']]==['MISSION_LOADED']

def test_full_closed_loop_lands_releases_rearms_and_returns(tmp_path):
    s=scene();s['goal']=[24.,16.,0.];plant=Plant(s)
    class PlantAdapter(Adapter):
        def __init__(self):super().__init__();self.clock=1000
        def poll(self,now):
            self.clock=now;plant.step(.05);super().poll(now)
            self.t.position=plant.p[:];self.t.velocity=plant.v[:];self.t.armed=plant.armed;self.t.battery=plant.battery;self.t.nearest=plant.nearest();self.t.mode='GUIDED' if plant.mode==4 else 'LAND';self.payload_feedback={'released':plant.payload_released,'at':now};return self.t
        def velocity(self,v):plant.target=list(v);plant.last_command=plant.age
        def land(self):plant.mode=9;plant.last_command=plant.age
        def guided(self):plant.mode=4
        def arm(self):plant.armed=True;plant.last_command=plant.age
        def release_payload(self):self.acks.append({'command':31002,'accepted':plant.release_payload(),'at':self.clock})
    e=FlightEngine(tmp_path);e.s=s;e.adapter=PlantAdapter();e.route=astar(s['home'],s['goal'],s);e.index=1;e.phase='EXECUTING';e.started=1;plant.armed=True;plant.last_command=plant.age
    seen=set()
    for i in range(4000):
        e.tick(1000+i*.05);seen.add(e.phase)
        if e.phase in ('COMPLETED','STOPPED'):break
    assert e.phase=='COMPLETED' and e.delivered and plant.payload_released and not plant.armed and not plant.collision
    assert {'DELIVERY_LANDING','DELIVERY_RELEASING','DEPARTURE_ARMING','RETURNING'}<=seen
    confirmation=next(x for x in e.events if x['name']=='DELIVERY_CONFIRMED')
    assert confirmation['details']['armed'] is False and confirmation['details']['position'][2]<.15
