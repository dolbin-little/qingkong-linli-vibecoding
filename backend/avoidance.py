"""Standalone Dynamic Window Approach experiment, not a certified flight controller.
State (x,y,yaw,speed,yaw_rate), circular obstacles (x,y,r), all in SI units.
"""
import math
import numpy as np

def dwa(state, goal, obstacles, dt=.2, horizon=2., radius=.8):
    x,y,yaw,speed,omega=state
    best=None
    for v in np.linspace(max(0,speed-1.5*dt),min(5,speed+1.5*dt),7):
        for w in np.linspace(max(-1,omega-1.8*dt),min(1,omega+1.8*dt),11):
            px,py,angle=x,y,yaw;trajectory=[];clearance=math.inf
            for _ in range(int(horizon/dt)):
                angle+=w*dt;px+=v*math.cos(angle)*dt;py+=v*math.sin(angle)*dt
                trajectory.append([px,py,angle])
                for ox,oy,r in obstacles:clearance=min(clearance,math.hypot(px-ox,py-oy)-r-radius)
            if clearance <= v*v/(2*1.5)+.05:continue
            score=math.hypot(px-goal[0],py-goal[1])-.25*v+.8/max(.1,clearance)
            if best is None or score<best['score']:
                best={'speed':float(v),'yaw_rate':float(w),'trajectory':trajectory,'score':score,'safe':True}
    return best or {'speed':0.,'yaw_rate':0.,'trajectory':[],'safe':False,'reason':'无安全采样轨迹，需执行上层紧急制动策略'}
