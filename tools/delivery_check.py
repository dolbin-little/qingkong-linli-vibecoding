from pathlib import Path
import sys,time,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autonomy.client import command,rpc
R=Path(__file__).resolve().parents[1];checks=[]
def cmd(c,d=None):return command(c,d,owner='test')
def run(name,fault=None):
    cmd('connect');time.sleep(1);cmd('lease');args={'scenario':'neighborhood','seed':42}
    if fault:args['goal']=[24.,16.,12.]
    cmd('load',args);time.sleep(1)
    if fault:cmd('inject',{'fault':fault})
    cmd('arm');time.sleep(1);cmd('start');seen=[];samples=[];start=time.monotonic()
    while time.monotonic()-start<250:
        s=rpc();cmd('lease');seen.append(s['phase']);samples.append({'phase':s['phase'],'position':s['telemetry']['position'],'armed':s['telemetry']['armed'],'delivered':s['delivered']})
        if s['phase'] in ('COMPLETED','STOPPED'):break
        time.sleep(.25)
    truth=json.loads((R/'data/simulator-truth.json').read_text());flight=json.loads((R/'reports'/('flight-'+s['run_id']+'.json')).read_text(encoding='utf-8'))
    if fault:ok=s['phase']=='STOPPED' and not s['delivered'] and not truth['payload_released'] and not s['telemetry']['armed']
    else:
        confirms=[e for e in flight['events'] if e['name']=='DELIVERY_CONFIRMED']
        ok=s['phase']=='COMPLETED' and s['delivered'] and truth['payload_released'] and not truth['collision'] and bool(confirms) and not confirms[0]['details']['armed'] and confirms[0]['details']['position'][2]<=.15 and {'DELIVERY_RELEASING','DEPARTURE_ARMING','RETURNING'}<=set(seen)
    result={'test':name,'passed':ok,'run_id':s['run_id'],'phase':s['phase'],'fault':s['fault'],'delivered':s['delivered'],'seen':list(dict.fromkeys(seen)),'truth':truth,'samples':samples,'events':flight['events']};checks.append(result)
    (R/'reports/landed-delivery-integration.json').write_text(json.dumps({'results':checks},ensure_ascii=False,indent=2),encoding='utf-8');print(name,ok,s['phase'],s['fault'],flush=True);cmd('release')
    if s['telemetry']['armed']:raise RuntimeError('test did not finish grounded')
run('full_delivery_land_release_rearm_return')
run('payload_failure_remains_grounded',fault='payload')
print('RESULT',sum(c['passed'] for c in checks),'/',len(checks),flush=True)
