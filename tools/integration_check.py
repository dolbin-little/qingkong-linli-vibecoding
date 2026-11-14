"""Destructive only to this project's synthetic simulator state; never use on real aircraft."""
import sys,time,json,urllib.request,urllib.error
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autonomy.client import rpc,command
from autonomy.worker import key
ROOT=Path(__file__).resolve().parents[1];results=[]
def record(name,ok,**details):
    item={'test':name,'passed':bool(ok),'details':details};results.append(item);print(json.dumps(item,ensure_ascii=False),flush=True)
    (ROOT/'reports/integration-results.json').write_text(json.dumps({'environment':'custom MAVLink simulator, Windows, real time','results':results},ensure_ascii=False,indent=2),encoding='utf-8')
def cmd(c,d=None):return command(c,d,owner='test')
def wait(predicate,seconds=10):
    start=time.monotonic()
    while time.monotonic()-start<seconds:
        s=rpc()
        if s.get('lease')=='test':cmd('lease')
        if predicate(s):return s
        time.sleep(.15)
    raise AssertionError('timeout '+str(rpc().get('reason')))
def prep(goal=[24.,16.,6.],scenario='neighborhood'):
    cmd('lease');cmd('connect');wait(lambda s:s['phase']=='CONNECTED');cmd('load',{'scenario':scenario,'seed':42,'goal':goal});time.sleep(.8);cmd('arm');wait(lambda s:s['phase']=='ARMED');cmd('start');return wait(lambda s:s['telemetry']['position'][2]>3)
def finish():return wait(lambda s:s['phase'] in ('STOPPED','COMPLETED') and not s['telemetry']['armed'],140)
def main():
    try:
        urllib.request.urlopen('http://127.0.0.1:19052/state');record('worker denies anonymous',False)
    except urllib.error.HTTPError as e:record('worker denies anonymous',e.code==401,status=e.code)
    req=urllib.request.Request('http://127.0.0.1:19052/command',data=b'{"command":"lease"}',headers={'X-Sky-Key':key(),'Origin':'http://evil.test','Content-Type':'application/json'})
    try:urllib.request.urlopen(req);record('worker rejects browser Origin',False)
    except urllib.error.HTTPError as e:record('worker rejects browser Origin',e.code==403,status=e.code)
    cmd('lease')
    try:command('lease',owner='desktop');record('single operator ownership',False)
    except ValueError:record('single operator ownership',True)
    s=prep();s=finish();truth=json.loads((ROOT/'data/simulator-truth.json').read_text())
    record('normal landed release takeoff return landing',s['phase']=='COMPLETED' and s['delivered'] and truth.get('payload_released') and not truth['collision'],run=s['run_id'],phase=s['phase'],interventions=s['stats']['guard_interventions'],truth=truth)
    for fault,expected in [('sensor','PERCEPTION_STALE'),('gps','POSITION_QUALITY'),('battery','BATTERY_RESERVE')]:
        prep();cmd('inject',{'fault':fault});s=finish();names=[e['details'].get('reason') for e in s['events'] if e['name']=='FAULT' and e['time']>s.get('started',0)];truth=json.loads((ROOT/'data/simulator-truth.json').read_text())
        record(fault+' fault protected landing',s['fault']==expected and not truth['collision'],run=s['run_id'],phase=s['phase'],faults=names,truth=truth)
        cmd('inject',{'fault':'clear'});time.sleep(.7)
    prep();cmd('inject',{'fault':'link'});time.sleep(4);s=rpc();record('link loss requests landing and marks stale',s['phase']=='LANDING' and s['fault']=='LINK_LOSS',fault=s['fault'],ages=s['ages'])
    # Restore only synthetic downlink to obtain an explicit disarmed confirmation.
    cmd('inject',{'fault':'clear'});s=finish();record('link restored confirms touchdown',not s['telemetry']['armed'],run=s['run_id'],phase=s['phase'])
    cmd('load',{'scenario':'neighborhood','seed':42});time.sleep(.8)
    upload=cmd('upload',{'items':[{'lat':24.966,'lon':102.866,'alt':12},{'lat':24.9661,'lon':102.8661,'alt':12}]})
    record('MAVLink mission handshake 2 items',upload.get('accepted') and upload.get('count')==2,result=upload)
    try:cmd('upload',{'items':[{'lat':200,'lon':102,'alt':12}]});record('reject invalid global waypoint',False)
    except ValueError:record('reject invalid global waypoint',True)
    cmd('inject',{'fault':'ack_loss'});cmd('arm');s=wait(lambda s:s['phase']=='ARMED');time.sleep(3.2);s=rpc()
    record('ACK loss uses heartbeat truth without fake ACK',s['telemetry']['armed'] and any(a['result']=='TIMEOUT' for a in s['acks']),acks=s['acks'][-3:])
    cmd('inject',{'fault':'clear'});cmd('land');finish();cmd('release')
    print('RESULT',sum(x['passed'] for x in results),'/',len(results),flush=True)
if __name__=='__main__':
    try:main()
    except Exception as e:record('integration runner',False,error=str(e));raise
