import json,time,math,threading,uuid
from pathlib import Path
from .models import scene,SCENARIOS,distance,norm,finite_vector
from .mavlink_adapter import MAVLinkAdapter
from .planning import astar,PositionController,energy_budget,safe_segment
from .safety import SafetyGuard
from .research import AuditChain,ResidualMonitor,offload
from .perception import Tracker

ROOT=Path(__file__).resolve().parents[1]
DELIVERY_TEXT={'PENDING':'等待到达','DESCENDING':'下降至交付点','LANDING':'着陆停桨','RELEASING':'等待卸货反馈','CONFIRMED':'交付已确认（模拟）','FAILED':'交付流程已中止'}
FAULT_TEXT={'PAYLOAD_RELEASE_REJECTED':'卸货机构拒绝执行，留在交付点','PAYLOAD_CONFIRM_TIMEOUT':'卸货确认超时，留在交付点','DELIVERY_GROUND_STATE_LOST':'卸货地面条件不满足','RETURN_ARM_FAILED':'交付后重新解锁失败，留在交付点','RETURN_CORRIDOR_UNAVAILABLE':'返航走廊不可达，留在交付点'}

class FlightEngine:
    def __init__(self,root=ROOT):
        self.root=Path(root);self.root.joinpath('logs').mkdir(exist_ok=True,parents=True);self.lock=threading.RLock();self.adapter=None;self.s=scene();self.route=[];self.index=0;self.phase='DISCONNECTED';self.events=[];self.guard=SafetyGuard();self.controller=PositionController(max_speed=2.7);self.tracker=Tracker();self.monitor=ResidualMonitor();self.audit=AuditChain(self.root/'logs/flight-chain.jsonl');self.edge=AuditChain(self.root/'logs/edge-checkpoints.jsonl');self.fault=None;self.simulation=True;self.running=True;self.last_tick=time.monotonic();self.last_sample=0;self.started=None;self.finished=None;self.run_id=None;self.trace=[];self.hold_since=None;self.manual=False;self.lease=None;self.lease_at=0.;self.pending_arm=False;self.returning=False;self.delivery_at=None;self.delivered=False;self.order_id=None;self.reason='请连接模拟飞控或真实遥测';self.cloud=True;self.stats={'ticks':0,'guard_interventions':0,'max_period_ms':0.,'replans':0};self.model_score={'score':0,'status':'待采集'};self.last_manual=0.;self.manual_v=[0.,0.,0.]
    def event(self,name,payload=None):
        item={'time':time.time(),'run_id':self.run_id,'name':name,'details':payload or {}};self.events.insert(0,item);self.events=self.events[:100]
        self.audit.append(name,item)
        if name in ('COMPLETED','MISSION_LOADED','LAND','RTL','FAULT','CONNECT'):self.edge.append('flight_checkpoint',{'head':self.audit.head,'count':self.audit.count,'name':name})
    def take_lease(self,owner):
        now=time.monotonic()
        if self.lease and self.lease!=owner and now-self.lease_at<20:raise ValueError('另一控制端正在持有操控权，请先移交')
        self.lease=owner;self.lease_at=now;return {'owner':owner,'ttl_seconds':20}
    def check_lease(self,owner):
        if self.lease!=owner or time.monotonic()-self.lease_at>20:raise ValueError('请先获取操控权')
        self.lease_at=time.monotonic()
    def require_write(self):
        if not self.adapter:raise ValueError('未连接飞控')
        if self.simulation:return
        config=json.loads((self.root/'config/project.json').read_text(encoding='utf-8'))
        if not config.get('real_control_enabled') or not getattr(self,'live_confirmed',False):raise ValueError('真实飞控为只读；需本机配置及桌面确认后启用写控制')
    def action(self,cmd,data=None,owner='web'):
        data=data or {}
        with self.lock:
            if cmd=='lease':return self.take_lease(owner)
            if cmd=='release':
                if self.lease==owner:self.lease=None
                return {'released':True}
            if cmd=='connect':
                if self.adapter and self.adapter.t.armed:raise ValueError('飞行中禁止切换连接')
                endpoint=data.get('endpoint','udpout:127.0.0.1:18651')
                # Only this explicitly owned simulator endpoint gets simulation command privilege.
                is_simulation=endpoint=='udpout:127.0.0.1:18651'
                cfg=json.loads((self.root/'config/project.json').read_text(encoding='utf-8'));offset=[0.,0.,0.] if is_simulation else cfg.get('external_position_offset_neu',[0.,0.,0.])
                if not finite_vector(offset):raise ValueError('external_position_offset_neu必须为三个有限数值')
                new_adapter=MAVLinkAdapter(endpoint,int(data.get('baud',115200)),offset)
                if self.adapter:self.adapter.close()
                self.adapter=new_adapter;self.simulation=is_simulation;self.phase='CONNECTING';self.live_confirmed=False;self.route=[];self.run_id=None;self.started=None;self.trace=[];self.delivered=False;self.delivery_status='PENDING';self.pending_arm=False;self.reason='等待MAVLink心跳、定位与测距';self.event('CONNECT',{'endpoint':endpoint,'simulation':self.simulation,'offset_neu':offset});return {'connected':False,'waiting_heartbeat':True}
            if cmd=='cloud':self.cloud=bool(data.get('enabled',True));return {'cloud':self.cloud}
            if cmd=='confirm_real':
                self.check_lease(owner)
                if owner!='desktop' or data.get('phrase')!='确认场地安全并保留遥控接管':raise ValueError('必须由本机桌面输入完整确认语句')
                self.live_confirmed=True;self.event('REAL_WRITE_CONFIRM');return {'confirmed':True}
            if cmd=='detections':
                self.tracker.ingest(data.get('detections'),time.monotonic(),'external');return {'count':len(self.tracker.tracks)}
            if cmd=='load':
                self.check_lease(owner);self.require_write()
                if self.adapter.t.armed:raise ValueError('请先降落，禁止在空中替换任务')
                self.s=scene(data.get('scenario','neighborhood'),int(data.get('seed',42)));self.s['clearance']=4.
                if 'goal' in data:
                    if not finite_vector(data['goal']) or not 0<=data['goal'][2]<=35:raise ValueError('目标坐标无效')
                    self.s['goal']=data['goal']
                self.s['cruise_altitude']=max(12.,self.s['goal'][2]);self.s['goal']=[*self.s['goal'][:2],0.]
                self.route=astar(self.s['home'],self.s['goal'],self.s,altitude=self.s['cruise_altitude']);self.index=1;self.controller.reset();self.returning=False;self.delivery_at=None;self.delivery_status='PENDING';self.delivery_release_at=None;self.delivered=False;self.finished=None;self.started=None;self.fault=None;self.manual=False;self.pending_arm=False;self.trace=[];self.stats.update(guard_interventions=0,replans=0);self.order_id=data.get('order_id');self.phase='READY';self.run_id=uuid.uuid4().hex[:10];self.monitor=ResidualMonitor();self.tracker=Tracker()
                if self.simulation:self.adapter.command(31000,list(SCENARIOS).index(self.s['id']),self.s['seed'],*self.s['goal'])
                self.reason='任务已载入，等待飞前检查和解锁';self.event('MISSION_LOADED',{'scenario':self.s['id'],'route':self.route,'order':self.order_id});return {'route':self.route,'energy':energy_budget(self.route)}
            if cmd in ('hold','land','rtl','manual'):
                self.require_write() # Protective actions may be requested from either authenticated local UI.
            else:self.check_lease(owner);self.require_write()
            if cmd=='arm':
                if not self.route or self.phase not in ('READY','COMPLETED'):raise ValueError('先载入任务')
                ok,reason=self.guard.preflight(self.adapter.t,self.s,time.monotonic())
                if not ok:raise ValueError('飞前检查未通过：'+reason)
                budget=energy_budget(self.route)['estimated_wh']*2
                if budget>(self.adapter.t.battery-25)/100*180:raise ValueError('不足以覆盖任务与返航电量')
                self.adapter.guided();self.pending_arm=True;self.arm_requested_at=time.monotonic();self.phase='ARMING';self.reason='等待GUIDED模式及解锁回执';self.event('ARM_REQUEST')
            elif cmd=='start':
                if not self.simulation:raise ValueError('真实自主交付须先适配着陆点和投放机构反馈；当前交付闭环仅在本机模拟器验证')
                if not self.adapter.t.armed or self.phase not in ('ARMED','HOLD'):raise ValueError('需要飞控确认解锁；故障锁止须先复位')
                ok,reason=self.guard.check(self.adapter.t,self.s,time.monotonic())
                if ok:raise ValueError('当前不满足执行条件：'+ok)
                if self.fault:raise ValueError('故障未复位')
                self.phase='RETURNING' if self.returning else 'EXECUTING';self.reason='自主执行航点';self.started=self.started or time.time();self.hold_since=None;self.controller.reset();self.event('START')
            elif cmd=='hold':self.pending_arm=False;self.phase='HOLD';self.manual=False;self.adapter.velocity([0.,0.,0.]);self.reason='操作员请求安全悬停';self.event('HOLD')
            elif cmd=='land':self.pending_arm=False;self.adapter.land();self.phase='LANDING';self.reason='请求飞控受控降落';self.event('LAND')
            elif cmd=='rtl':self.begin_return()
            elif cmd=='manual':self.phase='MANUAL';self.manual=True;self.pending_arm=False;self.adapter.velocity([0.,0.,0.]);self.reason='人工接管，自动航点暂停';self.event('MANUAL')
            elif cmd=='jog':
                if self.phase!='MANUAL' or not self.adapter.t.armed:raise ValueError('需已解锁并处于人工模式')
                v=data.get('velocity')
                if not finite_vector(v) or norm(v)>1.5:raise ValueError('手动指令超出1.5m/s限幅')
                self.manual_v=list(v);self.last_manual=time.monotonic()
            elif cmd=='reset_fault':
                if self.adapter.t.armed:raise ValueError('故障复位需先完成降落')
                reason,_=self.guard.check(self.adapter.t,self.s,time.monotonic())
                if reason:raise ValueError('故障仍在：'+reason)
                self.fault=None;self.route=[];self.index=0;self.phase='CONNECTED';self.reason='保护已复位，请重新载入任务';self.event('FAULT_RESET')
            elif cmd=='inject':
                if not self.simulation:raise ValueError('故障注入仅对本机模拟飞控开放')
                faults={'clear':0,'sensor':1,'link':2,'gps':3,'battery':4,'ack_loss':5,'payload':6}
                if data.get('fault') not in faults:raise ValueError('未知故障')
                self.adapter.command(31001,faults[data['fault']]);self.event('INJECT',data)
            elif cmd=='upload':
                if self.adapter.t.armed:raise ValueError('上传任务前需落地')
                result=self.adapter.upload_mission(data.get('items',[]));self.event('MISSION_UPLOAD',result);return result
            else:raise ValueError('未知命令')
            return {'ok':True,'phase':self.phase,'reason':self.reason}
    def begin_return(self):
        self.route=astar(self.adapter.t.position,self.s['home'],self.s,altitude=self.s.get('cruise_altitude'));self.index=1;self.returning=True;self.phase='RETURNING';self.reason='自主返航，保留电量余量';self.controller.reset();self.event('RTL')
    def delivery_step(self,t,now):
        if self.phase=='DELIVERY_LANDING':
            ready=(not t.armed and abs(t.position[2])<=.15 and norm(t.velocity)<.2 and distance(t.position,self.s['goal'])<1 and now-t.heartbeat_at<1 and now-t.position_at<.5)
            if ready:
                if not self.simulation:
                    self.phase='DELIVERY_WAIT';self.reason='已落地，真实投放机构未适配，等待人工处置';return
                self.adapter.release_payload();self.delivery_release_at=now;self.phase='DELIVERY_RELEASING';self.delivery_status='RELEASING';self.reason='已落地停桨，等待模拟卸货机构回执和货物反馈'
                self.event('PAYLOAD_RELEASE_REQUEST',{'position':t.position[:],'armed':t.armed,'simulation':True})
            elif now-self.delivery_at>30:self.protect('DELIVERY_LANDING_TIMEOUT','LAND')
        elif self.phase=='DELIVERY_RELEASING':
            fresh=now-t.heartbeat_at<1 and now-t.position_at<.5
            feedback=getattr(self.adapter,'payload_feedback',{})
            ack=next((a for a in reversed(self.adapter.acks) if a['command']==31002 and a['at']>=self.delivery_release_at),None)
            if t.armed or abs(t.position[2])>.15 or norm(t.velocity)>.2 or distance(t.position,self.s['goal'])>1:self.delivery_abort('DELIVERY_GROUND_STATE_LOST');return
            if ack and not ack['accepted']:self.delivery_abort('PAYLOAD_RELEASE_REJECTED');return
            if fresh and ack and ack['accepted'] and feedback.get('released') and feedback.get('at',0)>=self.delivery_release_at and now-feedback['at']<1 and now-self.delivery_release_at>=3:
                self.delivered=True;self.delivery_status='CONFIRMED'
                self.event('DELIVERY_CONFIRMED',{'position':t.position[:],'armed':t.armed,'simulator_feedback':True,'physical_release_verified':False})
                ok,why=self.guard.preflight(t,self.s,now)
                if not ok:self.delivery_abort('RETURN_PREFLIGHT_'+why);return
                try:self.begin_return()
                except ValueError:self.delivery_abort('RETURN_CORRIDOR_UNAVAILABLE');return
                self.phase='DEPARTURE_ARMING';self.reason='模拟交付已确认，等待重新解锁并爬升返航';self.adapter.guided();self.pending_arm=True;self.arm_requested_at=now
            elif now-self.delivery_release_at>10:self.delivery_abort('PAYLOAD_CONFIRM_TIMEOUT')
    def delivery_abort(self,reason):
        self.pending_arm=False;self.fault=reason;self.delivery_status='FAILED';self.phase='LANDING';self.reason=reason;self.event('DELIVERY_ABORT',{'reason':reason})
        if self.adapter.t.armed:self.adapter.land()
    def protect(self,reason,action):
        if reason!=self.fault:
            self.stats['guard_interventions']+=1;self.event('FAULT',{'reason':reason,'response':action})
        self.fault=reason;self.pending_arm=False;self.reason=reason
        if action=='LAND':self.adapter.land();self.phase='LANDING'
        elif action=='RTL' and not self.returning:
            try:self.begin_return()
            except ValueError:self.adapter.land();self.phase='LANDING'
        elif action=='HOLD':self.phase='HOLD';self.hold_since=self.hold_since or time.monotonic();self.adapter.velocity([0.,0.,0.])
    def tick(self,now=None):
        now=now or time.monotonic()
        with self.lock:
            period=now-self.last_tick;self.last_tick=now;self.stats['ticks']+=1;self.stats['max_period_ms']=max(self.stats['max_period_ms'],round(period*1000,1))
            if not self.adapter:return
            t=self.adapter.poll(now)
            detection=getattr(self.adapter,'detection',None)
            if self.simulation and detection and now-detection['at']<.25 and detection['at']>getattr(self,'last_detection_at',0):
                self.tracker.ingest([detection],detection['at'],'synthetic_sensor_MAVLink');self.last_detection_at=detection['at']
            if self.phase=='CONNECTING' and now-t.heartbeat_at<1:self.phase='CONNECTED';self.reason='飞控心跳已建立，请载入任务'
            if self.pending_arm and t.mode=='GUIDED':self.adapter.arm();self.pending_arm=False
            if self.phase in ('ARMING','DEPARTURE_ARMING'):
                departure=self.phase=='DEPARTURE_ARMING'
                if t.armed:
                    self.phase='RETURNING' if departure else 'ARMED';self.reason='交付完成，原地爬升并返航' if departure else '飞控已确认解锁，点击开始执行'
                    if departure:self.event('DELIVERY_DEPARTURE',{'position':t.position[:]})
                elif now-getattr(self,'arm_requested_at',now)>5 or (not self.pending_arm and any(a['command']==400 and not a['accepted'] and a['at']>=getattr(self,'arm_requested_at',0) for a in self.adapter.acks[-2:])):
                    self.pending_arm=False
                    if departure:self.delivery_abort('RETURN_ARM_FAILED')
                    else:self.phase='READY';self.reason='模式或解锁确认超时，请检查飞控后重试'
            self.delivery_step(t,now)
            if not t.armed and self.started and self.phase in ('EXECUTING','RETURNING','HOLD','MANUAL'):
                self.fault=self.fault or 'AUTOPILOT_DISARMED';self.phase='LANDING'
            if t.armed:
                reason,response=self.guard.check(t,self.s,now)
                if reason and not (reason=='BATTERY_RESERVE' and self.returning):self.protect(reason,response)
                if self.phase=='HOLD' and self.hold_since and now-self.hold_since>2.5:self.adapter.land();self.phase='LANDING';self.reason='保护悬停超时，转受控降落'
                if self.phase in ('EXECUTING','RETURNING'):
                    if self.index>=len(self.route):
                        if self.returning:self.adapter.land();self.phase='LANDING'
                        else:
                            self.adapter.velocity([0.,0.,0.]);self.adapter.land();self.delivery_at=now;self.delivery_status='LANDING';self.phase='DELIVERY_LANDING';self.reason='已下降至交付点，等待落地停桨确认'
                            self.event('DELIVERY_LAND_REQUEST',{'position':t.position[:],'armed':t.armed})
                    else:
                        target=self.route[self.index]
                        if not self.returning and self.index==len(self.route)-1:
                            self.delivery_status='DESCENDING';self.reason='已到达交付点上方，正在垂直下降至地面'
                        if distance(t.position,target)<.35 and norm(t.velocity)<.3:self.index+=1;self.controller.reset()
                        else:
                            v=self.controller.step(t.position,t.velocity,target,.05);r,a=self.guard.check(t,self.s,now,v)
                            if r=='BATTERY_RESERVE' and self.returning:r=None
                            if r:self.protect(r,a)
                            elif self.tracker.risk(t.position,v,now)<14 and now-getattr(self,'last_replan',0)>2:
                                try:
                                    import copy
                                    avoid=copy.deepcopy(self.s)
                                    for ob in self.tracker.tracks.values():avoid['obstacles'].append({'id':ob['id'],'x':ob['position'][0]+2*ob['velocity'][0],'y':ob['position'][1]+2*ob['velocity'][1],'r':ob['radius']+2,'h':ob['position'][2]+4})
                                    self.route=astar(t.position,self.route[-1],avoid);self.index=1;self.controller.reset();self.stats['replans']+=1;self.last_replan=now;self.adapter.velocity([0.,0.,0.]);self.event('DYNAMIC_REPLAN',{'tracks':len(self.tracker.tracks)})
                                except ValueError as e:
                                    self.event('DYNAMIC_REPLAN_REJECT',{'reason':str(e),'position':t.position[:]});self.protect('TRACK_PREDICTED_CONFLICT','HOLD')
                            elif self.tracker.risk(t.position,v,now)<3:self.protect('TRACK_PREDICTED_CONFLICT','HOLD')
                            else:self.adapter.velocity(v)
                elif self.phase in ('ARMED','HOLD'):self.adapter.velocity([0.,0.,0.])
                elif self.phase=='MANUAL':
                    v=self.manual_v if now-self.last_manual<.35 else [0.,0.,0.];r,a=self.guard.check(t,self.s,now,v)
                    if r:self.protect(r,a)
                    else:self.adapter.velocity(v)
            elif self.phase=='LANDING':
                self.finished=time.time();self.phase='COMPLETED' if self.delivered and self.returning and distance(t.position,self.s['home'])<1 and not self.fault else 'STOPPED';self.reason='交付并返航落地，任务记录已保存' if self.phase=='COMPLETED' else '已落地停止：'+FAULT_TEXT.get(self.fault,str(self.fault or '任务未完成'));self.event(self.phase,{'delivered':self.delivered,'delivery':{'status':getattr(self,'delivery_status','PENDING'),'label':DELIVERY_TEXT.get(getattr(self,'delivery_status','PENDING'),'等待到达'),'mode':'landed_release','height_m':0,'simulation':self.simulation},'fault':self.fault})
                report=self.snapshot(now);report['trace']=self.trace[:];report['trace_window_limit_seconds']=600
                (self.root/'reports').mkdir(exist_ok=True);(self.root/'reports'/f'flight-{self.run_id or "manual"}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            if now-self.last_sample>.2:
                self.last_sample=now;self.trace.append({'t':now,'p':t.position[:],'v':t.velocity[:],'battery':t.battery,'armed':t.armed,'delivered':self.delivered,'delivery_status':getattr(self,'delivery_status','PENDING'),'phase':self.phase});self.trace=self.trace[-3000:]
                self.model_score=self.monitor.score([norm(t.velocity)/3,t.battery/100,max(0,min(5,now-t.position_at))],None)
                if self.run_id:
                    with (self.root/'logs'/f'trace-{self.run_id}.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(self.trace[-1],ensure_ascii=False)+'\n')
    def snapshot(self,now=None):
        now=now or time.monotonic()
        with self.lock:
            t=self.adapter.t if self.adapter else None
            ages={'heartbeat':round(max(0,now-t.heartbeat_at),2),'position':round(max(0,now-t.position_at),2),'sensor':round(max(0,now-t.sensor_at),2)} if t else {}
            return {'name':'晴空邻里','phase':self.phase,'reason':self.reason,'simulation':self.simulation,'telemetry':t.dump() if t else None,'ages':ages,'scenario':self.s,'route':self.route,'waypoint':self.index,'returning':self.returning,'delivered':self.delivered,'delivery':{'status':getattr(self,'delivery_status','PENDING'),'label':DELIVERY_TEXT.get(getattr(self,'delivery_status','PENDING'),'等待到达'),'mode':'landed_release','height_m':0,'simulation':self.simulation},'fault':self.fault,'lease':self.lease if now-self.lease_at<20 else None,'stats':self.stats,'events':[e for e in self.events if e.get('run_id')==self.run_id][:25],'acks':self.adapter.acks[-12:] if self.adapter else [],'pending':list(self.adapter.pending) if self.adapter else [],'traffic':{'received':self.adapter.received,'sent':self.adapter.sent} if self.adapter else {},'tracks':list(self.tracker.tracks.values()),'anomaly':self.model_score,'edge':offload(cloud=self.cloud),'critical_compute':offload(priority=3,cloud=self.cloud,deadline_ms=70),'audit':{'flight_head':self.audit.head,'flight_count':self.audit.count,'edge_head':self.edge.head,'verified':AuditChain.verify(self.audit.path)},'trace':self.trace[-300:],'run_id':self.run_id,'started':self.started,'finished':self.finished,'energy':energy_budget(self.route) if self.route else {},'order_id':self.order_id,'real_control':'只读' if not getattr(self,'live_confirmed',False) else '已在本机确认'}
    def loop(self):
        while self.running:
            start=time.monotonic()
            try:self.tick(start)
            except Exception as e:
                with self.lock:
                    self.reason='控制循环异常：'+str(e);self.fault='LOOP_ERROR';self.phase='HOLD'
                    if self.adapter:
                        try:self.adapter.land()
                        except Exception:pass
            time.sleep(max(.002,.05-(time.monotonic()-start)))
