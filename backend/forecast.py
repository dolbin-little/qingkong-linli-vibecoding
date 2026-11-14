"""NumPy LSTM (1 input, 12 hidden units), trained with BPTT on synthetic solar.
This is an executable research baseline, not a weather-service forecast.
"""
import json
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
MODEL=ROOT/'data'/'lstm.npz'

def sigmoid(x): return 1/(1+np.exp(-np.clip(x,-30,30)))

def forward(sequence, w):
    h=np.zeros(w['v'].shape[0]); c=h.copy(); cache=[]
    for x in sequence:
        z=np.r_[h,x]; gates=z@w['W']+w['b']; n=len(h)
        f=sigmoid(gates[:n]); i=sigmoid(gates[n:2*n]); g=np.tanh(gates[2*n:3*n]); o=sigmoid(gates[3*n:])
        previous=c; c=f*c+i*g; h=o*np.tanh(c)
        cache.append((z,f,i,g,o,c,previous))
    return float(h@w['v']+w['by'][0]), cache, h

def train(epochs=35, seed=42):
    rng=np.random.default_rng(seed); n=12
    w={'W':rng.normal(0,.16,(n+1,4*n)), 'b':np.r_[np.ones(n),np.zeros(3*n)],
       'v':rng.normal(0,.1,n),'by':np.zeros(1)}
    series=[]
    # Ten-minute intervals; solar day curves with variable cloud attenuation.
    for day in range(35):
        hour=np.arange(144)/6
        cloud=np.convolve(rng.uniform(.45,1,154),np.ones(11)/11,mode='valid')
        series.append(np.maximum(0,np.sin((hour-6)/12*np.pi))*cloud*rng.uniform(.8,1))
    series=np.concatenate(series)
    indices=np.arange(12,28*144)
    losses=[]; m={k:np.zeros_like(v) for k,v in w.items()}; v2={k:np.zeros_like(v) for k,v in w.items()}; step=0
    for ep in range(epochs):
        total=0
        for idx in rng.choice(indices,240,replace=False):
            pred,cache,h=forward(series[idx-12:idx],w); diff=pred-series[idx]; total+=diff*diff
            grads={k:np.zeros_like(v) for k,v in w.items()}; grads['v']=2*diff*h;grads['by'][0]=2*diff
            dh=2*diff*w['v'];dc=np.zeros(n)
            for z,f,i,g,o,c,previous in reversed(cache):
                tanh=np.tanh(c);do=dh*tanh;dc=dc+dh*o*(1-tanh*tanh)
                df=dc*previous;di=dc*g;dg=dc*i
                dgates=np.r_[df*f*(1-f),di*i*(1-i),dg*(1-g*g),do*o*(1-o)]
                grads['W']+=np.outer(z,dgates);grads['b']+=dgates
                dh=(w['W']@dgates)[:n];dc=dc*f
            step+=1
            for k in w:
                grad=np.clip(grads[k],-1,1);m[k]=.9*m[k]+.1*grad;v2[k]=.999*v2[k]+.001*grad*grad
                w[k]-=.003*(m[k]/(1-.9**step))/(np.sqrt(v2[k]/(1-.999**step))+1e-8)
        losses.append(round(total/240,6))
    errors=[]; persistence=[]
    for idx in range(28*144,len(series),3):
        pred,_,_=forward(series[idx-12:idx],w);errors.append(abs(pred-series[idx]));persistence.append(abs(series[idx-1]-series[idx]))
    MODEL.parent.mkdir(exist_ok=True);np.savez(MODEL,**w)
    report={'model':'LSTM 1–12–1 / NumPy BPTT','epochs':epochs,'seed':seed,'train_days':28,'test_days':7,
            'mae_w_m2':round(float(np.mean(errors))*1000,3),'persistence_mae_w_m2':round(float(np.mean(persistence))*1000,3),
            'loss':losses,'source':'合成光照时间序列，按天划分训练/测试；不代表真实气象预测精度'}
    (ROOT/'data'/'forecast-training.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report

def predict_irradiance(current, history=None):
    # Real chronological history is required; otherwise explicit persistence/decay baseline.
    if not MODEL.exists() or history is None or len(history)<12:
        return [max(0,current*(1-.08*t)) for t in range(6)], '短时衰减基线（历史样本不足）'
    with np.load(MODEL) as f:w={k:f[k] for k in ('W','b','v','by')}
    seq=[x/1000 for x in history[-12:]];out=[]
    for _ in range(6):
        value,_,_=forward(seq[-12:],w);value=float(np.clip(value,0,1.2));seq.append(value);out.append(value*1000)
    return out,'LSTM 合成数据训练模型'

if __name__=='__main__': print(json.dumps(train(),ensure_ascii=False))
