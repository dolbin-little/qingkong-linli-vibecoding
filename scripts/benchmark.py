"""Run independent multi-seed experiments and save raw observations, no cherry-picking."""
import argparse
import json
from pathlib import Path
from backend.app import generate
from backend.store import seed_state
from backend.planner import dispatch

def run(count=12,seeds=(42,71,108)):
    output=[]
    for seed in seeds:
        s=seed_state();s['orders']=[];generate(s,count,seed)
        for method in ('greedy','vns','dqn'):
            r=dispatch(s,method,seed=seed)
            output.append({'seed':seed,'count':count,'method':method,'assigned':sum(len(x['orders']) for x in r['routes']),
                           'distance_m':sum(x['distance_m'] for x in r['routes']),'energy_wh':sum(x['energy_wh'] for x in r['routes']),
                           'score':r['score'],'elapsed_ms':r['elapsed_ms'],'history':r['history']})
    target=Path(__file__).resolve().parents[1]/'data'/'benchmark.json'
    target.write_text(json.dumps({'source':'synthetic, no real flight evidence','results':output},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(output,ensure_ascii=False))

if __name__=='__main__':run()
