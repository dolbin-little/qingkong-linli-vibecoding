import copy
import pytest
from backend import store
from backend.flight_orders import FlightOrders
from backend.simulation import apply_dispatch


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'DB_PATH', tmp_path/'business.db')
    return FlightOrders()


def snap(task, phase, delivered=False, fault=None):
    return dict(run_id=task['run_id'], order_id=task['order_id'], phase=phase,
                delivered=delivered, fault=fault, reason=phase, lease='web', telemetry={'battery':84.})


def test_all_public_pickups_have_clear_ground_routes(ledger):
    for order in ledger.list()['orders']:
        p = ledger.preview(order['id'])
        assert p['selected']['eligible']
        assert p['selected']['route'][0] == p['selected']['scene']['home']
        assert p['selected']['route'][-1][2] == 0


def test_reservation_excludes_legacy_dispatch_and_cancel_restores_once(ledger):
    before = store.read_state()
    t = ledger.reserve('LH-DEMO-001', 'run1')
    s = store.read_state();st = next(x for x in s['stations'] if x['id']==t['station_id'])
    old = next(x for x in before['stations'] if x['id']==t['station_id'])
    assert st['inventory']['powerbank'] == old['inventory']['powerbank']-1
    with pytest.raises(ValueError):ledger.reserve('LH-DEMO-001', 'run2')
    with store.transaction() as s:
        result = apply_dispatch(s, 'greedy')
        assert all('LH-DEMO-001' not in r['orders'] and r['drone_id']!=t['drone_id'] for r in result['routes'])
    ledger.release('run1');once=store.read_state();ledger.release('run1')
    assert store.read_state()['stations']==once['stations']
    assert next(o for o in once['orders'] if o['id']=='LH-DEMO-001')['status']=='pending'


def test_delivery_confirmed_before_return_is_not_return_complete(ledger):
    task=ledger.reserve('LH-DEMO-001','run1')
    ledger.sync(snap(task,'EXECUTING')); assert store.read_state()['orders'][0]['status']=='flight_active'
    ledger.sync(snap(task,'RETURNING',True))
    s=store.read_state();assert s['orders'][0]['status']=='delivered'
    assert next(d for d in s['drones'] if d['id']==task['drone_id'])['status']=='flight_active'
    stock=copy.deepcopy(s['stations']);ledger.sync(snap(task,'RETURNING',True))
    assert store.read_state()['stations']==stock
    ledger.sync(snap(task,'COMPLETED',True))
    assert next(d for d in store.read_state()['drones'] if d['id']==task['drone_id'])['status']=='idle'


def test_failed_delivery_never_delivered_and_requires_recovery(ledger):
    task=ledger.reserve('LH-DEMO-001','run1');ledger.sync(snap(task,'STOPPED',False,'PAYLOAD_REJECTED'))
    s=store.read_state();assert s['orders'][0]['status']=='flight_exception'
    assert s['orders'][0]['delivered_at'] is None
    with pytest.raises(ValueError):ledger.release('run1')
    with pytest.raises(ValueError):ledger.release('run1',True,'')
    ledger.release('run1',True,'飞机已返站，货物检查完整并入库')
    s=store.read_state();assert s['orders'][0]['status']=='pending'
    assert next(d for d in s['drones'] if d['id']==task['drone_id'])['status']=='maintenance'


def test_restart_preserves_reserved_stock_and_blocks_new_dispatch(ledger):
    task=ledger.reserve('LH-DEMO-001','run1');stock=store.read_state()['stations']
    ledger.recover_after_restart()
    assert ledger.list()['tasks'][0]['phase']=='INTERRUPTED'
    assert store.read_state()['stations']==stock
    with pytest.raises(ValueError):ledger.reserve('LH-DEMO-002','run2')


def test_no_inventory_or_overweight_rejects_without_mutation(ledger):
    with store.transaction() as s:
        for st in s['stations']:st['inventory']['powerbank']=0
    s=store.read_state()
    with pytest.raises(ValueError,match='库存不足'):ledger.reserve('LH-DEMO-001','run1')
    assert store.read_state()==s


def test_postdelivery_failure_does_not_refund_delivered_goods(ledger):
    task=ledger.reserve('LH-DEMO-001','run1');ledger.sync(snap(task,'STOPPED',True,'RETURN_ARM_FAILED'))
    stock=store.read_state()['stations'];ledger.release('run1',True,'飞机已回收至站点，货物已交付无需入库')
    assert store.read_state()['stations']==stock
    assert store.read_state()['orders'][0]['status']=='delivered'


def test_preview_does_not_reserve_inventory(ledger):
    before=store.read_state();ledger.preview('LH-DEMO-001')
    assert store.read_state()==before


def test_concurrent_load_reserves_once(ledger):
    from concurrent.futures import ThreadPoolExecutor
    def reserve(i):
        try:return ledger.reserve('LH-DEMO-001',str(i))
        except ValueError:return None
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(reserve,range(2)))
    assert sum(r is not None for r in results)==1
    assert len(ledger.list()['tasks'])==1


def test_preview_does_not_hold_control_lock(ledger,tmp_path):
    import threading
    from autonomy.engine import FlightEngine
    engine=FlightEngine(tmp_path,business=ledger);done=threading.Event()
    def run():
        engine.action('preview_order',{'order_id':'LH-DEMO-001'});done.set()
    with engine.lock:
        thread=threading.Thread(target=run);thread.start()
        assert done.wait(3),'Order planning blocked on control-loop lock'
    thread.join()


def test_simulator_initial_battery_can_only_change_on_ground():
    from autonomy.simulator import Plant
    from autonomy.models import scene
    p=Plant(scene())
    assert p.configure_battery(74) and p.battery==74
    p.armed=True
    assert not p.configure_battery(95) and p.battery==74
    p.armed=False;p.p[2]=12
    assert not p.configure_battery(95)
    p.p[2]=0
    assert not p.configure_battery(float('nan'))
