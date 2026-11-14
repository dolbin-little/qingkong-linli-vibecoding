"""Independent MAVLink-speaking simulator. Not PX4/ArduPilot SITL or hardware verification."""
import argparse,time,math,json,random
from pathlib import Path
from pymavlink import mavutil
from .models import scene,norm,distance

class Plant:
    def __init__(self,s):self.reset(s)
    def reset(self,s):self.s=s;self.p=s['home'][:];self.v=[0.,0.,0.];self.target=[0.,0.,0.];self.battery=95.;self.armed=False;self.mode=4;self.age=0.;self.distance=0.;self.energy_wh=0.;self.collision=False;self.last_command=0.;self.injected=None;self.initial=95.;self.payload_released=False
    def release_payload(self):
        # Simulated latch, not a command for a real commercial payload mechanism.
        if self.armed or self.p[2]>.15 or norm(self.v)>.2 or distance(self.p,[*self.s['goal'][:2],0.])>1 or self.injected=='payload':return False
        self.payload_released=True;return True
    def obstacle(self):
        if self.s['id']!='crossing':return None
        return {'id':'DYN1','position':[48.+12*math.sin(self.age*.13),50.,12.],'radius':2.}
    def nearest(self):
        d=80.
        for o in self.s['obstacles']:
            if self.p[2]<o['h']:d=min(d,math.hypot(self.p[0]-o['x'],self.p[1]-o['y'])-o['r'])
        ob=self.obstacle()
        if ob:d=min(d,distance(self.p,ob['position'])-ob['radius'])
        return max(.1,d)
    def step(self,dt):
        self.age+=dt
        if not self.armed:self.v=[0.,0.,0.];return
        target=self.target[:]
        if self.age-self.last_command>1. and self.mode==4:target=[0.,0.,0.]
        if self.age-self.last_command>3. and self.p[2]>.1:self.mode=9
        if self.mode==9:target=[0.,0.,-.8]
        if self.mode==6:
            h=math.hypot(self.p[0]-10,self.p[1]-10)
            target=[max(-2,min(2,10-self.p[0])),max(-2,min(2,10-self.p[1])),(-.8 if h<1 else max(-1,min(1,12-self.p[2])))]
        old=self.p[:]
        for i in range(3):
            desired=target[i]+(self.s['wind'][i]*.08 if self.p[2]>.2 or target[2]>.2 else 0.)
            a=max(-2.2,min(2.2,(desired-self.v[i])/.35));self.v[i]+=a*dt;self.p[i]+=self.v[i]*dt
        if self.p[2]<0:self.p[2]=0;self.v[2]=0
        if self.mode in (6,9) and self.p[2]<=.02:self.armed=False
        metres=distance(old,self.p);self.distance+=metres;wh=(240+15*norm(self.v))*dt/3600;self.energy_wh+=wh;self.battery=max(0,self.battery-wh/180*100)
        if self.nearest()<.45 and self.p[2]>.5:self.collision=True

