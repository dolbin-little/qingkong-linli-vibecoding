from pathlib import Path
import sys,time,json,argparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autonomy.client import command,rpc
R=Path(__file__).resolve().parents[1]
def run(name,seed=42):
    command('connect');time.sleep(1);command('lease',owner='test');command('load',{'scenario':name,'seed':seed},owner='test');time.sleep(1);command('arm',owner='test');time.sleep(1);command('start',owner='test');start=time.monotonic()
    while time.monotonic()-start<220:
        s=rpc()
        if s['lease']=='test':command('lease',owner='test')
        if s['phase'] in ['COMPLETED','STOPPED']:break
        time.sleep(.4)
    truth=json.loads((R/'data/simulator-truth.json').read_text());p={'scene':name,'seed':seed,'phase':s['phase'],'fault':s['fault'],'delivered':s['delivered'],'stats':s['stats'],'run_id':s['run_id'],'truth':truth,'events':s['events']}
    (R/'reports'/('scenario-'+name+'-'+str(seed)+'.json')).write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(p,ensure_ascii=False),flush=True)
    if s['telemetry']['armed']:command('land',owner='test')
    command('release',owner='test')
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('scenario');a.add_argument('--seed',type=int,default=42);p=a.parse_args();run(p.scenario,p.seed)
