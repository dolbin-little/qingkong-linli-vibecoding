"""Explicit method transfers, not reproductions of the cited learned models/patent systems."""
import json,hashlib,math,statistics,threading
from pathlib import Path

def canonical(obj):return json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)

class AuditChain:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True);self.head='0'*64;self.count=0
        if self.path.exists():
            if not self.verify(self.path):raise ValueError('审计记录校验失败，请保留现场并核查日志')
            rows=[json.loads(x) for x in self.path.read_text(encoding='utf-8').splitlines() if x.strip()]
            if rows:self.head=rows[-1]['hash'];self.count=rows[-1]['seq']
        self.lock=threading.RLock();self.expected=self.stamp();self.checked=self.expected;self.valid=True
    def stamp(self):
        try:
            s=self.path.stat();return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        except FileNotFoundError:return None
    def verified(self):
        """Reuse a verified file version; re-read when metadata changes externally."""
        with self.lock:
            stamp=self.stamp()
            if stamp!=self.checked:
                self.valid=stamp is not None and self.verify(self.path,self.head,self.count);self.checked=stamp
            return self.valid
    def append(self,event,payload):
        with self.lock:
            if self.stamp()!=self.expected:raise ValueError('审计文件发生外部变化，禁止接续写入，请保留记录核查')
            row={'seq':self.count+1,'event':event,'payload':payload,'previous':self.head};row['hash']=hashlib.sha256(canonical(row).encode()).hexdigest()
            with self.path.open('a',encoding='utf-8') as f:f.write(canonical(row)+'\n')
            self.count=row['seq'];self.head=row['hash'];self.expected=self.stamp();self.checked=self.expected;self.valid=True
            return row
    @staticmethod
    def verify(path,expected_head=None,expected_count=None):
        head='0'*64;seq=0
        try:
            with Path(path).open(encoding='utf-8') as stream:
                for line in stream:
                    if not line.strip():continue
                    r=json.loads(line);h=r.pop('hash');seq+=1
                    if r['previous']!=head or r['seq']!=seq or hashlib.sha256(canonical(r).encode()).hexdigest()!=h:return False
                    head=h
            return (expected_head is None or head==expected_head) and (expected_count is None or seq==expected_count)
        except (OSError,ValueError,KeyError,TypeError,AttributeError):return False

def offload(cycles=30e6,size_bytes=40000,deadline_ms=180,priority=1,cloud=True,queue_ms=0.):
    if any(not isinstance(x,(int,float)) or not math.isfinite(x) for x in (cycles,size_bytes,deadline_ms,queue_ms)) or cycles<0 or size_bytes<0 or deadline_ms<=0 or queue_ms<0 or priority not in (1,2,3):raise ValueError('计算任务参数无效')
    # Critical flight control never leaves the device; finite candidate latency evaluation.
    nodes=[('机载',.5e9,0,0),('站点边缘',3e9,8,20e6)]+([('云端',10e9,70,10e6)] if cloud else [])
    options=[]
    for name,hz,net,bps in nodes:
        latency=cycles/hz*1000+net+(size_bytes*8/bps*1000 if bps else 0)+(queue_ms if name!='机载' else 0)
        feasible=latency<=deadline_ms and (priority<3 or name=='机载')
        cost=latency+(.005*cycles/1e6 if name=='机载' else 4)
        options.append({'node':name,'latency_ms':round(latency,2),'feasible':feasible,'objective':round(cost,2)})
    good=[o for o in options if o['feasible']]
    return {'selected':min(good,key=lambda o:o['objective'])['node'] if good else '拒绝非关键任务','options':options,'method':'优先级与时限约束的枚举调度，非原论文排队优化复现'}

class ResidualMonitor:
    def __init__(self):self.baseline=[]
    def score(self,features,neighbors=None):
        # Flight telemetry advisory only. No GGAD weights, graph encoder or clinical claim.
        if len(self.baseline)<20:self.baseline.append(features[:]);return {'score':0.,'status':'基线采集中','method':'残差/邻域一致性统计迁移'}
        center=[statistics.median(row[i] for row in self.baseline) for i in range(len(features))]
        scale=[max(.05,statistics.median(abs(row[i]-center[i]) for row in self.baseline)*1.4826) for i in range(len(features))]
        hr=math.sqrt(sum(((x-c)/sd)**2 for x,c,sd in zip(features,center,scale))/len(features))
        ar=sum(abs(x-y) for x,y in zip(features,neighbors or center))/len(features)
        score=.7*hr+.3*ar
        if score<2.5:self.baseline=(self.baseline+[features[:]])[-100:]
        return {'score':round(score,3),'center_residual':round(hr,3),'affinity_residual':round(ar,3),'status':'异常线索' if score>4 else '正常范围','method':'受DR-GGAD双残差思路启发的统计监测，非原模型'}
