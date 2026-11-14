"""Exercise the desktop's actual action callbacks against the local simulator."""
import json,time,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from desktop.console import Console

c=Console();c.root.withdraw();checks=[]
def wait(predicate):
    end=time.monotonic()+12
    while time.monotonic()<end:
        c.root.update()
        if predicate():return
        time.sleep(.05)
    raise AssertionError(c.message.cget('text'))

try:
    wait(lambda:c.state is not None and c.task_data['orders'])
    c.act('lease');wait(lambda:c.state.get('lease')=='desktop' and not c.busy)
    checks.append('Desktop acquires shared control lease')
    o=next(o for o in c.task_data['orders'] if o['id']=='LH-DEMO-001')
    c.order.set(o['id']+' · '+o['address'])
    c.act('preview_order');wait(lambda:not c.busy)
    checks.append('Desktop order preview returns')
    c.act('load');wait(lambda:c.state['phase']=='READY' and c.state['order_id']==o['id'] and not c.busy)
    checks.append('Desktop loads same business task API')
    c.act('cancel_task');wait(lambda:c.state['phase']=='CONNECTED' and not c.busy)
    checks.append('Desktop cancels ground reservation')
    c.act('release');wait(lambda:c.state.get('lease') is None and not c.busy)
    checks.append('Desktop releases control lease')
    Path('reports/desktop-order-check.json').write_text(json.dumps({'checks':checks},ensure_ascii=False,indent=2),encoding='utf-8')
    print('Desktop checks passed',len(checks))
finally:c.closing=True;c.root.destroy()
