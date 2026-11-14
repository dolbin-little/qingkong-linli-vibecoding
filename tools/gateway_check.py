from pathlib import Path
import sys,json,time,subprocess,os
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from autonomy.client import rpc
R=Path(__file__).resolve().parents[1];checks=[];BASE='http://127.0.0.1:19051'
def record(name,ok,detail=None):checks.append({'test':name,'passed':bool(ok),'detail':detail});print(name,bool(ok),flush=True)
with httpx.Client(base_url=BASE,timeout=10) as c:
    record('autonomy requires login',c.get('/api/autonomy/state').status_code==401)
    record('resident login',c.post('/api/login',json={'username':'resident','password':'GreenFlight2026!'}).status_code==200)
    record('resident cannot control flight',c.post('/api/autonomy/command',json={'command':'land'}).status_code==403)
    c.post('/api/logout')
    record('admin login',c.post('/api/login',json={'username':'admin','password':'GreenFlight2026!'}).status_code==200)
    record('cross-origin rejected',c.post('/api/autonomy/command',json={'command':'land'},headers={'Origin':'http://invalid.example'}).status_code==403)
    record('web cannot enable real control',c.post('/api/autonomy/command',json={'command':'confirm_real','data':{'phrase':'x'}}).status_code==403)
    state=c.get('/api/autonomy/state');record('gateway sees MAVLink telemetry',state.status_code==200 and state.json()['traffic']['received']>0)
    record('community retained',c.get('/community').status_code==200 and c.get('/api/state').status_code==200)
    record('detailed models local',c.get('/assets/model3d/index.html').status_code==200 and c.get('/assets/model3d/vendor/three/build/three.module.js').status_code==200)
    record('export downloads JSON',c.get('/api/autonomy/export').headers.get('content-type','').startswith('application/json'))
    record('provenance available',len(c.get('/api/autonomy/technical-sources').json())==6)
    record('flight records available',any(x['file'].startswith('flight-') for x in c.get('/api/autonomy/reports').json()))
# Stop only the web PID owned by the launcher; engine and simulator must continue independently.
before=rpc();record_path=R/'data/process-web.json';rec=json.loads(record_path.read_text(encoding='utf-8'))
if rec.get('root')!=str(R):raise RuntimeError('PID root mismatch')
script="$p=Get-CimInstance Win32_Process -Filter 'ProcessId="+str(int(rec['pid']))+"'; if($p -and $p.ExecutablePath -eq '"+str(R/'runtime/python/python.exe').replace("'","''")+"'){Stop-Process -Id $p.ProcessId -Force}"
subprocess.run(['powershell','-NoProfile','-Command',script],creationflags=0x08000000,check=True)
time.sleep(2);after=rpc();record('flight daemon survives web stop',after['stats']['ticks']>before['stats']['ticks']+15,{'before_phase':before['phase'],'after_phase':after['phase'],'before_ticks':before['stats']['ticks'],'after_ticks':after['stats']['ticks'],'received':after['traffic']['received']})
subprocess.run([str(R/'runtime/python/python.exe'),'-B',str(R/'tools/launch.py'),'--web-only','--no-browser'],cwd=R,creationflags=0x08000000,check=True)
(R/'reports/gateway-results.json').write_text(json.dumps({'results':checks},ensure_ascii=False,indent=2),encoding='utf-8')
print('RESULT',sum(x['passed'] for x in checks),'/',len(checks))
