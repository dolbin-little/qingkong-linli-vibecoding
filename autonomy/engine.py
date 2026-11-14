import json,time,math,threading,uuid
from pathlib import Path
from .models import scene,SCENARIOS,distance,norm,finite_vector
from .mavlink_adapter import MAVLinkAdapter
from .planning import astar,PositionController,energy_budget,safe_segment
from .safety import SafetyGuard
from .safety_status import describe,LoopTiming
from .research import AuditChain,ResidualMonitor,offload
from .perception import Tracker

ROOT=Path(__file__).resolve().parents[1]
DELIVERY_TEXT={'PENDING':'等待到达','DESCENDING':'下降至交付点','LANDING':'着陆停桨','RELEASING':'等待卸货反馈','CONFIRMED':'交付已确认（模拟）','FAILED':'交付流程已中止'}
FAULT_TEXT={'PAYLOAD_RELEASE_REJECTED':'卸货机构拒绝执行，留在交付点','PAYLOAD_CONFIRM_TIMEOUT':'卸货确认超时，留在交付点','DELIVERY_GROUND_STATE_LOST':'卸货地面条件不满足','RETURN_ARM_FAILED':'交付后重新解锁失败，留在交付点','RETURN_CORRIDOR_UNAVAILABLE':'返航走廊不可达，留在交付点'}

