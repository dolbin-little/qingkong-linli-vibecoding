"""Validated detections and alpha-beta tracks. Synthetic and external sources stay labelled."""
import math
from .models import finite_vector,distance

class Tracker:
    def __init__(self):self.tracks={};self.updated=0.
    def ingest(self,detections,now,source='external'):
        if not isinstance(detections,list) or len(detections)>100:raise ValueError('目标列表无效')
        clean=[]
        for d in detections:
            if not isinstance(d,dict) or not isinstance(d.get('id'),str) or len(d['id'])>64 or not finite_vector(d.get('position')):raise ValueError('目标字段无效')
            if any(abs(x)>10000 for x in d['position']):raise ValueError('目标超出局部坐标范围')
            if not isinstance(d.get('radius',1),(int,float)) or not math.isfinite(d.get('radius',1)) or not(0<d.get('radius',1)<100):raise ValueError('半径无效')
            clean.append(d)
        for d in clean:
            old=self.tracks.get(d['id']);p=d['position'];velocity=[0.,0.,0.]
            if old:
                dt=max(.02,min(2.,now-old['at']));pred=[x+v*dt for x,v in zip(old['position'],old['velocity'])];res=[x-y for x,y in zip(p,pred)]
                p=[x+.7*e for x,e in zip(pred,res)];velocity=[max(-15.,min(15.,v+.15*e/dt)) for v,e in zip(old['velocity'],res)]
            self.tracks[d['id']]={'id':d['id'],'position':p,'velocity':velocity,'radius':float(d.get('radius',1)),'at':now,'source':source}
        self.updated=now;self.prune(now)
    def prune(self,now):self.tracks={k:v for k,v in self.tracks.items() if 0<=now-v['at']<1.5}
    def risk(self,p,v,now):
        self.prune(now);nearest=1e9
        for t in self.tracks.values():
            rel=[a-b for a,b in zip(t['position'],p)];rv=[a-b for a,b in zip(t['velocity'],v)]
            tau=max(0.,min(2.,-sum(a*b for a,b in zip(rel,rv))/max(.001,sum(x*x for x in rv))))
            nearest=min(nearest,math.sqrt(sum((a+b*tau)**2 for a,b in zip(rel,rv)))-t['radius'])
        return nearest
