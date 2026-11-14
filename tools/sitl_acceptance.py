"""Owned official ArduCopter SITL only. Never accepts an external aircraft endpoint."""
from pathlib import Path
import sys,subprocess,time,json,shutil,socket,hashlib,os,math
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from autonomy.mavlink_adapter import MAVLinkAdapter
from autonomy.planning import PositionController
from autonomy.models import distance,norm

def run():
    vendor=ROOT/'third_party/ardupilot_sitl';binary=vendor/'ArduCopter.exe'
    report={'suite':'official-arducopter-sitl','scope':'真实ArduCopter软件仿真：本项目MAVLink适配器与外环控制；不含真实传感器、货物机构和业务订单验收',
            'firmware_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'checks':[],'trace':[],'passed':False}
    stamp=time.strftime('%Y%m%d-%H%M%S');work=ROOT/'data'/('sitl-'+stamp);work.mkdir(parents=True)
    shutil.copyfile(vendor/'copter.parm',work/'copter.parm')
    # Preserve arming checks. Only configure simulation/GCS stream and speed settings.
    with (work/'copter.parm').open('a') as f:f.write('\nSYSID_MYGCS 245\nRTL_ALT 500\nLAND_SPEED 60\nWPNAV_SPEED 200\n')
    sock=socket.socket()
    if os.name=='nt':sock.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
    try:sock.bind(('127.0.0.1',15770))
    finally:sock.close()
    args=[str(binary),'--model','+','--home','24.966,102.866,1900,0','--speedup','1',
          '--base-port','15770','--rc-in-port','15779','--serial0','tcp:15770','--defaults','copter.parm','--wipe']
    report['command']=args;report['arming_checks_disabled']=False
    log=(work/'sitl.log').open('wb');proc=None;adapter=None
    def check(name,ok,details=None):
        report['checks'].append({'name':name,'passed':bool(ok),'details':details});print(name,ok,flush=True)
        if not ok:raise AssertionError(name+': '+str(details))
    def wait(name,predicate,timeout=30,step=None):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            if proc.poll() is not None:raise RuntimeError('SITL已退出：'+str(proc.returncode))
            t=adapter.poll(time.monotonic())
            if step:step(t)
            if predicate(t):check(name,True);return t
            time.sleep(.05)
        check(name,False,adapter.status_texts[-8:])
    def sample(t):
        now=time.monotonic()
        if not report['trace'] or now-report['trace'][-1]['t']>.2:
            report['trace'].append({'t':now,'p':t.position[:],'v':t.velocity[:],'armed':t.armed,'mode':t.mode})
    def fly_to(target,label):
        c=PositionController(max_speed=2);stable=[None]
        def step(t):adapter.velocity(c.step(t.position,t.velocity,target));sample(t)
        def reached(t):
            if distance(t.position,target)<.65 and norm(t.velocity)<.4:
                stable[0]=stable[0] or time.monotonic()
                return time.monotonic()-stable[0]>1
            stable[0]=None;return False
        wait(label,reached,55,step)
    def arm_takeoff(label):
        adapter.guided();wait(label+'模式确认',lambda t:t.mode=='GUIDED',10)
        at=time.monotonic();adapter.arm()
        wait(label+'解锁回执与状态',lambda t:t.armed and any(a['command']==400 and a['accepted'] and a['at']>=at for a in adapter.acks),15)
        adapter.takeoff(5);wait(label+'起飞到5米',lambda t:t.position[2]>4.5,35,sample)
    try:
        proc=subprocess.Popen(args,cwd=work,stdout=log,stderr=subprocess.STDOUT,creationflags=0x08000000 if os.name=='nt' else 0)
        for _ in range(100):
            if proc.poll() is not None:raise RuntimeError('SITL启动失败，查看日志')
            try:adapter=MAVLinkAdapter('tcp:127.0.0.1:15770',position_offset=[10,10,0]);break
            except OSError:time.sleep(.2)
        if not adapter:raise RuntimeError('SITL未监听15770')
        wait('官方飞控心跳与定位',lambda t:adapter.autopilot==3 and t.gps_fix>=3 and time.monotonic()-t.position_at<.5,65)
        # Allow EKF alignment and automatic preflight calibrations, without bypassing checks.
        end=time.monotonic()+20
        while time.monotonic()<end:adapter.poll(time.monotonic());time.sleep(.05)
        report['boot_messages']=adapter.status_texts[:]
        adapter.command(512,148);wait('遥测保持有效',lambda t:time.monotonic()-t.heartbeat_at<1,3)
        at=time.monotonic();adapter.command(176,1,999)
        wait('无效模式被飞控明确拒绝',lambda t:any(a['command']==176 and not a['accepted'] and a['result']!='TIMEOUT' and a['at']>=at for a in adapter.acks),10)
        arm_takeoff('首次')
        fly_to([18,14,5],'交付点上方到达')
        # Stop external setpoints while keeping GCS heartbeat: built-in GUIDED timeout must brake.
        adapter.velocity([1,0,0]);end=time.monotonic()+1
        while time.monotonic()<end:adapter.poll(time.monotonic());adapter.velocity([1,0,0]);time.sleep(.05)
        check('停发前已建立水平运动',math.hypot(*adapter.t.velocity[:2])>.3,adapter.t.velocity[:])
        end=time.monotonic()+6
        while time.monotonic()<end:sample(adapter.poll(time.monotonic()));time.sleep(.05)
        check('停止速度指令后飞控自行减速',norm(adapter.t.velocity)<.5,{'speed':norm(adapter.t.velocity)})
        fly_to([18,14,5],'恢复指令后回到交付上方')
        adapter.land();wait('交付点落地停桨',lambda t:not t.armed and abs(t.position[2])<.3,40,sample)
        check('落点水平误差小于1米',math.hypot(adapter.t.position[0]-18,adapter.t.position[1]-14)<1,adapter.t.position[:])
        report['payload']='未连接卸货机构；地面停留仅为软件流程检查，不宣称实物交付'
        end=time.monotonic()+3
        while time.monotonic()<end:adapter.poll(time.monotonic());time.sleep(.05)
        arm_takeoff('再次')
        fly_to([10,10,5],'返回起点上方')
        adapter.land();wait('返航落地停桨',lambda t:not t.armed and abs(t.position[2])<.3,40,sample)
        check('返航水平误差小于1米',math.hypot(adapter.t.position[0]-10,adapter.t.position[1]-10)<1,adapter.t.position[:])
        report['passed']=True
    except Exception as e:
        report['error']=str(e);print('FAIL',e,flush=True)
    finally:
        if adapter:
            report['acks']=adapter.acks[:];report['status_texts']=adapter.status_texts[:];report['firmware_version']=adapter.version
            if adapter.t.armed:
                try:adapter.land();wait('异常收尾落地',lambda t:not t.armed,30,sample)
                except Exception:pass
            adapter.close()
        if proc and proc.poll() is None:
            proc.terminate()
            try:proc.wait(timeout=8)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()
        log.close();report['log']=str(work/'sitl.log')
        (ROOT/'reports').mkdir(exist_ok=True)
        (ROOT/'reports/official-sitl-acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    return report['passed']

if __name__=='__main__':sys.exit(0 if run() else 1)
