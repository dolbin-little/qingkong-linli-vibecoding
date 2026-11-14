"""Runs only against this edition's local simulator. Creates two demo orders.
Requires running tools/launch.py. Never connects to external flight hardware.
"""
import json, time, urllib.request, http.cookiejar, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from autonomy.client import command, rpc

ROOT = Path(__file__).resolve().parents[1]
http = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

def api(path, body=None):
    req = urllib.request.Request('http://127.0.0.1:19051'+path,
        data=None if body is None else json.dumps(body).encode(), headers={'Content-Type':'application/json'})
    with http.open(req, timeout=8) as r: return json.load(r)

def cmd(name, data=None): return command(name, data, owner='test')

def wait_for(predicate, timeout=180):
    deadline=time.monotonic()+timeout; previous=None
    while time.monotonic()<deadline:
        cmd('lease');s=rpc()
        if s['phase']!=previous: print(s['phase'],s['reason'],flush=True);previous=s['phase']
        if predicate(s): return s
        if s.get('fault')=='LOOP_ERROR': raise AssertionError(s['reason'])
        time.sleep(.25)
    raise AssertionError('Timed out: '+str(s['phase'])+' / '+s['reason'])

def check(condition, label):
    assert condition, label
    checks.append(label)

checks=[];records=[]
api('/api/login', {'username':'admin','password':'GreenFlight2026!'})
cmd('connect');wait_for(lambda s:s['phase']=='CONNECTED',10)
for fail in (False,True):
    order=api('/api/orders',{'product':'umbrella','quantity':1,'pickup_point_id':'P01','deadline_minutes':6})
    before=api('/api/state');plan=cmd('preview_order',{'order_id':order['id']})
    check(api('/api/state')['stations']==before['stations'],'Preview leaves inventory unchanged '+str(fail))
    result=cmd('load',{'order_id':order['id']});run=result['run_id']
    duplicate=cmd('load',{'order_id':order['id']})
    check(duplicate.get('duplicate') and duplicate['run_id']==run,'Repeated load is idempotent '+str(fail))
    sid=result['task']['station_id'];did=result['task']['drone_id']
    initial=next(x for x in before['stations'] if x['id']==sid)['inventory']['umbrella']
    wait_for(lambda s:any(a['command']==31003 and a['accepted'] for a in s['acks']) and s['telemetry']['position']==s['scenario']['home'] and abs(s['telemetry']['battery']-plan['selected']['battery'])<=1.1,10)
    check(abs(rpc()['telemetry']['battery']-plan['selected']['battery'])<=1.1,'Simulated battery matches assigned aircraft '+str(fail))
    if fail:cmd('inject',{'fault':'payload'})
    cmd('arm');wait_for(lambda s:s['phase']=='ARMED',10);cmd('start')
    end=wait_for(lambda s:s['phase'] in ('COMPLETED','STOPPED'),180)
    state=api('/api/state');out=next(o for o in state['orders'] if o['id']==order['id'])
    task=next(t for t in state['flight_tasks'] if t['run_id']==run)
    stock=next(st for st in state['stations'] if st['id']==sid)['inventory']['umbrella']
    check(stock==initial-1,'Stock reserved exactly once '+str(fail))
    if not fail:
        check(end['phase']=='COMPLETED' and end['delivered'],'Normal delivery and return complete')
        check(out['status']=='delivered' and task['stock']=='consumed','Order delivered only on release confirmation')
        check(next(d for d in state['drones'] if d['id']==did)['status']=='idle','Aircraft released after return')
        check(any(h['phase']=='DELIVERY_LANDING' for h in task['history']),'Landing at delivery point recorded')
    else:
        check(end['phase']=='STOPPED' and not end['delivered'],'Payload failure stops on ground')
        check(out['status']=='flight_exception' and task['stock']=='reserved','Failure retains inventory and order exception')
        cmd('recover_task',{'run_id':run,'note':'模拟测试核对：飞机回收至站点，未交付货物已检查入库'})
        recovered=api('/api/state')
        check(next(o for o in recovered['orders'] if o['id']==order['id'])['status']=='pending','Recovery returns undelivered order to queue')
        check(next(st for st in recovered['stations'] if st['id']==sid)['inventory']['umbrella']==initial,'Recovery restores inventory once')
        check(next(d for d in recovered['drones'] if d['id']==did)['status']=='maintenance','Recovered aircraft requires maintenance check')
        cmd('inject',{'fault':'clear'})
    records.append({'order_id':order['id'],'run_id':run,'fault_injected':fail,'snapshot':end,'business_task':task})
cmd('release')
report={'time':time.strftime('%Y-%m-%d %H:%M:%S'),'environment':'local custom MAVLink simulator; no real aircraft', 'checks':checks,'runs':records}
(ROOT/'reports/business-acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS',len(checks),'checks; reports/business-acceptance.json',flush=True)