def run(port=18651,rate=1.):
    link=mavutil.mavlink_connection('udpin:127.0.0.1:'+str(port),source_system=1,source_component=1,dialect='ardupilotmega',udp_timeout=2)
    plant=Plant(scene());last=time.monotonic();ticks=0;mission={};mission_count=0;peer=False
    while True:
        now=time.monotonic();dt=min(.1,now-last);last=now
        for _ in range(60):
            try:m=link.recv_match(blocking=False)
            except ConnectionResetError:continue
            if m is None:break
            if m.get_type()=='BAD_DATA':continue
            peer=True;kind=m.get_type()
            if kind=='COMMAND_LONG':
                cmd=m.command;ok=0
                if cmd==400:
                    if m.param1==1:
                        if plant.battery<45 or plant.injected=='gps':ok=4
                        else:plant.armed=True;plant.last_command=plant.age
                    elif plant.p[2]<.3:plant.armed=False
                    else:ok=4
                elif cmd==176:plant.mode=int(m.param2)
                elif cmd==21:plant.mode=9;plant.last_command=plant.age
                elif cmd==20:plant.mode=6;plant.last_command=plant.age
                elif cmd==31000:
                    if plant.armed:ok=4
                    else:
                        names=list(__import__('autonomy.models',fromlist=['SCENARIOS']).SCENARIOS);idx=int(m.param1);plant.reset(scene(names[idx] if 0<=idx<len(names) else 'neighborhood',int(m.param2)))
                        if 1<=m.param3<=99 and 1<=m.param4<=79:plant.s['goal']=[m.param3,m.param4,0.]
                elif cmd==31002:ok=0 if plant.release_payload() else 4
                elif cmd==31001:
                    names={0:None,1:'sensor',2:'link',3:'gps',4:'battery',5:'ack_loss',6:'payload'};plant.injected=names.get(int(m.param1));
                    if plant.injected=='battery':plant.battery=22.
                else:ok=3
                if plant.injected!='ack_loss':link.mav.command_ack_send(cmd,ok)
            elif kind=='SET_POSITION_TARGET_LOCAL_NED':
                vals=[m.vx,m.vy,-m.vz]
                if all(math.isfinite(v) and abs(v)<=5 for v in vals):plant.target=vals;plant.last_command=plant.age
            elif kind=='MISSION_COUNT':mission_count=m.count;mission={};link.mav.mission_request_int_send(245,190,0)
            elif kind=='MISSION_ITEM_INT':
                mission[m.seq]=m.to_dict()
                if len(mission)<mission_count:link.mav.mission_request_int_send(245,190,len(mission))
                else:link.mav.mission_ack_send(245,190,0)
        plant.step(dt*rate);ticks+=1
        fault=plant.injected or (plant.s['fault'] if plant.age>11 else None)
        if fault=='battery' and plant.age>11:plant.battery=min(plant.battery,22.)
        if peer and fault!='link':
            if ticks%10==0:
                link.mav.heartbeat_send(2,3,(128 if plant.armed else 0)|1,plant.mode,4)
                link.mav.sys_status_send(0,0,0,100,16000,0,max(0,min(100,int(plant.battery))),0,0,0,0,0,0)
                link.mav.gps_raw_int_send(int(now*1e6),1 if fault=='gps' else 3,249660000,1028660000,int(1900*1000),90,100,0,0,12)
                link.mav.named_value_float_send(int(now*1000)%2**32,b'PAYLOAD',1. if plant.payload_released else 0.)
            link.mav.local_position_ned_send(int(now*1000)%2**32,*[plant.p[0],plant.p[1],-plant.p[2],plant.v[0],plant.v[1],-plant.v[2]])
            if fault!='sensor':link.mav.distance_sensor_send(int(now*1000)%2**32,10,8000,int(plant.nearest()*100),0,1,0,0)
            if fault!='sensor' and ticks%4==0 and plant.obstacle():
                measurement=plant.obstacle()['position']
                for name,value in zip((b'DYN_N',b'DYN_E',b'DYN_U'),measurement):link.mav.named_value_float_send(int(now*1000)%2**32,name,value+random.Random(ticks+len(name)).gauss(0,.12))
            # Evaluator truth is separate from planning input; published only for metrics/display.
            if ticks%5==0:
                report={'t':plant.age,'p':plant.p,'v':plant.v,'collision':plant.collision,'distance':plant.distance,'energy_wh':plant.energy_wh,'dynamic':plant.obstacle(),'payload_released':plant.payload_released}
                path=Path(__file__).resolve().parents[1]/'data/simulator-truth.json';tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(report),encoding='utf-8')
                try:tmp.replace(path)
                except OSError:pass
        time.sleep(max(.005,.05-(time.monotonic()-now)))

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--port',type=int,default=18651);a.add_argument('--rate',type=float,default=1.);args=a.parse_args();run(args.port,args.rate)
