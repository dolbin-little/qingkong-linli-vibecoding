"""ArduCopter GUIDED supervisory control, MAVLink, explicit ACKs and NEU/NED conversion."""
import time,math,socket
from pymavlink import mavutil
from .models import Telemetry

class EphemeralUDP(mavutil.mavfile):
    """Windows-safe UDP client: bind an ephemeral local port, not the destination port."""
    def __init__(self,endpoint):
        host,port=endpoint[7:].rsplit(':',1);self.destination=(host,int(port))
        if not 1<=int(port)<=65535:raise ValueError('UDP端口无效')
        address=socket.gethostbyname(host);bind_host='127.0.0.1' if address.startswith('127.') else '0.0.0.0'
        self.port=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);self.port.bind((bind_host,0));self.port.setblocking(False)
        super().__init__(self.port.fileno(),endpoint,source_system=245,source_component=190,input=False)
    def recv(self,n=None):
        try:
            data,address=self.port.recvfrom(65535)
            if address[1]!=self.destination[1] or address[0]!=socket.gethostbyname(self.destination[0]):return b''
            return data
        except (BlockingIOError,ConnectionResetError):return b''
    def write(self,buf):return self.port.sendto(buf,self.destination)
    def close(self):self.port.close()

class MAVLinkAdapter:
    def __init__(self,endpoint='udpout:127.0.0.1:18751',baud=115200,position_offset=None):
        if not isinstance(endpoint,str) or len(endpoint)>180:raise ValueError('连接地址无效')
        self.endpoint=endpoint;self.position_offset=position_offset or [0.,0.,0.];self.streams_requested=False;self.link=EphemeralUDP(endpoint) if endpoint.startswith('udpout:') else mavutil.mavlink_connection(endpoint,baud=baud,source_system=245,source_component=190,dialect='ardupilotmega');self.t=Telemetry();self.last_gcs=0.;self.acks=[];self.pending={};self.autopilot=None;self.sys=1;self.comp=1;self.received=0;self.sent=0;self.armed_confirmed=False;self.observation={};self.detection=None
    def close(self):self.link.close()
    def poll(self,now):
        if now-self.last_gcs>1:
            self.link.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS,mavutil.mavlink.MAV_AUTOPILOT_INVALID,0,0,mavutil.mavlink.MAV_STATE_ACTIVE);self.last_gcs=now
        for _ in range(150):
            m=self.link.recv_match(blocking=False)
            if m is None:break
            if m.get_type()=='BAD_DATA':continue
            kind=m.get_type()
            if kind=='HEARTBEAT' and m.type!=mavutil.mavlink.MAV_TYPE_GCS:
                if self.autopilot is not None and (m.get_srcSystem()!=self.sys or m.get_srcComponent()!=self.comp):continue
                self.sys=m.get_srcSystem();self.comp=m.get_srcComponent();self.autopilot=m.autopilot;self.t.heartbeat_at=now;self.t.armed=bool(m.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED);self.t.mode=mavutil.mode_string_v10(m);self.armed_confirmed=self.t.armed
                if not self.streams_requested and self.endpoint!='udpout:127.0.0.1:18751':
                    # Negotiate telemetry rates only; this never arms or enables motion.
                    for msg,interval in [(0,500000),(1,500000),(24,500000),(32,50000),(132,100000),(30,100000)]:self.command(511,msg,interval)
                    self.streams_requested=True
            elif m.get_srcSystem()!=self.sys:continue
            elif kind=='LOCAL_POSITION_NED':self.t.position=[a+b for a,b in zip([m.x,m.y,-m.z],self.position_offset)];self.t.velocity=[m.vx,m.vy,-m.vz];self.t.position_at=now
            elif kind=='SYS_STATUS':
                if 0<=m.battery_remaining<=100:self.t.battery=float(m.battery_remaining);self.t.battery_at=now
            elif kind=='GPS_RAW_INT':self.t.gps_fix=m.fix_type;self.t.satellites=m.satellites_visible;self.t.gps_at=now
            elif kind=='DISTANCE_SENSOR':
                if m.orientation in (0,1,2,3,4,5,6,7) and m.min_distance<=m.current_distance<=m.max_distance:self.t.nearest=m.current_distance/100.;self.t.sensor_at=now
            elif kind=='ATTITUDE':self.t.yaw=m.yaw
            elif kind=='NAMED_VALUE_FLOAT' and self.endpoint=='udpout:127.0.0.1:18751':
                name=m.name.decode() if isinstance(m.name,bytes) else m.name
                if name=='PAYLOAD':self.payload_feedback={'released':m.value==1.,'at':now}
                if name in ('DYN_N','DYN_E','DYN_U') and math.isfinite(m.value):
                    self.observation[name]=(m.value,now)
                    if len(self.observation)==3 and all(now-v[1]<.15 for v in self.observation.values()):self.detection={'id':'SIM-DYNAMIC','position':[self.observation[k][0] for k in ('DYN_N','DYN_E','DYN_U')],'radius':2.,'at':now}
            elif kind=='COMMAND_ACK':
                self.acks.append({'command':m.command,'result':m.result,'accepted':m.result==0,'at':now});self.acks=self.acks[-40:];self.pending.pop(m.command,None)
            self.received+=1
        for cmd,at in list(self.pending.items()):
            if now-at>3:self.acks.append({'command':cmd,'result':'TIMEOUT','accepted':False,'at':now});self.pending.pop(cmd,None)
        return self.t
    def command(self,cmd,*params):
        ps=list(params)+[0.]*7;self.link.mav.command_long_send(self.sys,self.comp,cmd,0,*ps[:7]);self.pending[cmd]=time.monotonic();self.sent+=1
    def guided(self):
        if self.autopilot!=mavutil.mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA:raise ValueError('写控制目前仅验证ArduCopter GUIDED；其他飞控只读')
        self.command(mavutil.mavlink.MAV_CMD_DO_SET_MODE,1,4)
    def arm(self):self.command(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,1)
    def disarm(self):
        if self.t.position[2]>.3:raise ValueError('禁止在空中解除电机')
        self.command(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,0)
    def land(self):self.command(mavutil.mavlink.MAV_CMD_NAV_LAND)
    def release_payload(self):
        if self.endpoint!='udpout:127.0.0.1:18751':raise ValueError('真实投放机构尚未适配，禁止发送模拟机构命令')
        self.command(31002)
    def rtl(self):self.command(mavutil.mavlink.MAV_CMD_NAV_RETURN_TO_LAUNCH)
    def velocity(self,v):
        # Ignore positions/acceleration/yaw, use all 3 velocity axes. 0x0DC7 per ArduPilot docs.
        self.link.mav.set_position_target_local_ned_send(int(time.monotonic()*1000)%2**32,self.sys,self.comp,mavutil.mavlink.MAV_FRAME_LOCAL_NED,0x0DC7,0,0,0,v[0],v[1],-v[2],0,0,0,0,0);self.sent+=1
    def upload_mission(self,items,timeout=6.):
        """Reliable MISSION_REQUEST_INT / MISSION_ITEM_INT handshake, explicit acceptance required.
        Coordinates global lat/lon and relative altitude. This does not arm/start automatically.
        """
        if not items or len(items)>100:raise ValueError('航点数量必须1至100')
        for p in items:
            if not all(isinstance(p.get(k),(int,float)) and math.isfinite(p[k]) for k in ['lat','lon','alt']):raise ValueError('航点值无效')
            if not(-90<=p['lat']<=90 and -180<=p['lon']<=180 and 1<=p['alt']<=35):raise ValueError('航点越界')
        self.link.mav.mission_count_send(self.sys,self.comp,len(items));end=time.monotonic()+timeout;last=time.monotonic();sent=set()
        while time.monotonic()<end:
            m=self.link.recv_match(type=['MISSION_REQUEST_INT','MISSION_REQUEST','MISSION_ACK'],blocking=True,timeout=.25)
            if not m:
                if time.monotonic()-last>.8:self.link.mav.mission_count_send(self.sys,self.comp,len(items));last=time.monotonic()
                continue
            if m.get_srcSystem()!=self.sys:continue
            if m.get_type()=='MISSION_ACK':
                if m.type!=mavutil.mavlink.MAV_MISSION_ACCEPTED or len(sent)!=len(items):raise ValueError('飞控拒绝或航点未完整请求')
                return {'accepted':True,'count':len(sent)}
            seq=m.seq
            if not(0<=seq<len(items)):raise ValueError('飞控请求航点序号无效')
            p=items[seq]
            if m.get_type()=='MISSION_REQUEST_INT':self.link.mav.mission_item_int_send(self.sys,self.comp,seq,mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,0,1,0,1,0,0,int(p['lat']*1e7),int(p['lon']*1e7),p['alt'])
            else:self.link.mav.mission_item_send(self.sys,self.comp,seq,mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT,mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,0,1,0,1,0,0,p['lat'],p['lon'],p['alt'])
            sent.add(seq);last=time.monotonic()
        raise TimeoutError('航点上传未收到接受回执')
