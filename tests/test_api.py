import pytest
from fastapi.testclient import TestClient
from backend import store
from backend.app import app

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DB_PATH',tmp_path/'test.db')
    with TestClient(app) as c:
        r=c.post('/api/login',json={'username':'admin','password':'GreenFlight2026!'})
        assert r.status_code==200
        yield c

def order(**extra):
    return {'product':'umbrella','quantity':1,'x':275,'y':250,'address':'测试公共取件点','priority':1,'deadline_minutes':6,**extra}

def test_auth_and_role_restrictions(client):
    client.post('/api/logout')
    assert client.get('/api/state').status_code==401
    client.post('/api/login',json={'username':'resident','password':'GreenFlight2026!'})
    assert client.post('/api/dispatch',json={}).status_code==403
    assert client.get('/api/export/orders').status_code==403
    assert client.post('/api/orders',json=order()).status_code==200

def test_create_order_rejects_no_fly_and_bad_values(client):
    assert client.post('/api/orders',json=order(x=420,y=230)).status_code==422
    assert client.post('/api/orders',json=order(quantity=0)).status_code==422
    assert client.post('/api/orders',json=order(product='unknown')).status_code==422

def test_cancel_pending_is_idempotent_guard(client):
    oid=client.post('/api/orders',json=order()).json()['id']
    assert client.post(f'/api/orders/{oid}/cancel').status_code==200
    assert client.post(f'/api/orders/{oid}/cancel').status_code==409
    state=client.get('/api/state').json()
    assert next(o for o in state['orders'] if o['id']==oid)['payment']=='simulated_refunded'

def test_delivery_return_settlement_inventory_roundtrip(client):
    # Deliver initial seed orders. Return one shared item to its original stock location.
    result=client.post('/api/dispatch',json={'method':'vns'}).json()
    assert result['routes']
    assert client.post('/api/weather',json={'irradiance':100,'wind':2,'rain':0}).status_code==409
    assert client.post('/api/simulation',json={'action':'advance','minutes':5}).status_code==200
    s=client.get('/api/state').json();original=next(o for o in s['orders'] if o['id']=='LH-DEMO-001')
    assert original['status']=='delivered'
    sid=original['station_id'];stock=next(st for st in s['stations'] if st['id']==sid)['inventory']['powerbank']
    r=client.post('/api/orders/LH-DEMO-001/return');assert r.status_code==200
    assert client.post('/api/orders/LH-DEMO-001/return').status_code==409
    retid=r.json()['id'];client.post('/api/dispatch',json={'method':'vns'})
    client.post('/api/simulation',json={'action':'advance','minutes':5})
    s=client.get('/api/state').json();o=next(o for o in s['orders'] if o['id']=='LH-DEMO-001')
    assert o['status']=='returned' and o['settled_amount']>=3.5
    assert next(st for st in s['stations'] if st['id']==sid)['inventory']['powerbank']==stock+1
    assert next(o for o in s['orders'] if o['id']==retid)['status']=='completed'

def test_resident_cannot_see_admin_orders(client):
    oid=client.post('/api/orders',json=order()).json()['id']
    client.post('/api/logout');client.post('/api/login',json={'username':'resident','password':'GreenFlight2026!'})
    assert oid not in [o['id'] for o in client.get('/api/state').json()['orders']]
    assert client.post(f'/api/orders/{oid}/cancel').status_code==403

def test_persistent_state_after_reinitialization(client):
    oid=client.post('/api/orders',json=order()).json()['id'];store.init_db()
    assert oid in [o['id'] for o in client.get('/api/state').json()['orders']]

def test_cross_origin_mutation_blocked(client):
    assert client.post('/api/orders',json=order(),headers={'Origin':'https://untrusted.example'}).status_code==403

def test_csv_escapes_formula_injection(client):
    client.post('/api/orders',json=order(address='=1+1'))
    response=client.get('/api/export/orders')
    assert response.status_code==200 and "'=1+1" in response.text

def test_experiment_does_not_modify_operational_orders(client):
    ids=[o['id'] for o in client.get('/api/state').json()['orders']]
    r=client.post('/api/experiments',json={'count':5,'seed':71})
    assert r.status_code==200 and len(r.json()['results'])==3
    assert [o['id'] for o in client.get('/api/state').json()['orders']]==ids

def test_maintenance_and_station_guards(client):
    assert client.patch('/api/drones/LH-001',json={'status':'maintenance'}).status_code==200
    r=client.post('/api/dispatch',json={'method':'vns'}).json()
    assert 'LH-001' not in [r['drone_id'] for r in r['routes']]
    flying=r['routes'][0]
    assert client.patch('/api/drones/'+flying['drone_id'],json={'status':'maintenance'}).status_code==409
    assert client.patch('/api/stations/'+flying['station_id'],json={'online':False}).status_code==409

def test_registration_cannot_escalate_role(client):
    data={'username':'test_resident','password':'StrongTest123!','role':'admin'}
    assert client.post('/api/register',json=data).json()['role']=='resident'
    assert client.post('/api/register',json=data).status_code==409
    client.post('/api/logout')
    assert client.post('/api/login',json=data).status_code==200
    assert client.get('/api/state').json()['orders']==[]
    assert client.post('/api/dispatch',json={}).status_code==403

def test_illegal_zone_rejected(client):
    assert client.post('/api/zones',json={'name':'cover station','x':150,'y':160,'w':30,'h':30}).status_code==409
    assert client.post('/api/zones',json={'name':'out of map','x':900,'y':600,'w':200,'h':200}).status_code==422