class FlightEngine:
    def __init__(self,root=ROOT,business=None):
        self.business=business;self.task=None;self.tracking_enabled=True;self.timing=LoopTiming();self.last_protection_send=0.
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
        # Read-only planning and SQLite reads must not hold the flight-loop lock.
        if cmd=='tasks':
            return self.business.list() if self.business else {'orders':[], 'tasks':[]}
        if cmd=='preview_order':
            if not self.business:raise ValueError('业务联动未启用')
            return self.business.preview(data.get('order_id'),int(data.get('seed',42)))
        with self.lock:
            if cmd=='lease':return self.take_lease(owner)
            if cmd in ('cancel_task','recover_task'):
                self.check_lease(owner)
                if not self.business:raise ValueError('业务联动未启用')
                if self.adapter:
                    t=self.adapter.t;now=time.monotonic()
                    if t.armed or abs(t.position[2])>.15 or now-t.heartbeat_at>1 or now-t.position_at>.5:
                        raise ValueError('需新鲜遥测确认已落地停桨，不能释放不明状态资源')
                elif cmd=='cancel_task':raise ValueError('请先连接并确认已落地')
                if cmd=='cancel_task' and (self.phase!='READY' or self.started):raise ValueError('仅未起飞且未解锁的准备任务可以取消')
                task_id=data.get('run_id') or self.run_id
                result=self.business.release(task_id,cmd=='recover_task',data.get('note',''))
                if task_id==self.run_id:
                    self.task=None;self.order_id=None;self.route=[];self.index=0;self.pending_arm=False;self.phase='CONNECTED' if self.adapter else 'DISCONNECTED';self.reason=result['reason']
                self.event(cmd.upper(),{'task':task_id});return {'ok':True,'reason':result['reason']}

            if cmd=='release':
                if self.lease==owner:
                    self.lease=None
                    if self.phase=='MANUAL' and self.adapter and self.adapter.t.armed:
                        self.manual_v=[0.,0.,0.];self.protect('CONTROL_LEASE_EXPIRED','HOLD')
                return {'released':True}
            if cmd=='connect':
                if self.task:raise ValueError('有关联业务任务，先完成或取消/核对恢复，再切换连接')
                if self.adapter and self.adapter.t.armed:raise ValueError('飞行中禁止切换连接')
                endpoint=data.get('endpoint','udpout:127.0.0.1:18751')
                # Only this explicitly owned simulator endpoint gets simulation command privilege.
                is_simulation=endpoint=='udpout:127.0.0.1:18751'
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
                now=time.monotonic()
                if now-self.adapter.t.heartbeat_at>1 or now-self.adapter.t.position_at>.5 or abs(self.adapter.t.position[2])>.15:
                    raise ValueError('请等待新鲜心跳与定位确认地面状态后载入')
                if self.task:
                    if data.get('order_id')==self.order_id:
                        return {'route':self.route,'run_id':self.run_id,'reason':'该订单已载入，保留当前任务与库存，不重复创建','duplicate':True}
                    raise ValueError('当前订单任务尚未结束，先取消准备任务或处理异常')
                run_id=uuid.uuid4().hex[:10];task=None
                if data.get('order_id'):
                    if not self.simulation:raise ValueError('业务订单闭环当前仅在模拟飞控验证')
                    if not self.business:raise ValueError('业务联动未启用')
                    task=self.business.reserve(data['order_id'],run_id,int(data.get('seed',42)))
                    candidate=task['plan']['selected'];new_scene=candidate['scene'];new_route=candidate['route']
                else:
                    new_scene=scene(data.get('scenario','neighborhood'),int(data.get('seed',42)));new_scene['clearance']=4.
                    if 'goal' in data:
                        if not finite_vector(data['goal']) or not 0<=data['goal'][2]<=35:raise ValueError('目标坐标无效')
                        new_scene['goal']=data['goal']
                    new_scene['cruise_altitude']=max(12.,new_scene['goal'][2]);new_scene['goal']=[*new_scene['goal'][:2],0.]
                    new_route=astar(new_scene['home'],new_scene['goal'],new_scene,altitude=new_scene['cruise_altitude'])
                # Install only after all planning succeeds, leaving the old scene intact on rejection.
                self.s=new_scene;self.route=new_route;self.task=task;self.index=1;self.controller.reset();self.returning=False;self.delivery_at=None;self.delivery_status='PENDING';self.delivery_release_at=None;self.delivered=False;self.finished=None;self.started=None;self.fault=None;self.manual=False;self.pending_arm=False;self.trace=[];self.stats.update(guard_interventions=0,replans=0);self.order_id=data.get('order_id');self.phase='READY';self.run_id=run_id;self.monitor=ResidualMonitor();self.tracker=Tracker()
                if self.simulation:
                    self.scene_requested_at=time.monotonic()
                    try:
                        self.adapter.command(31000,list(SCENARIOS).index(self.s['id']),self.s['seed'],*self.s['goal'],*self.s['home'][:2])
                        if task:self.adapter.command(31003,task['plan']['selected']['battery'])
                    except Exception:
                        self.phase='STOPPED';self.fault='SCENE_TRANSPORT_ERROR';self.reason='场景指令发送失败，资源保持待核对';self.sync_business();raise
                self.reason='任务已载入，等待场景回执及飞前检查';self.event('MISSION_LOADED',{'scenario':self.s['id'],'route':self.route,'order':self.order_id});self.sync_business()
                return {'route':self.route,'run_id':self.run_id,'energy':energy_budget(self.route),'reason':self.reason,'task':task}
            if cmd in ('hold','land','rtl','manual'):
                self.require_write() # Protective actions may be requested from either authenticated local UI.
            else:self.check_lease(owner);self.require_write()
            if cmd=='arm':
                if not self.route or self.phase!='READY':raise ValueError('先载入新的准备任务，不能重复执行已完成订单')
                if self.simulation and hasattr(self,'scene_requested_at'):
                    ack=next((a for a in reversed(self.adapter.acks) if a['command']==31000 and a['at']>=self.scene_requested_at),None)
                    if not ack or not ack['accepted'] or distance(self.adapter.t.position,self.s['home'])>.5:
                        raise ValueError('模拟场景尚未确认或飞机不在起点，请等待遥测回执后重试')
                    if self.task:
                        configured=next((a for a in reversed(self.adapter.acks) if a['command']==31003 and a['at']>=self.scene_requested_at),None)
                        if not configured or not configured['accepted'] or self.adapter.t.battery_at<self.scene_requested_at or abs(self.adapter.t.battery-self.task['plan']['selected']['battery'])>1.1:
                            raise ValueError('等待模拟飞机电量与已分配机队电量同步确认')
                ok,reason=self.guard.preflight(self.adapter.t,self.s,time.monotonic())
                if not ok:raise ValueError('飞前检查未通过：'+reason)
                budget=energy_budget(self.route)['estimated_wh']*2
                if budget>(self.adapter.t.battery-25)/100*180:raise ValueError('不足以覆盖任务与返航电量')
                self.adapter.guided();self.pending_arm=True;self.arm_requested_at=time.monotonic();self.phase='ARMING';self.reason='等待GUIDED模式及解锁回执';self.event('ARM_REQUEST')
            elif cmd=='start':
                if not self.simulation:raise ValueError('真实自主交付须先适配着陆点和投放机构反馈；当前交付闭环仅在本机模拟器验证')
                if not self.adapter.t.armed or self.phase not in ('ARMED','HOLD','MANUAL'):raise ValueError('需要飞控确认解锁；故障锁止须先复位')
                ok,reason=self.guard.check(self.adapter.t,self.s,time.monotonic())
                if ok:raise ValueError('当前不满足执行条件：'+ok)
                if self.fault:raise ValueError('故障未复位')
                self.manual=False;self.manual_v=[0.,0.,0.]
                self.phase='RETURNING' if self.returning else 'EXECUTING';self.reason='自主执行航点';self.started=self.started or time.time();self.hold_since=None;self.controller.reset();self.event('START')
            elif cmd=='hold':self.pending_arm=False;self.phase='HOLD';self.manual=False;self.adapter.velocity([0.,0.,0.]);self.reason='操作员请求安全悬停';self.event('HOLD')
            elif cmd=='land':self.pending_arm=False;self.adapter.land();self.phase='LANDING';self.reason='请求飞控受控降落';self.event('LAND')
            elif cmd=='rtl':
                if self.fault or self.phase in ('LANDING','LINK_LOST'):raise ValueError('保护锁止中，禁止恢复航线')
                try:self.begin_return()
                except ValueError:self.protect('RETURN_ROUTE_BLOCKED','LAND')
            elif cmd=='manual':
                self.check_lease(owner)
                if not self.adapter.t.armed or self.fault or self.phase in ('LANDING','LINK_LOST'):raise ValueError('当前不能接管速度控制；保护锁止请先受控落地')
                self.manual_v=[0.,0.,0.];self.last_manual=0.;self.phase='MANUAL';self.manual=True;self.pending_arm=False;self.adapter.velocity([0.,0.,0.]);self.reason='人工接管，自动航点暂停';self.event('MANUAL')
            elif cmd=='jog':
                if self.phase!='MANUAL' or not self.adapter.t.armed:raise ValueError('需已解锁并处于人工模式')
                v=data.get('velocity')
                if not finite_vector(v) or norm(v)>1.5:raise ValueError('手动指令超出1.5m/s限幅')
                self.manual_v=list(v);self.last_manual=time.monotonic()
            elif cmd=='reset_fault':
                if self.adapter.t.armed:raise ValueError('故障复位需先完成降落')
                reason,_=self.guard.check(self.adapter.t,self.s,time.monotonic())
                if reason:raise ValueError('故障仍在：'+reason)
                if self.task:raise ValueError('请先核对关联订单任务的飞机与货物，再恢复资源')
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
            self.sync_business()
            return {'ok':True,'phase':self.phase,'reason':self.reason}
    def sync_business(self):
        if self.business and self.order_id:
            self.business.sync({'run_id':self.run_id,'order_id':self.order_id,'phase':self.phase,
                                'reason':self.reason,'delivered':self.delivered,'fault':self.fault,
                                'lease':self.lease if time.monotonic()-self.lease_at<20 else None,
                                'telemetry':self.adapter.t.dump() if self.adapter else None})
            if self.phase=='COMPLETED':self.task=None
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
    def can_control(self):
        if self.simulation:return True
        try:
            cfg=json.loads((self.root/'config/project.json').read_text(encoding='utf-8'))
            return bool(cfg.get('real_control_enabled') and getattr(self,'live_confirmed',False))
        except (OSError,ValueError):return False

    def protect(self,reason,action,now=None):
        if reason!=self.fault:
            self.stats['guard_interventions']+=1;self.event('FAULT',{'reason':reason,'response':action})
        self.fault=reason;self.pending_arm=False
        info=describe(reason,self.phase);self.reason=info['title']+'；'+info['action']
        if not self.can_control():return
        now=time.monotonic() if now is None else now
        if reason=='LINK_LOSS':
            self.phase='LINK_LOST'
            if now-self.last_protection_send>1:
                self.adapter.land();self.last_protection_send=now
            return
        # Once landing has started, no lower-severity fault may restore velocity control.
        if self.phase=='LANDING':return
        if action=='LAND':self.adapter.land();self.phase='LANDING'
        elif action=='RTL' and not self.returning:
            try:self.begin_return()
            except ValueError:self.protect('RETURN_ROUTE_BLOCKED','LAND',now)
        elif action=='HOLD':self.phase='HOLD';self.hold_since=self.hold_since or now;self.adapter.velocity([0.,0.,0.])
    def tick(self,now=None):
        now=now or time.monotonic()
        with self.lock:
            late=self.timing.observe(now)
            period=now-self.last_tick;self.last_tick=now;self.stats['ticks']+=1;self.stats['max_period_ms']=max(self.stats['max_period_ms'],round(period*1000,1))
            if not self.adapter:return
            t=self.adapter.poll(now)
            detection=getattr(self.adapter,'detection',None)
            if self.simulation and self.tracking_enabled and detection and now-detection['at']<.25 and detection['at']>getattr(self,'last_detection_at',0):
                self.tracker.ingest([detection],detection['at'],'synthetic_sensor_MAVLink');self.last_detection_at=detection['at']
            if self.phase=='CONNECTING' and now-t.heartbeat_at<1:self.phase='CONNECTED';self.reason='飞控心跳已建立，请载入任务'
            if not self.can_control():
                self.reason='外部飞控只读：仅接收遥测，不执行自动保护控制'
                return
            if self.phase=='LINK_LOST' and now-t.heartbeat_at<1 and now-t.position_at<.5:
                self.adapter.land();self.phase='LANDING';self.reason='链路恢复，重新请求降落；禁止自动恢复任务'
            if self.pending_arm and t.mode=='GUIDED' and not t.armed:
                ready,why=self.guard.preflight(t,self.s,now)
                if ready:self.adapter.arm();self.pending_arm=False
                else:
                    self.pending_arm=False
                    if self.phase=='DEPARTURE_ARMING':self.delivery_abort('RETURN_PREFLIGHT_'+why)
                    else:self.phase='READY';self.reason='解锁前复检未通过：'+why
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
                if late:self.protect('CONTROL_LOOP_LATE','LAND',now)
                if self.phase=='MANUAL' and (not self.lease or now-self.lease_at>20):
                    self.manual_v=[0.,0.,0.];self.protect('CONTROL_LEASE_EXPIRED','HOLD',now)
                reason,response=self.guard.check(t,self.s,now)
                if reason and not (reason=='BATTERY_RESERVE' and self.returning):self.protect(reason,response,now)
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
                            if r:self.protect(r,a,now)
                            elif self.tracker.risk(t.position,v,now)<14 and now-getattr(self,'last_replan',0)>2:
                                try:
                                    import copy
                                    avoid=copy.deepcopy(self.s)
                                    for ob in self.tracker.tracks.values():avoid['obstacles'].append({'id':ob['id'],'x':ob['position'][0]+2*ob['velocity'][0],'y':ob['position'][1]+2*ob['velocity'][1],'r':ob['radius']+2,'h':ob['position'][2]+4})
                                    self.route=astar(t.position,self.route[-1],avoid);self.index=1;self.controller.reset();self.stats['replans']+=1;self.last_replan=now;self.adapter.velocity([0.,0.,0.]);self.event('DYNAMIC_REPLAN',{'tracks':len(self.tracker.tracks)})
                                except ValueError as e:
                                    self.event('DYNAMIC_REPLAN_REJECT',{'reason':str(e),'position':t.position[:]});self.protect('TRACK_PREDICTED_CONFLICT','HOLD',now)
                            elif self.tracker.risk(t.position,v,now)<3:self.protect('TRACK_PREDICTED_CONFLICT','HOLD',now)
                            else:self.adapter.velocity(v)
                elif self.phase in ('ARMED','HOLD'):self.adapter.velocity([0.,0.,0.])
                elif self.phase=='MANUAL':
                    v=self.manual_v if now-self.last_manual<.35 else [0.,0.,0.];r,a=self.guard.check(t,self.s,now,v)
                    if r:self.protect(r,a,now)
                    else:self.adapter.velocity(v)
            elif self.phase=='LANDING' and now-t.heartbeat_at<1 and now-t.position_at<.5 and abs(t.position[2])<=.15 and norm(t.velocity)<.2:
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
            return {'name':'晴空邻里','phase':self.phase,'reason':self.reason,'simulation':self.simulation,'telemetry':t.dump() if t else None,'ages':ages,'scenario':self.s,'route':self.route,'waypoint':self.index,'returning':self.returning,'delivered':self.delivered,'delivery':{'status':getattr(self,'delivery_status','PENDING'),'label':DELIVERY_TEXT.get(getattr(self,'delivery_status','PENDING'),'等待到达'),'mode':'landed_release','height_m':0,'simulation':self.simulation},'fault':self.fault,'lease':self.lease if now-self.lease_at<20 else None,'stats':{**self.stats,'timing':self.timing.dump()},'safety_status':describe(self.fault,self.phase,not self.can_control()),'events':[e for e in self.events if e.get('run_id')==self.run_id][:25],'acks':self.adapter.acks[-12:] if self.adapter else [],'pending':list(self.adapter.pending) if self.adapter else [],'traffic':{'received':self.adapter.received,'sent':self.adapter.sent} if self.adapter else {},'tracks':list(self.tracker.tracks.values()),'anomaly':self.model_score,'edge':offload(cloud=self.cloud),'critical_compute':offload(priority=3,cloud=self.cloud,deadline_ms=70),'audit':{'flight_head':self.audit.head,'flight_count':self.audit.count,'edge_head':self.edge.head,'verified':AuditChain.verify(self.audit.path)},'trace':self.trace[-300:],'run_id':self.run_id,'started':self.started,'finished':self.finished,'energy':energy_budget(self.route) if self.route else {},'order_id':self.order_id,'business_task':self.task,'real_control':'只读' if not getattr(self,'live_confirmed',False) else '已在本机确认'}
    def loop(self):
        while self.running:
            start=time.monotonic()
            try:
                # Planning can hold the lock; timestamp received ACKs after it
                # releases, otherwise a new ACK can appear older than its request.
                with self.lock:
                    self.tick(time.monotonic())
                    self.sync_business()
            except Exception as e:
                with self.lock:
                    self.reason='控制循环异常：'+str(e);self.fault='LOOP_ERROR';self.pending_arm=False;self.phase='LANDING'
                    if self.adapter and self.can_control():
                        try:self.adapter.land()
                        except Exception:pass
            time.sleep(max(.002,.05-(time.monotonic()-start)))
