"""2.5D A* corridor planning + 3D clearance checking, independent from renderer."""
import math,heapq
from .models import finite_vector,distance,norm

def safe_point(p,s,margin=None):
    if not finite_vector(p): return False
    x,y,z=p;b=s['bounds'];m=s['clearance'] if margin is None else margin
    if not(b[0]+1<=x<=b[1]-1 and b[2]+1<=y<=b[3]-1 and b[4]<=z<=b[5]):return False
    return all(z>o['h']+m or math.hypot(x-o['x'],y-o['y'])>o['r']+m for o in s['obstacles'])

def safe_segment(a,b,s):
    n=max(2,math.ceil(distance(a,b)/.5))
    return all(safe_point([a[j]+(b[j]-a[j])*i/n for j in range(3)],s) for i in range(n+1))

def astar(start,goal,s,altitude=None):
    if not finite_vector(goal) or not safe_point(goal,s):raise ValueError('目标越界或位于障碍缓冲区')
    z=altitude or max(12.,goal[2]);a=[start[0],start[1],z];b=[goal[0],goal[1],z]
    if not safe_segment(start,a,s) or not safe_point(b,s):raise ValueError('起降走廊不可达')
    step=2.;key=lambda p:(round(p[0]/step),round(p[1]/step))
    pos=lambda k:[k[0]*step,k[1]*step,z]
    def anchor(p):
        near=key(p);candidates=[]
        # Rounding a safe point can place its grid node inside a buffered building.
        for dx in range(-4,5):
            for dy in range(-4,5):
                k=(near[0]+dx,near[1]+dy)
                if safe_segment(p,pos(k),s):candidates.append((distance(p,pos(k)),k))
        if not candidates:raise ValueError('当前位置缺少可连接的安全网格锚点')
        return min(candidates)[1]
    st=anchor(a);end=anchor(b)
    q=[(0.,st)];cost={st:0.};parent={};found=False
    for _ in range(10000):
        if not q:break
        _,u=heapq.heappop(q)
        if u==end:found=True;break
        for dx,dy in [(1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)]:
            v=(u[0]+dx,u[1]+dy)
            if not safe_segment(pos(u),pos(v),s):continue
            c=cost[u]+math.hypot(dx,dy)*step
            if c<cost.get(v,1e99):cost[v]=c;parent[v]=u;heapq.heappush(q,(c+distance(pos(v),pos(end)),v))
    if not found:raise ValueError('未找到满足净空约束的航线')
    ks=[end]
    while ks[-1]!=st:ks.append(parent[ks[-1]])
    raw=[a]+[pos(k) for k in reversed(ks)]+[b]
    compact=[raw[0]];i=0
    while i<len(raw)-1:
        j=len(raw)-1
        while j>i+1 and not safe_segment(raw[i],raw[j],s):j-=1
        compact.append(raw[j]);i=j
    route=[list(start)]+compact+[list(goal)]
    route=[p for i,p in enumerate(route) if i==0 or distance(p,route[i-1])>.05]
    if not all(safe_segment(x,y,s) for x,y in zip(route,route[1:])):raise ValueError('路径复核失败')
    return route

class PositionController:
    """Outer position P / velocity feedback, acceleration-limited NEU setpoint."""
    def __init__(self,kp=.9,kd=.16,max_speed=3.5,max_acc=1.8):self.kp=kp;self.kd=kd;self.max_speed=max_speed;self.max_acc=max_acc;self.previous=[0.,0.,0.]
    def reset(self):self.previous=[0.,0.,0.]
    def step(self,p,v,target,dt=.05):
        desired=[self.kp*(t-x)-self.kd*vv for t,x,vv in zip(target,p,v)]
        mag=norm(desired)
        if mag>self.max_speed:desired=[x*self.max_speed/mag for x in desired]
        out=[max(old-self.max_acc*dt,min(old+self.max_acc*dt,x)) for old,x in zip(self.previous,desired)]
        out[2]=max(-1.3,min(1.5,out[2]));self.previous=out;return out

def energy_budget(route,payload=.5,wind=0.,irradiance=720.):
    metres=sum(distance(a,b) for a,b in zip(route,route[1:]));seconds=metres/3.+30.
    gross=(220+85*payload+2*wind*wind)*seconds/3600
    solar=min(gross*.3,irradiance*.12*.2*.9*seconds/3600)
    return {'distance_m':round(metres,2),'estimated_wh':round(gross-solar+.8,3),'gross_wh':round(gross+.8,3),'solar_wh':round(solar,3),'basis':'原平台参数化模型，未实测标定'}
