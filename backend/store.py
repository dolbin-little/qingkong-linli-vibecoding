import copy
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from backend.planner import DEFAULT_ZONES, PRODUCTS
from backend.pickup import PICKUP_POINTS

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.environ.get('GREENFLIGHT_DB', ROOT / 'data' / 'community.db'))
LOCK = threading.RLock()

def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    return db

def password_hash(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 200_000).hex()

def seed_state():
    names = [('S01', '银杏苑共享站', 160, 170, '校园北区'), ('S02', '云大生活服务站', 800, 160, '校园东区'),
             ('S03', '青禾社区站', 150, 580, '社区南区'), ('S04', '邻里便利店', 825, 580, '社区东区')]
    stations = [{'id': i, 'name': name, 'x': x, 'y': y, 'area': area, 'online': True,
                 'inventory': {'powerbank': 12, 'umbrella': 10, 'water': 24, 'firstaid': 6},
                 'pv_area': 3., 'chargers': 2, 'storage_wh': 650., 'storage_capacity_wh': 1000.}
                for i, name, x, y, area in names]
    drones = [{'id': f'LH-{i+1:03}', 'name': f'绿航 {i+1:02}', 'station_id': stations[i//2]['id'],
               'x': stations[i//2]['x'], 'y': stations[i//2]['y'], 'battery': [92, 74, 88, 61, 96, 83, 72, 35][i],
               'capacity_wh': 180., 'max_payload': 1.8, 'status': 'idle', 'flight_minutes': 0., 'distance_m': 0.}
              for i in range(8)]
    orders = []
    for i, (point, product) in enumerate(zip(PICKUP_POINTS, ['powerbank', 'umbrella', 'water', 'firstaid', 'powerbank', 'umbrella'])):
        orders.append({'id': f'LH-DEMO-{i+1:03}', 'user_id': 'resident', 'product': product, 'quantity': 1,
                       'x': point['x'], 'y': point['y'], 'address': point['name'], 'pickup_point_id': point['id'],
                       'priority': 2 if i == 3 else 1, 'created': 0., 'deadline': 6., 'status': 'pending',
                       'kind': 'delivery', 'payment': 'simulated_paid', 'amount': PRODUCTS[product]['price'] + 1.5,
                       'station_id': None, 'drone_id': None, 'delivered_at': None, 'returned_at': None,
                       'source': 'seed', 'events': [{'at': 0, 'text': '演示订单已创建，模拟支付完成'}]})
    return {'clock': 0., 'revision': 0, 'running': False, 'speed': 6, 'cloud_online': True,
            'weather': {'label': '晴间多云', 'irradiance': 720., 'wind': 2.4, 'rain': 0., 'temperature': 23},
            'stations': stations, 'drones': drones, 'zones': copy.deepcopy(DEFAULT_ZONES), 'orders': orders,
            'flights': [], 'dispatches': [], 'energy_log': [], 'experiments': [],
            'logs': [{'at': 0, 'kind': 'system', 'text': '绿航智递仿真环境已初始化 · 所有地理和运行数据均为模拟'}],
            'settings': {'auto_dispatch': False, 'algorithm': 'vns'}, 'next_order': 1001}

def init_db():
    with LOCK, connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, salt TEXT NOT NULL, hash TEXT NOT NULL, role TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, username TEXT NOT NULL, expires REAL NOT NULL);
        ''')
        if not db.execute('SELECT 1 FROM state').fetchone():
            db.execute('INSERT INTO state VALUES (1,?)', (json.dumps(seed_state(), ensure_ascii=False),))
        for username, role in [('admin', 'admin'), ('resident', 'resident')]:
            if not db.execute('SELECT 1 FROM users WHERE username=?', (username,)).fetchone():
                salt = secrets.token_hex(16)
                password = os.environ.get('GREENFLIGHT_PASSWORD', 'GreenFlight2026!')
                db.execute('INSERT INTO users VALUES (?,?,?,?)', (username, salt, password_hash(password, salt), role))

@contextmanager
def transaction():
    with LOCK, connect() as db:
        db.execute('BEGIN IMMEDIATE')
        state = json.loads(db.execute('SELECT body FROM state WHERE id=1').fetchone()[0])
        yield state
        state['revision'] += 1
        db.execute('UPDATE state SET body=? WHERE id=1', (json.dumps(state, ensure_ascii=False),))

def read_state():
    with LOCK, connect() as db:
        return json.loads(db.execute('SELECT body FROM state WHERE id=1').fetchone()[0])

def log(state, text, kind='system'):
    state['logs'].insert(0, {'at': round(state['clock'], 2), 'kind': kind, 'text': text})
    state['logs'] = state['logs'][:200]
