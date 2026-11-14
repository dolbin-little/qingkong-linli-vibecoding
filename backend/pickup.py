"""Named pickup destinations shared by all clients and demo orders."""
from backend.planner import inside

PICKUP_POINTS = (
    {'id': 'P01', 'name': '银杏苑 2 栋取件点', 'x': 285, 'y': 230},
    {'id': 'P02', 'name': '图书馆东侧', 'x': 575, 'y': 135},
    {'id': 'P03', 'name': '东区公共取件点', 'x': 885, 'y': 330},
    {'id': 'P04', 'name': '青禾广场', 'x': 390, 'y': 595},
    {'id': 'P05', 'name': '社区服务中心', 'x': 580, 'y': 445},
    {'id': 'P06', 'name': '校园西门', 'x': 90, 'y': 340},
)


def list_pickup_points(zones):
    return [{**p, 'available': not any(inside((p['x'], p['y']), z) for z in zones)}
            for p in PICKUP_POINTS]
