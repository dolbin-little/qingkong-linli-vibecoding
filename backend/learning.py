"""Small NumPy DQN with replay and target network; synthetic training only.
The policy ranks feasible insertion candidates, never overrides MILP safety checks.
"""
from pathlib import Path
import json
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT/'data'/'dqn.npz'
REPORT = ROOT/'data'/'training.json'

def features(battery, distance, energy, duration, remaining):
    return np.array([battery/100, distance/2000, energy/30, duration/10, remaining/24, 1.], dtype=float)

def predict(x, weights):
    a = np.maximum(0, x @ weights['w1'] + weights['b1'])
    return (a @ weights['w2'] + weights['b2']).reshape(-1)

def train(episodes=350, seed=42):
    rng = np.random.default_rng(seed)
    w = {'w1': rng.normal(0, .15, (6,32)), 'b1': np.zeros(32), 'w2': rng.normal(0,.1,(32,1)), 'b2': np.zeros(1)}
    target = {k:v.copy() for k,v in w.items()}
    replay, rewards, losses = [], [], []
    step = 0
    def candidates(battery, remaining):
        distance = rng.uniform(100, 1800, 4)
        energy = distance/600 * rng.uniform(3, 8, 4)
        duration = distance/540 + .4
        return np.stack([features(battery[i], distance[i], energy[i], duration[i], remaining) for i in range(4)]), energy
    for ep in range(episodes):
        batteries = rng.uniform(45, 100, 4)
        x, energy = candidates(batteries, 12)
        total = 0
        for t in range(12):
            valid = batteries - energy/180*100 >= 20
            if not valid.any(): break
            q = predict(x, w); q[~valid] = -1e9
            action = rng.choice(np.flatnonzero(valid)) if rng.random() < max(.05, .8*(1-ep/episodes)) else int(q.argmax())
            dist, en, dur = x[action,1]*2000, x[action,2]*30, x[action,3]*10
            reward = -(.45*dist/1000+.35*en/20+.2*dur/3)
            batteries[action] -= en/180*100
            nx, ne = candidates(batteries, 11-t)
            nv = batteries-ne/180*100>=20
            done = t == 11 or not nv.any()
            replay.append((x[action].copy(), reward, nx.copy(), nv.copy(), done))
            replay = replay[-6000:]; total += reward; step += 1
            if len(replay) >= 48:
                batch = [replay[i] for i in rng.choice(len(replay), 48, replace=False)]
                bx = np.stack([b[0] for b in batch]); ys=[]
                for _, r, nxt, mask, terminal in batch:
                    nxtq = predict(nxt, target); nxtq[~mask] = -1e9
                    ys.append(r if terminal else r+.90*nxtq.max())
                h = np.maximum(0, bx@w['w1']+w['b1']); pred = (h@w['w2']+w['b2']).ravel()
                error = pred-np.array(ys); grad = np.clip(error,-1,1)[:,None]/len(batch)
                dh = (grad@w['w2'].T)*(h>0)
                grads={'w2':h.T@grad,'b2':grad.sum(axis=0),'w1':bx.T@dh,'b1':dh.sum(axis=0)}
                for key in w: w[key] -= .008*np.clip(grads[key],-1,1)
                losses.append(float(np.mean(error**2)))
            if step%80==0: target={k:v.copy() for k,v in w.items()}
            x, energy = nx, ne
            if done: break
        rewards.append(round(total,4))
    MODEL.parent.mkdir(exist_ok=True); np.savez(MODEL, **w)
    report={'algorithm':'DQN · NumPy 6–32–1', 'episodes':episodes,'seed':seed,'steps':step,
            'rewards':rewards,'loss_tail':round(float(np.mean(losses[-100:])),6),
            'source':'合成简化电量分配环境；仅用于候选排序，未使用真实飞行数据，不能证明真实场景泛化能力',
            'trained': True}
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report

def model_info():
    if MODEL.exists() and REPORT.exists(): return json.loads(REPORT.read_text(encoding='utf-8'))
    return {'trained':False,'algorithm':'DQN','source':'模型未训练；DQN 模式显式退回可行方案代价排序'}

def rank_candidates(candidates, drones, remaining):
    if not MODEL.exists(): return min(candidates,key=lambda c:c[0])[1]
    with np.load(MODEL) as f: w={k:f[k] for k in ('w1','b1','w2','b2')}
    xs=[]
    for _, d, routes in candidates:
        route=next(r for r in routes if r['drone_id']==drones[d]['id'])
        xs.append(features(drones[d]['battery'],route['distance_m'],route['energy_wh'],route['duration_min'],remaining))
    return candidates[int(predict(np.stack(xs),w).argmax())][1]

if __name__=='__main__':
    report=train(); print(json.dumps({k:v for k,v in report.items() if k!='rewards'},ensure_ascii=False))
