"""NEU metre coordinates internally; MAVLink LOCAL_NED is converted at the boundary."""
from dataclasses import dataclass, field, asdict
import math

@dataclass
class Telemetry:
    position: list = field(default_factory=lambda:[10.,10.,0.])
    velocity: list = field(default_factory=lambda:[0.,0.,0.])
    battery: float = 95.
    armed: bool = False
    heartbeat_at: float = 0.
    position_at: float = 0.
    sensor_at: float = 0.
    battery_at: float = 0.
    gps_at: float = 0.
    gps_fix: int = 0
    satellites: int = 0
    mode: str = 'DISCONNECTED'
    nearest: float = 100.
    yaw: float = 0.
    source: str = 'MAVLink'
    def dump(self): return asdict(self)

def norm(a): return math.sqrt(sum(x*x for x in a))
def distance(a,b): return norm([x-y for x,y in zip(a,b)])
def finite_vector(v): return isinstance(v,(list,tuple)) and len(v)==3 and all(isinstance(x,(int,float)) and math.isfinite(x) for x in v)

SCENARIOS={
 'neighborhood':{'name':'邻里共享配送','goal':[86.,65.,12.],'wind':[.4,.2,0.], 'fault':None},
 'crossing':{'name':'低空动态障碍','goal':[86.,65.,12.],'wind':[.5,0.,0.], 'fault':None},
 'wind':{'name':'阵风与能源约束','goal':[86.,65.,15.],'wind':[1.4,.6,0.], 'fault':None},
 'low_battery':{'name':'低电量返航','goal':[86.,65.,12.],'wind':[0.,0.,0.], 'fault':'battery'},
 'sensor_loss':{'name':'感知中断保护','goal':[86.,65.,12.],'wind':[0.,0.,0.], 'fault':'sensor'},
 'link_loss':{'name':'遥测链路中断','goal':[86.,65.,12.],'wind':[0.,0.,0.], 'fault':'link'},
 'gps_loss':{'name':'定位质量下降','goal':[86.,65.,12.],'wind':[0.,0.,0.], 'fault':'gps'},
}

def scene(name='neighborhood',seed=42):
    if name not in SCENARIOS: raise ValueError('未知场景')
    import copy,random
    r=random.Random(seed);s=copy.deepcopy(SCENARIOS[name]);s.update(id=name,seed=seed,home=[10.,10.,0.],bounds=[0,100,0,80,0,35],clearance=3.,obstacles=[{'id':'B1','x':35.,'y':30.,'r':9.,'h':24.},{'id':'B2','x':65.,'y':46.,'r':10.,'h':30.},{'id':'B3','x':26.,'y':61.,'r':6.,'h':18.}])
    s['wind'][0]+=r.uniform(-.05,.05)
    s['description']='独立合成社区，坐标单位米；建筑、风和传感器均为研究仿真。'
    return s
