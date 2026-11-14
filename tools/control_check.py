from pathlib import Path
import sys,time,json,math
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autonomy.client import rpc,command
R=Path(__file__).resolve().parents[1];results=[]
def cmd(name,data=None):return command(name,data,owner='test')
def record(name,ok,detail=None):results.append({'test':name,'passed':bool(ok),'detail':detail});print(name,bool(ok),flush=True)
for _ in range(300):
    report=json.loads((R/'reports/integration-results.json').read_text(encoding='utf-8'));s=rpc()
    if len(report['results'])==12 and s['lease'] is None and not s['telemetry']['armed']:break
    time.sleep(1)
else:raise RuntimeError('previous integration suite not idle')
cmd('lease');cmd('connect');time.sleep(1);cmd('load',{'scenario':'neighborhood','seed':42});time.sleep(1);cmd('arm');time.sleep(1);cmd('start')
for _ in range(40):
    s=rpc()
    if s['telemetry']['position'][2]>3:break
    time.sleep(.2)
cmd('manual');time.sleep(.4);x=rpc()['telemetry']['position'][0];cmd('jog',{'velocity':[1.,0.,0.]});time.sleep(1.5);s=rpc()
record('manual command moves aircraft',s['telemetry']['position'][0]>x+.05,{'before_n':x,'after_n':s['telemetry']['position'][0]})
record('manual deadman returns velocity toward zero',math.sqrt(sum(v*v for v in s['telemetry']['velocity']))<.3,s['telemetry']['velocity'])
try:cmd('jog',{'velocity':[3.,0.,0.]});record('manual speed limit',False)
except ValueError:record('manual speed limit',True)
cmd('land')
for _ in range(150):
    s=rpc()
    if not s['telemetry']['armed'] and s['phase']=='STOPPED':break
    time.sleep(.2)
record('manual flight lands and terminates',not s['telemetry']['armed'] and s['phase']=='STOPPED')
cmd('connect',{'endpoint':'udpout:localhost:18751'});time.sleep(1.5);s=rpc()
record('non-allowlisted endpoint classified external',not s['simulation'] and s['traffic']['received']>0)
try:cmd('load',{'scenario':'neighborhood'});record('external device defaults read only',False)
except ValueError as e:record('external device defaults read only','只读' in str(e),str(e))
cmd('connect');time.sleep(1);cmd('release')
(R/'reports/control-results.json').write_text(json.dumps({'results':results},ensure_ascii=False,indent=2),encoding='utf-8');print('RESULT',sum(x['passed'] for x in results),'/',len(results))
