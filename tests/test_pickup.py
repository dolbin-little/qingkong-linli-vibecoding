"""Destination selection contract used by the web and mini-program clients."""
import pytest
from fastapi.testclient import TestClient
from backend import store
from backend.app import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'DB_PATH', tmp_path / 'pickup.db')
    with TestClient(app) as client:
        assert client.post('/api/login', json={'username': 'resident', 'password': 'GreenFlight2026!'}).status_code == 200
        yield client


def test_all_named_destinations_resolve_without_manual_coordinates(client):
    points = client.get('/api/pickup-points').json()
    assert len(points) == 6 and len({p['id'] for p in points}) == 6
    assert client.get('/api/state').json()['pickup_points'] == points
    for point in points:
        assert point['available']
        result = client.post('/api/orders', json={'product': 'umbrella', 'pickup_point_id': point['id']})
        assert result.status_code == 200
        order = result.json()
        assert (order['address'], order['x'], order['y']) == (point['name'], point['x'], point['y'])


def test_named_destination_cannot_use_unrelated_address_or_coordinates(client):
    result = client.post('/api/orders', json={'product': 'umbrella', 'pickup_point_id': 'P06',
                                             'address': '错误地址', 'x': 285, 'y': 230})
    assert result.status_code == 200
    assert (result.json()['address'], result.json()['x'], result.json()['y']) == ('校园西门', 90, 340)


@pytest.mark.parametrize('location', [
    {}, {'pickup_point_id': 'missing'}, {'x': 285, 'address': '缺少坐标'},
    {'x': 285, 'y': 230, 'address': '  '}, {'x': 10, 'y': 230, 'address': '越界位置'},
    {'x': 420, 'y': 230, 'address': '禁飞区位置'},
])
def test_invalid_destination_rejected(client, location):
    assert client.post('/api/orders', json={'product': 'umbrella', **location}).status_code == 422


def test_custom_map_destination_still_supported(client):
    response = client.post('/api/orders', json={'product': 'water', 'x': 280, 'y': 250, 'address': '地图取件点（280, 250）'})
    assert response.status_code == 200
    assert response.json()['pickup_point_id'] is None
    assert response.json()['x'] == 280


def test_new_no_fly_zone_disables_named_destination(client):
    with store.transaction() as state:
        state['orders'] = [o for o in state['orders'] if o.get('pickup_point_id') != 'P06']
    client.post('/api/logout')
    client.post('/api/login', json={'username': 'admin', 'password': 'GreenFlight2026!'})
    assert client.post('/api/zones', json={'name': '西门临时禁飞', 'x': 80, 'y': 330, 'w': 25, 'h': 25}).status_code == 200
    point = next(p for p in client.get('/api/pickup-points').json() if p['id'] == 'P06')
    assert not point['available']
    assert client.post('/api/orders', json={'product': 'water', 'pickup_point_id': 'P06'}).status_code == 422


def test_destinations_require_login(client):
    client.post('/api/logout')
    assert client.get('/api/pickup-points').status_code == 401
